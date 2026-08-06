#!/usr/bin/env python3
"""Query the agent-first Db2 for z/OS DDL generation layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPOSITORY_ROOT / "kb" / "agent"


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as error:
        raise SystemExit(f"Agent JSON file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid agent JSON at {path}:{error.lineno}:{error.colno}: {error.msg}") from error


def emit_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


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


def command_registry(args: argparse.Namespace) -> None:
    registry = load_json(AGENT_ROOT / "object-registry.json")
    if args.as_json:
        emit_json(registry)
        return
    print_rows(
        ["OBJECT", "STATUS", "SPEC", "ROLE"],
        (
            (
                obj["id"],
                obj["status"],
                obj.get("spec", ""),
                obj.get("default_agent_role", ""),
            )
            for obj in registry["objects"]
        ),
    )


def command_spec(args: argparse.Namespace) -> None:
    path = AGENT_ROOT / "specs" / f"{args.object}.json"
    spec = load_json(path)
    if args.as_json:
        emit_json(spec)
        return
    print(f"object: {spec['object']}")
    print(f"status: {spec['status']}")
    print(f"summary: {spec['agent_summary']}")
    print("generation families:")
    for family in spec.get("generation_families", []):
        target = family.get("recipe") or family.get("template") or "planned"
        print(f"  - {family['id']}: {target}")


def iter_recipe_paths(object_name: str | None = None) -> list[Path]:
    recipe_root = AGENT_ROOT / "recipes"
    if object_name:
        return sorted((recipe_root / object_name).glob("*.json"))
    return sorted(recipe_root.glob("*/*.json"))


def command_recipes(args: argparse.Namespace) -> None:
    recipes = [load_json(path) for path in iter_recipe_paths(args.object)]
    if args.as_json:
        emit_json(recipes)
        return
    print_rows(
        ["ID", "OBJECT", "CATEGORY", "STATUS", "TEMPLATE"],
        (
            (
                recipe["id"],
                recipe["object"],
                recipe.get("category", ""),
                recipe.get("status", ""),
                recipe.get("template", ""),
            )
            for recipe in recipes
        ),
    )


def command_show_recipe(args: argparse.Namespace) -> None:
    for path in iter_recipe_paths(args.object):
        recipe = load_json(path)
        if recipe["id"] == args.recipe_id:
            emit_json(recipe)
            return
    suffix = f" for object {args.object!r}" if args.object else ""
    raise SystemExit(f"Unknown recipe {args.recipe_id!r}{suffix}")


def command_fixtures(args: argparse.Namespace) -> None:
    fixtures = [load_json(path) for path in sorted((AGENT_ROOT / "fixtures").glob("*.json"))]
    if args.as_json:
        emit_json(fixtures)
        return
    print_rows(
        ["ID", "OBJECT", "CAPABILITIES"],
        (
            (
                fixture["id"],
                fixture["object"],
                ",".join(fixture.get("provides_capabilities", [])),
            )
            for fixture in fixtures
        ),
    )


def command_validate(args: argparse.Namespace) -> None:
    errors: list[str] = []
    registry = load_json(AGENT_ROOT / "object-registry.json")
    for obj in registry["objects"]:
        spec = obj.get("spec", "").split("#", 1)[0]
        if spec and not (REPOSITORY_ROOT / spec).is_file():
            errors.append(f"missing spec for {obj['id']}: {spec}")

    for recipe_path in iter_recipe_paths():
        recipe = load_json(recipe_path)
        template = recipe.get("template")
        if template and not (REPOSITORY_ROOT / template).is_file():
            errors.append(f"{recipe_path}: missing template {template}")
        for fixture in recipe.get("fixtures", []):
            if not (REPOSITORY_ROOT / fixture).is_file():
                errors.append(f"{recipe_path}: missing fixture {fixture}")

    for manifest_path in sorted((REPOSITORY_ROOT / "kb" / "templates").glob("*.manifest.json")):
        manifest = load_json(manifest_path)
        template = REPOSITORY_ROOT / manifest["template"]
        if not template.is_file():
            errors.append(f"{manifest_path}: missing template {manifest['template']}")
            continue
        text = template.read_text(encoding="utf-8")
        for token in manifest.get("required_tokens", []):
            if "{{" + token + "}}" not in text:
                errors.append(f"{manifest_path}: token {token} not found in {manifest['template']}")
        for required in manifest.get("must_include", []):
            if required not in text:
                errors.append(f"{manifest_path}: required text {required!r} not found")
        for forbidden in manifest.get("must_exclude", []):
            if forbidden in text:
                errors.append(f"{manifest_path}: forbidden text {forbidden!r} found")

    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("Agent layer validation OK")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    registry = subparsers.add_parser("registry", help="list agent-known objects")
    registry.add_argument("--json", dest="as_json", action="store_true")
    registry.set_defaults(func=command_registry)

    spec = subparsers.add_parser("spec", help="show an object generation spec")
    spec.add_argument("object")
    spec.add_argument("--json", dest="as_json", action="store_true")
    spec.set_defaults(func=command_spec)

    recipes = subparsers.add_parser("recipes", help="list generation recipes")
    recipes.add_argument("--object", choices=["trigger", "view"], help="filter recipes")
    recipes.add_argument("--json", dest="as_json", action="store_true")
    recipes.set_defaults(func=command_recipes)

    show_recipe = subparsers.add_parser("show-recipe", help="show one recipe as JSON")
    show_recipe.add_argument("recipe_id")
    show_recipe.add_argument("--object", choices=["trigger", "view"], help="filter recipes")
    show_recipe.set_defaults(func=command_show_recipe)

    fixtures = subparsers.add_parser("fixtures", help="list reusable fixtures")
    fixtures.add_argument("--json", dest="as_json", action="store_true")
    fixtures.set_defaults(func=command_fixtures)

    validate = subparsers.add_parser("validate", help="validate agent-layer references")
    validate.set_defaults(func=command_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
