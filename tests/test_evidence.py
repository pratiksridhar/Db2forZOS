"""Catalog evidence: CSV export conversion and seeded defects in the catalog comparison."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402
import db2check  # noqa: E402
import qa  # noqa: E402

PROFILE = qa.read(paths.EXAMPLE_PROFILE)


def exemplar_contract():
    text = paths.VARIED_SCHEMA.read_text()
    report = db2check.analyze(text, db2check.Options.from_profile(PROFILE))
    names = db2check.NameMap({"QAV": "QAVR"}, {"QAVDB01": "QAVRDB01"})
    return json.loads(db2check.bundle(report, text, names, "QAV", PROFILE)["catalog-contract.json"])


def exports(directory=paths.CATALOG_EXPORTS):
    return {path.stem: path for path in Path(directory).glob("*.csv")}


class DelimitedReaderTests(unittest.TestCase):
    def test_quoting_is_kept_per_field(self):
        records = qa.read_delimited('A,B,C\n"x, ""y""",,""\nplain,  padded  ,"multi\r\nline"\n')
        self.assertEqual([(1, [("A", False), ("B", False), ("C", False)]),
                          (2, [('x, "y"', True), ("", False), ("", True)]),
                          (3, [("plain", False), ("  padded  ", False), ("multi\r\nline", True)])], records)

    def test_line_endings_trailing_fields_and_last_record(self):
        self.assertEqual([(1, [("A", False), ("B", False)]), (2, [("1", False), ("", False)])], qa.read_delimited("A,B\r\n1,"))
        self.assertEqual([(1, [("A", False)]), (2, [("", True)])], qa.read_delimited('A\n""'))
        self.assertEqual([], qa.read_delimited(""))
        self.assertEqual([(1, [("A", False), ("B", False)])], qa.read_delimited("A\tB\n", "\t"))

    def test_malformed_quoting_is_rejected(self):
        for text in ('A\n"open', 'A\n"closed"x'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                qa.read_delimited(text)


class TypedValueTests(unittest.TestCase):
    def value(self, text, quoted, declared, null=""):
        return qa.typed_value(text, quoted, declared, null, "test")

    def test_integers_and_nulls_follow_the_declaration(self):
        self.assertEqual(-1, self.value(" -1 ", False, "INTEGER"))
        self.assertIsNone(self.value("", False, "SMALLINT WITH DEFAULT NULL"))
        self.assertIsNone(self.value("NULL", False, "INTEGER", null="NULL"))
        for text, quoted, declared in (("", False, "SMALLINT NOT NULL"), ("", True, "INTEGER"), ("5.0", False, "SMALLINT NOT NULL"),
                                       ("1,048,576", True, "INTEGER NOT NULL WITH DEFAULT")):
            with self.subTest(text=text, declared=declared), self.assertRaises(ValueError):
                self.value(text, quoted, declared)

    def test_text_is_kept_exactly(self):
        self.assertEqual("BP0     ", self.value("BP0     ", False, "CHAR(8) NOT NULL"))
        self.assertEqual("", self.value("", False, "VARCHAR(1536) NOT NULL WITH DEFAULT"))  # NOT NULL: never NULL
        self.assertIsNone(self.value("", False, "CHAR(1) WITH DEFAULT NULL"))
        self.assertEqual("", self.value("", True, "CHAR(1) WITH DEFAULT NULL"))
        self.assertEqual("NULL", self.value("NULL", True, "CHAR(1) WITH DEFAULT NULL", null="NULL"))
        self.assertEqual("NULL", self.value("NULL", False, "VARCHAR(128) NOT NULL", null="NULL"))

    def test_unmodeled_types_are_refused(self):
        with self.assertRaises(ValueError):
            self.value("1.5", False, "FLOAT NOT NULL WITH DEFAULT -1")


class SnapshotConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = exemplar_contract()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for path in exports().values():
            shutil.copy(path, self.dir / path.name)

    def tearDown(self):
        self.tmp.cleanup()

    def convert(self, side="source", **options):
        return qa.snapshot(self.contract, side, exports(self.dir), **options)

    def edit(self, query, old, new):
        path = self.dir / f"{query}.csv"
        text = path.read_text(encoding="utf-8-sig")
        self.assertEqual(1, text.count(old), "the edit must change exactly one place")
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_fixture_meets_every_expectation_of_the_bundle_contract(self):
        source, replay = self.convert(), self.convert("replay")
        result = qa.compare(self.contract, source, replay)
        self.assertEqual(("match", []), (result["status"], result["differences"]))
        self.assertEqual(80, len(self.contract["assertions"]))
        self.assertEqual(95, sum(len(rows) for rows in source["catalog"].values()))
        pbr = next(r for r in source["catalog"]["tablespaces_1"] if r["NAME"] == "QAVS03")
        self.assertEqual((None, -1, "BP0     "), (pbr["FREEPAGE"], pbr["LOCKMAX"], pbr["BPOOL"]))
        self.assertEqual("STATUS IN ('A', 'I', 'S')", source["catalog"]["checks_1"][0]["CHECKCONDITION"])
        fixture = qa.snapshot(self.contract, "source", exports())["provenance"]["files"]["checks_1"]
        self.assertEqual(("tests/fixtures/varied-schema-catalog/checks_1.csv", 3), (fixture["file"], fixture["rows"]))

    def test_every_result_set_needs_exactly_one_well_formed_export(self):
        files = exports(self.dir)
        for broken in ({k: v for k, v in files.items() if k != "checks_1"}, {**files, "extra_1": files["checks_1"]}):
            with self.assertRaises(ValueError):
                qa.snapshot(self.contract, "source", broken)
        cases = [("tables_1", "TSNAME_EXPLICIT\n", "TSNAME\n"),                   # wrong column name
                 ("relations_1", "PARENT_SCHEMA_MATCH\n", "PARENT_SCHEMA_MATCH,COLCOUNT\n"),  # repeated column
                 ("foreign_keys_1", "CUSTOMER_ID,3\n", "CUSTOMER_ID\n"),           # short row
                 ("index_keys_1", "SKU,2,", "SKU,two,"),                           # text in SMALLINT
                 ("tablespaces_1", '"QAVS01","G",1,', '"QAVS01","G",,')]           # NULL in a NOT NULL column
        for query, old, new in cases:
            with self.subTest(query=query, new=new):
                self.tearDown()
                self.setUp()
                self.edit(query, old, new)
                with self.assertRaises(ValueError):
                    self.convert()
        (self.dir / "database_1.csv").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "header"):
            self.convert()

    def test_contracts_without_declared_types_are_refused(self):
        contract = copy.deepcopy(self.contract)
        del contract["catalog"][0]["types"]
        with self.assertRaisesRegex(ValueError, "declared types"):
            qa.snapshot(contract, "source", exports(self.dir))

    def test_column_order_delimiter_bom_and_null_marker_do_not_change_values(self):
        baseline = self.convert()["catalog"]
        lines = (self.dir / "foreign_keys_1.csv").read_text().splitlines()
        rewritten = "\r\n".join(";".join(reversed(line.split(","))) for line in lines) + "\r\n"
        (self.dir / "foreign_keys_1.csv").write_text("\ufeff" + rewritten, encoding="utf-8")
        self.edit("tablespaces_1", ",,,,,,,,", ",NULL,NULL,NULL,NULL,NULL,NULL,NULL,")

        def one(query, **options):
            contract = {**self.contract, "catalog": [q for q in self.contract["catalog"] if q["id"] == query]}
            return qa.snapshot(contract, "source", {query: self.dir / f"{query}.csv"}, **options)["catalog"][query]
        self.assertEqual(baseline["foreign_keys_1"], one("foreign_keys_1", delimiter=";"))
        self.assertEqual(baseline["tablespaces_1"], one("tablespaces_1", null="NULL"))

    def test_cli_writes_a_new_snapshot_and_never_overwrites(self):
        contract = self.dir / "contract.json"
        contract.write_text(qa.dump(self.contract))
        out = self.dir / "source.json"
        base = [sys.executable, str(ROOT / "tools/qa.py"), "snapshot", "--contract", str(contract), "--side", "source",
                "--csv-dir", str(self.dir), "--out", str(out)]
        first = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertIn("rows database_1=1", first.stderr)
        self.assertEqual(self.convert()["catalog"], qa.read(out)["catalog"])
        self.assertEqual(2, subprocess.run(base, capture_output=True, text=True).returncode)
        moved = self.dir / "elsewhere.csv"
        (self.dir / "checks_1.csv").rename(moved)
        override = subprocess.run(base[:-2] + ["--result", f"checks_1={moved}"], capture_output=True, text=True)
        self.assertEqual(0, override.returncode, override.stderr)
        self.assertEqual(3, len(json.loads(override.stdout)["catalog"]["checks_1"]))
        missing = subprocess.run(base[:-2], capture_output=True, text=True)
        self.assertEqual(2, missing.returncode)
        self.assertIn("checks_1", missing.stderr)


# (result set, row selector, field, seeded value, asserted by the contract)
CATALOG_DEFECTS = [
    ("database_1", {}, "INDEXBP", "BP1     ", True),
    ("tablespaces_1", {"NAME": "QAVS01"}, "MAXROWS", 255, True),
    ("tablespaces_1", {"NAME": "QAVS02"}, "SEGSIZE", 32, True),
    ("tablespaces_1", {"NAME": "QAVS03"}, "PAGENUM", "A", True),
    ("tablespaces_1", {"NAME": "QAVS04"}, "LOCKMAX", 0, True),
    ("tablespace_parts_1", {"TSNAME": "QAVS03", "PARTITION": 1}, "FREEPAGE", 0, False),
    ("tablespace_parts_1", {"TSNAME": "QAVS03", "PARTITION": 3}, "COMPRESS", " ", False),
    ("tablespace_parts_1", {"TSNAME": "QAVS03", "PARTITION": 1}, "LIMITKEY", "'2024-12-30'", False),
    ("tables_1", {"NAME": "CUSTOMER"}, "DATACAPTURE", " ", True),
    ("tables_1", {"NAME": "CUSTOMER"}, "AUDITING", "C", True),
    ("tables_1", {"NAME": "PRODUCT"}, "SPLIT_ROWS", " ", True),
    ("columns_1", {"TBNAME": "CUSTOMER", "COLNO": 1}, "DEFAULT", "J", True),
    ("columns_1", {"TBNAME": "CUSTOMER", "COLNO": 10}, "HIDDEN", "N", True),
    ("columns_1", {"TBNAME": "CUSTOMER", "COLNO": 4}, "DEFAULTVALUE", "B", False),
    ("columns_1", {"TBNAME": "SALES_ORDER", "COLNO": 5}, "DEFAULTVALUE", "WEB ", False),
    ("columns_1", {"TBNAME": "SALES_ORDER", "COLNO": 2}, "PARTKEY_ORDERING", "D", False),
    ("relations_1", {"TBNAME": "SALES_ORDER", "RELNAME": "ORDER_CODE_FK"}, "DELETERULE", "N", True),
    ("relations_1", {"TBNAME": "PRODUCT_DOC", "RELNAME": "DOC_PRODUCT_FK"}, "DELETERULE", "R", True),
    ("relations_1", {"TBNAME": "ORDER_LINE", "RELNAME": "LINE_ORDER_FK"}, "ENFORCED", "Y", True),
    ("relations_1", {"TBNAME": "ORDER_LINE", "RELNAME": "PRODUCT_ID"}, "DELETERULE", "R", False),
    ("checks_1", {"CHECKNAME": "CUSTOMER_CK"}, "CHECKCONDITION", "STATUS IN ('A', 'I')", False),
    ("indexes_1", {"NAME": "PRODUCT_SKUIX"}, "PADDED", "N", True),
    ("indexes_1", {"NAME": "ORDER_DATEIX"}, "CLUSTERING", "N", True),
    ("index_keys_1", {"IXNAME": "PRODUCT_SKUIX", "COLSEQ": 1}, "ORDERING", "A", True),
    ("index_keys_1", {"IXNAME": "CUSTOMER_UKIX", "COLSEQ": 2}, "ORDERING", "A", True),
    ("index_parts_1", {"IXNAME": "ORDER_DATEIX", "PARTITION": 2}, "PCTFREE", 15, False),
]


class SeededCatalogDefectTests(unittest.TestCase):
    """Each seeded single-field defect must turn a matching comparison into a mismatch that names the
    result set, and a defect on both sides must still fail where the contract encodes an expectation."""

    @classmethod
    def setUpClass(cls):
        cls.contract = exemplar_contract()
        cls.source = qa.snapshot(cls.contract, "source", exports())
        cls.replay = qa.snapshot(cls.contract, "replay", exports())

    def seed(self, snapshot, query, where, field, value):
        seeded = copy.deepcopy(snapshot)
        rows = [r for r in seeded["catalog"][query] if all(r[k] == v for k, v in where.items())]
        self.assertEqual(1, len(rows), (query, where))
        self.assertNotEqual(rows[0][field], value, "a seeded defect must change the value")
        rows[0][field] = value
        return seeded

    def test_defects_in_the_replay_are_reported_against_their_result_set(self):
        for query, where, field, value, asserted in CATALOG_DEFECTS:
            with self.subTest(query=query, where=where, field=field):
                result = qa.compare(self.contract, self.source, self.seed(self.replay, query, where, field, value))
                self.assertEqual("mismatch", result["status"])
                changed = [d for d in result["differences"] if d["catalog"] == query and "replay_only" in d]
                self.assertEqual(1, len(changed))
                padded = field in next(q for q in self.contract["catalog"] if q["id"] == query)["rtrim_fields"]
                self.assertEqual(value.rstrip(" ") if padded else value, changed[0]["replay_only"][0][field])
                failed = [d for d in result["differences"] if "failed_assertion" in d]
                self.assertEqual(asserted, bool(failed))
                self.assertTrue(all(d["side"] == "replay" for d in failed))

    def test_identical_wrong_definitions_fail_where_an_expectation_exists(self):
        for query, where, field, value, asserted in CATALOG_DEFECTS:
            if not asserted:
                continue
            with self.subTest(query=query, where=where, field=field):
                source = self.seed(self.source, query, where, field, value)
                replay = self.seed(self.replay, query, where, field, value)
                result = qa.compare(self.contract, source, replay)
                self.assertEqual("mismatch", result["status"])
                self.assertEqual({"source", "replay"}, {d["side"] for d in result["differences"]})
                self.assertTrue(all("failed_assertion" in d for d in result["differences"]))

    def test_lost_and_renamed_rows_are_mismatches(self):
        lost = copy.deepcopy(self.replay)
        lost["catalog"]["columns_1"] = [r for r in lost["catalog"]["columns_1"] if r["NAME"] != "PICK_TIME"]
        result = qa.compare(self.contract, self.source, lost)  # 38 rows is inside the 38..39 range
        self.assertEqual("mismatch", result["status"])
        self.assertTrue(any(d.get("failed_assertion", {}).get("where") == {"TBNAME": "SALES_ORDER", "COLNO": 8} for d in result["differences"]))
        renamed = copy.deepcopy(self.replay)
        for query in ("relations_1", "foreign_keys_1"):
            for row in renamed["catalog"][query]:
                if row["RELNAME"] == "ORDER_CODE_FK":
                    row["RELNAME"] = "ORDER_CODE_FK2"
        result = qa.compare(self.contract, self.source, renamed)
        self.assertEqual({"relations_1", "foreign_keys_1"}, {d["catalog"] for d in result["differences"]})

    def test_order_padding_and_unselected_columns_do_not_matter(self):
        replay = copy.deepcopy(self.replay)
        for rows in replay["catalog"].values():
            rows.reverse()
        for row in replay["catalog"]["tablespaces_1"]:
            row["BPOOL"] = row["BPOOL"].rstrip()  # CHAR(8) padding, declared as an rtrim field
            row["PQTY"] = 999  # a column the contract does not select
        self.assertEqual("match", qa.compare(self.contract, self.source, replay)["status"])

    def test_malformed_evidence_is_an_error_not_a_result(self):
        mutations = {
            "missing result set": lambda s: s["catalog"].pop("checks_1"),
            "row count outside the contract": lambda s: s["catalog"]["tablespaces_1"].pop(),
            "duplicate key": lambda s: s["catalog"]["tablespaces_1"][1].update(NAME="QAVS01"),
            "string for SMALLINT": lambda s: s["catalog"]["index_keys_1"][0].update(COLSEQ="1"),
            "NULL in a NOT NULL column": lambda s: s["catalog"]["tables_1"][0].update(STATUS=None),
            "wrong side label": lambda s: s.update(side="source"),
            "converted for another contract": lambda s: s["provenance"].update(contract_sha256="0" * 64),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                replay = copy.deepcopy(self.replay)
                mutate(replay)
                with self.assertRaises(ValueError):
                    qa.compare(self.contract, self.source, replay)

    def test_a_defect_seeded_in_the_csv_export_survives_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in exports().values():
                shutil.copy(path, Path(tmp) / path.name)
            path = Path(tmp) / "relations_1.csv"
            text = path.read_text()
            path.write_text(text.replace("ORDER_LINE,LINE_PARENT_FK,ORDER_LINE,2,A,", "ORDER_LINE,LINE_PARENT_FK,ORDER_LINE,2,C,"))
            result = qa.compare(self.contract, self.source, qa.snapshot(self.contract, "replay", exports(tmp)))
        self.assertEqual("mismatch", result["status"])
        self.assertEqual("C", next(d for d in result["differences"] if "replay_only" in d)["replay_only"][0]["DELETERULE"])


if __name__ == "__main__":
    unittest.main()


class OutcomeRecordTests(unittest.TestCase):
    """Phase results are appended to the case record; only recorded evidence moves its status."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        text = paths.VARIED_SCHEMA.read_text()
        report = db2check.analyze(text, db2check.Options.from_profile(PROFILE))
        names = db2check.NameMap({"QAV": "QAVR"}, {"QAVDB01": "QAVRDB01"})
        for name, content in db2check.bundle(report, text, names, "QAV", PROFILE).items():
            (self.dir / name).write_text(content, encoding="utf-8")
        self.log = self.evidence("run.log", "statement 1: SQLCODE 0\n")
        self.product_sql = self.evidence("product-generated.sql", paths.REGENERATED_SCHEMA.read_text())
        self.contract = qa.read(self.dir / "catalog-contract.json")

    def tearDown(self):
        self.tmp.cleanup()

    def evidence(self, name, text):
        path = self.dir / "evidence" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
        return path

    def record(self, phase, result="pass", **options):
        defaults = {"source": {"evidence": [self.log], "sqlcode": 0},
                    "extraction": {"evidence": [self.product_sql], "product": "Product", "product_version": "1.0"},
                    "replay": {"evidence": [self.log], "sqlcode": 0}}.get(phase, {})
        return qa.record_outcome(self.dir, phase, result, **{**defaults, **options})[0]

    def snapshots(self, replay_edit=None):
        source = qa.snapshot(self.contract, "source", exports())
        replay = qa.snapshot(self.contract, "replay", exports())
        if replay_edit:
            replay_edit(replay)
        files = []
        for side, data in (("source", source), ("replay", replay)):
            files.append(self.dir / f"{side}.json")
            files[-1].write_text(qa.dump(data))
        return (self.dir / "catalog-contract.json", *files)

    def test_a_round_trip_passes_only_after_every_phase_has_evidence(self):
        self.assertEqual("design", qa.read(self.dir / "case.json")["status"])
        statuses = [self.record(phase)["status"] for phase in ("source", "extraction", "replay")]
        self.assertEqual(["in_progress"] * 3, statuses)
        record = qa.record_outcome(self.dir, "comparison", snapshots=self.snapshots())[0]
        self.assertEqual("pass", record["status"])
        comparison = record["outcomes"]["comparison"][0]
        self.assertEqual({"status": "match", "differences": 0, "failed_assertions": 0}, comparison["compare"])
        self.assertEqual(["catalog-contract.json", "source.json", "replay.json"], [e["path"] for e in comparison["evidence"]])
        self.assertEqual("evidence/run.log", record["outcomes"]["source"][0]["evidence"][0]["path"])
        qa.validate_case(record)
        self.assertEqual([], qa.case_status(self.dir)["problems"])

    def test_phases_follow_their_prerequisites_and_need_evidence(self):
        with self.assertRaisesRegex(ValueError, "passing source"):
            self.record("extraction")
        with self.assertRaisesRegex(ValueError, "missing evidence"):
            self.record("source", evidence=[])
        with self.assertRaisesRegex(ValueError, "missing or empty"):
            self.record("source", evidence=[self.evidence("empty.log", "")])
        with self.assertRaisesRegex(ValueError, "--note"):
            self.record("source", "blocked", evidence=[])
        with self.assertRaisesRegex(ValueError, "negative SQLCODE"):
            self.record("source", sqlcode=-204)
        self.record("source")
        with self.assertRaisesRegex(ValueError, "--product"):
            self.record("extraction", product=None, product_version=None)
        self.assertEqual(1, len(qa.read(self.dir / "case.json")["outcomes"]["source"]), "refused attempts are not recorded")

    def test_comparison_result_comes_from_compare(self):
        for phase in ("source", "extraction", "replay"):
            self.record(phase)
        with self.assertRaisesRegex(ValueError, "comes from compare"):
            qa.record_outcome(self.dir, "comparison", "pass", snapshots=self.snapshots())
        broken = self.snapshots(lambda replay: replay["catalog"]["tables_1"][0].update(DATACAPTURE=" "))
        record = qa.record_outcome(self.dir, "comparison", snapshots=broken)[0]
        self.assertEqual("fail", record["status"])
        self.assertEqual({"status": "mismatch", "differences": 2, "failed_assertions": 1}, record["outcomes"]["comparison"][0]["compare"])
        malformed = self.snapshots(lambda replay: replay["catalog"].pop("checks_1"))
        with self.assertRaisesRegex(ValueError, "missing result set"):
            qa.record_outcome(self.dir, "comparison", snapshots=malformed)
        self.assertEqual(1, len(qa.read(self.dir / "case.json")["outcomes"]["comparison"]))
        # A later attempt replaces the verdict: the fixed replay passes.
        self.assertEqual("pass", qa.record_outcome(self.dir, "comparison", snapshots=self.snapshots())[0]["status"])

    def test_failures_and_blocks_decide_the_status(self):
        self.assertEqual("blocked", self.record("source", "blocked", evidence=[], note="Storage group not available")["status"])
        self.assertEqual("in_progress", self.record("source")["status"])
        self.record("extraction")
        self.assertEqual("fail", self.record("replay", "fail", sqlcode=-104, sqlstate="42601")["status"])
        self.assertEqual("fail", self.record("cleanup", "fail", evidence=[], note="drop failed")["status"])

    def test_negative_cases_end_at_the_source_run(self):
        model = qa.models()["index-core"]
        constraint = model["constraints"][0]["id"]
        raw, _ = qa.candidates(model)
        selection = next(s for s in raw if qa.violations(model, s) == [constraint])
        record, _ = qa.make_case(model, selection, PROFILE, "NG", 1, constraint)
        (self.dir / "case.json").write_text(qa.dump(record))
        (self.dir / "catalog-contract.json").unlink()
        with self.assertRaisesRegex(ValueError, "does not apply"):
            self.record("extraction")
        with self.assertRaisesRegex(ValueError, "SQLCODE of the intended failure"):
            self.record("source", sqlcode=None)
        with self.assertRaisesRegex(ValueError, "reports success"):
            self.record("source", sqlcode=0)
        self.assertEqual("pass", self.record("source", sqlcode=-669, sqlstate="42917")["status"])

    def test_cases_with_behavior_probes_need_the_probe_phase(self):
        selection = {"access": "contains", "determinism": "omitted", "body": "compact"}
        record, contract = qa.make_case(qa.models()["procedure-native"], selection, PROFILE, "PR", 1)
        (self.dir / "case.json").write_text(qa.dump(record))
        (self.dir / "catalog-contract.json").write_text(qa.dump(contract))
        catalog = {  # typed rows for this selection, as in test_routine_models
            "routine": [{"ROUTINETYPE": "P", "ORIGIN": "N", "LANGUAGE": "SQL", "PARM_COUNT": 2, "DETERMINISTIC": "N",
                         "SQL_DATA_ACCESS": "C", "NULL_CALL": "Y", "RESULT_SETS": 0, "COMMIT_ON_RETURN": "N",
                         "VERSION": "V1", "ACTIVE": "Y", "DEBUG_MODE": "N", "PARAMETER_CCSID": 1208}],
            "parameters": [{"ORDINAL": 1, "PARMNAME": "P_FLAG", "ROWTYPE": "P", "TYPENAME": "INTEGER", "LENGTH": 4, "SCALE": 0, "CCSID": 0},
                           {"ORDINAL": 2, "PARMNAME": "P_TEXT", "ROWTYPE": "O", "TYPENAME": "VARCHAR", "LENGTH": 64, "SCALE": 0, "CCSID": 1208}],
            "package": [{"TYPE": "N", "VERSION": "V1", "APPLCOMPAT": PROFILE["product_context"]["applcompat"]}]}
        snapshots = [self.dir / "catalog-contract.json"]
        for side in ("source", "replay"):
            snapshots.append(self.dir / f"{side}.json")
            snapshots[-1].write_text(qa.dump({"case_id": record["id"], "side": side, "catalog": catalog}))
        for phase in ("source", "extraction", "replay"):
            self.record(phase)
        self.assertEqual("in_progress", qa.record_outcome(self.dir, "comparison", snapshots=snapshots)[0]["status"])
        self.assertEqual("probes", qa.case_status(self.dir)["next"])
        self.assertEqual("pass", self.record("probes", evidence=[self.log])["status"])

    def test_status_reports_progress_and_changed_evidence(self):
        self.record("source")
        report = qa.case_status(self.dir / "case.json")
        self.assertEqual(("in_progress", "extraction", []), (report["status"], report["next"], report["problems"]))
        command = [sys.executable, str(ROOT / "tools/qa.py"), "status", str(self.dir)]
        self.assertEqual(1, subprocess.run(command, capture_output=True).returncode)
        self.log.write_text("edited after the fact\n")
        result = subprocess.run(command + ["--json"], capture_output=True, text=True)
        self.assertEqual(2, result.returncode)
        self.assertIn("changed after it was recorded", json.loads(result.stdout)[0]["problems"][0])

    def test_validation_rejects_statuses_without_matching_evidence(self):
        record = qa.read(self.dir / "case.json")
        for status in ("pass", "in_progress", "fail"):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "needs outcomes"):
                qa.validate_case({**record, "status": status})
        recorded = self.record("source")
        with self.assertRaisesRegex(ValueError, "contradicts"):
            qa.validate_case({**recorded, "status": "pass"})
        self.assertEqual("retired", qa.derive_status({**recorded, "status": "retired"}))
        (self.dir / "case.json").write_text(qa.dump({**recorded, "status": "retired"}))
        with self.assertRaisesRegex(ValueError, "retired"):
            self.record("extraction")

    def test_cli_records_a_comparison_from_the_contract_beside_the_case(self):
        for phase in ("source", "extraction", "replay"):
            self.record(phase)
        _, source, replay = self.snapshots()
        base = [sys.executable, str(ROOT / "tools/qa.py"), "record", str(self.dir), "--phase", "comparison",
                "--source", str(source), "--replay", str(replay), "--at", "2026-10-10T12:00:00Z"]
        result = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("comparison pass", result.stdout)
        self.assertEqual("2026-10-10T12:00:00Z", qa.read(self.dir / "case.json")["outcomes"]["comparison"][0]["recorded_at"])
        self.assertEqual(2, subprocess.run(base + ["--result", "pass"], capture_output=True).returncode)
