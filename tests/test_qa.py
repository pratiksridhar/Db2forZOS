from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import qa


class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = qa.models()
        cls.profile = qa.read(ROOT / "kb/campaigns/profiles/example.json")

    def test_pairwise_covers_independently_enumerated_feasible_pairs(self):
        for model in self.models.values():
            raw, valid = qa.candidates(model)
            selected, report = qa.select_cases(valid, "pairwise")
            self.assertTrue(report["complete"])
            self.assertLessEqual(len(selected), len(valid))
            for a, b in itertools.combinations(model["dimensions"], 2):
                expected = {(s[a], s[b]) for s in valid}
                actual = {(s[a], s[b]) for s in selected}
                self.assertEqual(actual, expected, (model["id"], a, b))
            self.assertEqual(qa.select_cases(valid, "pairwise"), (selected, report))

    def test_budget_leaves_explicit_gaps(self):
        _, valid = qa.candidates(self.models["table-core"])
        selected, report = qa.select_cases(valid, "pairwise", 1)
        self.assertEqual(len(selected), 1)
        self.assertFalse(report["complete"])
        self.assertTrue(report["uncovered_interactions"])

    def test_exhaustive_is_not_complete_when_only_values_are_covered(self):
        valid = [{"a": "x", "b": "x"}, {"a": "y", "b": "y"}, {"a": "x", "b": "y"}]
        _, report = qa.select_cases(valid, "exhaustive", 2)
        self.assertEqual(report["uncovered_interactions"], [])
        self.assertFalse(report["complete"])

    def test_each_choice_and_single_axis_models(self):
        valid = [{"a": "x"}, {"a": "y"}]
        for strategy in ("each-choice", "pairwise", "exhaustive"):
            selected, report = qa.select_cases(valid, strategy)
            self.assertEqual(selected, valid)
            self.assertTrue(report["complete"])

    def test_constraints_and_isolated_negatives(self):
        model = self.models["index-core"]
        raw, valid = qa.candidates(model)
        self.assertEqual(len(raw), 288)
        self.assertEqual(len(valid), 108)
        for s in valid:
            self.assertEqual(s["partitioned"], "no")
            self.assertTrue(s["include"] == "no" or s["unique"] == "yes")
        for constraint in model["constraints"]:
            isolated = [s for s in raw if qa.violations(model, s) == [constraint["id"]]]
            self.assertTrue(isolated)

    def test_dependency_order_and_failures(self):
        nodes = [{"id": "index", "depends_on": ["table"]}, {"id": "table", "depends_on": ["space"]}, {"id": "space", "depends_on": []}]
        self.assertEqual([n["id"] for n in qa.order_nodes(nodes)], ["space", "table", "index"])
        for invalid in ([{"id": "a", "depends_on": ["missing"]}], [{"id": "a", "depends_on": ["b"]}, {"id": "b", "depends_on": ["a"]}], [nodes[0], nodes[0]]):
            with self.assertRaises(ValueError):
                qa.order_nodes(invalid)

    def test_profiles_reject_injection_missing_context_and_bad_levels(self):
        for key, value in (("source_schema", "QA'; DROP DATABASE X;--"), ("source_schema", "SYSIBM"), ("replay_schema", "QASRC"), ("table_bufferpool", "BP32K"), ("verified", "false")):
            profile = copy.deepcopy(self.profile)
            profile[key] = value
            with self.assertRaises(ValueError, msg=(key, value)):
                qa.validate_profile(profile, self.models["table-core"])

    def test_existing_system_default_storage_group_can_be_referenced(self):
        profile = copy.deepcopy(self.profile)
        profile["storage_group"] = "SYSDEFLT"
        qa.validate_profile(profile, self.models["table-core"])

    def test_profiles_reject_incompatible_or_unrecorded_environment(self):
        for key, value in (("applcompat", "V13R1M509"), ("function_level", "unknown"), ("current_rules", "STD"), ("data_sharing", "false")):
            profile = copy.deepcopy(self.profile)
            profile["product_context"][key] = value
            with self.assertRaises(ValueError, msg=(key, value)):
                qa.validate_profile(profile, self.models["table-core"])

    def test_validate_case_rejects_unresolved_sources_tokens_and_empty_action(self):
        model = self.models["table-core"]
        selection = qa.candidates(model)[1][0]
        original, _ = qa.make_case(model, selection, self.profile, "QA", 1)
        qa.validate_case(original)
        for field, value in (("source_refs", ["ibm-invented"]), ("action_sql", ["CREATE TABLE {{NAME}} (ID INT)"]), ("action_sql", [])):
            record = copy.deepcopy(original)
            record[field] = value
            with self.assertRaises(ValueError):
                qa.validate_case(record)

    def test_render_rejects_missing_or_recursive_tokens(self):
        for text, params in (("{{A}}", {}), ("{{A}}", {"A": "{{B}}"}), ("{{a}}", {})):
            with self.assertRaises(ValueError):
                qa.render(text, params)

    def test_models_detect_broken_references_and_unknown_values(self):
        for field, value in (("covers", ["table.not-real"]), ("rule_refs", ["table.not-real"]), ("source_refs", ["ibm-not-real"])):
            model = copy.deepcopy(self.models["table-core"])
            model[field] = value
            with self.assertRaises(ValueError):
                qa.validate_model(model, qa.kb())
        model = copy.deepcopy(self.models["index-core"])
        model["constraints"][0]["when"] = {"include": "typo"}
        with self.assertRaises(ValueError):
            qa.validate_model(model, qa.kb())

    def test_model_rejects_assertion_typos_and_setup_after_action(self):
        model = copy.deepcopy(self.models["table-core"])
        model["assertions"][0]["catalog"] = "typo"
        with self.assertRaises(ValueError):
            qa.validate_model(model, qa.kb())
        model = copy.deepcopy(self.models["table-core"])
        model["nodes"].append({"id": "late", "role": "setup", "depends_on": ["table"], "sql": "SELECT 1", "drop": "SELECT 1"})
        with self.assertRaises(ValueError):
            qa.validate_model(model, qa.kb())

    def test_all_valid_combinations_render_and_have_resolved_refs(self):
        for model in self.models.values():
            qa.validate_model(model, qa.kb())
            _, valid = qa.candidates(model)
            for selection in valid:
                case, contract = qa.make_case(model, selection, self.profile, "QA", 1)
                self.assertNotIn("{{", json.dumps(case))
                for query in contract["catalog"]:
                    self.assertNotIn("{{", query["source_sql"])
                    self.assertNotIn("{{", query["replay_sql"])
                self.assertEqual(case["status"], "design")
                self.assertTrue(contract["assertions"])

    def test_schema_validation_of_every_emitted_case(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.fail("Install requirements-dev.txt to run JSON Schema validation")
        validator = Draft202012Validator(qa.read(ROOT / "kb/data/test-case.schema.json"))
        for model in self.models.values():
            raw, valid = qa.candidates(model)
            for selection in valid:
                case, _ = qa.make_case(model, selection, self.profile, "QA", 1)
                validator.validate(case)
            for constraint in model["constraints"]:
                selection = next(s for s in raw if qa.violations(model, s) == [constraint["id"]])
                case, _ = qa.make_case(model, selection, self.profile, "QA", 2, constraint["id"])
                validator.validate(case)
                self.assertIsNone(case["expected"]["sqlcode"])

    def test_inventory_and_scaffolds(self):
        inventory = qa.coverage_inventory()
        self.assertEqual(len(inventory), 7)
        procedure = next(i for i in inventory if i["object"] == "procedure")
        self.assertIn("native-body", procedure["modeled_clauses"])
        self.assertIn("external-runtime", procedure["unmodeled_clauses"])
        self.assertTrue(procedure["unmodeled_clauses"])
        self.assertIn("body_matrix", qa.context_pack("trigger"))
        with self.assertRaises(ValueError):
            qa.context_pack("view")

    def test_cli_build_is_reproducible_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = [sys.executable, str(ROOT / "tools/qa.py"), "build", "--model", "index-core", "--profile", str(ROOT / "kb/campaigns/profiles/example.json"), "--run", "QA", "--budget", "2", "--negative"]
            for dest in ("first", "second"):
                result = subprocess.run(base + ["--out", str(Path(tmp) / dest)], cwd=tmp, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            first, second = Path(tmp) / "first", Path(tmp) / "second"
            self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
            manifest = qa.read(first / "manifest.json")
            self.assertEqual(len(manifest["case_ids"]), 4)
            self.assertFalse(manifest["coverage"]["complete"])
            for case_id in manifest["case_ids"]:
                case = qa.read(first / "cases" / case_id / "case.json")
                self.assertTrue(case["cleanup_sql"][0].startswith("DROP INDEX"))
                self.assertTrue(case["setup_sql"][0].startswith("CREATE TABLESPACE"))
                self.assertTrue(case["setup_sql"][1].startswith("CREATE TABLE"))
            result = subprocess.run(base + ["--out", str(first)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())


class CatalogComparisonTests(unittest.TestCase):
    def setUp(self):
        self.contract = {"case_id": "TEST", "violated_constraint": None, "catalog": [
            {"id": "columns", "key": ["COLNO"], "fields": ["COLNO", "NAME", "DEFAULTVALUE"], "rtrim_fields": ["NAME"], "min_rows": 2, "max_rows": 2}
        ], "assertions": []}
        self.source = {"case_id": "TEST", "side": "source", "catalog": {"columns": [
            {"COLNO": 1, "NAME": "ID   ", "DEFAULTVALUE": ""},
            {"COLNO": 2, "NAME": "VAL", "DEFAULTVALUE": "MiXeD "}
        ]}}
        self.replay = copy.deepcopy(self.source)
        self.replay["side"] = "replay"

    def test_reordered_rows_and_declared_catalog_padding_match(self):
        self.replay["catalog"]["columns"].reverse()
        self.replay["catalog"]["columns"][1]["NAME"] = "ID"
        self.assertEqual(qa.compare(self.contract, self.source, self.replay)["status"], "match")

    def test_empty_contract_is_not_a_vacuous_match(self):
        self.contract["catalog"] = []
        with self.assertRaises(ValueError):
            qa.compare(self.contract, self.source, self.replay)

    def test_contract_assertion_typos_cannot_be_silently_skipped(self):
        self.contract["assertions"] = [{"catalog": "typo", "where": {}, "equals": {"NAME": "ID"}}]
        with self.assertRaises(ValueError):
            qa.compare(self.contract, self.source, self.replay)

    def test_cli_compare_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contract.json").write_text(qa.dump(self.contract))
            (root / "source.json").write_text(qa.dump(self.source))
            for expected, value in ((0, "MiXeD "), (1, "wrong"), (2, "missing")):
                replay = copy.deepcopy(self.replay)
                if expected == 2:
                    replay["catalog"] = {}
                else:
                    replay["catalog"]["columns"][1]["DEFAULTVALUE"] = value
                (root / "replay.json").write_text(qa.dump(replay))
                result = subprocess.run([sys.executable, str(ROOT / "tools/qa.py"), "compare", "--contract", str(root / "contract.json"), "--source", str(root / "source.json"), "--replay", str(root / "replay.json")], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_preserves_literal_case_whitespace_nulls_and_numeric_types(self):
        for value in ("MiXeD", "MIXED ", None, 0):
            self.replay["catalog"]["columns"][1]["DEFAULTVALUE"] = value
            result = qa.compare(self.contract, self.source, self.replay)
            self.assertEqual(result["status"], "mismatch", value)
            self.assertTrue(result["differences"])

    def test_missing_empty_and_duplicate_evidence_is_never_a_match(self):
        mutations = [[], [self.source["catalog"]["columns"][0]] * 2, [{"COLNO": 1}, {"COLNO": 2}]]
        for rows in mutations:
            self.source["catalog"]["columns"] = rows
            self.replay["catalog"]["columns"] = rows
            with self.assertRaises(ValueError):
                qa.compare(self.contract, self.source, self.replay)
        self.source["catalog"] = {}
        with self.assertRaises(ValueError):
            qa.compare(self.contract, self.source, self.replay)

    def test_wrong_case_wrong_side_and_negative_contract_rejected(self):
        for field in ("case_id", "side"):
            replay = copy.deepcopy(self.replay)
            replay[field] = "wrong"
            with self.assertRaises(ValueError):
                qa.compare(self.contract, self.source, replay)
        self.contract["violated_constraint"] = "some-rule"
        with self.assertRaises(ValueError):
            qa.compare(self.contract, self.source, self.replay)

    def test_identical_wrong_source_and_replay_fail_expected_semantics(self):
        self.contract["assertions"] = [{"catalog": "columns", "where": {"COLNO": 2}, "equals": {"DEFAULTVALUE": "EXPECTED"}}]
        result = qa.compare(self.contract, self.source, self.replay)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(len(result["differences"]), 2)

    def test_changed_key_sequence_is_detected(self):
        self.replay["catalog"]["columns"][0]["COLNO"] = 2
        self.replay["catalog"]["columns"][1]["COLNO"] = 1
        self.assertEqual(qa.compare(self.contract, self.source, self.replay)["status"], "mismatch")


if __name__ == "__main__":
    unittest.main()
