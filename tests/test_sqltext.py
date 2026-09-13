from __future__ import annotations

import copy
import itertools
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import qa
from sqltext import emit_sql, inspect_sql, validate_statement


class SQLTextTests(unittest.TestCase):
    def test_semicolons_in_literals_identifiers_and_comments_are_not_code(self):
        sql = 'CREATE TABLE "A;B" (C VARCHAR(40) DEFAULT \'a;it\'\'s  x \') /* ; */ -- ;'
        self.assertEqual(inspect_sql(sql)["semicolon_positions"], [])
        self.assertEqual(emit_sql([sql]), sql + "\n;\n")

    def test_routine_body_is_preserved_byte_for_byte(self):
        sql = "CREATE PROCEDURE QA.P(OUT V VARCHAR(30)) LANGUAGE SQL\r\nBEGIN\r\n  SET V = 'MiXeD; it''s  x '; -- keep ;\r\nEND -- final comment"
        output = emit_sql([sql, "COMMIT"], terminator="@")
        self.assertIn(sql + "\n@\n\nCOMMIT\n@\n", output)
        self.assertEqual(len(inspect_sql(sql)["semicolon_positions"]), 1)
        with self.assertRaises(ValueError):
            emit_sql([sql])

    def test_invalid_framing_is_rejected(self):
        for sql in ("", "-- comment", "VALUES 'unfinished", 'VALUES "unfinished', "VALUES 1 /*", "VALUES 1 */", "VALUES 1; DROP TABLE QA.T", "VALUES 1;"):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                validate_statement(sql)
        for sql in ("BEGIN SET V=1; END;", "BEGIN SET V='a@b'; END", "BEGIN /* outer /* inner */ */ SET V=1; END"):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                validate_statement(sql, "sql_pl", "@")

    def test_metrics_do_not_claim_target_encoding_lengths(self):
        info = inspect_sql("VALUES 'é'")
        self.assertGreater(info["utf8_bytes"], info["characters"])
        self.assertEqual(info["maximum_line_characters"], len("VALUES 'é'"))

    def test_body_fragments_cannot_bypass_node_kind(self):
        model = copy.deepcopy(qa.models()["table-core"])
        model["dimensions"]["column"][next(iter(model["dimensions"]["column"]))]["sql"] = "V INTEGER); DROP TABLE QA.T"
        selection = qa.candidates(model)[1][0]
        with self.assertRaises(ValueError):
            qa.make_case(model, selection, qa.read(ROOT / "kb/campaigns/profiles/example.json"), "QA", 1)


class SelectionTests(unittest.TestCase):
    def test_three_way_covers_independent_feasible_triples(self):
        valid = [dict(zip("abcd", values)) for values in itertools.product("01", repeat=4) if values[:2] != ("1", "1")]
        selected, report = qa.select_cases(valid, "three-way")
        self.assertTrue(report["complete"])
        for axes in itertools.combinations("abcd", 3):
            self.assertEqual({tuple(s[a] for a in axes) for s in selected}, {tuple(s[a] for a in axes) for s in valid})
        self.assertEqual(report["strength"], 3)

    def test_repeat_selections_are_or_within_axis_and_across_axes(self):
        model = qa.models()["index-core"]
        filters = qa.selection_filters(model, ["unique=yes", "include=no", "include=yes"])
        raw, valid = qa.candidates(model, filters)
        self.assertTrue(valid)
        self.assertEqual({s["include"] for s in valid}, {"yes", "no"})
        self.assertTrue(all(s["unique"] == "yes" for s in raw))
        for settings in (["typo=yes"], ["unique="], ["unique=typo"], ["unique"]):
            with self.assertRaises(ValueError):
                qa.selection_filters(model, settings)

    def test_infeasible_filter_creates_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "bundle"
            result = subprocess.run([sys.executable, str(ROOT / "tools/qa.py"), "build", "--model", "index-core", "--profile", str(ROOT / "kb/campaigns/profiles/example.json"), "--run", "QA", "--set", "unique=no", "--set", "include=yes", "--out", str(destination)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("no valid combinations", result.stderr)
            self.assertFalse(destination.exists())

    def test_filtered_report_retains_full_model_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "bundle"
            result = subprocess.run([sys.executable, str(ROOT / "tools/qa.py"), "build", "--model", "index-core", "--profile", str(ROOT / "kb/campaigns/profiles/example.json"), "--run", "QA", "--set", "unique=yes", "--out", str(destination)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = qa.read(destination / "coverage.json")
            self.assertEqual(report["selection_filters"], {"unique": ["yes"]})
            self.assertLess(report["valid_combinations"], report["full_model_valid_combinations"])


class ProcedureCorrectionTests(unittest.TestCase):
    def test_standalone_procedure_needs_no_storage_or_database_setup(self):
        model = qa.models()["procedure-native"]
        profile = qa.read(ROOT / "kb/campaigns/profiles/example.json")
        for key in ("storage_group", "table_bufferpool", "index_bufferpool"):
            profile.pop(key)
        profile["product_context"]["active_buffer_pools"] = []
        qa.validate_profile(profile, model)
        case, _ = qa.make_case(model, qa.candidates(model)[1][0], profile, "PN", 1)
        self.assertNotIn("PNSDB", case["ofs_validation"]["name_map"])
        self.assertFalse(any("campaign database" in p for p in case["prerequisites"]))
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            profile_path.write_text(qa.dump(profile))
            destination = Path(tmp) / "procedure"
            result = subprocess.run([sys.executable, str(ROOT / "tools/qa.py"), "build", "--model", "procedure-native", "--profile", str(profile_path), "--run", "PN", "--budget", "1", "--out", str(destination)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = qa.read(destination / "manifest.json")
            self.assertFalse(manifest["uses_database"])
            self.assertIsNone(manifest["source_database"])
            self.assertNotIn("CREATE DATABASE", (destination / "bootstrap-source.sql").read_text())
            self.assertNotIn("DROP DATABASE", (destination / "cleanup-databases.sql").read_text())
            preflight = (destination / "preflight.sql").read_text()
            self.assertNotIn("SYSIBM.SYSTABLES", preflight)
            self.assertIn("SYSIBM.SYSROUTINES", preflight)

    def test_column_limit_keeps_dependent_table_distinction(self):
        clause = next(c for c in qa.kb()["objects"]["table"]["clauses"] if c["id"] == "column-definition")
        self.assertIn("749", clause["values"])
        self.assertIn("750", clause["values"])
        self.assertIn("dependent", clause["values"])

    def test_templates_cannot_choose_a_different_specific_name(self):
        for name in ("native-sql-procedure", "external-procedure"):
            text = (ROOT / f"kb/templates/{name}.template.sql").read_text()
            self.assertIn("SPECIFIC {{PROCEDURE_SCHEMA}}.{{PROCEDURE_NAME}}", text)
            self.assertNotIn("PROCEDURE_SPECIFIC_NAME", text)
        rules = {r["id"] for r in qa.kb()["objects"]["procedure"]["rules"]}
        self.assertIn("specific-name-matches-procedure", rules)
        self.assertIn("native-compound-not-atomic", rules)

    def test_cleanup_owns_tables_and_does_not_double_drop_spaces(self):
        profile = qa.read(ROOT / "kb/campaigns/profiles/example.json")
        for name in ("table-core", "tablespace-pbg", "index-core"):
            model = qa.models()[name]
            case, contract = qa.make_case(model, qa.candidates(model)[1][0], profile, "QA", 1)
            self.assertFalse(any(sql.startswith("DROP TABLE ") for sql in case["cleanup_sql"]))
            self.assertEqual(sum(sql.startswith("DROP TABLESPACE ") for sql in case["cleanup_sql"]), 1)
            self.assertTrue(contract["cleanup_ownership"])

    def test_cleanup_owner_must_be_an_actual_droppable_ancestor(self):
        original = qa.models()["table-core"]
        for owner in ("unknown", "table"):
            model = copy.deepcopy(original)
            node = next(n for n in model["nodes"] if n["drop"] is None)
            node["cleanup_via"] = owner
            with self.assertRaises(ValueError):
                qa.validate_model(model, qa.kb())


if __name__ == "__main__":
    unittest.main()
