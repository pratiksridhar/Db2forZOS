#!/usr/bin/env python3
"""Query the normalized Db2 for z/OS CREATE DDL knowledge base."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPOSITORY_ROOT / "kb" / "data" / "db2z13-create-ddl.json"
DEFAULT_TRIGGER_BODY_DATA = (
    REPOSITORY_ROOT / "kb" / "data" / "db2z13-trigger-body-statements.json"
)


def load_data(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as error:
        raise SystemExit(f"KB data file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid KB JSON at {path}:{error.lineno}:{error.colno}: {error.msg}") from error

    if not isinstance(data.get("objects"), dict) or not isinstance(data.get("sources"), dict):
        raise SystemExit(f"KB data file has no normalized objects/sources maps: {path}")
    return data


def load_trigger_body_data(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as error:
        raise SystemExit(f"Trigger body data file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"Invalid trigger body JSON at {path}:{error.lineno}:{error.colno}: {error.msg}"
        ) from error

    if not isinstance(data.get("statement_syntax"), dict):
        raise SystemExit(f"Trigger body data has no statement_syntax map: {path}")
    if not isinstance(data.get("basic", {}).get("statements"), list):
        raise SystemExit(f"Trigger body data has no basic statement list: {path}")
    if not isinstance(data.get("advanced", {}).get("direct_statements"), list):
        raise SystemExit(f"Trigger body data has no advanced direct statement list: {path}")
    return data


def get_object(data: dict[str, Any], name: str) -> dict[str, Any]:
    key = name.lower()
    objects = data["objects"]
    if key not in objects:
        choices = ", ".join(sorted(objects))
        raise SystemExit(f"Unknown object {name!r}. Choose one of: {choices}")
    return objects[key]


def emit_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False))


def print_rows(headers: list[str], rows: Iterable[Iterable[Any]]) -> None:
    materialized = [[str(value) for value in row] for row in rows]
    if not materialized:
        print("No matches.")
        return
    widths = [len(header) for header in headers]
    for row in materialized:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in materialized:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def source_rows(data: dict[str, Any], source_ids: Iterable[str]) -> list[dict[str, str]]:
    return [
        {"id": source_id, **data["sources"][source_id]}
        for source_id in source_ids
        if source_id in data["sources"]
    ]


def command_objects(data: dict[str, Any], args: argparse.Namespace) -> None:
    result = []
    for key, value in data["objects"].items():
        result.append(
            {
                "id": key,
                "display_name": value["display_name"],
                "statements": value["statements"],
                "clause_count": len(value["clauses"]),
                "rule_count": len(value["rules"]),
                "chapter": value["chapter"],
            }
        )
    if args.as_json:
        emit_json(result)
        return
    print_rows(
        ["OBJECT", "STATEMENTS", "CLAUSES", "RULES", "CHAPTER"],
        (
            (
                item["display_name"],
                "; ".join(item["statements"]),
                item["clause_count"],
                item["rule_count"],
                item["chapter"],
            )
            for item in result
        ),
    )


def command_clauses(data: dict[str, Any], args: argparse.Namespace) -> None:
    obj = get_object(data, args.object)
    clauses = obj["clauses"]
    if args.tag:
        wanted = args.tag.lower()
        clauses = [item for item in clauses if wanted in {tag.lower() for tag in item["tags"]}]
    if args.as_json:
        emit_json(clauses)
        return
    print_rows(
        ["ID", "REQUIRED", "SYNTAX", "DEFAULT", "TAGS"],
        (
            (
                item["id"],
                item["required"],
                item["syntax"],
                item["default"],
                ",".join(item["tags"]),
            )
            for item in clauses
        ),
    )


def command_show(data: dict[str, Any], args: argparse.Namespace) -> None:
    obj = get_object(data, args.object)
    for kind in ("clauses", "rules"):
        for item in obj[kind]:
            if item["id"].lower() != args.item.lower():
                continue
            result = {
                "object": args.object.lower(),
                "kind": kind[:-1],
                **item,
                "sources": source_rows(data, item["source_refs"]),
            }
            if args.as_json:
                emit_json(result)
                return
            print(f"{obj['display_name']} {kind[:-1]}: {item['id']}")
            if kind == "clauses":
                print(f"syntax:   {item['syntax']}")
                print(f"required: {item['required']}")
                print(f"values:   {item['values']}")
                print(f"default:  {item['default']}")
                print(f"summary:  {item['summary']}")
            else:
                print(f"kind:     {item['kind']}")
                print(f"clauses:  {', '.join(item['clauses']) or '(object-wide)'}")
                print(f"rule:     {item['text']}")
            print(f"tags:     {', '.join(item['tags'])}")
            print("sources:")
            for source in result["sources"]:
                print(f"  {source['id']}: {source['url']}")
            return
    available = sorted(item["id"] for kind in ("clauses", "rules") for item in obj[kind])
    raise SystemExit(
        f"Unknown clause/rule {args.item!r} for {args.object!r}. "
        f"Available IDs: {', '.join(available)}"
    )


def command_rules(data: dict[str, Any], args: argparse.Namespace) -> None:
    obj = get_object(data, args.object)
    rules = obj["rules"]
    if args.tag:
        wanted = args.tag.lower()
        rules = [item for item in rules if wanted in {tag.lower() for tag in item["tags"]}]
    if args.as_json:
        emit_json(rules)
        return
    print_rows(
        ["ID", "KIND", "CLAUSES", "RULE", "TAGS"],
        (
            (
                item["id"],
                item["kind"],
                ",".join(item["clauses"]) or "(object-wide)",
                item["text"],
                ",".join(item["tags"]),
            )
            for item in rules
        ),
    )


def command_dimensions(data: dict[str, Any], args: argparse.Namespace) -> None:
    obj = get_object(data, args.object)
    dimensions = obj["dimensions"]
    if args.as_json:
        emit_json(dimensions)
        return
    for item in dimensions:
        print(f"- {item}")


def searchable_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(searchable_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(searchable_text(item) for item in value.values())
    return str(value)


def command_search(data: dict[str, Any], args: argparse.Namespace) -> None:
    needle = args.query.casefold()
    matches: list[dict[str, Any]] = []
    for object_name, obj in data["objects"].items():
        for kind in ("clauses", "rules"):
            for item in obj[kind]:
                if needle in searchable_text(item).casefold():
                    matches.append(
                        {
                            "object": object_name,
                            "kind": kind[:-1],
                            "id": item["id"],
                            "text": item.get("summary", item.get("text", "")),
                        }
                    )
        for dimension in obj["dimensions"]:
            if needle in dimension.casefold():
                matches.append(
                    {
                        "object": object_name,
                        "kind": "dimension",
                        "id": dimension.split(":", 1)[0],
                        "text": dimension,
                    }
                )
    for source_id, source in data["sources"].items():
        if needle in searchable_text(source).casefold() or needle in source_id.casefold():
            matches.append(
                {
                    "object": "-",
                    "kind": "source",
                    "id": source_id,
                    "text": source["title"],
                }
            )
    if args.as_json:
        emit_json(matches)
        return
    print_rows(
        ["OBJECT", "KIND", "ID", "MATCH"],
        ((item["object"], item["kind"], item["id"], item["text"]) for item in matches),
    )


def command_sources(data: dict[str, Any], args: argparse.Namespace) -> None:
    rows = [{"id": key, **value} for key, value in data["sources"].items()]
    if args.as_json:
        emit_json(rows)
        return
    print_rows(
        ["SOURCE ID", "TITLE", "URL"],
        ((item["id"], item["title"], item["url"]) for item in rows),
    )


def trigger_statement_rows(body: dict[str, Any], category: str) -> list[dict[str, Any]]:
    syntax_map = body["statement_syntax"]
    if category == "basic":
        rows = body["basic"]["statements"]
    elif category == "direct":
        rows = body["advanced"]["direct_statements"]
    elif category == "nested":
        rows = body["advanced"]["sql_procedure_statement_matrix"]["allowed"]
    elif category == "excluded":
        return [
            {
                "id": statement,
                "activation_times": [],
                "trigger_supported": False,
                "syntax": "(excluded by the IBM SQL-trigger-body matrix)",
                "restrictions": ["Not supported in an SQL trigger body."],
                "source_refs": ["ibm-sql-procedure-statement"],
            }
            for statement in body["advanced"]["sql_procedure_statement_matrix"]["excluded"]
        ]
    elif category == "controls":
        return [
            {
                "activation_times": [],
                "restrictions": [],
                **row,
            }
            for row in body["advanced"]["control_statements"]
        ]
    elif category == "ddl":
        result = []
        for row in body["advanced"]["repository_ddl_subset"]:
            syntax = syntax_map.get(row["id"], {})
            supported = row["status"] == "supported nested row"
            result.append(
                {
                    "trigger_supported": supported,
                    "syntax": syntax.get("syntax", row["statement"]),
                    "restrictions": row.get("restrictions", [] if supported else [row["status"]]),
                    **row,
                }
            )
        return result
    elif category == "syntax":
        return [
            {
                "id": statement_id,
                "activation_times": [],
                "trigger_supported": None,
                "restrictions": [],
                **details,
            }
            for statement_id, details in syntax_map.items()
        ]
    else:  # pragma: no cover - argparse constrains this value
        raise SystemExit(f"Unknown trigger statement category: {category}")

    result = []
    for row in rows:
        statement_id = row["id"]
        syntax = syntax_map.get(statement_id, {})
        result.append(
            {
                "trigger_supported": True,
                **syntax,
                **row,
                "restrictions": [
                    *syntax.get("restrictions", []),
                    *row.get("restrictions", []),
                ],
                "source_refs": list(
                    dict.fromkeys(
                        [*syntax.get("source_refs", []), *row.get("source_refs", [])]
                    )
                ),
            }
        )
    return result


def normalize_activation(value: str) -> str:
    normalized = value.replace("_", " ").upper()
    if normalized not in {"BEFORE", "AFTER", "INSTEAD OF"}:
        raise argparse.ArgumentTypeError("choose BEFORE, AFTER, or INSTEAD OF")
    return normalized


def command_trigger_statements(data: dict[str, Any], args: argparse.Namespace) -> None:
    body = load_trigger_body_data(args.trigger_body_data.resolve())
    rows = trigger_statement_rows(body, args.category)

    if args.activation:
        rows = [row for row in rows if args.activation in row.get("activation_times", [])]
    if args.statement:
        wanted = args.statement.casefold()
        rows = [row for row in rows if row["id"].casefold() == wanted]

    if args.as_json:
        emit_json(rows)
        return

    print_rows(
        ["ID", "ACTIVATION", "SUPPORTED", "SYNTAX", "RESTRICTIONS"],
        (
            (
                row["id"],
                "/".join(row.get("activation_times", [])) or "context-dependent",
                (
                    "yes"
                    if row.get("trigger_supported") is True
                    else "no"
                    if row.get("trigger_supported") is False
                    else "see matrix"
                ),
                row.get("syntax", "(see IBM statement syntax)"),
                "; ".join(row.get("restrictions", [])) or "-",
            )
            for row in rows
        ),
    )


def add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help=f"normalized KB JSON (default: {DEFAULT_DATA})",
    )
    parser.add_argument(
        "--trigger-body-data",
        type=Path,
        default=DEFAULT_TRIGGER_BODY_DATA,
        help=f"trigger body matrix JSON (default: {DEFAULT_TRIGGER_BODY_DATA})",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    objects = commands.add_parser("objects", help="list modeled objects")
    add_json_option(objects)
    objects.set_defaults(handler=command_objects)

    clauses = commands.add_parser("clauses", help="list clauses for an object")
    clauses.add_argument("object")
    clauses.add_argument("--tag", help="require an exact tag")
    add_json_option(clauses)
    clauses.set_defaults(handler=command_clauses)

    show = commands.add_parser("show", help="show one clause or rule by ID")
    show.add_argument("object")
    show.add_argument("item")
    add_json_option(show)
    show.set_defaults(handler=command_show)

    rules = commands.add_parser("rules", help="list cross-clause rules for an object")
    rules.add_argument("object")
    rules.add_argument("--tag", help="require an exact tag")
    add_json_option(rules)
    rules.set_defaults(handler=command_rules)

    dimensions = commands.add_parser("dimensions", help="list suggested coverage dimensions")
    dimensions.add_argument("object")
    add_json_option(dimensions)
    dimensions.set_defaults(handler=command_dimensions)

    search = commands.add_parser("search", help="search clauses, rules, dimensions, and sources")
    search.add_argument("query")
    add_json_option(search)
    search.set_defaults(handler=command_search)

    sources = commands.add_parser("sources", help="list official IBM sources")
    add_json_option(sources)
    sources.set_defaults(handler=command_sources)

    trigger_statements = commands.add_parser(
        "trigger-statements",
        help="list basic, advanced, nested, excluded, control, repository DDL, or syntax body rows",
    )
    trigger_statements.add_argument(
        "category",
        choices=("basic", "direct", "nested", "excluded", "controls", "ddl", "syntax"),
    )
    trigger_statements.add_argument(
        "--activation",
        type=normalize_activation,
        help="filter by BEFORE, AFTER, or INSTEAD OF (also accepts INSTEAD_OF)",
    )
    trigger_statements.add_argument("--statement", help="filter by exact statement ID")
    add_json_option(trigger_statements)
    trigger_statements.set_defaults(handler=command_trigger_statements)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    data = load_data(args.data.resolve())
    args.handler(data, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
