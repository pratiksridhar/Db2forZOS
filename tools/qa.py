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

import paths
from sqltext import emit_sql, validate_statement

ROOT = paths.ROOT
MODEL_DIR = paths.MODELS
TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def kb():
    return read(paths.CREATE_DDL)


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
    context_schema = read(paths.CASE_SCHEMA)["$defs"]["product_context"]
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


def catalog_types(query, tables=None):
    """Declared type of every selected field: catalog columns from the verified column list, computed
    fields from the query's expression_types. Snapshots are typed and checked against these."""
    tables = tables if tables is not None else read(paths.CATALOG_COLUMNS)["tables"]
    table = tables.get(query.get("table"))
    if table is None:
        raise ValueError(f"Catalog query {query.get('id')}: table {query.get('table')!r} has no verified columns "
                         f"in {paths.rel(paths.CATALOG_COLUMNS)}")
    computed = query.get("expression_types", {})
    types = {}
    for field in query["fields"]:
        if field in computed:
            types[field] = computed[field]
        elif field in table["columns"]:
            types[field] = table["columns"][field]
        else:
            raise ValueError(f"Catalog query {query['id']}: {field} is not a verified column of {query['table']}; "
                             "declare a computed field in expression_types")
    return types


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
    tables = read(paths.CATALOG_COLUMNS)["tables"]
    for query in model["catalog"]:
        if not query["fields"] or not set(query["key"]) <= set(query["fields"]):
            raise ValueError("Catalog keys must be selected fields")
        catalog_types(query, tables)
        if not re.search(rf"\bFROM\s+{re.escape(query['table'])}\b", query["sql"]):
            raise ValueError(f"Catalog query {query['id']} does not select from its declared table {query['table']}")
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
    tables = read(paths.CATALOG_COLUMNS)["tables"]
    for query in model["catalog"]:
        queries.append({**query, "types": catalog_types(query, tables), "source_sql": render(query["sql"], params), "replay_sql": render(query["sql"], replay)})
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
        "2. Run bootstrap-source.sql once if it contains database setup. Per case, run setup.sql then action.sql; retain statement-level SQLCODE/SQLSTATE and stop after a setup error. Commit positive DDL. "
        "Record each run: tools/qa.py record cases/<id> --phase source --result pass|fail|blocked --sqlcode N --evidence <log>.\n"
        "3. For negative cases require successful setup and the intended action failure, and record it with the failing SQLCODE. Do not count arbitrary setup/authority errors as a pass. Skip product extraction for absent objects.\n"
        "4. For positive cases export each catalog-source.sql result set as CSV with its header row, named <result set id>.csv in one directory per case and side, and convert it: "
        "tools/qa.py snapshot --contract cases/<id>/catalog-contract.json --side source --csv-dir <dir> --out <file>. Verify source attributes against the selection and IBM references. "
        "Inspect behavior-probes.json and retain any required body-text or behavioral evidence separately.\n"
        "5. Extract DDL using the administration product, preserving product version, options and raw output as product-generated.sql. Include table spaces, enforcing indexes and dependent objects in the extraction scope. "
        "Record it with --phase extraction --product <name> --product-version <version> --evidence product-generated.sql.\n"
        "6. Run bootstrap-replay.sql once if it contains database setup. Apply the recorded name map through the product or an SQL-aware adapter; replay actual product output and record --phase replay. reference-replay.sql only tests the harness and is never product evidence.\n"
        "7. Capture catalog-replay.sql with the same adapter and convert it with --side replay. tools/qa.py record cases/<id> --phase comparison --source <file> --replay <file> runs the comparison and records it. "
        "A matching snapshot covers only the selected fields. Run required behavioral probes on both sides separately and record --phase probes. tools/qa.py status . reports every case.\n"
        "8. Retain execution evidence before cleanup. Run only drops for objects this run created. Where present, database cleanup removes entire dedicated databases; separately clean routine objects listed in case cleanup.\n\n"
        "Snapshots and outcome records are described in docs/workflows/product-verification.md; the execution protocol is in "
        "docs/workflows/campaign.md. No credentials or automatic execution are provided.\n")
    args.out.mkdir(parents=True, exist_ok=False)
    for path, content in files.items():
        target = args.out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(dump({"output": str(args.out), "cases": len(cases), "coverage": coverage}))


INTEGER_FAMILIES = {"SMALLINT", "INTEGER", "INT", "BIGINT"}
TEXT_FAMILIES = {"CHAR", "CHARACTER", "VARCHAR", "TIMESTAMP", "DATE", "TIME"}


def declared(type_text):
    """(family, nullable) of a catalog declaration such as 'SMALLINT NOT NULL WITH DEFAULT'."""
    words = re.sub(r"^FL \d+ ", "", type_text.upper()).split()
    return re.sub(r"\(.*", "", words[0]), "NOT NULL" not in type_text.upper()


def read_delimited(text, delimiter=","):
    """RFC 4180 records as (line, [(text, quoted), ...]). Unlike the csv module it keeps whether a field
    was quoted, so an unquoted empty field (how many clients export SQL NULL) differs from a quoted ''."""
    records, record, field = [], [], []
    quoted, at_start, line, start = False, True, 1, 1
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if at_start and ch == '"':
            i += 1
            while True:
                if i >= n:
                    raise ValueError(f"line {start}: quoted field is not closed")
                if text[i] == '"':
                    if text[i + 1:i + 2] == '"':
                        field.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                line += text[i] == "\n"
                field.append(text[i])
                i += 1
            if i < n and text[i] not in (delimiter, "\r", "\n"):
                raise ValueError(f"line {line}: text follows a closing quote")
            quoted, at_start = True, False
        elif ch == delimiter:
            record.append(("".join(field), quoted))
            field, quoted, at_start = [], False, True
            i += 1
        elif ch in "\r\n":
            record.append(("".join(field), quoted))
            records.append((start, record))
            record, field, quoted, at_start = [], [], False, True
            i += 2 if text[i:i + 2] == "\r\n" else 1
            line += 1
            start = line
        else:
            field.append(ch)
            at_start = False
            i += 1
    if record or field or quoted:
        record.append(("".join(field), quoted))
        records.append((start, record))
    return records


def typed_value(value, quoted, type_text, null, where):
    family, nullable = declared(type_text)
    is_null = not quoted and value == null
    if family in INTEGER_FAMILIES:
        if is_null and nullable:
            return None
        try:
            return int(value.strip())
        except ValueError:
            raise ValueError(f"{where}: {value!r} is not a value of {type_text}") from None
    if family in TEXT_FAMILIES:
        # A NOT NULL column cannot hold NULL, so its unquoted empty field is the empty string.
        return None if is_null and nullable else value
    raise ValueError(f"{where}: no conversion rule for declared type {type_text}")


def snapshot(contract, side, files, null="", delimiter=",", encoding="utf-8"):
    """Turn one CSV export per catalog result set into the snapshot that compare reads. Values are typed by
    the contract's declared types; text keeps its exact characters, padding included."""
    if side not in ("source", "replay"):
        raise ValueError("side must be source or replay")
    if not isinstance(contract, dict) or not contract.get("case_id") or not contract.get("catalog"):
        raise ValueError("Contract must identify a case and contain catalog queries")
    if len(delimiter) != 1 or delimiter in '"\r\n':
        raise ValueError("The delimiter must be one character other than a quote or line break")
    ids = [q["id"] for q in contract["catalog"]]
    missing, unknown = [i for i in ids if i not in files], sorted(set(files) - set(ids))
    if missing or unknown:
        raise ValueError(f"Every result set needs exactly one export. Missing: {missing or 'none'}; not in the contract: {unknown or 'none'}")
    catalog, provenance = {}, {}
    for query in contract["catalog"]:
        types = query.get("types")
        if not types or set(query["fields"]) - types.keys():
            raise ValueError(f"Contract query {query['id']} lacks declared types; rebuild the bundle or campaign with the current tools")
        path = Path(files[query["id"]])
        raw = path.read_bytes()
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as error:
            raise ValueError(f"{path}: not {encoding} text ({error.reason}); pass --encoding") from None
        records = read_delimited(text.removeprefix("﻿"), delimiter)
        if not records:
            raise ValueError(f"{path}: empty file; export the header row with the result set")
        header = [name.strip().upper() for name, _ in records[0][1]]
        duplicate = sorted({h for h in header if header.count(h) > 1})
        absent, extra = [f for f in query["fields"] if f not in header], [h for h in header if h not in query["fields"]]
        if duplicate or absent or extra:
            raise ValueError(f"{path}: header does not match result set {query['id']} "
                             f"(missing {absent or 'none'}, unexpected {extra or 'none'}, repeated {duplicate or 'none'})")
        rows = []
        for line, record in records[1:]:
            if record == [("", False)] and len(header) > 1:
                continue  # a blank line
            if len(record) != len(header):
                raise ValueError(f"{path} line {line}: {len(record)} fields; the header has {len(header)}")
            rows.append({name: typed_value(value, quoted, types[name], null, f"{path} line {line} {name}")
                         for name, (value, quoted) in zip(header, record)})
        catalog[query["id"]] = rows
        provenance[query["id"]] = {"file": paths.portable(path), "sha256": hashlib.sha256(raw).hexdigest(), "rows": len(rows)}
    return {"case_id": contract["case_id"], "side": side, "catalog": catalog,
            "provenance": {"converted_by": "tools/qa.py snapshot", "contract_sha256": digest(contract),
                           "null": null, "delimiter": delimiter, "encoding": encoding, "files": provenance}}


def check_types(query, side, rows):
    """Reject values whose JSON type contradicts the declared column type, such as "5" for SMALLINT."""
    for row in rows:
        for field, type_text in query.get("types", {}).items():
            family, nullable = declared(type_text)
            value = row.get(field)
            if value is None:
                if not nullable:
                    raise ValueError(f"{side}.{query['id']}: {field} is NULL, but {type_text} cannot be")
            elif family in INTEGER_FAMILIES and (type(value) is not int):
                raise ValueError(f"{side}.{query['id']}: {field} must be a JSON integer for {type_text}, not {value!r}")
            elif family in TEXT_FAMILIES and not isinstance(value, str):
                raise ValueError(f"{side}.{query['id']}: {field} must be a JSON string for {type_text}, not {value!r}")


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
        converted_for = (snapshot.get("provenance") or {}).get("contract_sha256")
        if converted_for is not None and converted_for != digest(contract):
            raise ValueError(f"{side} snapshot was converted for a different contract; convert the exports again with this one")
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
            check_types(query, side, rows)
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
    pack = {"object": object_name, "policy": "Read AGENTS.md and docs/workflows/campaign.md. IBM Db2 13 is authoritative; all generated cases start in design.",
            "normalized": obj, "sources": {s: data["sources"][s] for s in sorted(sources)},
            "campaign_models": [m for m in models().values() if m["object"] == object_name],
            "coverage": next(x for x in coverage_inventory() if x["object"] == object_name)}
    if object_name == "trigger":
        pack["body_matrix"] = read(paths.TRIGGER_BODY)
    return pack


PHASES = ("source", "extraction", "replay", "comparison", "probes", "cleanup")
PREREQUISITE = {"extraction": "source", "replay": "extraction", "comparison": "replay", "probes": "replay"}
VERDICTS = ("pass", "fail", "blocked")


def case_path(path):
    path = Path(path)
    return path / "case.json" if path.is_dir() else path


def required_phases(record, probes=False):
    """Phases whose latest attempts decide the status. A positive round trip needs every phase; an
    expected SQL or operational error needs only the source run; an expected product error ends at extraction."""
    outcome = record["expected"]["outcome"]
    if outcome == "success":
        return ["source", "extraction", "replay", "comparison"] + (["probes"] if probes else [])
    return ["source", "extraction"] if outcome == "ofs_error" else ["source"]


def latest_attempts(record):
    return {phase: attempts[-1] for phase, attempts in record.get("outcomes", {}).items() if attempts}


def derive_status(record, probes=False):
    """design or ready until something is recorded; then fail, blocked or pass once a required phase decides
    it, otherwise in_progress. A case can never be set to pass by hand."""
    if record["status"] == "retired":
        return "retired"
    latest = latest_attempts(record)
    if not latest:
        return record["status"] if record["status"] in ("design", "ready") else "design"
    results = [latest.get(phase, {}).get("result") for phase in required_phases(record, probes)]
    for verdict in ("fail", "blocked"):
        if verdict in results:
            return verdict
    return "pass" if all(result == "pass" for result in results) else "in_progress"


def case_contract(path, record):
    contract = Path(path).parent / record.get("artifacts", {}).get("catalog_contract", "catalog-contract.json")
    return read(contract) if contract.is_file() else None


def probes_required(path, record):
    contract = case_contract(path, record)
    return bool(contract and contract.get("probes"))


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_outcome(path, phase, result=None, evidence=(), sqlcode=None, sqlstate=None, note=None, product=None,
                   product_version=None, options=None, snapshots=None, at=None):
    """Append one attempt to a case record and derive its status. The comparison result comes from compare
    itself; malformed or missing evidence is refused rather than recorded."""
    import datetime
    import os

    path = case_path(path)
    record = read(path)
    if not isinstance(record, dict) or not {"id", "status", "expected"} <= record.keys():
        raise ValueError(f"{path} is not a case record")
    if record["status"] == "retired":
        raise ValueError(f"{record['id']} is retired; nothing more is recorded")
    if phase not in PHASES:
        raise ValueError(f"Unknown phase {phase!r}; use one of {', '.join(PHASES)}")
    applicable = required_phases(record, probes=True) + ["cleanup"]
    if phase not in applicable:
        raise ValueError(f"{record['id']} expects {record['expected']['outcome']}; the {phase} phase does not apply")
    before = PREREQUISITE.get(phase)
    if before in applicable and latest_attempts(record).get(before, {}).get("result") != "pass":
        raise ValueError(f"Record a passing {before} phase before {phase}")
    stamp = at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp):
        raise ValueError("--at must be a UTC time such as 2026-10-10T14:30:00Z")
    files = [Path(p) for p in evidence]
    entry = {}
    if phase == "comparison":
        if result is not None:
            raise ValueError("The comparison result comes from compare; give --contract, --source and --replay instead of --result")
        contract_path, source_path, replay_path = (Path(p) for p in snapshots)
        contract = read(contract_path)
        if contract.get("case_id") != record["id"]:
            raise ValueError(f"{contract_path} belongs to {contract.get('case_id')}, not {record['id']}")
        compared = compare(contract, read(source_path), read(replay_path))
        result = "pass" if compared["status"] == "match" else "fail"
        entry["compare"] = {"status": compared["status"], "differences": len(compared["differences"]),
                            "failed_assertions": sum("failed_assertion" in d for d in compared["differences"])}
        files = [contract_path, source_path, replay_path] + files
    elif snapshots:
        raise ValueError("--contract, --source and --replay apply only to the comparison phase")
    if result not in VERDICTS:
        raise ValueError(f"--result must be one of {', '.join(VERDICTS)}")
    if sqlstate is not None and not re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
        raise ValueError("SQLSTATE is five digits or uppercase letters")
    expected = record["expected"]
    expects_error = phase == "source" and expected["outcome"] == "sql_error"
    if result == "pass" and sqlcode is not None:
        if expects_error and sqlcode >= 0:
            raise ValueError("A negative case passes only when the action fails; this SQLCODE reports success")
        if not expects_error and phase in ("source", "replay") and sqlcode < 0:
            raise ValueError(f"A {phase} pass cannot carry a negative SQLCODE")
    if expects_error and result == "pass":
        if sqlcode is None:
            raise ValueError("Record the SQLCODE of the intended failure (--sqlcode)")
        for name, observed in (("sqlcode", sqlcode), ("sqlstate", sqlstate)):
            if expected.get(name) is not None and observed is not None and observed != expected[name]:
                raise ValueError(f"The case expects {name.upper()} {expected[name]}, not {observed}")
    if phase == "extraction" and (product or product_version or options):
        if not (product and product_version):
            raise ValueError("Record the product with --product and --product-version")
        entry["product"] = {"name": product, "version": product_version, **({"options": options} if options else {})}
    if phase == "extraction" and result == "pass" and "product" not in entry:
        raise ValueError("An extraction pass needs --product and --product-version")
    if result == "pass" and not files:
        raise ValueError("A pass needs evidence (--evidence FILE): missing evidence is not a pass")
    if result != "pass" and not files and not note:
        raise ValueError("Explain a fail or blocked result with --evidence or --note")
    recorded = []
    for file in files:
        if not file.is_file() or file.stat().st_size == 0:
            raise ValueError(f"Evidence {file} is missing or empty")
        relative = Path(os.path.relpath(file.resolve(), path.parent.resolve())).as_posix()
        recorded.append({"path": relative, "sha256": file_digest(file)})
    entry = {"result": result, "recorded_at": stamp, **({"sqlcode": sqlcode} if sqlcode is not None else {}),
             **({"sqlstate": sqlstate} if sqlstate is not None else {}), **entry,
             **({"note": note} if note else {}), "evidence": recorded}
    record.setdefault("outcomes", {}).setdefault(phase, []).append(entry)
    record["status"] = derive_status(record, probes_required(path, record))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(dump(record), encoding="utf-8")
    temporary.replace(path)
    return record, entry


def case_status(path):
    """Derived status, latest result per required phase, the next phase and any evidence problems."""
    path = case_path(path)
    record = read(path)
    probes = probes_required(path, record)
    problems = []
    for phase, attempts in record.get("outcomes", {}).items():
        for item in attempts:
            for evidence in item["evidence"]:
                file = path.parent / evidence["path"]
                if not file.is_file():
                    problems.append(f"{phase}: evidence {evidence['path']} is missing")
                elif file_digest(file) != evidence["sha256"]:
                    problems.append(f"{phase}: evidence {evidence['path']} changed after it was recorded")
    derived = derive_status(record, probes)
    if derived != record["status"]:
        problems.append(f"status is {record['status']}, but the recorded outcomes give {derived}")
    latest = latest_attempts(record)
    phases = {phase: latest.get(phase, {}).get("result") for phase in required_phases(record, probes)}
    open_phase = next((p for p, r in phases.items() if r != "pass"), None)
    return {"case": record["id"], "path": paths.portable(path), "status": record["status"], "phases": phases,
            "next": open_phase if derived in ("design", "ready", "in_progress") else None, "problems": problems}


def find_cases(targets):
    found = []
    for target in map(Path, targets):
        if target.is_file():
            found.append(target)
        elif (target / "case.json").is_file():
            found.append(target / "case.json")
        elif target.is_dir():
            found.extend(sorted(target.rglob("case.json")))
        else:
            raise ValueError(f"{target}: no such case file or directory")
    if not found:
        raise ValueError("No case.json found")
    return found


def validate_case(record):
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        raise ValueError("Case schema validation requires requirements-dev.txt; use .venv/bin/python") from error
    validator = Draft202012Validator(read(paths.CASE_SCHEMA))
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
    if record.get("outcomes"):
        # Behavioral probes may or may not be required; that is in the catalog contract, not the record.
        if record["status"] not in {derive_status(record), derive_status(record, probes=True)}:
            raise ValueError(f"Status {record['status']} contradicts the recorded outcomes")
    elif record["status"] in ("in_progress", "pass", "fail", "blocked"):
        raise ValueError(f"Status {record['status']} needs outcomes recorded by tools/qa.py record; missing evidence is not a result")


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
    snap = commands.add_parser("snapshot", help="turn CSV exports of the catalog result sets into a compare snapshot")
    snap.add_argument("--contract", type=Path, required=True)
    snap.add_argument("--side", choices=["source", "replay"], required=True)
    snap.add_argument("--csv-dir", type=Path, help="directory with one QUERY-ID.csv per result set")
    snap.add_argument("--result", action="append", default=[], metavar="QUERY-ID=FILE", help="export for one result set; overrides --csv-dir")
    snap.add_argument("--delimiter", default=",", help="field delimiter; 'tab' for tab-separated exports")
    snap.add_argument("--null", default="", help="unquoted text the client writes for SQL NULL (default: an empty unquoted field)")
    snap.add_argument("--encoding", default="utf-8", help="encoding of the export files (default utf-8; a BOM is ignored)")
    snap.add_argument("--out", type=Path, help="write a new snapshot file; an existing file is never overwritten")
    rec = commands.add_parser("record", help="append one phase result with its evidence to a case record and derive its status")
    rec.add_argument("case", type=Path, help="case.json or the directory that holds it")
    rec.add_argument("--phase", choices=PHASES, required=True)
    rec.add_argument("--result", choices=VERDICTS, help="pass, fail or blocked; the comparison result comes from compare")
    rec.add_argument("--evidence", action="append", default=[], type=Path, metavar="FILE", help="file that shows the result; hashed and stored relative to the case")
    rec.add_argument("--sqlcode", type=int)
    rec.add_argument("--sqlstate")
    rec.add_argument("--note")
    rec.add_argument("--product", help="administration product that generated the DDL (extraction)")
    rec.add_argument("--product-version")
    rec.add_argument("--option", action="append", default=[], metavar="KEY=VALUE", help="product generation option (extraction)")
    rec.add_argument("--contract", type=Path, help="comparison: the case's catalog contract (default: the one beside the case)")
    rec.add_argument("--source", type=Path, help="comparison: source snapshot")
    rec.add_argument("--replay", type=Path, help="comparison: replay snapshot")
    rec.add_argument("--at", help="UTC time of the result, such as 2026-10-10T14:30:00Z (default: now)")
    state = commands.add_parser("status", help="report each case's status, phase results, next phase and evidence problems")
    state.add_argument("targets", nargs="+", type=Path, help="case.json files, case directories, bundles or campaigns")
    state.add_argument("--json", action="store_true")
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
        elif args.command == "snapshot":
            contract = read(args.contract)
            files = {}
            if args.csv_dir:
                files = {q["id"]: args.csv_dir / f"{q['id']}.csv" for q in contract.get("catalog", [])
                         if (args.csv_dir / f"{q['id']}.csv").is_file()}
            for item in args.result:
                query_id, separator, path = item.partition("=")
                if not separator or not query_id or not path:
                    raise ValueError(f"--result expects QUERY-ID=FILE, not {item!r}")
                files[query_id] = Path(path)
            delimiter = "\t" if args.delimiter in ("tab", "\\t") else args.delimiter
            result = snapshot(contract, args.side, files, args.null, delimiter, args.encoding)
            if args.out:
                with args.out.open("x", encoding="utf-8") as handle:
                    handle.write(dump(result))
            else:
                print(dump(result), end="")
            counts = ", ".join(f"{q}={len(rows)}" for q, rows in result["catalog"].items())
            print(f"{args.side} snapshot for {result['case_id']}: rows {counts}. Not compared yet; run compare.", file=sys.stderr)
        elif args.command == "record":
            snapshots = None
            if args.phase == "comparison" or args.source or args.replay or args.contract:
                if not (args.source and args.replay):
                    raise ValueError("The comparison phase needs --source and --replay snapshots")
                path = case_path(args.case)
                contract = args.contract or path.parent / read(path).get("artifacts", {}).get("catalog_contract", "catalog-contract.json")
                snapshots = (contract, args.source, args.replay)
            options = {}
            for item in args.option:
                key, separator, value = item.partition("=")
                if not separator or not key:
                    raise ValueError(f"--option expects KEY=VALUE, not {item!r}")
                options[key] = value
            record, entry = record_outcome(args.case, args.phase, args.result, args.evidence, args.sqlcode, args.sqlstate,
                                           args.note, args.product, args.product_version, options, snapshots, args.at)
            detail = f" ({entry['compare']['differences']} difference(s))" if "compare" in entry else ""
            print(f"{record['id']}: {args.phase} {entry['result']}{detail}; status {record['status']}.")
        elif args.command == "status":
            reports = [case_status(path) for path in find_cases(args.targets)]
            if args.json:
                print(dump(reports), end="")
            else:
                columns = list(dict.fromkeys(phase for report in reports for phase in report["phases"]))
                rows = [["CASE", "STATUS", *(c.upper() for c in columns), "NEXT"]]
                rows += [[r["case"], r["status"], *(r["phases"].get(c) or "-" for c in columns), r["next"] or "-"] for r in reports]
                widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
                for row in rows:
                    print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
                for report in reports:
                    for problem in report["problems"]:
                        print(f"PROBLEM {report['case']}: {problem}")
                totals = ", ".join(f"{k}={v}" for k, v in sorted(Counter(r["status"] for r in reports).items()))
                print(f"{len(reports)} case(s): {totals}. Statuses come only from recorded evidence; nothing was executed.")
            if any(r["problems"] for r in reports):
                return 2
            return 0 if all(r["status"] in ("pass", "retired") for r in reports) else 1
        elif args.command == "validate":
            import db2check
            profile = read(paths.EXAMPLE_PROFILE)
            options = db2check.Options.from_profile(profile, assume=["stogroup:" + profile["storage_group"]])
            for model in models().values():
                validate_model(model, kb())
                validate_profile(profile, model)
                _, valid = candidates(model)
                for selection in valid:
                    record, contract = make_case(model, selection, profile, "QA", 1)
                    # Every rendered case must also pass the IBM-rule checker used for agent-written SQL.
                    terminator = contract["statement_terminator"]
                    sql = f"CREATE DATABASE QASDB STOGROUP {profile['storage_group']};\n" if model.get("uses_database", True) else ""
                    sql += (f"--#SET TERMINATOR {terminator}\n" if terminator != ";" else "") + sql_file(record["setup_sql"] + record["action_sql"], "", terminator)
                    options.terminator = ";"
                    findings = [f for f in db2check.analyze(sql, options).findings if f.severity in ("error", "unsupported", "warning")]
                    if findings:
                        raise ValueError(f"{model['id']} {selection}: lint {findings[0].rule}: {findings[0].message}")
            print("Campaign model validation OK (static only; rendered SQL passes tools/ddl.py lint rules)")
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
