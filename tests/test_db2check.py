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
    "table.fk-self-reference-delete-rule": DB + "CREATE TABLE S.T (C INTEGER NOT NULL PRIMARY KEY, P INTEGER) IN DATABASE QADB1;\n"
                                           "ALTER TABLE S.T ADD FOREIGN KEY (P) REFERENCES S.T;",
    "table.alter-key-needs-index": DB + TS + "CREATE TABLE S.T (C INTEGER NOT NULL) IN QADB1.TS1;\nALTER TABLE S.T ADD PRIMARY KEY (C);",
    "table.fk-delete-paths": DB + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY, B INTEGER NOT NULL UNIQUE) IN DATABASE QADB1;\n"
                             "CREATE TABLE S.C (A INTEGER REFERENCES S.P ON DELETE RESTRICT, B INTEGER REFERENCES S.P (B) ON DELETE SET NULL) "
                             "IN DATABASE QADB1;",
    "table.fk-delete-cycle": DB + "CREATE TABLE S.A (K INTEGER NOT NULL PRIMARY KEY, B INTEGER) IN DATABASE QADB1;\n"
                             "CREATE TABLE S.B (K INTEGER NOT NULL PRIMARY KEY, A INTEGER REFERENCES S.A ON DELETE CASCADE) IN DATABASE QADB1;\n"
                             "ALTER TABLE S.A ADD FOREIGN KEY (B) REFERENCES S.B ON DELETE CASCADE;",
    "table.fk-set-null-partitioning-key": DB + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
                                          "CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2;\n"
                                          "CREATE TABLE S.C (K INTEGER, A INTEGER) IN QADB1.TS1 PARTITION BY (K) "
                                          "(PARTITION 1 ENDING AT (10), PARTITION 2 ENDING AT (MAXVALUE));\n"
                                          "CREATE INDEX S.CI ON S.C (K, A) PARTITIONED;\n"
                                          "ALTER TABLE S.C ADD FOREIGN KEY (K) REFERENCES S.P ON DELETE SET NULL;",
    "table.alter-clause-for-table-kind": "ALTER TABLE SYSIBM.SYSTABLES AUDIT ALL;",
    "table.data-capture-not-logged": DB + "CREATE TABLESPACE TS1 IN QADB1 NOT LOGGED;\n"
                                     "CREATE TABLE S.T (C INTEGER) IN QADB1.TS1 DATA CAPTURE CHANGES;",
    "syntax.alter-add-required": DB + "CREATE TABLE S.T (C INTEGER NOT NULL) IN DATABASE QADB1;\nALTER TABLE S.T CHECK (C > 0);",
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

    def test_self_reference_through_alter_table_needs_cascade_or_no_action(self):
        base = (DB + TS + "CREATE TABLE S.T (C INTEGER NOT NULL, P INTEGER, PRIMARY KEY (C)) IN QADB1.TS1;\n"
                "CREATE UNIQUE INDEX S.I ON S.T (C);\n")
        for rule in ("CASCADE", "NO ACTION"):
            with self.subTest(rule=rule):
                self.assertFalse(rules(base + f"ALTER TABLE S.T ADD FOREIGN KEY (P) REFERENCES S.T ON DELETE {rule};"))
        for clause in (" ON DELETE SET NULL", " ON DELETE RESTRICT", ""):
            with self.subTest(clause=clause):
                found = rules(base + f"ALTER TABLE S.T ADD FOREIGN KEY (P) REFERENCES S.T{clause};")
                self.assertEqual({"table.fk-self-reference-delete-rule"}, found)
        # The omitted rule follows CURRENT RULES when the ALTER runs: NO ACTION under 'STD'.
        self.assertFalse(rules(base + "SET CURRENT RULES = 'STD';\nALTER TABLE S.T ADD FOREIGN KEY (P) REFERENCES S.T;"))

    def test_alter_table_follows_the_sql_reference(self):
        parent = DB + "CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
        child = parent + "CREATE TABLE S.C (A INTEGER) IN DATABASE QADB1;\n"
        # ADD may be omitted before a first unique or referential constraint, and a name may follow FOREIGN KEY.
        for statement in ("ALTER TABLE S.C FOREIGN KEY (A) REFERENCES S.P;", "ALTER TABLE S.C CONSTRAINT F1 FOREIGN KEY (A) REFERENCES S.P;",
                          "ALTER TABLE S.C ADD FOREIGN KEY F1 (A) REFERENCES S.P;", "ALTER TABLE S.C FOREIGN KEY F1 (A) REFERENCES S.P APPEND YES;"):
            with self.subTest(statement=statement):
                self.assertFalse(rules(child + statement))
                self.assertNotIn("ALTER TABLE", analyze(child + statement).not_checked)
        sample = DB + ("CREATE TABLE S.DEPT (DEPTNO CHAR(3) NOT NULL PRIMARY KEY, ADMRDEPT CHAR(3) NOT NULL) IN DATABASE QADB1;\n"
                       "ALTER TABLE S.DEPT FOREIGN KEY RDD (ADMRDEPT) REFERENCES S.DEPT ON DELETE CASCADE;")
        self.assertFalse(rules(sample))
        for statement in ("ALTER TABLE S.C APPEND YES FOREIGN KEY (A) REFERENCES S.P;", "ALTER TABLE S.C CONSTRAINT K CHECK (A > 0);"):
            with self.subTest(statement=statement):
                self.assertEqual({"syntax.alter-add-required"}, rules(child + statement))
        self.assertIn("script.parse-error", rules(child + "ALTER TABLE S.C ADD CONSTRAINT F1 FOREIGN KEY F2 (A) REFERENCES S.P;"))
        self.assertEqual({"name.duplicate-constraint"}, rules(child + "ALTER TABLE S.C ADD CONSTRAINT F1 FOREIGN KEY (A) REFERENCES S.P;\n"
                                                                       "ALTER TABLE S.C ADD CONSTRAINT F1 CHECK (A > 0);"))
        # A key added by ALTER needs its unique index first unless Db2 created the table space.
        explicit = DB + TS + "CREATE TABLE S.T (C INTEGER NOT NULL) IN QADB1.TS1;\n"
        self.assertEqual({"table.alter-key-needs-index"}, rules(explicit + "ALTER TABLE S.T ADD UNIQUE (C);\nCREATE UNIQUE INDEX S.I ON S.T (C);"))
        self.assertFalse(rules(explicit + "CREATE UNIQUE INDEX S.I ON S.T (C);\nALTER TABLE S.T ADD UNIQUE (C);"))
        self.assertFalse(rules(DB + "CREATE TABLE S.T (C INTEGER NOT NULL) IN DATABASE QADB1;\nALTER TABLE S.T PRIMARY KEY (C);"))

    def test_delete_rules_follow_the_delete_connection_rules(self):
        parents = DB + ("CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY, B INTEGER NOT NULL UNIQUE) IN DATABASE QADB1;\n"
                        "CREATE TABLE S.Q (A INTEGER NOT NULL PRIMARY KEY, P INTEGER REFERENCES S.P ON DELETE CASCADE) IN DATABASE QADB1;\n")
        child = "CREATE TABLE S.C (A INTEGER REFERENCES S.P ON DELETE {}, B INTEGER REFERENCES {} ON DELETE {}) IN DATABASE QADB1;"
        cases = {("RESTRICT", "S.P (B)", "RESTRICT"): set(), ("CASCADE", "S.P (B)", "CASCADE"): set(),
                 ("SET NULL", "S.P (B)", "SET NULL"): {"table.fk-delete-paths"},
                 ("NO ACTION", "S.Q", "RESTRICT"): {"table.fk-delete-paths"},  # deletes from P cascade to Q
                 ("RESTRICT", "S.Q", "RESTRICT"): set()}
        for (first, parent, second), expected in cases.items():
            with self.subTest(first=first, parent=parent, second=second):
                self.assertEqual(expected, rules(parents + child.format(first, parent, second)))
        # A CASCADE self-reference (the SQL Reference's ALTER TABLE example 4) beside a SET NULL cycle between two tables.
        sample = DB + ("CREATE TABLE S.DEPT (DEPTNO CHAR(3) NOT NULL PRIMARY KEY, MGRNO CHAR(6), ADMRDEPT CHAR(3) NOT NULL) IN DATABASE QADB1;\n"
                       "CREATE TABLE S.EMP (EMPNO CHAR(6) NOT NULL PRIMARY KEY, WORKDEPT CHAR(3) REFERENCES S.DEPT ON DELETE SET NULL) "
                       "IN DATABASE QADB1;\n"
                       "ALTER TABLE S.DEPT FOREIGN KEY RDD (ADMRDEPT) REFERENCES S.DEPT ON DELETE CASCADE;\n"
                       "ALTER TABLE S.DEPT FOREIGN KEY RDE (MGRNO) REFERENCES S.EMP ON DELETE {};")
        self.assertFalse(rules(sample.format("SET NULL")))
        self.assertEqual({"table.fk-delete-cycle"}, rules(sample.format("CASCADE")))  # EMP is delete-connected to DEPT
        # SET NULL only matters for the key of a partitioning index.
        partitioned = NEGATIVE["table.fk-set-null-partitioning-key"]
        self.assertNotIn("table.fk-set-null-partitioning-key", rules(partitioned.replace("S.C (K, A) PARTITIONED", "S.C (A, K)")))
        self.assertNotIn("table.fk-set-null-partitioning-key", rules(partitioned.replace("S.C (K, A)", "S.C (K DESC, A)")))

    def test_alter_table_clauses_depend_on_the_kind_of_table(self):
        kinds = {"materialized query": DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\n"
                                            "CREATE TABLE S.M AS (SELECT C FROM S.T) DATA INITIALLY DEFERRED REFRESH DEFERRED IN DATABASE QADB1;\n",
                 "accelerator-only": DB + "CREATE TABLE S.M (C INTEGER) IN ACCELERATOR ACC1;\n",
                 "auxiliary": DB + TS + "CREATE LOB TABLESPACE LS1 IN QADB1;\nCREATE TABLE S.T (C CLOB(1M)) IN QADB1.TS1;\n"
                                        "CREATE AUX TABLE S.M IN QADB1.LS1 STORES S.T COLUMN C PART 1;\nCREATE UNIQUE INDEX S.XI ON S.M;\n"}
        accepted = {"materialized query": "AUDIT ALL DATA CAPTURE CHANGES ADD RESTRICT ON DROP", "accelerator-only": "ADD RESTRICT ON DROP",
                    "auxiliary": "APPEND YES"}
        for kind, script in kinds.items():
            with self.subTest(kind=kind):
                self.assertNotIn("table.alter-clause-for-table-kind", rules(script + f"ALTER TABLE S.M {accepted[kind]};"))
                self.assertIn("table.alter-clause-for-table-kind", rules(script + "ALTER TABLE S.M VOLATILE;"))
        self.assertFalse(rules("ALTER TABLE SYSIBM.SYSTABLES DATA CAPTURE CHANGES;"))
        self.assertEqual({"table.alter-clause-for-table-kind"}, rules("ALTER TABLE SYSIBM.SYSTABLES DATA CAPTURE NONE;"))
        logged = DB + "CREATE TABLESPACE TS2 IN QADB1 NOT LOGGED;\nCREATE TABLE S.T (C INTEGER) IN QADB1.TS2;\n"
        self.assertEqual({"table.data-capture-not-logged"}, rules(logged + "ALTER TABLE S.T DATA CAPTURE CHANGES;"))
        self.assertEqual({"table.data-capture-not-logged"}, rules(DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1 NOT LOGGED DATA CAPTURE CHANGES;"))

    def test_alter_table_options_are_checked(self):
        base = DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\n"
        self.assertFalse(rules(base + "ALTER TABLE S.T DATA CAPTURE CHANGES AUDIT ALL APPEND NO NOT VOLATILE;"))
        self.assertEqual({"syntax.duplicate-clause"}, rules(base + "ALTER TABLE S.T AUDIT ALL AUDIT NONE;"))
        self.assertEqual({"script.parse-error"}, rules(base + "ALTER TABLE S.T DATA CAPTURE SOMETIMES;"))
        self.assertEqual({"dependency.external"}, rules(DB + "ALTER TABLE S.MISSING APPEND YES;"))

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

    def test_partitions_inherit_outer_values_and_using_is_one_block(self):
        source = DB + ("CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2 (PARTITION 1 USING STOGROUP SG2) "
                       "USING STOGROUP SG1 PRIQTY 48 FREEPAGE 10;")
        repeated = DB + ("CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2 (PARTITION 1 USING STOGROUP SG2 FREEPAGE 10, "
                         "PARTITION 2 USING STOGROUP SG1 PRIQTY 48 FREEPAGE 10);")
        self.assertEqual(self.diff(source, repeated)["status"], "match")
        lost = self.diff(source, repeated.replace("PRIQTY 48 FREEPAGE 10", "FREEPAGE 0"))
        self.assertIn(("different", "partition 2 freepage"), self.statuses(lost))
        self.assertIn(("different", "partition 2 priqty"), self.statuses(lost))
        # Partition 1 has its own USING clause, so it does not inherit the outer PRIQTY 48.
        block = self.diff(source, repeated.replace("STOGROUP SG2 FREEPAGE", "STOGROUP SG2 PRIQTY 48 FREEPAGE"))
        self.assertIn(("different", "partition 1 priqty"), self.statuses(block))

    def test_omitted_inclusive_and_delimited_identifiers_are_the_same_definition(self):
        source = DB + ("CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2;\n"
                       "CREATE TABLE S.T (C INTEGER NOT NULL, CHECK (C > 0)) IN QADB1.TS1 "
                       "PARTITION BY (C) (PARTITION 1 ENDING AT (10), PARTITION 2 ENDING AT (maxvalue));")
        target = source.replace("CHECK (C > 0)", 'CHECK ("C" > 0)').replace("(10)", "(10) INCLUSIVE")
        self.assertEqual(self.diff(source, target)["status"], "match")
        self.assertIn(("different", "check constraints"), self.statuses(self.diff(source, target.replace('"C" >', '"c" >'))))

    def test_unnamed_source_constraints_accept_generated_names(self):
        source = DB + "CREATE TABLE S.T (C INTEGER, CHECK (C > 0), CONSTRAINT K2 CHECK (C < 9)) IN DATABASE QADB1;"
        generated = self.diff(source, source.replace("CHECK (C > 0)", "CONSTRAINT C CHECK (C > 0)"))
        self.assertEqual(generated["status"], "match")
        self.assertIn(("equivalent-default", "check constraints"), self.statuses(generated))
        renamed = self.diff(source, source.replace("K2", "K3"))
        self.assertIn(("different", "check constraints"), self.statuses(renamed))
        self.assertEqual("Only constraint names differ.", renamed["differences"][0]["detail"])

    def test_character_subtype_default_follows_encoding_and_mixed_data(self):
        def table(ccsid, subtype=""):
            return DB.replace("INDEXBP BP0", f"INDEXBP BP0 CCSID {ccsid}") + f"CREATE TABLE S.T (C VARCHAR(8){subtype}) IN DATABASE QADB1;"
        self.assertEqual(self.diff(table("UNICODE"), table("UNICODE", " FOR MIXED DATA"))["status"], "match")
        self.assertIn(("different", "column C.subtype"), self.statuses(self.diff(table("UNICODE"), table("UNICODE", " FOR SBCS DATA"))))
        ebcdic = self.diff(table("EBCDIC"), table("EBCDIC", " FOR SBCS DATA"))
        self.assertIn(("environment-dependent", "column C.subtype"), self.statuses(ebcdic))
        self.assertEqual(self.diff(table("EBCDIC"), table("EBCDIC", " FOR SBCS DATA"), prof=profile(MIXED="NO"))["status"], "match")
        self.assertIn(("different", "column C.subtype"), self.statuses(self.diff(table("EBCDIC"), table("EBCDIC", " FOR SBCS DATA"), prof=profile(MIXED="YES"))))
        self.assertIn(("different", "column C.type"), self.statuses(self.diff(table("EBCDIC"), table("EBCDIC", " FOR BIT DATA"))))

    def test_expressions_fieldprocs_and_null_ordering_are_compared(self):
        source = DB + ("CREATE TABLESPACE TS1 IN QADB1 NUMPARTS 2;\n"
                       "CREATE TABLE S.T (C INTEGER, W VARCHAR(128) GENERATED ALWAYS AS (USER), "
                       "F CHAR(8) FIELDPROC S.FP1 (1, 2)) IN QADB1.TS1 "
                       "PARTITION BY (C NULLS LAST DESC) (PARTITION 1 ENDING AT (100), PARTITION 2 ENDING AT (MINVALUE));")
        self.assertEqual(self.diff(source, source.replace("AS (USER)", "AS (SESSION_USER)"))["status"], "match")
        for original, changed, attribute in (("AS (USER)", "AS (CURRENT SQLID)", "column W.generated_expression"),
                                             ("S.FP1 (1, 2)", "S.FP1 (9)", "column F.fieldproc_parameters"),
                                             ("(C NULLS LAST DESC)", "(C DESC)", "partitioning")):
            with self.subTest(changed=changed):
                self.assertIn(("different", attribute), self.statuses(self.diff(source, source.replace(original, changed))))

    def test_alter_table_options_fold_into_the_definition(self):
        options = "AUDIT ALL DATA CAPTURE CHANGES APPEND YES VOLATILE VALIDPROC S.VP1 WITH RESTRICT ON DROP"
        source = DB + f"CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1 {options};"
        altered = (DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1 VALIDPROC S.OLD;\n"
                   "ALTER TABLE S.T DATA CAPTURE CHANGES AUDIT ALL;\n"
                   "ALTER TABLE S.T APPEND YES VOLATILE CARDINALITY ADD RESTRICT ON DROP VALIDPROC S.VP1;")
        self.assertEqual("match", self.diff(source, altered)["status"])
        for later, attribute in (("ALTER TABLE S.T DATA CAPTURE NONE;", "data_capture"), ("ALTER TABLE S.T AUDIT CHANGES;", "audit"),
                                 ("ALTER TABLE S.T NOT VOLATILE;", "volatile"), ("ALTER TABLE S.T VALIDPROC NULL;", "validproc"),
                                 ("ALTER TABLE S.T DROP RESTRICT ON DROP;", "restrict_on_drop")):
            with self.subTest(later=later):
                self.assertIn(("different", attribute), self.statuses(self.diff(source, altered + "\n" + later)))
        # Removing what was never set leaves the documented default.
        plain = DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;"
        self.assertEqual("match", self.diff(plain, plain + "\nALTER TABLE S.T DROP RESTRICT ON DROP DATA CAPTURE NONE;")["status"])
        self.assertIn(("not-compared", None), self.statuses(self.diff(plain, plain + "\nALTER TABLE S.T ADD COLUMN D INTEGER;")))
        # Db2 rejects a statement that does not parse, so none of its clauses apply.
        aborted = self.statuses(self.diff(plain, plain + "\nALTER TABLE S.T DATA CAPTURE CHANGES AUDIT;"))
        self.assertEqual({("not-compared", None)}, aborted)

    def test_alter_table_constraint_forms_order_and_rules_follow_the_manual(self):
        base = DB + ("CREATE TABLE S.P (A INTEGER NOT NULL PRIMARY KEY) IN DATABASE QADB1;\n"
                     "CREATE TABLE S.C (A INTEGER) IN DATABASE QADB1;\n")
        named = base + "ALTER TABLE S.C ADD CONSTRAINT F1 FOREIGN KEY (A) REFERENCES S.P ON DELETE CASCADE;"
        for form in ("ALTER TABLE S.C FOREIGN KEY F1 (A) REFERENCES S.P ON DELETE CASCADE;",
                     "ALTER TABLE S.C CONSTRAINT F1 FOREIGN KEY (A) REFERENCES S.P ON DELETE CASCADE;"):
            with self.subTest(form=form):
                self.assertEqual("match", self.diff(named, base + form)["status"])
        # DROP clauses run before ADD clauses, whatever their written order.
        restricted = DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1 WITH RESTRICT ON DROP;"
        plain = DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\n"
        for clauses in ("DROP RESTRICT ON DROP ADD RESTRICT ON DROP", "ADD RESTRICT ON DROP DROP RESTRICT ON DROP"):
            with self.subTest(clauses=clauses):
                self.assertFalse(rules(plain + f"ALTER TABLE S.T {clauses};"))
                self.assertEqual("match", self.diff(restricted, plain + f"ALTER TABLE S.T {clauses};")["status"])
        # An omitted delete rule follows CURRENT RULES when the ALTER runs, not when the table was created.
        late = base + "SET CURRENT RULES = 'STD';\nALTER TABLE S.C ADD CONSTRAINT F1 FOREIGN KEY (A) REFERENCES S.P;"
        explicit = base + "ALTER TABLE S.C ADD CONSTRAINT F1 FOREIGN KEY (A) REFERENCES S.P ON DELETE {};"
        self.assertEqual("match", self.diff(late, explicit.format("NO ACTION"))["status"])
        self.assertIn(("different", "foreign constraints"), self.statuses(self.diff(late, explicit.format("RESTRICT"))))
        report = analyze(late.replace("S.", "QAV."))
        contract = json.loads(db2check.bundle(report, late.replace("S.", "QAV."), db2check.NameMap({"QAV": "QAVR"}, {"QADB1": "QADB2"}),
                                              "VX1", PROFILE)["catalog-contract.json"])
        self.assertEqual("A", next(a["equals"]["DELETERULE"] for a in contract["assertions"] if a["where"].get("RELNAME") == "F1"))

    def test_unread_or_unmodeled_input_is_never_a_match(self):
        source = DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\nCREATE VIEW S.V AS SELECT C FROM S.T;"
        cases = {"partial CREATE": source.replace("IN DATABASE QADB1;", "IN DATABASE QADB1 FROBNICATE YES;"),
                 "unmodeled ALTER": source + "\nALTER TABLESPACE QADB1.T1 LOCKSIZE ROW;",
                 "unknown statement": source + "\nFROBNICATE TABLE S.T;"}
        self.assertEqual({("not-compared", None)}, {(d["status"], d.get("attribute")) for d in self.diff(source, source)["differences"]})
        for name, target in cases.items():
            with self.subTest(name):
                result = self.diff(source, target)
                self.assertEqual(result["status"], "unresolved")
                self.assertGreaterEqual(result["counts"]["not-compared"], 2)

    def test_cli_text_lists_entries_to_review_and_keeps_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source.sql", Path(tmp) / "target.sql"
            source.write_text(DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1;\n")
            target.write_text(DB + "CREATE TABLE S.T (C INTEGER) IN DATABASE QADB1 AUDIT NONE;\nALTER TABLESPACE QADB1.X CLOSE NO;\n")
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / "tools/ddl.py"), "diff", str(source), str(target), *a],
                                            capture_output=True, text=True)
            text = run("--text")
            self.assertEqual(text.returncode, 3)
            lines = text.stdout.splitlines()
            self.assertEqual(["not-compared: statement 3: target: ALTER TABLESPACE is not modeled; its effect on compared objects is unknown."],
                             lines[:-1])
            self.assertTrue(lines[-1].startswith("UNRESOLVED: equivalent-default=1, not-compared=1."))
            self.assertEqual(json.loads(run().stdout)["status"], "unresolved")


REGENERATION_DEFECTS = [  # (text in the regenerated fixture, seeded defect, object, attribute)
    ("GBPCACHE CHANGED COMPRESS YES TRACKMOD YES", "GBPCACHE CHANGED COMPRESS NO TRACKMOD YES", "tablespace QAVDB01.QAVS03", "partition 3 compress"),
    ("FREEPAGE 5 PCTFREE 20", "FREEPAGE 0 PCTFREE 20", "tablespace QAVDB01.QAVS03", "partition 1 freepage"),
    ("MAXROWS 100", "MAXROWS 255", "tablespace QAVDB01.QAVS01", "maxrows"),
    ("LOCKSIZE PAGE\n    LOCKMAX 0", "LOCKSIZE PAGE\n    LOCKMAX SYSTEM", "tablespace QAVDB01.QAVS02", "lockmax"),
    ("DATA CAPTURE CHANGES", "DATA CAPTURE NONE", "table QAV.CUSTOMER", "data_capture"),
    ("CACHE 50", "CACHE 20", "table QAV.CUSTOMER", "column CUSTOMER_ID.identity"),
    (" IMPLICITLY HIDDEN", "", "table QAV.CUSTOMER", "column AUDIT_NOTE.hidden"),
    ("WITH DEFAULT 'A'", "WITH DEFAULT 'B'", "table QAV.CUSTOMER", "column STATUS.default_text"),
    ('"STATUS" CHAR(1) FOR SBCS DATA', '"STATUS" CHAR(1) FOR BIT DATA', "table QAV.CUSTOMER", "column STATUS.type"),
    ('("QTY" > 0)', '("QTY" >= 0)', "table QAV.ORDER_LINE", "check constraints"),
    ("NOT ENFORCED ENABLE QUERY OPTIMIZATION", "ENFORCED", "table QAV.ORDER_LINE", "foreign constraints"),
    ('("CUSTOMER_CODE")\n    ON DELETE RESTRICT', '("CUSTOMER_CODE")\n    ON DELETE NO ACTION', "table QAV.SALES_ORDER", "foreign constraints"),
    ('ON DELETE SET NULL ENFORCED', 'ON DELETE RESTRICT ENFORCED', "table QAV.PRODUCT_DOC", "foreign constraints"),
    ('"ORDER_CUSTOMER_FK"', '"ORDER_CUST_FK"', "table QAV.SALES_ORDER", "foreign constraints"),
    ("'2024-12-31'", "'2024-12-30'", "table QAV.SALES_ORDER", "partitioning"),
    (',"PICK_TIME" TIME\n', "", "table QAV.SALES_ORDER", "columns"),
    ('("SKU" DESC)', '("SKU" ASC)', "index QAV.PRODUCT_SKUIX", "keys"),
    ('("ORDER_ID" ASC, "LINE_NO" ASC)\n    NOT CLUSTER', '("LINE_NO" ASC, "ORDER_ID" ASC)\n    NOT CLUSTER', "index QAV.LINE_PKIX", "keys"),
    ('INCLUDE ("STATUS")\n', "", "index QAV.CUSTOMER_UKIX", "include"),
    ('"CUSTOMER_ID" ASC)\n    CLUSTER', '"CUSTOMER_ID" ASC)\n    NOT CLUSTER', "index QAV.ORDER_DATEIX", "cluster"),
    (",PARTITION 2 USING STOGROUP SYSDEFLT PRIQTY -1 SECQTY -1 ERASE NO\n       FREEPAGE 0 PCTFREE 10",
     ",PARTITION 2 USING STOGROUP SYSDEFLT PRIQTY -1 SECQTY -1 ERASE NO\n       FREEPAGE 0 PCTFREE 15", "index QAV.ORDER_DATEIX", "partition 2 pctfree"),
    ('CREATE TABLE "QAV"."PRODUCT_DOC"', 'CREATE TABLE "QAV"."PRODUCT_DOCS"', "table QAV.PRODUCT_DOC", None),
]


class RegeneratedOutputTests(unittest.TestCase):
    """Extraction tools rewrite DDL without changing it; the diff must accept those rewrites and still
    report every seeded single-attribute defect."""

    FULL = profile(DPSEGSZ=32, IMPTKMOD="YES", MIXED="NO")

    @classmethod
    def setUpClass(cls):
        cls.source = EXAMPLE.read_text()
        cls.regenerated = paths.REGENERATED_SCHEMA.read_text()

    def diff(self, target, prof=None):
        return db2check.diff(analyze(self.source), analyze(target, allow_placeholders=True), None, prof)

    def test_rewrites_are_not_differences(self):
        loose = self.diff(self.regenerated, PROFILE)
        self.assertEqual("unresolved", loose["status"])
        self.assertFalse([d for d in loose["differences"] if d["status"] not in ("equivalent-default", "environment-dependent")])
        remaining = {(d["object"], d["attribute"]) for d in self.diff(self.regenerated, self.FULL)["differences"]
                     if d["status"] != "equivalent-default"}
        self.assertEqual({("index QAV.CUSTOMER_PKIX", "define"), ("tablespace QAVDB01.QAVS04", "dssize")}, remaining)

    def test_every_seeded_defect_is_reported(self):
        for original, defect, obj, attribute in REGENERATION_DEFECTS:
            with self.subTest(defect=defect.strip() or f"removed {original.strip()}"):
                self.assertEqual(1, self.regenerated.count(original), "the defect must change exactly one place")
                result = self.diff(self.regenerated.replace(original, defect), self.FULL)
                self.assertEqual("mismatch", result["status"])
                found = {(d["object"], d.get("attribute")) for d in result["differences"] if d["status"] in ("different", "missing")}
                self.assertIn((obj, attribute), found)


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
        self.assertTrue(all(set(q["types"]) == set(q["fields"]) for q in contract["catalog"]))
        # Imitation CSV exports of the exemplar's catalog meet every encoded expectation;
        # tests/test_evidence.py seeds defects into them.
        exports = {path.stem: path for path in paths.CATALOG_EXPORTS.glob("*.csv")}
        source, replay = qa.snapshot(contract, "source", exports), qa.snapshot(contract, "replay", exports)
        self.assertEqual(qa.compare(contract, source, replay)["status"], "match")
        replay["catalog"]["tablespaces_1"][0]["SEGSIZE"] = 999
        self.assertEqual(qa.compare(contract, source, replay)["status"], "mismatch")

    def test_bundle_expectations_and_cleanup_follow_alter_table(self):
        text = (DB + "CREATE TABLE QAV.T (C INTEGER) IN DATABASE QADB1;\n"
                "ALTER TABLE QAV.T DATA CAPTURE CHANGES ADD RESTRICT ON DROP;\n")
        _, files = self.make(text, databases={"QADB1": "QADB2"})
        expected = [a["equals"] for a in json.loads(files["catalog-contract.json"])["assertions"] if a["where"] == {"NAME": "T"}][0]
        self.assertEqual(("Y", "Y"), (expected["DATACAPTURE"], expected["CLUSTERTYPE"]))
        source_cleanup = files["cleanup-source.sql"]
        self.assertLess(source_cleanup.index("ALTER TABLE QAV.T DROP RESTRICT ON DROP"), source_cleanup.index("DROP DATABASE QADB1"))
        self.assertIn("ALTER TABLE QAVR.T DROP RESTRICT ON DROP", files["cleanup-replay.sql"])

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
