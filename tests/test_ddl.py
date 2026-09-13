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
import ddl
import qa


class AuthoringPlanTests(unittest.TestCase):
    def setUp(self):
        self.request = qa.read(ROOT / "kb/authoring/examples/index-include.json")

    def plan(self, request=None):
        return ddl.make_plan(self.request if request is None else request)

    def codes(self, plan):
        return {gap["code"] for gap in plan["gaps"]}

    def test_exact_filtered_plan_retains_review_and_environment_limits(self):
        result = self.plan()
        self.assertEqual(result["status"], "design")
        self.assertEqual(result["review_status"], "agent_review_required")
        self.assertFalse(result["structured_scope_has_gaps"])
        self.assertFalse(result["environment"]["verified"])
        self.assertEqual(result["environment"]["execution_status"], "not_executed")
        current = result["objects"][0]
        coverage = current["coverage_preview"]
        self.assertEqual(coverage["valid_combinations"], 36)
        self.assertEqual(coverage["full_model_valid_combinations"], 108)
        self.assertTrue(coverage["complete"])
        argv = current["offline_build_argv"]
        self.assertIn("unique=yes", argv)
        self.assertIn("include=yes", argv)
        self.assertIn("IX01", argv)
        self.assertNotIn("--negative", argv)
        self.assertEqual(current["selected_sql_fragments"]["unique"], {"yes": "UNIQUE"})
        model = qa.models()["index-core"]
        feasible = [row for row in qa.candidates(model)[1] if row["unique"] == row["include"] == "yes"]
        for a, b in itertools.combinations(model["dimensions"], 2):
            self.assertEqual({(row[a], row[b]) for row in current["selected_combinations"]},
                             {(row[a], row[b]) for row in feasible})

    def test_multiple_axis_values_are_or_and_the_command_retains_them(self):
        self.request["objects"][0]["select"]["pctfree"] = ["0", "99"]
        result = self.plan()["objects"][0]
        self.assertEqual(result["coverage_preview"]["valid_combinations"], 24)
        self.assertIn("pctfree=0", result["offline_build_argv"])
        self.assertIn("pctfree=99", result["offline_build_argv"])
        self.assertNotIn("pctfree=10", result["offline_build_argv"])

    def test_unknown_reference_is_an_explicit_gap_not_a_guessed_clause(self):
        self.request["objects"][0]["clause_refs"].append("index.invented")
        self.request["objects"][0]["rule_refs"].append("index.unknown")
        result = self.plan()
        self.assertIn("unknown_clause_reference", self.codes(result))
        self.assertIn("unknown_rule_reference", self.codes(result))
        self.assertIsNone(result["objects"][0]["offline_build_argv"])
        self.assertTrue(result["research_tasks"])

    def test_scaffold_and_unknown_objects_preserve_the_gap(self):
        for object_name, status in (("view", "extension_candidate"), ("invented", "unknown")):
            self.request["objects"] = [{"id": "example", "object": object_name}]
            result = self.plan()
            gap = next(g for g in result["gaps"] if g["code"] == "object_not_normalized")
            self.assertEqual(gap["registry_status"], status)
            self.assertIsNone(result["objects"][0]["offline_build_argv"])

    def test_model_selection_is_explicit_and_models_must_match_object(self):
        for model, code in ((None, "model_selection_required"), ("invented", "unknown_model"), ("table-core", "model_object_mismatch")):
            request = copy.deepcopy(self.request)
            if model is None:
                del request["objects"][0]["model"]
            else:
                request["objects"][0]["model"] = model
            result = self.plan(request)
            self.assertIn(code, self.codes(result))
            self.assertIsNone(result["objects"][0]["offline_build_argv"])

    def test_unknown_dimensions_values_and_infeasible_pairs_do_not_generate_commands(self):
        for selection, code in (({"invented": ["yes"]}, "invalid_selection"),
                                ({"unique": ["invented"]}, "invalid_selection"),
                                ({"unique": ["no"], "include": ["yes"]}, "infeasible_selection")):
            self.request["objects"][0]["select"] = selection
            result = self.plan()
            self.assertIn(code, self.codes(result))
            self.assertIsNone(result["objects"][0]["offline_build_argv"])

    def test_clause_paths_are_measured_after_filters_and_budget(self):
        self.request["objects"] = [{"id": "table", "object": "table", "model": "table-core",
                                   "clause_refs": ["table.identity"], "select": {"column": ["integer-nullable"]}}]
        result = self.plan()
        self.assertIn("clause_outside_preview", self.codes(result))
        self.assertNotIn("table.identity", result["objects"][0]["clause_paths_in_preview"])
        self.assertIsNone(result["objects"][0]["offline_build_argv"])

    def test_cited_rule_is_not_assumed_to_be_an_encoded_predicate(self):
        self.request["objects"][0]["rule_refs"].append("index.expression-restrictions")
        result = self.plan()
        self.assertIn("rule_outside_model", self.codes(result))
        current = result["objects"][0]
        self.assertIn("index.include-requires-unique", current["model_scope"]["rule_refs"])
        self.assertTrue(current["model_scope"]["constraints"])

    def test_budget_gaps_keep_denominator_and_uncovered_interactions(self):
        self.request["budget"] = 1
        result = self.plan()
        self.assertIn("coverage_budget", self.codes(result))
        coverage = result["objects"][0]["coverage_preview"]
        self.assertEqual(coverage["selected_cases"], 1)
        self.assertTrue(coverage["uncovered_interactions"])
        self.assertFalse(coverage["complete"])

    def test_three_way_previews_use_actual_three_way_selection(self):
        self.request["strategy"] = "three-way"
        result = self.plan()
        current = result["objects"][0]
        self.assertEqual(current["coverage_preview"]["strength"], 3)
        model = qa.models()["index-core"]
        feasible = [row for row in qa.candidates(model)[1] if row["unique"] == row["include"] == "yes"]
        for axes in itertools.combinations(model["dimensions"], 3):
            self.assertEqual({tuple(row[a] for a in axes) for row in current["selected_combinations"]},
                             {tuple(row[a] for a in axes) for row in feasible})

    def test_negative_cases_need_isolated_violations_inside_selected_scope(self):
        self.request["negative"] = True
        result = self.plan()
        self.assertIn("negative_not_isolatable", self.codes(result))
        self.assertIsNone(result["objects"][0]["offline_build_argv"])
        self.request["objects"][0]["select"] = {}
        result = self.plan()
        self.assertFalse(result["structured_scope_has_gaps"])
        self.assertEqual(len(result["objects"][0]["negative_preview"]), 2)
        for negative in result["objects"][0]["negative_preview"]:
            self.assertEqual(qa.violations(qa.models()["index-core"], negative["selection"]), [negative["constraint"]])
            self.assertIsNone(negative["sqlcode"])
            self.assertIsNone(negative["sqlstate"])

    def test_freeform_formatting_length_and_behavior_are_never_auto_satisfied(self):
        for kind in ("formatting", "length", "behavior"):
            self.request["requirements"] = [{"id": "text", "kind": kind,
                                             "text": "Preserve 'MiXeD ;  ' exactly.\n72 columns in the target encoding.", "objects": ["indexes"]}]
            result = self.plan()
            gap = next(g for g in result["gaps"] if g["code"] == "freeform_requirement_review")
            self.assertEqual(gap["requirement"], self.request["requirements"][0])
            self.assertIsNone(result["objects"][0]["offline_build_argv"])

    def test_context_contains_dependencies_sources_and_trigger_body_matrix(self):
        result = self.plan()
        self.assertIn("index", result["context"])
        self.assertIn("table", result["context"])
        for context in result["context"].values():
            self.assertTrue(context["normalized"]["rules"])
            for source in context["sources"].values():
                self.assertTrue(source["url"].startswith("https://www.ibm.com/docs/"))
        self.request["objects"] = [{"id": "trigger", "object": "trigger"}]
        result = self.plan()
        self.assertIn("body_matrix", result["context"]["trigger"])

    def test_request_graph_orders_but_does_not_pretend_to_connect_campaigns(self):
        parent = copy.deepcopy(self.request["objects"][0])
        parent["id"] = "parent"
        child = copy.deepcopy(parent)
        child.update(id="child", depends_on=["parent"])
        self.request["objects"] = [child, parent]
        result = self.plan()
        self.assertEqual(result["dependency_order"], ["parent", "child"])
        self.assertIn("bespoke_dependency_graph", self.codes(result))
        self.assertTrue(all(obj["offline_build_argv"] is None for obj in result["objects"]))

    def test_invalid_graphs_and_requirement_targets_are_input_errors(self):
        request = copy.deepcopy(self.request)
        request["objects"][0]["depends_on"] = ["absent"]
        with self.assertRaisesRegex(ValueError, "unresolved dependency"):
            self.plan(request)
        request["objects"][0]["depends_on"] = ["indexes"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.plan(request)
        request = copy.deepcopy(self.request)
        request["objects"].append(copy.deepcopy(request["objects"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate instance"):
            self.plan(request)
        request = copy.deepcopy(self.request)
        request["requirements"] = [{"id": "r", "kind": "syntax", "text": "Example", "objects": ["missing"]}]
        with self.assertRaisesRegex(ValueError, "unknown object instance"):
            self.plan(request)

    def test_missing_unreadable_and_incompatible_profiles_are_gaps(self):
        del self.request["profile"]
        self.assertIn("profile_missing", self.codes(self.plan()))
        self.request["profile"] = "/missing/db2-ddl-profile.json"
        self.assertIn("profile_unreadable", self.codes(self.plan()))
        with tempfile.TemporaryDirectory() as tmp:
            profile = qa.read(ROOT / "kb/campaigns/profiles/example.json")
            profile["product_context"]["current_rules"] = "STD"
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(profile))
            self.request["profile"] = str(path)
            result = self.plan()
            self.assertIn("profile_incompatible", self.codes(result))
            self.assertIsNone(result["objects"][0]["offline_build_argv"])

    def test_schema_rejects_unknown_fields_empty_choices_and_wrong_types(self):
        variants = []
        for key, value in (("invented", True), ("budget", True), ("budget", 0), ("strategy", "random"), ("run_prefix", "TOOLONG")):
            request = copy.deepcopy(self.request)
            request[key] = value
            variants.append(request)
        for value in ([], "yes", ["yes", "yes"]):
            request = copy.deepcopy(self.request)
            request["objects"][0]["select"] = {"unique": value}
            variants.append(request)
        request = copy.deepcopy(self.request)
        request["objects"][0]["cluase_refs"] = []
        variants.append(request)
        for request in variants:
            with self.assertRaises(ValueError):
                ddl.validate_request(request)

    def test_examples_conform_to_json_schema_and_builtin_validation(self):
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(qa.read(ddl.SCHEMA))
        for path in (ROOT / "kb/authoring/examples").glob("*.json"):
            request = qa.read(path)
            validator.validate(request)
            ddl.validate_request(request)

    def test_output_is_reproducible_across_working_directories_and_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = [sys.executable, str(ROOT / "tools/ddl.py"), "plan", "--request", str(ROOT / "kb/authoring/examples/index-include.json"), "--require-modeled"]
            first = subprocess.run(base, cwd=ROOT, text=True, capture_output=True)
            second = subprocess.run(base, cwd=tmp, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            path = Path(tmp) / "plan.json"
            result = subprocess.run(base + ["--out", str(path)], cwd=tmp, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(first.stdout, path.read_text())
            result = subprocess.run(base + ["--out", str(path)], cwd=tmp, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(first.stdout, path.read_text())

    def test_cli_emits_gaps_with_exit_one_and_distinguishes_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.json"
            self.request["objects"][0]["model"] = "missing"
            path.write_text(json.dumps(self.request))
            base = [sys.executable, str(ROOT / "tools/ddl.py"), "plan", "--request", str(path), "--require-modeled"]
            result = subprocess.run(base, cwd=tmp, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("unknown_model", self.codes(json.loads(result.stdout)))
            path.write_text('{"schema_version": "typo"}')
            result = subprocess.run(base, cwd=tmp, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(result.stdout)

    def test_planned_command_builds_the_exact_previewed_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.request["output_root"] = tmp
            current = self.plan()["objects"][0]
            result = subprocess.run(current["offline_build_argv"], cwd=tmp, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            bundle = Path(tmp) / "indexes"
            manifest = qa.read(bundle / "manifest.json")
            emitted = [qa.read(bundle / "cases" / case_id / "catalog-contract.json")["selection"] for case_id in manifest["case_ids"]]
            self.assertEqual(current["selected_combinations"], emitted)
            for field in ("valid_combinations", "selected_cases", "required_interactions", "covered_interactions", "complete"):
                self.assertEqual(manifest["coverage"][field], current["coverage_preview"][field])


if __name__ == "__main__":
    unittest.main()
