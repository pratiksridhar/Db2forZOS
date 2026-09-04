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
QA_1000_SQL_PATH = ROOT / "kb" / "test-design" / "create-1000-table-qa-workload.sql"


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
            {"stogroup", "database", "tablespace", "table", "index", "trigger", "procedure"},
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
        self.assertTrue(QA_1000_SQL_PATH.is_file())
        for name in (
            "object-stack",
            "pbg-table",
            "pbr-table",
            "basic-trigger",
            "advanced-trigger",
            "advanced-trigger-ddl-body",
            "native-sql-procedure",
            "external-procedure",
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
        self.assertNotRegex(basic, r"\b(?:OLD|NEW)\s+ROW\b")
        self.assertNotRegex(advanced, mode_clause)
        self.assertNotRegex(ddl, mode_clause)
        self.assertIn("BEGIN ATOMIC", basic)
        self.assertIn("BEGIN ATOMIC", advanced)
        for statement in ("CREATE TABLE", "CREATE UNIQUE INDEX", "CREATE VIEW"):
            self.assertIn(statement, ddl)
        self.assertGreaterEqual(sum(text.count("END!") for text in (basic, advanced, ddl)), 3)

        basic_before = (ROOT / "kb" / "templates" / "basic-before-validation.template.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("NO CASCADE BEFORE", basic_before)
        self.assertNotRegex(basic_before, r"\b(?:OLD|NEW)\s+ROW\b")

    def test_procedure_templates_select_current_definition_kinds(self) -> None:
        native = (ROOT / "kb" / "templates" / "native-sql-procedure.template.sql").read_text(
            encoding="utf-8"
        )
        external = (ROOT / "kb" / "templates" / "external-procedure.template.sql").read_text(
            encoding="utf-8"
        )
        native_sql = "\n".join(line for line in native.splitlines() if not line.startswith("--"))
        self.assertIn("LANGUAGE SQL", native_sql)
        self.assertIn("BEGIN", native_sql)
        self.assertIn("END!", native_sql)
        self.assertNotIn("FENCED", native_sql)
        self.assertNotIn("EXTERNAL", native_sql)
        self.assertIn("LANGUAGE COBOL", external)
        self.assertIn("EXTERNAL NAME", external)
        self.assertIn("WLM ENVIRONMENT", external)
        self.assertNotIn("LANGUAGE SQL", external)

        catalog = (ROOT / "kb" / "test-design" / "catalog-verification.sql").read_text(
            encoding="utf-8"
        )
        for table in ("SYSROUTINES", "SYSPARMS", "SYSPACKAGE", "SYSPACKDEP", "SYSROUTINEAUTH"):
            self.assertIn(f"SYSIBM.{table}", catalog)
        self.assertIn("TYPE   = 'N'", catalog)
        self.assertIn("DTYPE   = 'N'", catalog)

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

    def test_test_case_schema_accepts_trigger_and_procedure_identifiers(self) -> None:
        pattern = re.compile(self.schema["properties"]["id"]["pattern"])
        self.assertRegex("DB2Z13-TRIGGER-BODY-DDL-001", pattern)
        self.assertIn("trigger", self.schema["properties"]["object"]["enum"])
        self.assertRegex("DB2Z13-PROCEDURE-VERSION-001", pattern)
        self.assertIn("procedure", self.schema["properties"]["object"]["enum"])

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

    def test_create_table_syntax_matches_critical_ibm_diagram_paths(self) -> None:
        table = self.data["objects"]["table"]
        clauses = {row["id"]: row for row in table["clauses"]}
        rules = {row["id"]: row for row in table["rules"]}

        self.assertEqual(clauses["default"]["syntax"], "[ WITH ] DEFAULT [ <default-value> ]")
        self.assertEqual(
            clauses["identity"]["syntax"],
            "GENERATED [ ALWAYS | BY DEFAULT ] AS IDENTITY [(identity-options)]",
        )
        self.assertEqual(
            clauses["row-change-timestamp"]["syntax"],
            "GENERATED [ ALWAYS | BY DEFAULT ] FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP",
        )
        self.assertEqual(
            clauses["rowid"]["syntax"],
            "ROWID NOT NULL GENERATED [ ALWAYS | BY DEFAULT ]",
        )
        for clause_id in (
            "transaction-start-id",
            "row-begin",
            "row-end",
            "generated-provenance",
        ):
            self.assertIn("GENERATED [ ALWAYS ]", clauses[clause_id]["syntax"])

        required_clause_ids = {
            "copy-options",
            "xml-type-modifier",
            "column-constraint",
            "in-accelerator",
            "organization-by-hash",
            "partition-hash-space",
            "editproc",
            "validproc",
            "obid",
            "logged",
            "compress",
            "dssize",
            "bufferpool",
            "member-cluster",
            "trackmod",
            "pagenum",
        }
        self.assertFalse(required_clause_ids - set(clauses))

        required_rule_ids = {
            "top-level-clause-order-cardinality",
            "column-clause-cardinality",
            "copy-options-context",
            "copy-options-order-cardinality",
            "mqt-option-cardinality",
            "generated-keyword-default",
            "identity-option-order-separators",
            "xml-modifier-rules",
            "placement-exclusive",
            "partitioning-exclusive",
            "dssize-every-conflict",
            "pagenum-relative-requires-partitioning",
            "accelerator-restrictions",
            "hash-cross-clause-restrictions",
            "compatibility-synonyms",
        }
        self.assertFalse(required_rule_ids - set(rules))
        self.assertIn("must not be specified with LIKE", rules["copy-options-context"]["text"])
        self.assertEqual(
            rules["hash-current-unsupported"]["clauses"],
            ["organization-by-hash", "partition-hash-space"],
        )

        compatibility_text = rules["compatibility-synonyms"]["text"]
        for spelling in (
            "NOCACHE",
            "NOCYCLE",
            "NOMINVALUE",
            "NOMAXVALUE",
            "NOORDER",
            "DEFINITION ONLY",
            "CREATE SUMMARY TABLE",
            "TIMEZONE",
        ):
            self.assertIn(spelling, compatibility_text)

        chapter = (ROOT / table["chapter"]).read_text(encoding="utf-8")
        self.assertNotIn("GENERATED { ALWAYS | BY DEFAULT } ROWID", chapter)
        self.assertNotIn("[ WITH DEFAULT | DEFAULT <default-value> ]", chapter)
        self.assertIn("<column-name> ROWID NOT NULL GENERATED [ ALWAYS | BY DEFAULT ]", chapter)
        self.assertIn("must not be specified with `LIKE`", chapter)

    def test_current_ibm_review_corrections_are_preserved(self) -> None:
        self.assertEqual(self.data["baseline"]["documentation_reviewed"], "2026-09-03")
        self.assertEqual(self.data["baseline"]["latest_reviewed_function_level"], "V13R1M509")
        self.assertEqual(
            self.trigger_body["baseline"]["documentation_reviewed"],
            "2026-09-03",
        )

        tablespace = self.data["objects"]["tablespace"]
        tablespace_clauses = {row["id"]: row for row in tablespace["clauses"]}
        self.assertIn("LOB: LOCKSIZE { ANY | LOB }", tablespace_clauses["locksize"]["syntax"])
        self.assertNotIn("TABLESPACE | LOB", tablespace_clauses["locksize"]["syntax"])
        tablespace_chapter = (ROOT / tablespace["chapter"]).read_text(encoding="utf-8")
        self.assertIn("[ LOCKSIZE { ANY | LOB } ]", tablespace_chapter)
        self.assertNotIn("[ LOCKSIZE { ANY | TABLESPACE | LOB } ]", tablespace_chapter)

        index_rules = {row["id"]: row for row in self.data["objects"]["index"]["rules"]}
        temporal_partition_rule = index_rules[
            "temporal-without-overlaps-partition-attributes-conflict"
        ]
        self.assertEqual(
            temporal_partition_rule["clauses"],
            ["business-time", "partition-attributes"],
        )
        index_chapter = (ROOT / self.data["objects"]["index"]["chapter"]).read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "cannot be specified with `BUSINESS_TIME WITHOUT OVERLAPS`",
            index_chapter,
        )

        procedure = self.data["objects"]["procedure"]
        procedure_clauses = {row["id"]: row for row in procedure["clauses"]}
        procedure_rules = {row["id"]: row for row in procedure["rules"]}
        self.assertEqual(
            procedure_clauses["parameter-varchar"]["syntax"],
            "PARAMETER VARCHAR { NULTERM | STRUCTURE }",
        )
        self.assertIn("external:", procedure_clauses["sql-data-access"]["syntax"])
        self.assertIn("parameter-varchar-family-scope", procedure_rules)
        self.assertIn("no-sql-external-only", procedure_rules)
        procedure_chapter = (ROOT / procedure["chapter"]).read_text(encoding="utf-8")
        self.assertIn("[PARAMETER VARCHAR {NULTERM | STRUCTURE}]", procedure_chapter)

        trigger = self.data["objects"]["trigger"]
        trigger_clauses = {row["id"]: row for row in trigger["clauses"]}
        trigger_rules = {row["id"]: row for row in trigger["rules"]}
        self.assertIn("basic: { NO CASCADE BEFORE", trigger_clauses["activation-time"]["syntax"])
        self.assertIn("advanced: REFERENCING [OLD [ROW]", trigger_clauses["referencing-row"]["syntax"])
        self.assertIn("basic-before-no-cascade-required", trigger_rules)
        self.assertIn("transition-row-keyword-advanced-only", trigger_rules)
        trigger_chapter = (ROOT / trigger["chapter"]).read_text(encoding="utf-8")
        self.assertIn("<basic-activation-time>    ::= NO CASCADE BEFORE", trigger_chapter)
        self.assertNotIn("<activation-time> ::= [NO CASCADE] BEFORE", trigger_chapter)

        self.assertIn("ibm-create-view", self.data["sources"])
        self.assertIn(
            "ibm-create-view",
            self.trigger_body["statement_syntax"]["create-view"]["source_refs"],
        )
        create_view_syntax = self.trigger_body["statement_syntax"]["create-view"]["syntax"]
        self.assertIn("[WITH <common-table-expression> [, ...]]", create_view_syntax)
        self.assertIn("[WITH [CASCADED | LOCAL] CHECK OPTION]", create_view_syntax)

    def test_generated_1000_table_workload_invariants(self) -> None:
        sql = QA_1000_SQL_PATH.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^CREATE STOGROUP ", sql, re.MULTILINE)), 1)
        self.assertEqual(len(re.findall(r"^CREATE DATABASE ", sql, re.MULTILINE)), 1)
        self.assertEqual(
            len(re.findall(r"^CREATE TABLESPACE S\d{7}$", sql, re.MULTILINE)),
            1000,
        )
        self.assertEqual(
            len(re.findall(r"^CREATE TABLE QA1K\.T\d{7}$", sql, re.MULTILINE)),
            1000,
        )

        table_spaces = re.findall(r"^CREATE TABLESPACE (S\d{7})$", sql, re.MULTILINE)
        tables = re.findall(r"^CREATE TABLE QA1K\.(T\d{7})$", sql, re.MULTILINE)
        self.assertEqual(len(set(table_spaces)), 1000)
        self.assertEqual(len(set(tables)), 1000)
        for number in range(1, 1001):
            self.assertEqual(sql.count(f"IN Q1KDB001.S{number:07d}"), 1)

        for family in (
            "identity-always",
            "system-time-period",
            "business-time-exclusive",
            "bitemporal-foundation",
            "composite-foreign-key",
            "like-with-identity",
            "as-fullselect-with-no-data",
            "materialized-query-table",
            "wide-32k-row",
        ):
            self.assertEqual(sql.count(f": {family};"), 50)

        self.assertIn("Replace {{VCAT}}", sql)
        self.assertNotIn("CREATE LOB TABLESPACE", sql)


    def test_agent_layer_json_and_references_are_valid(self) -> None:
        agent_root = ROOT / "kb" / "agent"
        self.assertTrue((agent_root / "README.md").is_file())
        self.assertTrue((agent_root / "TASKS.md").is_file())

        agent_json = {}
        for path in [*agent_root.rglob("*.json"), *(ROOT / "kb" / "templates").glob("*.manifest.json")]:
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(path=relative):
                agent_json[relative] = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(agent_json[relative]["schema_version"], "1.0.0")

        registry = agent_json["kb/agent/object-registry.json"]
        registry_objects = {row["id"]: row for row in registry["objects"]}
        self.assertIn("trigger", registry_objects)
        self.assertIn("view", registry_objects)
        self.assertEqual(registry_objects["trigger"]["status"], "normalized")
        self.assertEqual(registry_objects["view"]["status"], "extension_candidate")
        for object_id, row in registry_objects.items():
            if row["status"] == "normalized":
                self.assertIn(row["normalized_object"], self.data["objects"], object_id)
            spec = row.get("spec", "").split("#", 1)[0]
            if spec:
                self.assertTrue((ROOT / spec).is_file(), f"missing spec for {object_id}: {spec}")

        for recipe_path in (agent_root / "recipes").glob("*/*.json"):
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            self.assertIn(recipe["object"], registry_objects)
            self.assertTrue((ROOT / recipe["template"]).is_file(), recipe_path)
            for fixture in recipe.get("fixtures", []):
                self.assertTrue((ROOT / fixture).is_file(), recipe_path)
            self.assertTrue(recipe.get("covers"), recipe_path)
            self.assertIn(recipe["expected"]["failure_phase"], self.schema["$defs"]["expected_failure_phase"]["enum"] if "$defs" in self.schema and "expected_failure_phase" in self.schema["$defs"] else {"none", "prepare_or_execute", "data_set_allocation", "data_change", "rebuild_or_utility", "ofs_generation", "recreate"})

    def test_agent_template_manifests_match_templates(self) -> None:
        for manifest_path in (ROOT / "kb" / "templates").glob("*.manifest.json"):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            template_path = ROOT / manifest["template"]
            self.assertTrue(template_path.is_file(), manifest_path)
            template = template_path.read_text(encoding="utf-8")
            for token in manifest.get("required_tokens", []):
                self.assertIn("{{" + token + "}}", template, manifest_path)
            for required in manifest.get("must_include", []):
                self.assertIn(required, template, manifest_path)
            for forbidden in manifest.get("must_exclude", []):
                self.assertNotIn(forbidden, template, manifest_path)

    def test_agent_cli_smoke(self) -> None:
        commands = [
            ["registry"],
            ["spec", "trigger"],
            ["spec", "view", "--json"],
            ["recipes"],
            ["recipes", "--object", "trigger"],
            ["show-recipe", "trigger_basic_before_validation"],
            ["fixtures"],
            ["validate"],
        ]
        for command in commands:
            completed = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "agent.py"), *command],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(completed.stdout.strip(), command)

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
            ["clauses", "procedure"],
            ["show", "procedure", "kind-discriminator"],
            ["rules", "procedure", "--tag", "versioning"],
            ["dimensions", "procedure"],
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
