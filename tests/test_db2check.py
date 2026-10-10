from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402
import db2check  # noqa: E402
import db2sql  # noqa: E402
import qa  # noqa: E402

EXAMPLE = paths.VARIED_SCHEMA
PROFILE = qa.read(paths.EXAMPLE_PROFILE)
DB = "CREATE DATABASE QADB1 STOGROUP SYSDEFLT BUFFERPOOL BP0 INDEXBP BP0;\n"
TS = "CREATE TABLESPACE TS1 IN QADB1;\n"


def analyze(sql, **options):
    return db2check.analyze(sql, db2check.Options(**options))


def rules(sql, severities=("error", "unsupported", "warning"), **options):
    return {f.rule for f in analyze(sql, **options).findings if f.severity in severities}


def profile(applcompat="V13R1M500", function_level=None, **params):
    data = copy.deepcopy(PROFILE)
    data["product_context"]["applcompat"] = applcompat
    data["product_context"]["function_level"] = function_level or applcompat
    data["product_context"]["subsystem_parameters"] = params
    return data


# One SQL fixture per rule. Each must produce the rule; the catalog test below
# fails if a rule is added without a fixture, so no check exists untested.
NEGATIVE = {
    "script.parse-error": "CREATE TABLE T1 (C1 INTEGER NOT NULL,);",
    "script.unrecognized-statement": "FROBNICATE TABLE T1;",
    "script.unterminated-statement": "COMMIT",
    "script.sqlpl-terminator": DB + TS + "CREATE TABLE S.T (C INTEGER) IN QADB1.TS1;\n"
                               "CREATE TRIGGER S.TR1 NO CASCADE BEFORE INSERT ON S.T REFERENCING NEW AS N "
                               "FOR EACH ROW MODE DB2SQL BEGIN ATOMIC SET N.C = 1; END;",
    "script.record-length": ("COMMIT;\n" + "-- " + "x" * 80 + "\n", {"max_line": 72}),
    "script.placeholder": "CREATE STOGROUP SG1 VOLUMES ('*') VCAT {{VCAT}};",
    "dialect.clause": DB + TS + "CREATE TABLE S.T (C INTEGER) IN QADB1.TS1 ORGANIZE BY ROW;",
    "dialect.data-type": DB + TS + "CREATE TABLE S.T (C BOOLEAN) IN QADB1.TS1;",
    "dialect.if-not-exists": "CREATE TABLE IF NOT EXISTS S.T (C INTEGER);",
    "dialect.if-exists": "DROP TABLE IF EXISTS S.T;",
    "dialect.or-replace": "CREATE OR REPLACE TABLE S.T (C INTEGER);",
    "dialect.null-attribute": DB + TS + "CREATE TABLE S.T (C INTEGER NULL) IN QADB1.TS1;",
    "dialect.referential-on-update": DB + TS + "CREATE TABLE S.P (K INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
                                     "CREATE TABLE S.C (K INTEGER REFERENCES S.P ON UPDATE CASCADE) IN QADB1.TS1;",
    "dialect.referential-action": DB + "CREATE TABLE S.P (K INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
                                  "CREATE TABLE S.C (K INTEGER REFERENCES S.P ON DELETE SET DEFAULT) IN DATABASE QADB1;",
    "dialect.partial-index": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C) WHERE C > 1;",
    "syntax.unrecognized-clause": DB + "CREATE TABLESPACE TS1 IN QADB1 FROBNICATE 4;",
    "syntax.unmodeled-xml-modifier": DB + "CREATE TABLE S.T (C XML(XMLSCHEMA ID S.X)) IN DATABASE QADB1;",
    "syntax.duplicate-clause": DB + "CREATE TABLESPACE TS1 IN QADB1 SEGSIZE 4 SEGSIZE 8;",
    "deprecated.large": DB + "CREATE LARGE TABLESPACE TS1 IN QADB1 NUMPARTS 2;",
    "deprecated.clause": DB + "CREATE TABLESPACE TS1 IN QADB1 LOCKPART YES;",
    "deprecated.index-controlled-partitioning": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\n"
                                                "CREATE INDEX S.I ON S.T (C) PARTITION BY RANGE (PARTITION 1 ENDING AT (10));",
    "name.length": "CREATE DATABASE TOOLONGNAME;",
    "name.column-expansion": (DB + TS + "CREATE TABLE S.T (" + "C" * 40 + " INTEGER) IN QADB1.TS1;",
                              {"column_name_expansion": True}),
    "name.short-identifier-form": "CREATE DATABASE \"qadb\";",
    "name.short-identifier-extender": "CREATE DATABASE QA_DB;",
    "name.reserved-database": "CREATE DATABASE DSN12345;",
    "name.bufferpool": "CREATE DATABASE QADB1 BUFFERPOOL BP99;",
    "name.duplicate-object": "CREATE DATABASE QADB1;\nCREATE DATABASE QADB1;",
    "name.duplicate-constraint": DB + "CREATE TABLE S.T (C INTEGER, CONSTRAINT X CHECK (C > 0), CONSTRAINT X CHECK (C < 9)) IN DATABASE QADB1;",
    "dependency.order": DB + "CREATE TABLE S.T (C INTEGER) IN QADB1.TS1;\n" + TS,
    "dependency.external": "CREATE TABLESPACE TS1 IN NODB;",
    "dependency.default-database": "CREATE TABLESPACE TS1;",
    "tablespace.segsize-range": DB + "CREATE TABLESPACE TS1 IN QADB1 SEGSIZE 30;",
    "tablespace.maxpartitions-range": DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 128 DSSIZE 256 G BUFFERPOOL BP0;",
    "tablespace.numparts-range": DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 2 NUMPARTS 3;",
    "tablespace.dssize-value": DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 4 DSSIZE 3 G;",
    "tablespace.dssize-dfsms": DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 4 DSSIZE 8 G;",
    "tablespace.free-space-range": DB + "CREATE TABLESPACE TS1 IN QADB1 PCTFREE 60 FOR UPDATE 50;",
    "tablespace.maxrows-range": DB + "CREATE TABLESPACE TS1 IN QADB1 MAXROWS 256;",
    "tablespace.locksize-value": DB + "CREATE TABLESPACE TS1 IN QADB1 LOCKSIZE LOB;",
    "tablespace.lockmax-locksize": DB + "CREATE TABLESPACE TS1 IN QADB1 LOCKSIZE TABLESPACE LOCKMAX 10;",
    "tablespace.pbr-only-clause": DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 4 PAGENUM RELATIVE;",
    "tablespace.partition-number": DB + "CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2 (PARTITION 3 FREEPAGE 1);",
    "tablespace.pbg-vcat": DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 2 USING VCAT CAT1;",
    "tablespace.space-quantity": DB + "CREATE TABLESPACE TS1 IN QADB1 USING STOGROUP SYSDEFLT PRIQTY 0;",
    "tablespace.workfile-usage": DB + "CREATE TABLESPACE TS1 IN QADB1 FOR SORT;",
    "tablespace.unused": DB + TS,
    "table.column-type-required": DB + "CREATE TABLE S.T (C NOT NULL) IN DATABASE QADB1;",
    "table.column-clause-repeated": DB + "CREATE TABLE S.T (C INTEGER NOT NULL NOT NULL) IN DATABASE QADB1;",
    "table.duplicate-column": DB + "CREATE TABLE S.T (C INTEGER, C SMALLINT) IN DATABASE QADB1;",
    "table.column-count": DB + "CREATE TABLE S.T (" + ", ".join(f"C{i} SMALLINT" for i in range(751)) + ") IN DATABASE QADB1;",
    "table.data-type-range": DB + "CREATE TABLE S.T (C DECIMAL(40, 2)) IN DATABASE QADB1;",
    "table.default-value-form": DB + "CREATE TABLE S.T (C TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP) IN DATABASE QADB1;",
    "table.default-on-generated": DB + "CREATE TABLE S.T (C INTEGER GENERATED ALWAYS AS IDENTITY WITH DEFAULT 1) IN DATABASE QADB1;",
    "table.identity-cardinality": DB + "CREATE TABLE S.T (C DECIMAL(9, 2) GENERATED ALWAYS AS IDENTITY) IN DATABASE QADB1;",
    "table.generated-cardinality": DB + "CREATE TABLE S.T (A TIMESTAMP NOT NULL GENERATED ALWAYS FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP, "
                                   "B TIMESTAMP NOT NULL GENERATED ALWAYS FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP) IN DATABASE QADB1;",
    "table.generated-not-null": DB + "CREATE TABLE S.T (A TIMESTAMP GENERATED ALWAYS FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP) IN DATABASE QADB1;",
    "table.key-column-missing": DB + "CREATE TABLE S.T (C INTEGER NOT NULL, PRIMARY KEY (D)) IN DATABASE QADB1;",
    "table.key-not-null": DB + "CREATE TABLE S.T (C INTEGER, PRIMARY KEY (C)) IN DATABASE QADB1;",
    "table.key-column-type": DB + "CREATE TABLE S.T (C CLOB(1M) NOT NULL, PRIMARY KEY (C)) IN DATABASE QADB1;",
    "table.primary-key-cardinality": DB + "CREATE TABLE S.T (C INTEGER NOT NULL PRIMARY KEY, D INTEGER NOT NULL, PRIMARY KEY (D)) IN DATABASE QADB1;",
    "table.key-count": DB + "CREATE TABLE S.T (C INTEGER NOT NULL, UNIQUE (C, C)) IN DATABASE QADB1;",
    "table.key-length": DB + "CREATE TABLE S.T (A CHAR(255) NOT NULL, B VARCHAR(2000) NOT NULL, PRIMARY KEY (A, B)) IN DATABASE QADB1;",
    "table.fk-key-length": DB + "CREATE TABLE S.P (A CHAR(200) NOT NULL, B CHAR(100) NOT NULL, PRIMARY KEY (A, B)) IN DATABASE QADB1;\n"
                           "CREATE TABLE S.C (A CHAR(200), B CHAR(100), FOREIGN KEY (A, B) REFERENCES S.P) IN DATABASE QADB1;",
    "table.fk-self-reference": DB + "CREATE TABLE S.T (C INTEGER NOT NULL PRIMARY KEY, P INTEGER REFERENCES S.T) IN DATABASE QADB1;",
    "table.fk-parent-key": DB + "CREATE TABLE S.P (A INTEGER NOT NULL, B INTEGER NOT NULL, PRIMARY KEY (A, B)) IN DATABASE QADB1;\n"
                           "CREATE TABLE S.C (A INTEGER, B INTEGER, FOREIGN KEY (B, A) REFERENCES S.P (B, A)) IN DATABASE QADB1;",
    "table.fk-arity": DB + "CREATE TABLE S.P (A INTEGER NOT NULL, B INTEGER NOT NULL, PRIMARY KEY (A, B)) IN DATABASE QADB1;\n"
                      "CREATE TABLE S.C (A INTEGER, FOREIGN KEY (A) REFERENCES S.P) IN DATABASE QADB1;",
    "table.fk-type-identity": DB + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
                              "CREATE TABLE S.C (A BIGINT, FOREIGN KEY (A) REFERENCES S.P) IN DATABASE QADB1;",
    "table.fk-set-null": DB + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
                         "CREATE TABLE S.C (A INTEGER NOT NULL REFERENCES S.P ON DELETE SET NULL) IN DATABASE QADB1;",
    "table.fk-parent-unique-index": DB + TS + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY) IN QADB1.TS1;\n"
                                    "CREATE TABLE S.C (A INTEGER REFERENCES S.P) IN DATABASE QADB1;",
    "table.fk-business-time": DB + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
                              "CREATE TABLE S.C (A INTEGER, FOREIGN KEY (A, PERIOD BUSINESS_TIME) REFERENCES S.P (A)) IN DATABASE QADB1;",
    "table.check-length": DB + "CREATE TABLE S.T (C VARCHAR(10), CHECK (C IN (" + ", ".join(f"'V{i:05d}'" for i in range(500)) + "))) IN DATABASE QADB1;",
    "table.explicit-space-physical-conflict": DB + TS + "CREATE TABLE S.T (C INTEGER) IN QADB1.TS1 COMPRESS YES;",
    "table.tablespace-eligibility": DB + TS + "CREATE TABLE S.A (C INTEGER) IN QADB1.TS1;\nCREATE TABLE S.B (C INTEGER) IN QADB1.TS1;",
    "table.partitioning-mismatch": DB + "CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2;\nCREATE TABLE S.T (C INTEGER) IN QADB1.TS1;",
    "table.partition-key-length": DB + "CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 1;\n"
                                  "CREATE TABLE S.T (A CHAR(255), B CHAR(10)) IN QADB1.TS1 PARTITION BY RANGE (A, B) (PARTITION 1 ENDING AT (MAXVALUE, MAXVALUE));",
    "table.period-columns": DB + "CREATE TABLE S.T (B TIMESTAMP, E TIMESTAMP, PERIOD FOR BUSINESS_TIME (B, E)) IN DATABASE QADB1;",
    "table.incomplete-definition": DB + TS + "CREATE TABLE S.T (C INTEGER NOT NULL PRIMARY KEY) IN QADB1.TS1;",
    "table.lob-auxiliary-missing": DB + TS + "CREATE TABLE S.T (C CLOB(1M)) IN QADB1.TS1;",
    "table.row-length": DB + TS + "CREATE TABLE S.T (" + ", ".join(f"C{i} CHAR(255)" for i in range(17)) + ") IN QADB1.TS1;",
    "table.cast-default-distinct": DB + "CREATE TABLE S.T (C DATE WITH DEFAULT DATE('2024-01-01')) IN DATABASE QADB1;",
    "table.copy-definition-unchecked": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE TABLE S.U LIKE S.T IN DATABASE QADB1;",
    "auxtable.placement": DB + TS + "CREATE TABLE S.T (C CLOB(1M)) IN QADB1.TS1;\n"
                          "CREATE AUX TABLE S.X IN QADB1.TS1 STORES S.T COLUMN C PART 1;",
    "auxtable.part-required": DB + TS + "CREATE LOB TABLESPACE LS1 IN QADB1;\nCREATE TABLE S.T (C CLOB(1M)) IN QADB1.TS1;\n"
                              "CREATE AUX TABLE S.X IN QADB1.LS1 STORES S.T COLUMN C;\nCREATE UNIQUE INDEX S.XI ON S.X;",
    "index.column-missing": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (D);",
    "index.key-count": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C, C);",
    "index.key-column-type": DB + "CREATE TABLE S.T (C CLOB(1M)) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C);",
    "index.key-length": DB + "CREATE TABLE S.T (A VARCHAR(1500), B VARCHAR(600)) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (A, B) PADDED;",
    "index.include-requires-unique": DB + "CREATE TABLE S.T (C INTEGER, D INTEGER) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C) INCLUDE (D);",
    "index.include-columns": DB + "CREATE TABLE S.T (C INTEGER, D DECFLOAT) IN DATABASE QADB1;\nCREATE UNIQUE INDEX S.I ON S.T (C) INCLUDE (D);",
    "index.partitioned-pbg": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C) PARTITIONED;",
    "index.unique-partitioned-superset": DB + "CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2;\n"
                                         "CREATE TABLE S.T (K INTEGER NOT NULL, C INTEGER NOT NULL) IN QADB1.TS1 PARTITION BY RANGE (K) "
                                         "(PARTITION 1 ENDING AT (10), PARTITION 2 ENDING AT (MAXVALUE));\n"
                                         "CREATE UNIQUE INDEX S.I ON S.T (C) PARTITIONED;",
    "index.cluster": DB + "CREATE TABLE S.T (C INTEGER, D INTEGER) IN DATABASE QADB1;\n"
                     "CREATE INDEX S.I1 ON S.T (C) CLUSTER;\nCREATE INDEX S.I2 ON S.T (D) CLUSTER;",
    "index.order-restrictions": DB + "CREATE TABLE S.T (C DECFLOAT) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C RANDOM);",
    "index.free-space-range": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C) PCTFREE 100;",
    "index.auxiliary": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE UNIQUE INDEX S.I ON S.T;",
    "index.padding-environment": (DB + "CREATE TABLE S.T (C VARCHAR(10)) IN DATABASE QADB1;\nCREATE INDEX S.I ON S.T (C);", {}, ("notice",)),
    "cleanup.drop-enforcing-index": DB + TS + "CREATE TABLE S.T (C INTEGER NOT NULL PRIMARY KEY) IN QADB1.TS1;\n"
                                    "CREATE UNIQUE INDEX S.I ON S.T (C);\nDROP INDEX S.I;",
    "fl.applcompat-gate": (DB + "CREATE TABLESPACE TS1 IN QADB1 COMPRESS YES HUFFMAN;", {"applcompat": "V12R1M508", "function_level": "V13R1M500"}),
    "fl.function-level-gate": ("INSERT INTO S.T (C) VALUES (1), (2);", {"applcompat": "V13R1M500", "function_level": "V13R1M500"}),
    "fl.profile-inconsistent": ("COMMIT;", {"applcompat": "V13R1M508", "function_level": "V13R1M500"}),
    "fl.requirements": (DB + "CREATE TABLESPACE TS1 IN QADB1 COMPRESS YES HUFFMAN;", {}, ("notice",)),
    "fl.removed-feature": "CREATE SYNONYM S.SYN FOR S.T;",
    "fl.behavior-change": (DB + TS, {}, ("notice",)),
    "fl.deprecated-feature": DB + "CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2 PAGENUM ABSOLUTE;",
    "scope.not-checked": ("CREATE VIEW S.V AS SELECT 1 AS X FROM SYSIBM.SYSDUMMY1;", {}, ("notice",)),
}


class CatalogIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.catalog = qa.read(paths.DDL_CHECKS)
        self.kb = qa.read(paths.CREATE_DDL)
        self.ids = [rule["id"] for rule in self.catalog["rules"]]

    def test_rules_are_unique_sourced_and_reference_known_kb_rules(self):
        self.assertEqual(len(self.ids), len(set(self.ids)))
        kb_rules = {f"{o}.{r['id']}" for o, obj in self.kb["objects"].items() for r in obj["rules"]}
        for rule in self.catalog["rules"]:
            self.assertIn(rule["severity"], self.catalog["severity_policy"], rule["id"])
            self.assertTrue(rule["source_refs"], rule["id"])
            for source in rule["source_refs"]:
                self.assertIn(source, self.kb["sources"], rule["id"])
                self.assertTrue(self.kb["sources"][source]["url"].startswith("https://www.ibm.com/docs/"), source)
            self.assertFalse(set(rule["kb_rules"]) - kb_rules, rule["id"])

    def test_every_rule_has_a_triggering_fixture(self):
        self.assertEqual(set(self.ids), set(NEGATIVE), "add or remove NEGATIVE fixtures to match the rule catalog")
        for rule, case in NEGATIVE.items():
            sql, options, severities = (case, {}, None) if isinstance(case, str) else (case + ((None,) if len(case) == 2 else ()))[:3]
            severities = severities or ("error", "unsupported", "warning", "notice")
            with self.subTest(rule=rule):
                found = rules(sql, severities, **options)
                self.assertIn(rule, found, f"{rule} not raised; got {sorted(found)}")

    def test_code_and_catalog_use_the_same_rule_ids(self):
        code = (ROOT / "tools/db2check.py").read_text() + (ROOT / "tools/db2sql.py").read_text()
        prefixes = {i.split(".")[0] for i in self.ids}
        calls = r'(?:find|add|append|Unsupported)\(\(?"([a-z]+\.[a-z0-9-]+)"'
        used = set(re.findall(calls, code)) | set(re.findall(r'\("([a-z]+\.[a-z0-9-]+)", (?:f?"|str\()', code))
        used = {u for u in used if u.split(".")[0] in prefixes}
        self.assertTrue(used, "the scan found no rule IDs; update the pattern")
        self.assertFalse(used - set(self.ids), "rule IDs used in code but missing from the catalog")

    def test_function_level_data_resolves_sources_and_clauses(self):
        data = qa.read(paths.FUNCTION_LEVELS)
        clauses = {f"{o}.{c['id']}" for o, obj in self.kb["objects"].items() for c in obj["clauses"]}
        levels = [level["id"] for level in data["levels"]]
        self.assertEqual(levels, ["V13R1M100"] + [f"V13R1M5{n:02d}" for n in range(0, 10)])
        refs = {level["source_ref"] for level in data["levels"]} | set(data["source_refs"])
        refs |= {item["source_ref"] for group in ("applcompat_gates", "behavior_changes", "deprecations", "announced_levels") for item in data[group]}
        self.assertFalse(refs - self.kb["sources"].keys())
        for group in ("applcompat_gates", "deprecations"):
            for item in data[group]:
                self.assertFalse(set(item["kb_clauses"]) - clauses, item)
        for level in data["levels"]:
            for note in level["ddl_notes"]:
                self.assertFalse(set(note["kb_clauses"]) - clauses, note["id"])
                self.assertFalse(set(note["checker_rules"]) - set(self.ids), note["id"])
        for gate in data["applcompat_gates"]:
            self.assertIsNotNone(db2check.level_key(gate["applcompat"]), gate["id"])
        code = (ROOT / "tools/db2check.py").read_text()
        for gate in re.findall(r'require\("([a-z0-9-]+)"', code) + list(db2check.TOKEN_GATES.values()):
            self.assertIn(gate, {g["id"] for g in data["applcompat_gates"]})

    def test_chapters_match_the_data(self):
        chapter = (paths.KB / "function-levels.md").read_text()
        data = qa.read(paths.FUNCTION_LEVELS)
        for item in data["levels"] + data["applcompat_gates"] + data["announced_levels"]:
            self.assertIn(item["id"], chapter)
        traps = (paths.KB / "dialect-traps.md").read_text()
        mentioned = set(re.findall(r"`([a-z]+\.[a-z0-9-]+)`", traps)) - {"*"}
        self.assertFalse({m for m in mentioned if not m.startswith("tablespace.*")} - set(self.ids))

    def test_catalog_queries_use_only_verified_columns(self):
        columns = qa.read(paths.CATALOG_COLUMNS)["tables"]
        for table, data in columns.items():
            self.assertIn(data["source_ref"], self.kb["sources"], table)
            self.assertTrue(data["columns"], table)


class SplitterAndParserTests(unittest.TestCase):
    def test_terminators_literals_comments_and_directives(self):
        text = ("CREATE TABLE S.T (C CHAR(3) WITH DEFAULT ';;') IN DATABASE QADB1; -- trailing ; comment\n"
                "/* ; */ COMMIT;\n--#SET TERMINATOR @\nCREATE TRIGGER S.TR AFTER INSERT ON S.T FOR EACH ROW BEGIN ATOMIC\n"
                "  SET X = 1; SET Y = 2;\nEND@\n--#SET TERMINATOR ;\nCOMMIT;\n")
        statements = db2sql.split_script(text)
        self.assertEqual([s.terminator for s in statements], [";", ";", "@", ";"])
        self.assertIn("';;'", statements[0].sql)
        self.assertIn("SET Y = 2;", statements[2].sql)
        self.assertEqual(statements[2].line, 4)

    def test_crlf_and_unclosed_literal(self):
        self.assertEqual(len(db2sql.split_script("COMMIT;\r\nCOMMIT;\r\n")), 2)
        with self.assertRaises(db2sql.ParseError):
            db2sql.split_script("CREATE TABLE S.T (C CHAR(1) DEFAULT 'x);")

    def test_type_spellings_normalize_for_foreign_keys(self):
        sql = (DB + "CREATE TABLE S.P (A INT NOT NULL, B CHARACTER VARYING(10) NOT NULL, D NUMERIC(5) NOT NULL, PRIMARY KEY (A, B, D)) IN DATABASE QADB1;\n"
               "CREATE TABLE S.C (A INTEGER, B VARCHAR(10), D DECIMAL(5, 0), FOREIGN KEY (A, B, D) REFERENCES S.P) IN DATABASE QADB1;")
        self.assertNotIn("table.fk-type-identity", rules(sql))

    def test_partial_statement_does_not_cascade_findings(self):
        sql = (DB + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY, B INTEGER REFERENCES S.X ON UPDATE CASCADE) IN DATABASE QADB1;\n"
               "CREATE TABLE S.C (A BIGINT REFERENCES S.P) IN DATABASE QADB1;")
        found = rules(sql)
        self.assertIn("dialect.referential-on-update", found)
        self.assertNotIn("table.fk-type-identity", found)


class LintBehaviorTests(unittest.TestCase):
    def test_exemplar_is_clean_and_meets_the_core_baseline(self):
        report = db2check.analyze(EXAMPLE.read_text(), db2check.Options.from_profile(PROFILE))
        self.assertFalse([f.as_dict(report.rules) for f in report.findings if f.severity != "notice"])
        result = db2check.coverage(report, db2check.load_baseline("core"))
        self.assertTrue(result["baseline"]["complete"], result["baseline"]["unmet"])
        self.assertFalse(db2check.coverage(report, db2check.load_baseline("extended"))["baseline"]["complete"])

    def test_all_campaign_model_cases_are_lint_clean(self):
        for model in qa.models().values():
            _, valid = qa.candidates(model)
            for selection in valid[:: max(1, len(valid) // 12)]:
                record, contract = qa.make_case(model, selection, PROFILE, "QA", 1)
                terminator = contract["statement_terminator"]
                sql = (DB.replace("SYSDEFLT", PROFILE["storage_group"]) if model.get("uses_database", True) else "")
                if terminator != ";":
                    sql += f"--#SET TERMINATOR {terminator}\n"
                sql += qa.sql_file(record["setup_sql"] + record["action_sql"], "", terminator)
                report = db2check.analyze(sql.replace("QADB1", "QASDB"), db2check.Options(assume=["stogroup:" + PROFILE["storage_group"]]))
                with self.subTest(model=model["id"], selection=selection):
                    self.assertFalse([f.as_dict(report.rules) for f in report.findings if f.severity in ("error", "unsupported", "warning")])

    def test_legacy_workload_is_clean_and_needs_v13r1m506(self):
        text = (paths.WORKLOAD_1000).read_text()
        report = db2check.analyze(text, db2check.Options.from_profile(profile("V13R1M509"), allow_placeholders=True))
        self.assertFalse([f.rule for f in report.findings if f.severity in ("error", "unsupported", "warning")])
        self.assertEqual(report.compatibility["minimum_applcompat"], "V13R1M506")
        self.assertEqual(len(report.tables), 1000)

    def test_self_reference_through_alter_table_is_accepted(self):
        sql = (DB + TS + "CREATE TABLE S.T (C INTEGER NOT NULL, P INTEGER, PRIMARY KEY (C)) IN QADB1.TS1;\n"
               "CREATE UNIQUE INDEX S.I ON S.T (C);\nALTER TABLE S.T ADD FOREIGN KEY (P) REFERENCES S.T ON DELETE SET NULL;")
        self.assertFalse(rules(sql))

    def test_enforcing_index_must_match_column_order(self):
        base = DB + TS + "CREATE TABLE S.T (A INTEGER NOT NULL, B INTEGER NOT NULL, PRIMARY KEY (A, B)) IN QADB1.TS1;\n"
        self.assertIn("table.incomplete-definition", rules(base + "CREATE UNIQUE INDEX S.I ON S.T (B, A);"))
        self.assertNotIn("table.incomplete-definition", rules(base + "CREATE UNIQUE INDEX S.I ON S.T (A, B);"))
        self.assertIn("table.incomplete-definition", rules(base + "CREATE UNIQUE WHERE NOT NULL INDEX S.I ON S.T (A, B);"))

    def test_without_overlaps_key_needs_matching_index(self):
        base = (DB + TS + "CREATE TABLE S.T (K INTEGER NOT NULL, B DATE NOT NULL, E DATE NOT NULL, PERIOD FOR BUSINESS_TIME (B, E), "
                "PRIMARY KEY (K, BUSINESS_TIME WITHOUT OVERLAPS)) IN QADB1.TS1;\n")
        self.assertIn("table.incomplete-definition", rules(base + "CREATE UNIQUE INDEX S.I ON S.T (K);"))
        self.assertNotIn("table.incomplete-definition", rules(base + "CREATE UNIQUE INDEX S.I ON S.T (K, BUSINESS_TIME WITHOUT OVERLAPS);"))

    def test_explicit_lob_objects_complete_the_table(self):
        sql = (DB + TS + "CREATE LOB TABLESPACE LS1 IN QADB1;\nCREATE TABLE S.T (C CLOB(1M)) IN QADB1.TS1;\n"
               "CREATE AUX TABLE S.X IN QADB1.LS1 STORES S.T COLUMN C PART 1;\nCREATE UNIQUE INDEX S.XI ON S.X;")
        self.assertFalse(rules(sql))

    def test_column_name_limit_depends_on_profile(self):
        sql = DB + "CREATE TABLE S.T (" + "C" * 40 + " INTEGER) IN DATABASE QADB1;"
        self.assertIn("name.length", rules(sql))
        options = db2check.Options.from_profile(profile(TABLE_COL_NAME_EXPANSION="ON"))
        self.assertEqual(options.column_name_expansion, True)
        report = db2check.analyze(sql, options)
        self.assertEqual({f.rule for f in report.findings if f.severity != "notice"}, {"name.column-expansion"})

    def test_varying_length_limit_follows_page_size(self):
        sql = DB + TS + "CREATE TABLE S.T (C VARCHAR(5000)) IN QADB1.TS1;"
        self.assertIn("table.data-type-range", rules(sql))
        self.assertNotIn("table.data-type-range", rules(sql.replace("IN QADB1;", "IN QADB1 BUFFERPOOL BP8K0;")))

    def test_function_level_gates_against_profile(self):
        sql = DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 2 COMPRESS YES HUFFMAN;\nCREATE TABLE S.T (C INTEGER) IN QADB1.TS1;"
        self.assertNotIn("fl.applcompat-gate", rules(sql, **{"applcompat": "V12R1M509", "function_level": "V13R1M500"}))
        self.assertIn("fl.applcompat-gate", rules(sql, **{"applcompat": "V12R1M508", "function_level": "V13R1M500"}))
        workfile = "CREATE DATABASE WF1 AS WORKFILE;\nCREATE TABLESPACE W1 IN WF1 MAXPARTITIONS 2 FOR DGTT;"
        found = rules(workfile, **{"applcompat": "V13R1M507", "function_level": "V13R1M509"})
        self.assertIn("fl.applcompat-gate", found)
        self.assertNotIn("tablespace.workfile-usage", found)
        self.assertNotIn("fl.applcompat-gate", rules(workfile, **{"applcompat": "V13R1M508", "function_level": "V13R1M508"}))
        report = analyze(sql)
        self.assertEqual(report.compatibility["minimum_applcompat"], "V12R1M509")

    def test_removed_features_downgrade_only_below_uts_baseline(self):
        sql = DB + "CREATE TABLE S.T (C INTEGER NOT NULL) IN DATABASE QADB1 ORGANIZE BY HASH UNIQUE (C);"
        self.assertIn("fl.removed-feature", rules(sql))
        found = rules(sql, applcompat="V12R1M503", function_level="V13R1M500")
        self.assertIn("fl.deprecated-feature", found)
        self.assertNotIn("fl.removed-feature", found)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / "good.sql", Path(tmp) / "bad.sql"
            good.write_text(DB)
            bad.write_text("CREATE DATABASE TOOLONGNAME;")
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / "tools/ddl.py"), *a], capture_output=True, text=True)
            self.assertEqual(run("lint", str(good)).returncode, 0)
            result = run("lint", str(bad), "--json")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "fail")
            self.assertEqual(run("lint", str(Path(tmp) / "missing.sql")).returncode, 2)
            self.assertEqual(run("coverage", str(good), "--baseline", "core").returncode, 1)
            self.assertEqual(run("coverage", str(EXAMPLE), "--baseline", "core").returncode, 0)
            levels = json.loads(run("levels", "--applcompat", "V13R1M505", "--json").stdout)
            unavailable = {g["id"] for g in levels["unavailable"]}
            self.assertIn("multirow-insert", unavailable)
            self.assertNotIn("interpret-function", unavailable)
            self.assertIn("pbg-default-maxpartitions", {b["id"] for b in levels["behavior_in_effect"]})
            self.assertEqual(run("levels", "--applcompat", "V9").returncode, 2)


class DiffTests(unittest.TestCase):
    def diff(self, source, target, names=None, prof=None):
        return db2check.diff(analyze(source), analyze(target), names, prof)

    def statuses(self, result):
        return {(d["status"], d.get("attribute")) for d in result["differences"]}

    def test_documented_defaults_and_environment_defaults(self):
        source = DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 4 CLOSE YES LOCKSIZE ROW LOCKMAX SYSTEM SEGSIZE 32;"
        target = DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 4 LOCKSIZE ROW;"
        result = self.diff(source, target)
        self.assertEqual(result["status"], "mismatch")
        self.assertIn(("equivalent-default", "close"), self.statuses(result))
        self.assertIn(("different", "lockmax"), self.statuses(result))
        self.assertIn(("environment-dependent", "segsize"), self.statuses(result))
        resolved = self.diff(source, target, prof=profile(DPSEGSZ=0))
        self.assertIn(("equivalent-default", "segsize"), self.statuses(resolved))

    def test_maxpartitions_default_depends_on_applcompat(self):
        source, target = DB + "CREATE TABLESPACE TS1 IN QADB1 MAXPARTITIONS 254;", DB + "CREATE TABLESPACE TS1 IN QADB1;"
        self.assertIn(("environment-dependent", "maxpartitions"), self.statuses(self.diff(source, target)))
        self.assertIn(("equivalent-default", "maxpartitions"), self.statuses(self.diff(source, target, prof=profile("V13R1M500"))))
        self.assertIn(("different", "maxpartitions"), self.statuses(self.diff(source, target, prof=profile("V12R1M510", "V13R1M100"))))

    def test_name_mapping_types_identity_and_constraints(self):
        source = (DB + "CREATE TABLE S.P (K INT NOT NULL GENERATED ALWAYS AS IDENTITY, V VARCHAR(10), PRIMARY KEY (K)) IN DATABASE QADB1;\n"
                  "CREATE TABLE S.C (K INTEGER, CHECK (K > 0), FOREIGN KEY (K) REFERENCES S.P) IN DATABASE QADB1;")
        target = (DB.replace("QADB1", "QADB2") + "CREATE TABLE R.P (K INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY (START WITH 1, INCREMENT BY 1, CACHE 20, NO CYCLE, NO ORDER), "
                  "V CHARACTER VARYING(10), PRIMARY KEY (K)) IN DATABASE QADB2;\n"
                  "CREATE TABLE R.C (K INTEGER, CHECK (K > 0), FOREIGN KEY (K) REFERENCES R.P ON DELETE RESTRICT) IN DATABASE QADB2;")
        names = db2check.NameMap({"S": "R"}, {"QADB1": "QADB2"})
        self.assertEqual(self.diff(source, target, names)["status"], "match")
        changed = target.replace("CHECK (K > 0)", "CHECK (K >= 0)").replace("CACHE 20", "CACHE 50")
        result = self.diff(source, changed, names)
        attributes = {d.get("attribute") for d in result["differences"]}
        self.assertIn("check constraints", attributes)
        self.assertIn("column K.identity", attributes)

    def test_missing_extra_and_literal_defaults(self):
        source = DB + "CREATE TABLE S.T (C CHAR(3) WITH DEFAULT 'A  ') IN DATABASE QADB1;"
        target = DB + "CREATE TABLE S.T (C CHAR(3) WITH DEFAULT 'A') IN DATABASE QADB1;\nCREATE TABLE S.X (C INTEGER) IN DATABASE QADB1;"
        result = self.diff(source, target)
        self.assertIn(("different", "column C.default_text"), self.statuses(result))
        self.assertIn(("extra", None), self.statuses(result))
        self.assertEqual(self.diff(target, source)["status"], "mismatch")


class BundleTests(unittest.TestCase):
    def make(self, text=None, **names):
        text = text or EXAMPLE.read_text()
        report = db2check.analyze(text, db2check.Options.from_profile(PROFILE))
        mapping = db2check.NameMap(names.get("schemas", {"QAV": "QAVR"}), names.get("databases", {"QAVDB01": "QAVDB02"}))
        return report, db2check.bundle(report, text, mapping, "VX1", PROFILE)

    def test_bundle_case_and_contract_round_trip_through_compare(self):
        _, files = self.make()
        self.assertEqual(files["source.sql"], EXAMPLE.read_text())
        qa.validate_case(json.loads(files["case.json"]))
        contract = json.loads(files["catalog-contract.json"])
        self.assertIn("DROP DATABASE QAVDB01", files["cleanup-source.sql"])
        self.assertIn("DROP DATABASE QAVDB02", files["cleanup-replay.sql"])
        self.assertTrue(all(len(line) <= 72 for line in files["catalog-source.sql"].splitlines()))
        # Build snapshots that satisfy every encoded expectation, then compare.
        snapshots = {}
        for side in ("source", "replay"):
            catalog = {}
            for query in contract["catalog"]:
                by_key = {}
                for assertion in (a for a in contract["assertions"] if a["catalog"] == query["id"]):
                    key = json.dumps(sorted(assertion["where"].items()))
                    row = by_key.setdefault(key, {f: f"{query['id']}-{len(by_key)}" for f in query["fields"]})
                    row.update(assertion["where"])
                    row.update(assertion["equals"])
                rows = list(by_key.values())
                while len(rows) < query["min_rows"]:
                    rows.append({f: f"{query['id']}-filler-{len(rows)}" for f in query["fields"]})
                catalog[query["id"]] = rows
            snapshots[side] = {"case_id": contract["case_id"], "side": side, "catalog": catalog}
        self.assertEqual(qa.compare(contract, snapshots["source"], snapshots["replay"])["status"], "match")
        broken = copy.deepcopy(snapshots["replay"])
        broken["catalog"]["tablespaces_1"][0]["SEGSIZE"] = 999
        self.assertEqual(qa.compare(contract, snapshots["source"], broken)["status"], "mismatch")

    def test_bundle_refuses_failing_scripts_and_missing_names(self):
        with self.assertRaisesRegex(ValueError, "lint"):
            self.make("CREATE DATABASE TOOLONGNAME;")
        with self.assertRaisesRegex(ValueError, "--replay-schema QAV"):
            self.make(schemas={})
        with self.assertRaisesRegex(ValueError, "8 bytes"):
            self.make(databases={"QAVDB01": "QAVDB0001"})

    def test_cli_bundle_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            args = [sys.executable, str(ROOT / "tools/ddl.py"), "bundle", str(EXAMPLE), "--run", "VX1", "--out", str(out),
                    "--profile", str(paths.EXAMPLE_PROFILE),
                    "--replay-schema", "QAV=QAVR", "--replay-database", "QAVDB01=QAVDB02"]
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 0)
            self.assertEqual((out / "source.sql").read_bytes(), EXAMPLE.read_bytes())
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
