#!/usr/bin/env python3
"""Plan, check, measure, compare and bundle Db2 13 for z/OS DDL offline.

plan      structured request -> IBM-linked authoring plan
lint      static checks of any DDL script against encoded IBM rules
coverage  syntax-variety report against normalized KB clause IDs (+ baseline gate)
diff      semantic comparison of source DDL and product-generated DDL
bundle    QA bundle (catalog queries/assertions, cleanup, name map, case) from a lint-clean script
context   IBM-linked context for one normalized object
levels    Db2 13 function levels and the DDL syntax gated above a given APPLCOMPAT

None of these commands connects to Db2 or executes SQL.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import db2check
import paths
import qa


ROOT = paths.ROOT
SCHEMA = paths.REQUEST_SCHEMA


def validate_shape(value, schema, path="$"):
    """Validate the request schema's small subset without a runtime dependency."""
    kinds = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if "type" in schema and type(value) is not kinds[schema["type"]]:
        raise ValueError(f"{path}: expected {schema['type']}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: expected one of {schema['enum']}")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise ValueError(f"{path}: missing {sorted(missing)}")
        properties = schema.get("properties", {})
        unknown = value.keys() - properties.keys()
        if schema.get("additionalProperties") is False and unknown:
            raise ValueError(f"{path}: unknown fields {sorted(unknown)}")
        for key, item in value.items():
            item_schema = properties.get(key, schema.get("additionalProperties", {}))
            if isinstance(item_schema, dict):
                validate_shape(item, item_schema, f"{path}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            raise ValueError(f"{path}: unsupported item count")
        if schema.get("uniqueItems") and len({qa.digest(v) for v in value}) != len(value):
            raise ValueError(f"{path}: items must be unique")
        for index, item in enumerate(value):
            validate_shape(item, schema.get("items", {}), f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", len(value)):
            raise ValueError(f"{path}: unsupported string length")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{path}: invalid format")
    elif type(value) is int:
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ValueError(f"{path}: outside supported range")


def validate_request(request):
    validate_shape(request, qa.read(SCHEMA))
    ids = [obj["id"] for obj in request["objects"]]
    if len(ids) != len(set(ids)):
        raise ValueError("objects: duplicate instance ID")
    requirements = request.get("requirements", [])
    if len({r["id"] for r in requirements}) != len(requirements):
        raise ValueError("requirements: duplicate requirement ID")
    for requirement in requirements:
        if set(requirement["objects"]) - set(ids):
            raise ValueError(f"requirement {requirement['id']}: unknown object instance")
    nodes = [{"id": obj["id"], "depends_on": obj.get("depends_on", [])} for obj in request["objects"]]
    return [node["id"] for node in qa.order_nodes(nodes)]


def references(data, group):
    return {f"{name}.{item['id']}": item for name, obj in data["objects"].items() for item in obj[group]}


def supported_clauses(model, valid=None):
    covered = set(model["covers"])
    if valid is None:
        for options in model["dimensions"].values():
            for option in options.values():
                covered.update(option["covers"])
    else:
        for selection in valid:
            covered.update(qa.refs(model, selection))
    return covered


def filter_candidates(model, selection):
    for axis, values in selection.items():
        if axis not in model["dimensions"]:
            raise ValueError(f"Unknown dimension {axis!r}; available: {sorted(model['dimensions'])}")
        unknown = set(values) - model["dimensions"][axis].keys()
        if unknown:
            raise ValueError(f"Unknown values for {axis}: {sorted(unknown)}; available: {list(model['dimensions'][axis])}")
    raw, all_valid = qa.candidates(model)
    selected = lambda row: all(row[axis] in values for axis, values in selection.items())
    return [row for row in raw if selected(row)], [row for row in all_valid if selected(row)], len(all_valid)


def object_context(name, data):
    obj = data["objects"][name]
    source_ids = {s for group in ("clauses", "rules") for item in obj[group] for s in item["source_refs"]}
    result = {"normalized": copy.deepcopy(obj), "sources": {s: data["sources"][s] for s in sorted(source_ids)}}
    if name == "trigger":
        result["body_matrix"] = qa.read(paths.TRIGGER_BODY)
    return result


def make_plan(request, root=ROOT):
    order = validate_request(request)
    data, available_models = qa.kb(), qa.models()
    clauses, rules = references(data, "clauses"), references(data, "rules")
    strategy = request.get("strategy", "pairwise")
    profile_path = root / request["profile"] if request.get("profile") else None
    profile, profile_error = None, None
    if profile_path:
        try:
            profile = qa.read(profile_path)
        except (OSError, ValueError) as error:
            profile_error = str(error)
    registry = {o["id"]: o for o in qa.read(paths.OBJECT_REGISTRY)["objects"]}
    plans, gaps, context_names = [], [], set()

    def gap(instance, code, message, **details):
        item = {"object_instance": instance, "code": code, "message": message, **details}
        gaps.append(item)
        return item

    for index, obj in enumerate(request["objects"], 1):
        name, instance = obj["object"], obj["id"]
        requested_clauses, requested_rules = set(obj.get("clause_refs", [])), set(obj.get("rule_refs", []))
        for group, requested, known in (("clause", requested_clauses, clauses), ("rule", requested_rules, rules)):
            for ref in sorted(requested - known.keys()):
                gap(instance, f"unknown_{group}_reference", f"No normalized {group} has ID {ref!r}. Correct the ID or research and normalize it.", reference=ref)
            context_names.update(ref.split(".", 1)[0] for ref in requested & known.keys())
        if name in data["objects"]:
            context_names.add(name)
        else:
            gap(instance, "object_not_normalized", f"{name!r} has no normalized IBM syntax entry.", registry_status=registry.get(name, {}).get("status", "unknown"))

        candidates = []
        for model in available_models.values():
            if model["object"] == name:
                covered = supported_clauses(model)
                candidates.append({"id": model["id"], "matched_clause_refs": sorted(requested_clauses & covered),
                                   "unmodeled_clause_refs": sorted(requested_clauses - covered),
                                   "dimensions": {axis: list(values) for axis, values in model["dimensions"].items()}})
        current = {"id": instance, "object": name, "depends_on": obj.get("depends_on", []),
                   "candidate_models": candidates, "chosen_model": obj.get("model"), "selection": obj.get("select", {}),
                   "offline_build_argv": None}
        plans.append(current)
        if obj.get("depends_on"):
            gap(instance, "bespoke_dependency_graph", "The request graph is ordered, but separate campaign builds do not connect object instances. Author the shared names, enforcing indexes, placement and cleanup in one model or case before building this stack.")
        if not obj.get("model"):
            gap(instance, "model_selection_required", "Choose an exact bounded model and dimension values, or author a source-reviewed case. A clause match does not establish all its syntax branches.")
            continue
        model = available_models.get(obj["model"])
        if model is None:
            gap(instance, "unknown_model", f"No executable model has ID {obj['model']!r}.")
            continue
        if model["object"] != name:
            gap(instance, "model_object_mismatch", f"Model {model['id']} creates {model['object']}, not {name}.")
            continue
        current["model_sha256"] = qa.digest(model)
        current["model_scope"] = {"evidence": model.get("evidence"), "minimum_function_level": model["minimum_function_level"],
                                  "minimum_applcompat": model["minimum_applcompat"], "rule_refs": model["rule_refs"],
                                  "constraints": model["constraints"], "dependencies": [{"id": n["id"], "role": n["role"], "depends_on": n["depends_on"]} for n in qa.order_nodes(model["nodes"])]}
        context_names.update(ref.split(".", 1)[0] for ref in model["covers"] + model["rule_refs"])
        try:
            raw, valid, full_count = filter_candidates(model, obj.get("select", {}))
        except ValueError as error:
            gap(instance, "invalid_selection", str(error))
            continue
        if not valid:
            gap(instance, "infeasible_selection", "No modeled positive combination satisfies these selections.",
                violated_constraints=sorted({c for row in raw for c in qa.violations(model, row)}))
            continue
        chosen, coverage = qa.select_cases(valid, strategy, request.get("budget"))
        coverage["full_model_valid_combinations"] = full_count
        current["coverage_preview"] = coverage
        current["selected_combinations"] = chosen
        current["selected_sql_fragments"] = {
            axis: {value: option["sql"] for value, option in options.items() if any(row[axis] == value for row in chosen)}
            for axis, options in model["dimensions"].items()}
        covered = supported_clauses(model, chosen)
        current["clause_paths_in_preview"] = sorted(covered)
        for ref in sorted((requested_clauses & clauses.keys()) - covered):
            gap(instance, "clause_outside_preview", f"No selected case has a compiler path tagged {ref!r}. Review the model, selected values and budget.", reference=ref)
        for ref in sorted((requested_rules & rules.keys()) - set(model["rule_refs"])):
            gap(instance, "rule_outside_model", f"Model {model['id']} does not cite requested rule {ref!r}. Review or extend its constraints and evidence.", reference=ref)
        if not coverage["complete"]:
            gap(instance, "coverage_budget", "The case budget leaves modeled interactions uncovered; inspect coverage_preview.uncovered_interactions.")
        negative_ready = True
        if request.get("negative", False):
            negatives = []
            for constraint in model["constraints"]:
                isolated = next((row for row in raw if qa.violations(model, row) == [constraint["id"]]), None)
                if isolated is None:
                    gap(instance, "negative_not_isolatable", f"Constraint {constraint['id']} has no isolated negative under these filters. Broaden the filters or use a separate request.")
                    negative_ready = False
                else:
                    negatives.append({"constraint": constraint["id"], "selection": isolated, "sqlcode": None, "sqlstate": None})
            current["negative_preview"] = negatives
        profile_ready = False
        if profile_path is None:
            gap(instance, "profile_missing", "Record an environment profile, or deliberately select the example unverified profile for offline authoring.")
        elif profile_error:
            gap(instance, "profile_unreadable", profile_error)
        else:
            try:
                qa.validate_profile(profile, model)
                profile_ready = True
            except (ValueError, KeyError, TypeError) as error:
                gap(instance, "profile_incompatible", str(error))
        # A shared requested topology cannot be realized by independent bundles.
        connected = bool(obj.get("depends_on")) or any(instance in other.get("depends_on", []) for other in request["objects"])
        if profile_ready and negative_ready and not connected:
            run = f"{request.get('run_prefix', 'QA')}{index:02d}"
            out = root / request.get("output_root", f"generated/{request['id']}") / instance
            argv = ["python3", str(ROOT / "tools/qa.py"), "build", "--model", model["id"], "--profile", str(profile_path),
                    "--run", run, "--strategy", strategy, "--out", str(out)]
            if "budget" in request:
                argv.extend(["--budget", str(request["budget"])])
            if request.get("negative", False):
                argv.append("--negative")
            for axis in model["dimensions"]:
                for value in model["dimensions"][axis]:
                    if value in obj.get("select", {}).get(axis, []):
                        argv.extend(["--set", f"{axis}={value}"])
            current["offline_build_argv"] = argv

    for requirement in request.get("requirements", []):
        for instance in requirement["objects"]:
            gap(instance, "freeform_requirement_review", "Free-form requirements are preserved for the agent; the planner does not infer that model clauses satisfy their meaning.", requirement=copy.deepcopy(requirement))
    for current in plans:
        current["gap_codes"] = sorted({g["code"] for g in gaps if g["object_instance"] == current["id"]})
        if current["gap_codes"]:
            current["offline_build_argv"] = None
        if current.get("coverage_preview", {}).get("selected_cases", 0) + len(current.get("negative_preview", [])) > 999:
            gap(current["id"], "campaign_size_limit", "The preview exceeds the compiler's 999-case limit. Add a budget or split the requested family.")
            current["gap_codes"].append("campaign_size_limit")
            current["offline_build_argv"] = None
    contexts = {name: object_context(name, data) for name in sorted(context_names)}
    research = [{"object_instance": item["object_instance"], "gap_code": item["code"], "task": item["message"],
                 "source_ids": sorted(contexts.get(next(p["object"] for p in plans if p["id"] == item["object_instance"]), {}).get("sources", {}))}
                for item in gaps]
    return {"schema_version": "1.0.0", "id": request["id"], "status": "design", "review_status": "agent_review_required",
            "intent": request["intent"], "intent_interpretation": "The intent is preserved verbatim, not parsed or certified. The agent must map every requirement to exact selections or an explicit gap.",
            "request_sha256": qa.digest(request), "kb_sha256": qa.digest(data), "request": copy.deepcopy(request),
            "tool_sha256": {name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest() for name in ("ddl.py", "qa.py")},
            "request_schema_sha256": qa.digest(qa.read(SCHEMA)),
            "structured_scope_has_gaps": bool(gaps), "dependency_order": order,
            "environment": {"profile": str(profile_path) if profile_path else None,
                            "verified": profile.get("verified", False) if isinstance(profile, dict) else False,
                            "execution_status": "not_executed", "profile_sha256": qa.digest(profile) if profile is not None else None},
            "objects": plans, "gaps": gaps, "research_tasks": research, "context": contexts,
            "review_obligations": [
                "Read every selected IBM syntax diagram, clause restriction, default and catalog definition; source links are traceability, not a fresh documentation review.",
                "A compiler path tagged with a clause does not cover all branches, values, cross-clause restrictions or interpretations of the request.",
                "Review exact SQL fragments, statement terminators, body literal whitespace, formatting and byte/character length requirements against the requested client and encoding.",
                "Resolve dependencies, enforcing indexes, implicit objects, names and cleanup ownership for a bespoke schema.",
                "Record actual function level, APPLCOMPAT, CURRENT RULES, subsystem defaults, active pools, storage and privileges before execution; unverified profiles permit offline design only.",
                "Retain source acceptance, actual product-generated DDL, product options, replay execution and catalog/behavior evidence separately. Static checks do not prove Db2 syntax acceptance or product correctness."]}


def _pairs(values, flag):
    result = {}
    for value in values or []:
        source, separator, target = value.partition("=")
        if not separator or not source or not target:
            raise ValueError(f"{flag} expects SOURCE=TARGET, not {value!r}")
        result[source.strip().upper()] = target.strip().upper()
    return result


def _read_sql(path):
    if str(path) == "-":
        return sys.stdin.read()
    # Bytes, not text mode: universal-newline translation would alter CR LF.
    return Path(path).read_bytes().decode("utf-8")


def _options(args, terminator=None):
    profile = qa.read(args.profile) if getattr(args, "profile", None) else None
    return db2check.Options.from_profile(
        profile, terminator=terminator or args.terminator, assume=list(getattr(args, "assume", []) or []),
        max_line=getattr(args, "max_line", None), allow_placeholders=getattr(args, "allow_placeholders", False)), profile


def _baseline(name):
    if not name:
        return None
    return db2check.load_baseline(name)


def _print_findings(path, report, allow_unsupported):
    rules = report.rules
    for finding in sorted(report.findings, key=lambda f: (f.line, f.rule)):
        sources = ",".join(rules[finding.rule]["source_refs"])
        print(f"{path}:{finding.line}: {finding.severity}: {finding.rule}: {finding.message} [{sources}]")
    summary = report.as_dict(allow_unsupported)
    counts = ", ".join(f"{k}={v}" for k, v in sorted(summary["counts"].items())) or "no findings"
    print(f"{summary['status'].upper()}: {summary['statements']} statements; {counts}. Static checks only; Db2 acceptance is not proven.")


def _print_diff(result):
    """One line per entry that needs review; equivalent-default entries stay in the JSON output."""
    def show(value):
        return "-" if value is None else value if isinstance(value, str) else json.dumps(value)
    for d in result["differences"]:
        if d["status"] == "equivalent-default":
            continue
        where = d["object"] + (f" {d['attribute']}" if d.get("attribute") else "")
        if d["status"] == "not-compared":
            text = f"{d['side']}: {d['detail']}"
        elif "source_only" in d:
            text = f"source only {show(d['source_only'])}, target only {show(d['target_only'])}"
        elif "source" in d or "target" in d:
            note = d.get("detail") or (f"default from {d['default_from']}" if d.get("default_from") else None)
            text = f"{show(d.get('source'))} -> {show(d.get('target'))}" + (f" ({note})" if note else "")
        else:
            text = d.get("detail") or ""
        print(f"{d['status']}: {where}: {text}")
    counts = ", ".join(f"{k}={v}" for k, v in sorted(result["counts"].items())) or "no differences"
    hidden = result["counts"].get("equivalent-default", 0)
    print(f"{result['status'].upper()}: {counts}." + (f" The {hidden} equivalent-default entries are listed only in JSON output." if hidden else "")
          + " Parsed DDL only; execution and catalog comparison still decide.")


def _levels(applcompat=None):
    data = db2check.function_level_data()
    lines = [f"Db2 13 function levels (reviewed {data['reviewed']}; source kb/data/db2z13-function-levels.json):"]
    for level in data["levels"]:
        notes = "; ".join(n["id"] for n in level["ddl_notes"])
        lines.append(f"  {level['id']} ({level['release']}): {notes}")
    for level in data["announced_levels"]:
        lines.append(f"  {level['id']} (announced only): {level['evidence']}")
    result = {"levels": data["levels"], "announced_levels": data["announced_levels"]}
    if applcompat:
        key = db2check.level_key(applcompat)
        if key is None:
            raise ValueError(f"{applcompat!r} is not a V10R1/V11R1/V12R1Mnnn/V13R1Mnnn level")
        above = [g for g in data["applcompat_gates"] if db2check.level_key(g["applcompat"]) > key]
        defaults = [b for b in data["behavior_changes"] if b.get("applcompat") and db2check.level_key(b["applcompat"]) <= key]
        result.update(applcompat=applcompat, unavailable=above, behavior_in_effect=defaults)
        lines.append(f"Gated syntax NOT available at APPLCOMPAT {applcompat}:")
        lines.extend(f"  {g['applcompat']} {g['id']}: {', '.join(g['statements'])}: {g['syntax']}" for g in above)
        lines.append(f"Default/behavior changes in effect at {applcompat}:")
        lines.extend(f"  {b['applcompat']} {b['id']}: {b['summary']}" for b in defaults)
    result["text"] = lines
    return result


def _add_common(command, profile=True):
    command.add_argument("--terminator", default=";", help="outer statement terminator (also honors --#SET TERMINATOR x)")
    command.add_argument("--assume", action="append", default=[], metavar="KIND:NAME",
                         help="declare a pre-existing object, e.g. table:SCHEMA.T1, database:DB1, type:SCHEMA.MONEY")
    if profile:
        command.add_argument("--profile", type=Path, help="environment profile (function level, APPLCOMPAT, subsystem parameters)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="export a deterministic request plan; does not generate or execute SQL")
    plan.add_argument("--request", type=Path, required=True)
    plan.add_argument("--out", type=Path, help="write a new plan file; an existing file is never overwritten")
    plan.add_argument("--require-modeled", action="store_true", help="return 1 when the plan has explicit gaps, while still emitting the plan")
    context = commands.add_parser("context", help="export the existing full IBM-linked object and model context")
    context.add_argument("object")
    lint = commands.add_parser("lint", help="static Db2 13 for z/OS checks; exit 0 pass, 1 findings, 2 bad input")
    lint.add_argument("sql", help="SQL script path, or - for stdin")
    _add_common(lint)
    lint.add_argument("--max-line", type=int, help="fail lines longer than this many characters (e.g. 72 for fixed records)")
    lint.add_argument("--allow-placeholders", action="store_true", help="report {{TOKEN}} placeholders as notices (templates only)")
    lint.add_argument("--allow-unsupported", action="store_true", help="do not fail on constructs the checker does not model")
    lint.add_argument("--json", action="store_true")
    cover = commands.add_parser("coverage", help="syntax-variety report; with --baseline exit 1 when requirements are unmet")
    cover.add_argument("sql")
    _add_common(cover)
    cover.add_argument("--baseline", help="baseline id from qa/variety-baseline.json (core, extended) or a file")
    cover.add_argument("--json", action="store_true")
    compare = commands.add_parser("diff", help="semantic DDL diff; exit 0 match, 1 mismatch, 3 unresolved, 2 bad input")
    compare.add_argument("source")
    compare.add_argument("target")
    compare.add_argument("--source-terminator", default=";")
    compare.add_argument("--target-terminator", default=";")
    compare.add_argument("--map", type=Path, help="name-map.json from a bundle (schemas/databases/objects)")
    compare.add_argument("--map-schema", action="append", default=[], metavar="SRC=TGT")
    compare.add_argument("--map-database", action="append", default=[], metavar="SRC=TGT")
    compare.add_argument("--profile", type=Path, help="resolves subsystem-parameter defaults such as DPSEGSZ, PADIX and MIXED")
    compare.add_argument("--text", action="store_true", help="print one line per entry that needs review instead of JSON")
    package = commands.add_parser("bundle", help="derive a QA bundle from a lint-clean script; never executes SQL")
    package.add_argument("sql")
    _add_common(package)
    package.add_argument("--run", required=True, help="2-8 uppercase characters identifying this bundle")
    package.add_argument("--out", type=Path, required=True, help="new output directory (never overwritten)")
    package.add_argument("--replay-schema", action="append", default=[], metavar="SRC=TGT")
    package.add_argument("--replay-database", action="append", default=[], metavar="SRC=TGT")
    levels = commands.add_parser("levels", help="list function levels, or what is gated above --applcompat")
    levels.add_argument("--applcompat", help="for example V13R1M500 or V12R1M510")
    levels.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "levels":
            result = _levels(args.applcompat)
            if args.json:
                print(qa.dump(result), end="")
            else:
                for line in result["text"]:
                    print(line)
            return 0
        if args.command == "context":
            print(qa.dump(qa.context_pack(args.object)), end="")
            return 0
        if args.command == "lint":
            options, _ = _options(args)
            report = db2check.analyze(_read_sql(args.sql), options)
            if args.json:
                print(qa.dump(report.as_dict(args.allow_unsupported)), end="")
            else:
                _print_findings(args.sql, report, args.allow_unsupported)
            return 1 if report.failed(args.allow_unsupported) else 0
        if args.command == "coverage":
            options, _ = _options(args)
            report = db2check.analyze(_read_sql(args.sql), options)
            result = db2check.coverage(report, _baseline(args.baseline))
            if args.json:
                print(qa.dump(result), end="")
            else:
                print(db2check.coverage_text(result))
            return 1 if args.baseline and not result["baseline"]["complete"] else 0
        if args.command == "diff":
            profile = qa.read(args.profile) if args.profile else None
            names = db2check.NameMap.load(qa.read(args.map)) if args.map else db2check.NameMap()
            names.schemas.update(_pairs(args.map_schema, "--map-schema"))
            names.databases.update(_pairs(args.map_database, "--map-database"))
            left = db2check.analyze(_read_sql(args.source), db2check.Options(terminator=args.source_terminator, allow_placeholders=True))
            right = db2check.analyze(_read_sql(args.target), db2check.Options(terminator=args.target_terminator, allow_placeholders=True))
            result = db2check.diff(left, right, names, profile)
            result["parse_findings"] = {"source": [f.as_dict(left.rules) for f in left.findings if f.severity == "unsupported"],
                                        "target": [f.as_dict(right.rules) for f in right.findings if f.severity == "unsupported"]}
            if args.text:
                _print_diff(result)
            else:
                print(qa.dump(result), end="")
            return {"match": 0, "mismatch": 1, "unresolved": 3}[result["status"]]
        if args.command == "bundle":
            options, profile = _options(args)
            text = _read_sql(args.sql)
            report = db2check.analyze(text, options)
            names = db2check.NameMap(_pairs(args.replay_schema, "--replay-schema"), _pairs(args.replay_database, "--replay-database"))
            files = db2check.bundle(report, text, names, args.run, profile)
            args.out.mkdir(parents=True, exist_ok=False)
            for name, content in files.items():
                (args.out / name).write_bytes(content.encode("utf-8"))
            print(qa.dump({"output": str(args.out), "files": sorted(files), "status": "design", "executed": False}), end="")
            return 0
        result = make_plan(qa.read(args.request))
        if args.out:
            with args.out.open("x", encoding="utf-8") as handle:
                handle.write(qa.dump(result))
        else:
            print(qa.dump(result), end="")
        return 1 if args.require_modeled and result["structured_scope_has_gaps"] else 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
