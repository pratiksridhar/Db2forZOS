from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "kb" / "data" / "db2z13-create-ddl.json"
TRIGGER_BODY_PATH = ROOT / "kb" / "data" / "db2z13-trigger-body-statements.json"
SCHEMA_PATH = ROOT / "kb" / "data" / "test-case.schema.json"
SAMPLE_PATH = ROOT / "kb" / "test-design" / "sample-case.json"


class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        cls.trigger_body = json.loads(TRIGGER_BODY_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))

    def test_exact_requested_object_set(self) -> None:
        self.assertEqual(
            set(self.data["objects"]),
            {"stogroup", "database", "tablespace", "table", "index", "trigger"},
        )

    def test_normalized_ids_are_unique(self) -> None:
        for object_name, obj in self.data["objects"].items():
            for collection in ("clauses", "rules"):
                ids = [item["id"] for item in obj[collection]]
                self.assertEqual(len(ids), len(set(ids)), f"duplicate {object_name} {collection} ID")

    def test_every_rule_clause_reference_resolves(self) -> None:
        for object_name, obj in self.data["objects"].items():
            clause_ids = {item["id"] for item in obj["clauses"]}
            for rule in obj["rules"]:
                self.assertFalse(
                    set(rule["clauses"]) - clause_ids,
                    f"unknown clause reference: {object_name}.{rule['id']}",
                )

    def test_every_source_reference_resolves_to_official_ibm_docs(self) -> None:
        sources = self.data["sources"]
        for source_id, source in sources.items():
            self.assertTrue(source_id.startswith("ibm-"))
            self.assertRegex(source["url"], r"^https://www\.ibm\.com/docs/")
        for object_name, obj in self.data["objects"].items():
            for collection in ("clauses", "rules"):
                for item in obj[collection]:
                    self.assertTrue(item["source_refs"], f"missing sources: {object_name}.{item['id']}")
                    for source_id in item["source_refs"]:
                        self.assertIn(source_id, sources, f"unknown source: {object_name}.{item['id']}")

        def assert_body_sources(value: object, location: str = "trigger-body") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "source_refs":
                        self.assertTrue(child, f"empty source list: {location}")
                        for source_id in child:
                            self.assertIn(source_id, sources, f"unknown source: {location}")
                    else:
                        assert_body_sources(child, f"{location}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    assert_body_sources(child, f"{location}[{index}]")

        assert_body_sources(self.trigger_body)

    def test_chapter_and_catalog_assets_exist(self) -> None:
        for obj in self.data["objects"].values():
            self.assertTrue((ROOT / obj["chapter"]).is_file())
        self.assertTrue((ROOT / "kb" / "test-design" / "catalog-verification.sql").is_file())
        for name in (
            "object-stack",
            "pbg-table",
            "pbr-table",
            "basic-trigger",
            "advanced-trigger",
            "advanced-trigger-ddl-body",
        ):
            self.assertTrue((ROOT / "kb" / "templates" / f"{name}.template.sql").is_file())
        self.assertTrue(TRIGGER_BODY_PATH.is_file())
        self.assertTrue((ROOT / "kb" / "trigger-body-statements.md").is_file())
        self.assertTrue((ROOT / self.data["objects"]["trigger"]["body_statement_inventory"]).is_file())

    def test_trigger_templates_select_the_expected_trigger_kind(self) -> None:
        basic = (ROOT / "kb" / "templates" / "basic-trigger.template.sql").read_text(
            encoding="utf-8"
        )
        advanced = (ROOT / "kb" / "templates" / "advanced-trigger.template.sql").read_text(
            encoding="utf-8"
        )
        ddl = (ROOT / "kb" / "templates" / "advanced-trigger-ddl-body.template.sql").read_text(
            encoding="utf-8"
        )
        mode_clause = re.compile(r"^\s+MODE DB2SQL\s*$", re.MULTILINE)
        self.assertRegex(basic, mode_clause)
        self.assertNotRegex(advanced, mode_clause)
        self.assertNotRegex(ddl, mode_clause)
        self.assertIn("BEGIN ATOMIC", basic)
        self.assertIn("BEGIN ATOMIC", advanced)
        for statement in ("CREATE TABLE", "CREATE UNIQUE INDEX", "CREATE VIEW"):
            self.assertIn(statement, ddl)
        self.assertGreaterEqual(sum(text.count("END!") for text in (basic, advanced, ddl)), 3)

    def test_case_sample_has_schema_required_fields_and_known_sources(self) -> None:
        required = set(self.schema["required"])
        self.assertFalse(required - set(self.sample), f"sample missing: {required - set(self.sample)}")
        self.assertRegex(
            self.sample["id"],
            re.compile(self.schema["properties"]["id"]["pattern"]),
        )
        self.assertIn(self.sample["object"], self.data["objects"])
        for source_id in self.sample["source_refs"]:
            self.assertIn(source_id, self.data["sources"])

    def test_test_case_schema_accepts_trigger_identifiers(self) -> None:
        pattern = re.compile(self.schema["properties"]["id"]["pattern"])
        self.assertRegex("DB2Z13-TRIGGER-BODY-DDL-001", pattern)
        self.assertIn("trigger", self.schema["properties"]["object"]["enum"])

    def test_source_manifest_mentions_every_normalized_source(self) -> None:
        manifest = (ROOT / "kb" / "sources.md").read_text(encoding="utf-8")
        for source_id in self.data["sources"]:
            self.assertIn(f"`{source_id}`", manifest)

    def test_markdown_source_ids_and_local_links_resolve(self) -> None:
        markdown_files = [ROOT / "README.md", *(ROOT / "kb").rglob("*.md")]
        known_sources = set(self.data["sources"])
        for path in markdown_files:
            text = path.read_text(encoding="utf-8")
            referenced_sources = set(re.findall(r"`(ibm-[a-z0-9-]+)`", text))
            self.assertFalse(referenced_sources - known_sources, path)
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if target.startswith(("http://", "https://", "#")):
                    continue
                local_target = target.split("#", 1)[0]
                self.assertTrue((path.parent / local_target).exists(), f"{path}: {target}")

    def test_trigger_direct_statement_sets_match_ibm_diagrams(self) -> None:
        self.assertEqual(self.trigger_body["baseline"]["release"], "13")
        self.assertEqual(self.trigger_body["baseline"]["authority"], "Official IBM documentation only")
        basic = {row["id"] for row in self.trigger_body["basic"]["statements"]}
        direct = {row["id"] for row in self.trigger_body["advanced"]["direct_statements"]}
        self.assertEqual(
            basic,
            {
                "call",
                "delete-searched",
                "fullselect",
                "insert",
                "merge",
                "refresh-table",
                "set-assignment",
                "signal",
                "truncate",
                "update-searched",
                "values",
                "values-into",
            },
        )
        self.assertEqual(
            direct,
            {
                "call",
                "delete-searched",
                "get-diagnostics",
                "insert",
                "merge",
                "refresh-table",
                "set-assignment",
                "signal",
                "truncate",
                "update-searched",
                "values-into",
            },
        )
        self.assertNotIn("fullselect", direct)
        self.assertNotIn("values", direct)

    def test_trigger_sql_procedure_statement_matrix_is_complete(self) -> None:
        matrix = self.trigger_body["advanced"]["sql_procedure_statement_matrix"]
        allowed = {row["id"] for row in matrix["allowed"]}
        excluded = set(matrix["excluded"])
        self.assertEqual(
            allowed,
            {
                "sql-control-statement",
                "allocate-cursor",
                "alter-function",
                "associate-locators",
                "call",
                "close",
                "comment",
                "create-index",
                "create-table",
                "create-view",
                "declare-cursor",
                "delete-searched",
                "drop",
                "execute",
                "execute-immediate",
                "explain",
                "fetch",
                "get-diagnostics",
                "grant",
                "insert",
                "label",
                "lock-table",
                "merge",
                "open",
                "prepare",
                "refresh-table",
                "rename",
                "revoke",
                "savepoint",
                "select-into",
                "set-assignment",
                "set-special-register",
                "truncate",
                "update-searched",
                "values-into",
            },
        )
        self.assertEqual(
            excluded,
            {
                "ALTER DATABASE",
                "ALTER INDEX",
                "ALTER MASK",
                "ALTER PERMISSION",
                "ALTER PROCEDURE (external, SQL - external, or SQL - native)",
                "ALTER SEQUENCE",
                "ALTER STOGROUP",
                "ALTER TABLE",
                "ALTER TABLESPACE",
                "ALTER TRIGGER",
                "ALTER TRUSTED CONTEXT",
                "ALTER VIEW",
                "COMMIT",
                "CONNECT",
                "CREATE ALIAS",
                "CREATE DATABASE",
                "CREATE FUNCTION",
                "CREATE GLOBAL TEMPORARY TABLE",
                "CREATE PROCEDURE (external)",
                "CREATE ROLE",
                "CREATE SEQUENCE",
                "CREATE STOGROUP",
                "CREATE TABLESPACE",
                "CREATE TRUSTED CONTEXT",
                "CREATE TYPE (array)",
                "CREATE TYPE (distinct)",
                "CREATE VARIABLE",
                "DECLARE GLOBAL TEMPORARY TABLE",
                "EXCHANGE",
                "RELEASE connection",
                "RELEASE SAVEPOINT",
                "ROLLBACK (with TO SAVEPOINT clause)",
                "ROLLBACK (without TO SAVEPOINT clause)",
                "SET CONNECTION",
            },
        )
        self.assertEqual(len(allowed) + len(excluded), 69)

    def test_trigger_ddl_subset_and_control_statement_boundary(self) -> None:
        allowed_rows = {
            row["id"]: row
            for row in self.trigger_body["advanced"]["sql_procedure_statement_matrix"]["allowed"]
        }
        self.assertEqual(
            allowed_rows["create-table"]["activation_times"],
            ["BEFORE", "AFTER", "INSTEAD OF"],
        )
        self.assertEqual(
            allowed_rows["create-index"]["activation_times"],
            ["AFTER", "INSTEAD OF"],
        )
        self.assertIn("LOB or XML", " ".join(allowed_rows["create-table"]["restrictions"]))
        excluded = self.trigger_body["advanced"]["sql_procedure_statement_matrix"]["excluded"]
        for statement in (
            "CREATE STOGROUP",
            "CREATE DATABASE",
            "CREATE TABLESPACE",
        ):
            self.assertIn(statement, excluded)
        self.assertIn("ALTER TRIGGER", excluded)
        ddl_subset = {
            row["id"]: row for row in self.trigger_body["advanced"]["repository_ddl_subset"]
        }
        self.assertEqual(ddl_subset["create-table"]["status"], "supported nested row")
        self.assertEqual(ddl_subset["create-index"]["activation_times"], ["AFTER", "INSTEAD OF"])
        self.assertEqual(
            ddl_subset["create-trigger"]["status"],
            "not listed in SQL-procedure-statement grammar",
        )

        controls = self.trigger_body["advanced"]["control_statements"]
        self.assertEqual(len(controls), 16)
        self.assertEqual(sum(row["trigger_supported"] for row in controls), 15)
        return_row = next(row for row in controls if row["id"] == "return")
        self.assertFalse(return_row["trigger_supported"])

    def test_trigger_statement_syntax_covers_every_supported_statement_id(self) -> None:
        syntax_ids = set(self.trigger_body["statement_syntax"])
        required_ids = {
            row["id"]
            for row in [
                *self.trigger_body["basic"]["statements"],
                *self.trigger_body["advanced"]["direct_statements"],
                *self.trigger_body["advanced"]["sql_procedure_statement_matrix"]["allowed"],
            ]
        }
        self.assertFalse(required_ids - syntax_ids)
        for statement_id in required_ids:
            self.assertTrue(self.trigger_body["statement_syntax"][statement_id]["syntax"])

    def test_cli_smoke_and_search(self) -> None:
        commands = [
            ["objects"],
            ["clauses", "tablespace"],
            ["show", "tablespace", "maxpartitions"],
            ["rules", "table", "--tag", "implicit"],
            ["dimensions", "index"],
            ["clauses", "trigger"],
            ["show", "trigger", "advanced-ddl-subset"],
            ["rules", "trigger", "--tag", "body"],
            ["dimensions", "trigger"],
            ["trigger-statements", "basic"],
            ["trigger-statements", "direct", "--activation", "AFTER"],
            ["trigger-statements", "nested", "--activation", "BEFORE"],
            ["trigger-statements", "ddl"],
            ["trigger-statements", "excluded", "--statement", "CREATE TABLESPACE"],
            ["trigger-statements", "controls", "--statement", "return"],
            ["trigger-statements", "syntax", "--statement", "create-table", "--json"],
            ["search", "WITHOUT OVERLAPS"],
        ]
        for command in commands:
            completed = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "kb.py"), *command],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(completed.stdout.strip(), command)


if __name__ == "__main__":
    unittest.main()
