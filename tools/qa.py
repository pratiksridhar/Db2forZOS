#!/usr/bin/env python3
"""Build offline, source-traceable Db2 13 DDL campaigns and compare catalog evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

from sqltext import emit_sql, validate_statement

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "kb" / "campaigns" / "models"
TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def kb():
    return read(ROOT / "kb/data/db2z13-create-ddl.json")


def models():
    return {p.stem: read(p) for p in sorted(MODEL_DIR.glob("*.json"))}


def render(sql, params):
    missing = set(TOKEN.findall(sql)) - params.keys()
    if missing:
        raise ValueError(f"Missing SQL parameters: {sorted(missing)}")
    result = TOKEN.sub(lambda m: str(params[m[1]]), sql)
    if "{{" in result or "}}" in result:
        raise ValueError("Unresolved or malformed SQL placeholder")
    return result


def identifier(value, maximum=128, allow_system=False):
    # A deliberately small identifier subset keeps profiles out of SQL syntax.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", value) or len(value) > maximum:
        raise ValueError(f"Expected uppercase ordinary identifier of at most {maximum} characters: {value!r}")
    if value.startswith("SYS") and not allow_system:
        raise ValueError(f"Reserved/system namespace is outside this generator's scope: {value}")
    return value


def level(value):
    if not isinstance(value, str) or not re.fullmatch(r"V13R1M[0-9]{3}", value):
        raise ValueError(f"Expected an exact Db2 13 level, not a range or assumption: {value!r}")
    return int(value[-3:])


def validate_profile(profile, model):
    if not isinstance(profile, dict):
        raise ValueError("Profile must be a JSON object")
    uses_database = model.get("uses_database", True)
    required = {"id", "verified", "product_context", "source_schema", "replay_schema"}
    if uses_database:
        required.update({"storage_group", "table_bufferpool", "index_bufferpool"})
    if required - profile.keys():
        raise ValueError(f"Profile missing: {sorted(required - profile.keys())}")
    if type(profile["verified"]) is not bool:
        raise ValueError("verified must be a boolean")
    if not isinstance(profile["id"], str) or not profile["id"]:
        raise ValueError("Profile requires a nonempty id")
    context = profile["product_context"]
    if not isinstance(context, dict):
        raise ValueError("product_context must be an object")
    context_schema = read(ROOT / "kb/data/test-case.schema.json")["$defs"]["product_context"]
    if set(context) - context_schema["properties"].keys() or set(context_schema["required"]) - context.keys():
        raise ValueError("product_context has unknown or missing fields; follow the case schema")
    if context.get("release") != "Db2 13 for z/OS":
        raise ValueError("Only Db2 13 for z/OS is supported")
    fl, ac = level(context.get("function_level")), level(context.get("applcompat"))
    if ac > fl:
        raise ValueError("APPLCOMPAT exceeds the recorded activated function level")
    if fl < level(model["minimum_function_level"]) or ac < level(model["minimum_applcompat"]):
        raise ValueError("Profile does not satisfy this model's compatibility gates")
    if context.get("current_rules") != "DB2":
        raise ValueError("These campaign models require CURRENT RULES DB2")
    if type(context.get("data_sharing")) is not bool or not isinstance(context.get("subsystem_parameters"), dict):
        raise ValueError("Record data_sharing and subsystem_parameters explicitly")
    for field in ("subsystem_parameters", "storage_context"):
        if field in context and (not isinstance(context[field], dict) or any(isinstance(v, (dict, list)) for v in context[field].values())):
            raise ValueError(f"{field} must map names to scalar values")
    if context.get("member") is not None and not isinstance(context["member"], str):
        raise ValueError("member must be a string or null")
    for name in (("storage_group", "table_bufferpool", "index_bufferpool") if uses_database else ()):
        identifier(profile[name], 8, allow_system=True)
    for name in ("source_schema", "replay_schema"):
        identifier(profile[name])
    if profile["source_schema"] == profile["replay_schema"]:
        raise ValueError("Source and replay schemas must differ")
    pools = context.get("active_buffer_pools", [])
    if not isinstance(pools, list) or any(not isinstance(p, str) for p in pools) or len(set(pools)) != len(pools):
        raise ValueError("active_buffer_pools must be a list of unique names")
    for name in (("table_bufferpool", "index_bufferpool") if uses_database else ()):
        if profile[name] not in pools or not re.fullmatch(r"BP(?:[0-9]|[1-4][0-9])", profile[name]):
            raise ValueError(f"{name} must be a recorded active 4 KB pool (BP0 through BP49)")
    if profile["verified"] and not profile.get("verification_evidence"):
        raise ValueError("A verified profile requires verification_evidence")


def matches(selection, condition):
    return all(selection.get(k) in (v if isinstance(v, list) else [v]) for k, v in condition.items())


def violations(model, selection):
    return [c["id"] for c in model["constraints"] if matches(selection, c["when"]) and not matches(selection, c["requires"])]


def selection_filters(model, settings):
    filters = {}
    for setting in settings:
        axis, separator, value = setting.partition("=")
        if not separator or axis not in model["dimensions"] or value not in model["dimensions"][axis]:
            raise ValueError(f"Unknown dimension selection {setting!r}; use models to list exact values")
        filters.setdefault(axis, set()).add(value)
    return {axis: sorted(values) for axis, values in sorted(filters.items())}


def candidates(model, filters=None):
    axes = list(model["dimensions"])
    count = 1
    for options in model["dimensions"].values():
        count *= len(options)
    if count > 100000:
        raise ValueError(f"Model has {count} combinations; split it into smaller families (limit 100000)")
    raw = [dict(zip(axes, values)) for values in itertools.product(*(list(model["dimensions"][a]) for a in axes))]
    if filters:
        for axis, values in filters.items():
            if axis not in model["dimensions"] or not values or set(values) - model["dimensions"][axis].keys():
                raise ValueError("Unknown or empty dimension filter")
        raw = [s for s in raw if matches(s, filters)]
    return raw, [s for s in raw if not violations(model, s)]


def interactions(selection, strength):
    items = sorted(selection.items())
    # Include individual values so single-axis models and constrained values count.
    return {tuple(pair) for n in range(1, min(strength, len(items)) + 1) for pair in itertools.combinations(items, n)}


def select_cases(valid, strategy, budget=None):
    if not valid:
        raise ValueError("Model has no valid combinations")
    if strategy not in {"each-choice", "pairwise", "three-way", "exhaustive"}:
        raise ValueError("Unknown coverage strategy")
    if budget is not None and (type(budget) is not int or budget < 1):
        raise ValueError("Budget must be a positive integer")
    strength = {"pairwise": 2, "three-way": 3}.get(strategy, 1)
    sets = [interactions(s, strength) for s in valid]
    universe = set().union(*sets)
    uncovered = set(universe)
    selected = []
    remaining = list(range(len(valid)))
    while remaining and (uncovered or strategy == "exhaustive") and (budget is None or len(selected) < budget):
        best = remaining[0] if strategy == "exhaustive" else max(remaining, key=lambda i: len(sets[i] & uncovered))
        selected.append(valid[best])
        uncovered -= sets[best]
        remaining.remove(best)
    return selected, {
        "strategy": strategy, "strength": strength,
        "valid_combinations": len(valid), "selected_cases": len(selected),
        "required_interactions": len(universe), "covered_interactions": len(universe - uncovered),
        "complete": not uncovered and (strategy != "exhaustive" or len(selected) == len(valid)),
        "uncovered_interactions": [dict(p) for p in sorted(uncovered)],
        "scope": "Only the modeled values and encoded constraints; this is not full IBM syntax coverage or execution coverage.",
    }


def order_nodes(nodes):
    by_id = {n["id"]: n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("Duplicate dependency node ID")
    result = []
    while len(result) < len(nodes):
        ready = [n for n in nodes if n["id"] not in result and set(n["depends_on"]) <= set(result)]
        if not ready:
            raise ValueError("Dependency graph contains a cycle or unresolved dependency")
        result.extend(n["id"] for n in ready)
    return [by_id[i] for i in result]


def refs(model, selection):
    covered = set(model["covers"])
    for axis, value in selection.items():
        covered.update(model["dimensions"][axis][value]["covers"])
    return sorted(covered)


def validate_model(model, data):
    if type(model.get("uses_database", True)) is not bool:
        raise ValueError("uses_database must be a boolean")
    if model["object"] not in data["objects"]:
        raise ValueError("Scaffolded or unknown objects cannot be compiled")
    if not model["dimensions"] or any(not options for options in model["dimensions"].values()):
        raise ValueError("Models need nonempty dimensions")
    clauses = {f"{o}.{c['id']}" for o, obj in data["objects"].items() for c in obj["clauses"]}
    rules = {f"{o}.{r['id']}" for o, obj in data["objects"].items() for r in obj["rules"]}
    all_covers = set(model["covers"])
    for options in model["dimensions"].values():
        for option in options.values():
            all_covers.update(option["covers"])
    if all_covers - clauses:
        raise ValueError(f"Unknown clause references: {sorted(all_covers - clauses)}")
    if set(model["rule_refs"]) - rules:
        raise ValueError("Unknown model rule reference")
    if not model["source_refs"] or set(model["source_refs"]) - data["sources"].keys():
        raise ValueError("Missing or unknown IBM source references")
    for source in model["source_refs"]:
        if not data["sources"][source]["url"].startswith("https://www.ibm.com/docs/"):
            raise ValueError("Non-IBM model source")
    ids = [c["id"] for c in model["constraints"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate constraint ID")
    for constraint in model["constraints"]:
        if constraint["rule_ref"] not in rules:
            raise ValueError("Unresolved constraint rule")
        for predicate in (constraint["when"], constraint["requires"]):
            if not predicate:
                raise ValueError("Empty constraint predicate")
            for axis, values in predicate.items():
                values = values if isinstance(values, list) else [values]
                if axis not in model["dimensions"] or set(values) - model["dimensions"][axis].keys():
                    raise ValueError("Constraint refers to an unknown dimension/value")
    ordered = order_nodes(model["nodes"])
    if sum(n["role"] == "action" for n in model["nodes"]) != 1:
        raise ValueError("Exactly one action node is required")
    if ordered[-1]["role"] != "action" or any(n["role"] not in {"setup", "action"} for n in ordered):
        raise ValueError("The action must follow all setup nodes")
    terminator = model.get("statement_terminator", ";")
    by_id = {n["id"]: n for n in ordered}
    for node in ordered:
        validate_statement(node["sql"], node.get("kind", "sql"), terminator)
        if node["drop"] is not None:
            validate_statement(node["drop"], "sql", terminator)
        else:
            owner = node.get("cleanup_via")
            ancestors, pending = set(), list(node["depends_on"])
            while pending:
                dependency = pending.pop()
                if dependency not in ancestors:
                    ancestors.add(dependency)
                    pending.extend(by_id[dependency]["depends_on"])
            if owner not in ancestors or not by_id[owner].get("drop"):
                raise ValueError("A node without DROP needs an ancestor with DROP as cleanup_via")
    query_map = {q["id"]: q for q in model["catalog"]}
    if not query_map or len(query_map) != len(model["catalog"]):
        raise ValueError("Catalog queries need unique IDs and cannot be empty")
    for query in model["catalog"]:
        if not query["fields"] or not set(query["key"]) <= set(query["fields"]):
            raise ValueError("Catalog keys must be selected fields")
        if not set(query.get("rtrim_fields", [])) <= set(query["fields"]):
            raise ValueError("Padding fields must be selected fields")
    assertions = list(model.get("assertions", []))
    for options in model["dimensions"].values():
        for option in options.values():
            assertions.extend(option.get("assertions", []))
            for query_id, count in option.get("catalog_row_counts", {}).items():
                if query_id not in query_map or type(count) is not int or count < 1:
                    raise ValueError("Invalid option catalog row count")
    for assertion in assertions:
        query = query_map.get(assertion["catalog"])
        if query is None or not assertion["equals"] or (set(assertion["where"]) | set(assertion["equals"])) - set(query["fields"]):
            raise ValueError("Assertion refers to a missing query/field or has no expected values")


def make_case(model, selection, profile, run, number, negative=None):
    case_id = f"DB2Z13-{model['object'].upper()}-{run}-{number:03d}"
    name = f"{run}{number:04d}"
    params = {
        "DATABASE": run + "SDB", "SCHEMA": profile["source_schema"], "TABLESPACE": name,
        "TABLE": name, "INDEX": name, "STOGROUP": profile.get("storage_group", ""),
        "TABLE_BP": profile.get("table_bufferpool", ""), "INDEX_BP": profile.get("index_bufferpool", ""),
        "PARENT_TABLESPACE": f"{run}P{number:03d}", "TRIGGER": name, "PROCEDURE": name,
        "APPLCOMPAT": profile["product_context"]["applcompat"],
    }
    for axis, value in selection.items():
        params[axis.upper()] = model["dimensions"][axis][value]["sql"]
    replay = {**params, "DATABASE": run + "RDB", "SCHEMA": profile["replay_schema"]}
    nodes = order_nodes(model["nodes"])
    terminator = model.get("statement_terminator", ";")
    for values in (params, replay):
        for node in nodes:
            validate_statement(render(node["sql"], values), node.get("kind", "sql"), terminator)
            if node["drop"] is not None:
                validate_statement(render(node["drop"], values), "sql", terminator)
    setup = [render(n["sql"], params) for n in nodes if n["role"] == "setup"]
    action = [render(n["sql"], params) for n in nodes if n["role"] == "action"]
    cleanup = [render(n["drop"], params) for n in reversed(nodes) if n["drop"] is not None]
    reference = [render(n["sql"], replay) for n in nodes]
    queries = []
    row_counts = {}
    for axis, value in selection.items():
        row_counts.update(model["dimensions"][axis][value].get("catalog_row_counts", {}))
    for query in model["catalog"]:
        queries.append({**query, "source_sql": render(query["sql"], params), "replay_sql": render(query["sql"], replay)})
        if query["id"] in row_counts:
            queries[-1].update(min_rows=row_counts[query["id"]], max_rows=row_counts[query["id"]])
    assertions = model.get("assertions", []) + [a for axis, value in selection.items() for a in model["dimensions"][axis][value].get("assertions", [])]
    covered = refs(model, selection)
    prerequisites = ["Run the campaign preflight; every planned name must be unused.",
                     "Verify profile values, definition/body APPLCOMPAT, and authority on the target subsystem."]
    if model.get("uses_database", True):
        prerequisites += ["Create the source campaign database using bootstrap-source.sql.",
                          "Verify the storage group and active 4 KB pools on the target subsystem."]
    record = {
        "schema_version": "1.0.0", "id": case_id, "title": f"{model['id']}: " + ", ".join(f"{k}={v}" for k, v in selection.items()),
        "object": model["object"], "category": "negative" if negative else "round_trip", "status": "design",
        "product_context": profile["product_context"], "source_refs": model["source_refs"],
        "variation": {"primary_clause": model["covers"][0], "dimensions": [f"{k}:{v}" for k, v in selection.items()], "explicitness": "not_applicable"},
        "parameters": params,
        "prerequisites": prerequisites + model.get("prerequisites", []),
        "setup_sql": setup, "action_sql": action,
        "expected": {
            "outcome": "sql_error" if negative else "success", "failure_phase": "prepare_or_execute" if negative else "none",
            "sqlcode": None if negative else 0, "sqlstate": None if negative else "00000",
            "catalog_assertions": (["Setup must succeed; the action must fail and leave no target object."] if negative else [f"{q['id']}: expected rows {q['min_rows']}..{q['max_rows']}; compare the selected fields after product DDL replay." for q in queries]),
            "notes": f"Violate only {negative}; SQLCODE/SQLSTATE need confirmation on Db2." if negative else "Catalog equivalence is scoped to catalog-contract.json. Check source semantics before attributing a replay failure to the product.",
        },
        "ofs_validation": {
            "generation_target": render(model["target"], params),
            "name_map": {params["SCHEMA"] + "." + name: replay["SCHEMA"] + "." + name, params["DATABASE"]: replay["DATABASE"]},
            "generated_ddl_must_include": [], "generated_ddl_must_exclude": [],
            "comparison_policy": {"semantic_fields": [q["id"] + "." + f for q in queries for f in q["fields"]],
                                  "ignored_fields": ["All unselected fields, including object IDs, timestamps and statistics"],
                                  "notes": "No text-based SQL rewriting. Use product name mapping or an SQL-aware adapter. Negative cases test Db2 acceptance, not product extraction."},
        },
        "cleanup_sql": cleanup,
        "artifacts": {"catalog_contract": "catalog-contract.json", "source_ddl": "source.sql", "ofs_generated_ddl": "product-generated.sql"},
    }
    for object_name in model.get("object_names", []):
        record["ofs_validation"]["name_map"][render(object_name, params)] = render(object_name, replay)
    if not model.get("uses_database", True):
        record["ofs_validation"]["name_map"].pop(params["DATABASE"], None)
    probes = [{**probe, "source_sql": render(probe["sql"], params), "replay_sql": render(probe["sql"], replay)} for probe in model.get("probes", [])]
    metrics = [{"node": node["id"], "kind": node.get("kind", "sql"), **validate_statement(render(node["sql"], params), node.get("kind", "sql"), terminator)} for node in nodes]
    return record, {"case_id": case_id, "model": model["id"], "selection": selection, "clause_refs": covered,
                    "rule_refs": model["rule_refs"], "violated_constraint": negative, "catalog": queries, "assertions": assertions,
                    "statement_terminator": terminator, "text_metrics": metrics, "probes": probes,
                    "preflight_sql": [render(sql, values) for values in (params, replay) for sql in model.get("preflight", [])],
                    "reference_replay_sql": reference,
                    "cleanup_ownership": {n["id"]: n.get("cleanup_via", n["id"]) for n in nodes},
                    "replay_cleanup_sql": [render(n["drop"], replay) for n in reversed(nodes) if n["drop"] is not None]}


def sql_file(statements, note="", terminator=";"):
    return emit_sql(statements, note, terminator)


def write_campaign(args):
    data = kb()
    model = models()[args.model]
    validate_model(model, data)
    profile = read(args.profile)
    validate_profile(profile, model)
    run = identifier(args.run, 4)
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,3}", run):
        raise ValueError("Run prefix must be 2 to 4 uppercase letters/digits, starting with a letter")
    if args.budget is not None and args.budget < 1:
        raise ValueError("Budget must be positive")
    filters = selection_filters(model, getattr(args, "settings", []))
    full_raw, full_valid = candidates(model)
    raw, valid = candidates(model, filters)
    selected, coverage = select_cases(valid, args.strategy, args.budget)
    negative = []
    if args.negative:
        for c in model["constraints"]:
            candidate = next((s for s in raw if violations(model, s) == [c["id"]]), None)
            if candidate is None:
                raise ValueError(f"Cannot isolate negative constraint {c['id']} within the selected filters")
            negative.append((candidate, c["id"]))
    if len(selected) + len(negative) > 999:
        raise ValueError("Case schema permits 999 cases per campaign; split the campaign or set --budget")
    cases = [make_case(model, s, profile, run, i + 1, n) for i, (s, n) in enumerate([(s, None) for s in selected] + negative)]
    coverage.update({"raw_combinations": len(raw), "excluded_combinations": len(raw) - len(valid), "negative_cases": len(negative), "runtime_passed_cases": 0})
    coverage.update({"selection_filters": filters, "full_model_raw_combinations": len(full_raw), "full_model_valid_combinations": len(full_valid)})
    uses_database = model.get("uses_database", True)
    source_db, replay_db = (run + "SDB", run + "RDB") if uses_database else (None, None)
    manifest = {"schema_version": "1.0.0", "id": run, "model": model["id"], "status": "design", "profile": profile,
                "model_sha256": digest(model), "kb_sha256": digest(data), "compiler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "source_database": source_db, "replay_database": replay_db,
                "case_ids": [c[0]["id"] for c in cases], "coverage": coverage,
                "source_refs": {s: data["sources"][s] for s in model["source_refs"]}}
    manifest["sqltext_sha256"] = hashlib.sha256((ROOT / "tools/sqltext.py").read_bytes()).hexdigest()
    manifest["statement_terminator"] = model.get("statement_terminator", ";")
    manifest["uses_database"] = uses_database
    # Prepare every artifact before creating the output directory.
    files = {}
    terminator = manifest["statement_terminator"]

    def add(path, content):
        files[path] = content

    def add_sql(path, statements, note=""):
        add(path, sql_file(statements, note, terminator))

    add("manifest.json", dump(manifest))
    add("coverage.json", dump(coverage))
    add("model.json", dump(model))
    for side, database in (("source", source_db), ("replay", replay_db)):
        if uses_database:
            bootstrap = f"CREATE DATABASE {database} STOGROUP {profile['storage_group']} BUFFERPOOL {profile['table_bufferpool']} INDEXBP {profile['index_bufferpool']} CCSID EBCDIC"
            add_sql(f"bootstrap-{side}.sql", [bootstrap, "COMMIT"], "Requires an unused database name and a verified environment.")
        else:
            add_sql(f"bootstrap-{side}.sql", [], "No campaign database is required by this model.")
    names = ", ".join("'" + c[0]["parameters"]["TABLE"] + "'" for c in cases)
    preflight = [f"SELECT NAME FROM SYSIBM.SYSDATABASE WHERE NAME IN ('{source_db}', '{replay_db}')",
                 f"SELECT CREATOR, NAME FROM SYSIBM.SYSTABLES WHERE CREATOR IN ('{profile['source_schema']}', '{profile['replay_schema']}') AND NAME IN ({names})",
                 f"SELECT CREATOR, NAME FROM SYSIBM.SYSINDEXES WHERE CREATOR IN ('{profile['source_schema']}', '{profile['replay_schema']}') AND NAME IN ({names})"]
    if not uses_database:
        preflight = []
    preflight += [sql for _, contract in cases for sql in contract["preflight_sql"]]
    add_sql("preflight.sql", preflight, "Every query must return zero rows. Stop on a collision.")
    for record, contract in cases:
        folder = "cases/" + record["id"] + "/"
        add(folder + "case.json", dump(record))
        add(folder + "catalog-contract.json", dump(contract))
        add(folder + "behavior-probes.json", dump({"case_id": record["id"], "status": "design", "probes": contract["probes"],
            "instructions": "Manual/harness execution only, after successful positive setup/action. Preserve results separately for source and actual product replay. Probes may mutate data; inspect mutates and prerequisites."}))
        add_sql(folder + "setup.sql", record["setup_sql"])
        add_sql(folder + "action.sql", record["action_sql"])
        add_sql(folder + "source.sql", record["setup_sql"] + record["action_sql"] + ["COMMIT"], "Stop if setup fails. Negative actions are expected to fail.")
        for side in ("source", "replay"):
            add_sql(folder + f"catalog-{side}.sql", [f"-- result set: {q['id']}\n{q[side + '_sql']}" for q in contract["catalog"]])
        if not contract["violated_constraint"]:
            add_sql(folder + "reference-replay.sql", contract["reference_replay_sql"], "Harness reference only. Product validation must replay the actual product-generated DDL.")
        add_sql(folder + "cleanup.sql", contract["replay_cleanup_sql"] + record["cleanup_sql"] + ["COMMIT"], "Run only drops for objects recorded as created in this run; failed/negative cases can have absent targets.")
    if uses_database:
        add_sql("cleanup-databases.sql", [f"DROP DATABASE {replay_db}", f"DROP DATABASE {source_db}", "COMMIT"], "Destructive: drops the two entire campaign databases. Verify run ownership and contents first.")
    else:
        add_sql("cleanup-databases.sql", [], "No campaign database was created; use each case's routine cleanup.")
    add("RUN.md",
        f"# Campaign {run}\n\nStatus: design. Environment verified: {profile['verified']}. Nothing has run on Db2.\n\n"
        f"All SQL files use outer terminator `{terminator}`. Configure the SQL processor accordingly; JSON statement arrays have no outer terminator. "
        "For SPUFI body-format tests use SQLFORMAT SQLPL to retain comments and line structure. Do not split routine/trigger bodies on semicolons. "
        "Text metrics describe UTF-8 artifacts, not target CCSID byte limits.\n\n"
        "1. Verify the profile, required authority, and SQL processor settings. Run preflight.sql; require zero rows for every query.\n"
        "2. Run bootstrap-source.sql once if it contains database setup. Per case, run setup.sql then action.sql; retain statement-level SQLCODE/SQLSTATE and stop after a setup error. Commit positive DDL.\n"
        "3. For negative cases require successful setup and the intended action failure. Do not count arbitrary setup/authority errors as a pass. Skip product extraction for absent objects.\n"
        "4. For positive cases capture catalog-source.sql result sets as JSON using the IDs in catalog-contract.json. Verify source attributes against the selection and IBM references. Inspect behavior-probes.json and retain any required body-text or behavioral evidence separately.\n"
        "5. Extract DDL using the administration product, preserving product version, options and raw output as product-generated.sql. Include table spaces, enforcing indexes and dependent objects in the extraction scope.\n"
        "6. Run bootstrap-replay.sql once if it contains database setup. Apply the recorded name map through the product or an SQL-aware adapter; replay actual product output. reference-replay.sql only tests the harness and is never product evidence.\n"
        "7. Capture catalog-replay.sql with the same adapter. Run tools/qa.py compare with the case contract and both JSON snapshots. A matching snapshot covers only the selected fields. Run required behavioral probes on both sides separately.\n"
        "8. Retain execution evidence before cleanup. Run only drops for objects this run created. Where present, database cleanup removes entire dedicated databases; separately clean routine objects listed in case cleanup.\n\n"
        "Snapshot format and the execution protocol are in kb/campaigns/README.md. No credentials or automatic execution are provided.\n")
    args.out.mkdir(parents=True, exist_ok=False)
    for path, content in files.items():
        target = args.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(dump({"output": str(args.out), "cases": len(cases), "coverage": coverage}))


def compare(contract, source, replay):
    if not isinstance(contract, dict) or not contract.get("case_id") or not contract.get("catalog"):
        raise ValueError("Contract must identify a case and contain catalog queries")
    if contract.get("violated_constraint"):
        raise ValueError("Negative cases have no product round-trip catalog comparison")
    query_map = {q["id"]: q for q in contract["catalog"]}
    if len(query_map) != len(contract["catalog"]):
        raise ValueError("Duplicate query IDs in contract")
    for assertion in contract.get("assertions", []):
        query = query_map.get(assertion["catalog"])
        if query is None or not assertion["equals"] or (set(assertion["where"]) | set(assertion["equals"])) - set(query["fields"]):
            raise ValueError("Contract assertion refers to a missing query/field or has no expected values")
    result = {"case_id": contract["case_id"], "status": "match", "differences": [], "scope": "Selected catalog fields only; not an overall product test pass."}
    for side, snapshot in (("source", source), ("replay", replay)):
        if not isinstance(snapshot, dict):
            raise ValueError(f"{side} snapshot must be an object")
        if snapshot.get("case_id") != contract["case_id"] or snapshot.get("side") != side:
            raise ValueError(f"{side} snapshot case_id/side mismatch")
        if not isinstance(snapshot.get("catalog"), dict):
            raise ValueError(f"{side} snapshot requires a catalog map")
    for query in contract["catalog"]:
        if not query.get("fields") or not query.get("key") or not set(query["key"]) <= set(query["fields"]):
            raise ValueError("Contract requires selected fields and stable row keys")
        if not set(query.get("rtrim_fields", [])) <= set(query["fields"]):
            raise ValueError("Contract padding fields must be selected fields")
        if query["min_rows"] < 1 or query["max_rows"] < query["min_rows"]:
            raise ValueError("These positive contracts require a nonempty row-count range")
        normalized = []
        for side, snapshot in (("source", source), ("replay", replay)):
            rows = snapshot["catalog"].get(query["id"])
            if not isinstance(rows, list) or not query["min_rows"] <= len(rows) <= query["max_rows"]:
                raise ValueError(f"{side}.{query['id']}: missing result set or unexpected row count")
            records, keys = [], set()
            for row in rows:
                if not isinstance(row, dict) or set(query["fields"]) - row.keys():
                    raise ValueError(f"{side}.{query['id']}: missing required fields")
                values = {}
                for field in query["fields"]:
                    value = row[field]
                    if isinstance(value, (dict, list)):
                        raise ValueError("Catalog values must be scalars")
                    if isinstance(value, str) and field in query.get("rtrim_fields", []):
                        value = value.rstrip(" ")
                    values[field] = value
                key = json.dumps([values[f] for f in query["key"]])
                if key in keys:
                    raise ValueError(f"{side}.{query['id']}: duplicate catalog key {key}")
                keys.add(key)
                records.append(json.dumps(values, sort_keys=True))
            for assertion in contract.get("assertions", []):
                if assertion["catalog"] != query["id"]:
                    continue
                matching = [json.loads(r) for r in records if all(json.loads(r).get(k) == v for k, v in assertion["where"].items())]
                if len(matching) != 1 or any(matching[0].get(k) != v for k, v in assertion["equals"].items()):
                    result["status"] = "mismatch"
                    result["differences"].append({"catalog": query["id"], "side": side, "failed_assertion": assertion, "actual": matching})
            normalized.append(Counter(records))
        if normalized[0] != normalized[1]:
            result["status"] = "mismatch"
            result["differences"].append({"catalog": query["id"],
                                           "source_only": [json.loads(r) for r in (normalized[0] - normalized[1]).elements()],
                                           "replay_only": [json.loads(r) for r in (normalized[1] - normalized[0]).elements()]})
    return result


def coverage_inventory():
    data = kb()
    implemented = set()
    for model in models().values():
        implemented.update(model["covers"])
        for options in model["dimensions"].values():
            for option in options.values():
                implemented.update(option["covers"])
    return [{"object": name, "normalized_clauses": len(obj["clauses"]),
             "modeled_clauses": [c["id"] for c in obj["clauses"] if name + "." + c["id"] in implemented],
             "unmodeled_clauses": [c["id"] for c in obj["clauses"] if name + "." + c["id"] not in implemented],
             "note": "Modeled means at least one compiler path, not every syntax branch or runtime coverage."}
            for name, obj in data["objects"].items()]


def context_pack(object_name):
    data = kb()
    if object_name not in data["objects"]:
        raise ValueError("Object is not normalized. Research and normalize its IBM syntax before generation.")
    obj = data["objects"][object_name]
    sources = {s for group in ("clauses", "rules") for item in obj[group] for s in item["source_refs"]}
    pack = {"object": object_name, "policy": "Read AGENTS.md and kb/campaigns/README.md. IBM Db2 13 is authoritative; all generated cases start in design.",
            "normalized": obj, "sources": {s: data["sources"][s] for s in sorted(sources)},
            "campaign_models": [m for m in models().values() if m["object"] == object_name],
            "coverage": next(x for x in coverage_inventory() if x["object"] == object_name)}
    if object_name == "trigger":
        pack["body_matrix"] = read(ROOT / "kb/data/db2z13-trigger-body-statements.json")
    return pack


def validate_case(record):
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        raise ValueError("Case schema validation requires requirements-dev.txt; use .venv/bin/python") from error
    validator = Draft202012Validator(read(ROOT / "kb/data/test-case.schema.json"))
    errors = sorted(validator.iter_errors(record), key=lambda e: str(list(e.path)))
    if errors:
        raise ValueError("; ".join(f"{'.'.join(map(str, e.path)) or '$'}: {e.message}" for e in errors))
    data = kb()
    if set(record["source_refs"]) - data["sources"].keys():
        raise ValueError("Case contains unresolved IBM source IDs")
    for statements in ("setup_sql", "action_sql", "cleanup_sql"):
        for statement in record.get(statements, []):
            if "{{" in statement or "}}" in statement:
                raise ValueError(f"Unresolved SQL placeholder in {statements}")
    if not record["action_sql"]:
        raise ValueError("Case requires at least one action statement")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory", help="report modeled and unmodeled normalized clauses as JSON")
    commands.add_parser("validate", help="check model references, constraints, SQL rendering and dependency graphs")
    commands.add_parser("models", help="list compilable campaign models as JSON")
    context = commands.add_parser("context", help="export a self-contained IBM-linked object context pack")
    context.add_argument("object")
    case_check = commands.add_parser("validate-case", help="validate a manually/agent-authored case's schema and source references; not SQL legality")
    case_check.add_argument("path", type=Path)
    build = commands.add_parser("build", help="write an offline campaign; never executes SQL")
    build.add_argument("--model", choices=sorted(models()), required=True)
    build.add_argument("--profile", type=Path, required=True)
    build.add_argument("--run", required=True)
    build.add_argument("--strategy", choices=["pairwise", "three-way", "each-choice", "exhaustive"], default="pairwise")
    build.add_argument("--set", dest="settings", action="append", default=[], metavar="AXIS=VALUE", help="restrict dimension values; repeat an axis for an OR subset")
    build.add_argument("--budget", type=int, help="positive-case limit; negative companions are additional")
    build.add_argument("--negative", action="store_true", help="add one isolated violation per encoded constraint")
    build.add_argument("--out", type=Path, required=True)
    comparison = commands.add_parser("compare", help="compare selected semantic fields in two catalog JSON snapshots")
    comparison.add_argument("--contract", type=Path, required=True)
    comparison.add_argument("--source", type=Path, required=True)
    comparison.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            write_campaign(args)
        elif args.command == "inventory":
            print(dump(coverage_inventory()))
        elif args.command == "models":
            print(dump([{"id": m["id"], "object": m["object"], "dimensions": {k: list(v) for k, v in m["dimensions"].items()}} for m in models().values()]))
        elif args.command == "context":
            print(dump(context_pack(args.object)))
        elif args.command == "validate-case":
            validate_case(read(args.path))
            print("Case schema and source validation OK (not Db2 syntax or execution validation)")
        elif args.command == "compare":
            result = compare(read(args.contract), read(args.source), read(args.replay))
            print(dump(result))
            return 1 if result["status"] == "mismatch" else 0
        elif args.command == "validate":
            profile = read(ROOT / "kb/campaigns/profiles/example.json")
            for model in models().values():
                validate_model(model, kb())
                validate_profile(profile, model)
                _, valid = candidates(model)
                for selection in valid:
                    make_case(model, selection, profile, "QA", 1)
            print("Campaign model validation OK (static only)")
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
