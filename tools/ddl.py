#!/usr/bin/env python3
"""Turn an agent-authored DDL request into an IBM-linked, offline authoring plan."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import qa


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "kb/authoring/request.schema.json"


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
        result["body_matrix"] = qa.read(ROOT / "kb/data/db2z13-trigger-body-statements.json")
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
    registry = {o["id"]: o for o in qa.read(ROOT / "kb/agent/object-registry.json")["objects"]}
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="export a deterministic request plan; does not generate or execute SQL")
    plan.add_argument("--request", type=Path, required=True)
    plan.add_argument("--out", type=Path, help="write a new plan file; an existing file is never overwritten")
    plan.add_argument("--require-modeled", action="store_true", help="return 1 when the plan has explicit gaps, while still emitting the plan")
    context = commands.add_parser("context", help="export the existing full IBM-linked object and model context")
    context.add_argument("object")
    args = parser.parse_args(argv)
    try:
        if args.command == "context":
            print(qa.dump(qa.context_pack(args.object)), end="")
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
