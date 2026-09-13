"""Bounded relational campaign checks; none of these executes Db2 SQL."""
from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import itertools
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import qa


class RelationalCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = qa.read(ROOT / 'kb/campaigns/models/table-relational.json')
        cls.profile = qa.read(ROOT / 'kb/campaigns/profiles/example.json')

    def selection(self, **changes):
        return {**dict(fk_nullability='one-nullable', delete_rule='cascade',
                    payload='varchar-literal', check_shape='compound'), **changes}

    def case(self, selection=None, run='QA', number=1):
        return qa.make_case(self.model, selection or self.selection(),
                            self.profile, run, number)

    def test_domain_and_pairs_against_independent_reference(self):
        axes = ['fk_nullability', 'delete_rule', 'payload', 'check_shape']
        expected = [dict(zip(axes, values)) for values in itertools.product(
            ['none-nullable', 'one-nullable', 'all-nullable'],
            ['omitted', 'restrict', 'no-action', 'cascade', 'set-null'],
            ['varchar-min', 'varchar-literal', 'decimal-wide', 'timestamp-max'],
            ['amount', 'compound', 'date-or-null'])
            if not (values[0] == 'none-nullable' and values[1] == 'set-null')]
        raw, actual = qa.candidates(self.model)
        self.assertEqual(len(raw), 180)
        self.assertEqual(len(actual), 168)
        self.assertEqual(actual, expected)
        selected, report = qa.select_cases(actual, 'pairwise')
        self.assertTrue(report['complete'])
        for left, right in itertools.combinations(axes, 2):
            self.assertEqual({(s[left], s[right]) for s in selected},
                             {(s[left], s[right]) for s in expected})

    def test_set_null_accepts_one_nullable_and_isolates_negative(self):
        raw, valid = qa.candidates(self.model)
        for nullable in ['one-nullable', 'all-nullable']:
            candidate = self.selection()
            candidate.update(delete_rule='set-null', fk_nullability=nullable)
            self.assertIn(candidate, valid)
        invalid = [s for s in raw if s not in valid]
        self.assertEqual(len(invalid), 12)
        for candidate in invalid:
            self.assertEqual(qa.violations(self.model, candidate),
                             ['set-null-requires-nullable'])
        record, _ = qa.make_case(self.model, invalid[0], self.profile,
                                 'QA', 2, 'set-null-requires-nullable')
        self.assertEqual(record['setup_sql'], self.case(number=2)[0]['setup_sql'])
        self.assertIsNone(record['expected']['sqlcode'])
        self.assertIsNone(record['expected']['sqlstate'])
        self.assertEqual(record['status'], 'design')

    def test_parent_indexes_precede_child_and_cleanup_uses_owners(self):
        ordered = [node['id'] for node in qa.order_nodes(self.model['nodes'])]
        for index in ['parent_primary_index', 'parent_unique_index']:
            self.assertLess(ordered.index('parent'), ordered.index(index))
            self.assertLess(ordered.index(index), ordered.index('child'))
        record, contract = self.case()
        self.assertEqual(len(record['setup_sql']), 5)
        self.assertEqual(len(record['action_sql']), 1)
        self.assertEqual(record['cleanup_sql'], [
            'DROP TABLESPACE QASDB.QA0001',
            'DROP TABLESPACE QASDB.QAP001'])
        self.assertEqual(contract['replay_cleanup_sql'], [
            'DROP TABLESPACE QARDB.QA0001',
            'DROP TABLESPACE QARDB.QAP001'])
        self.assertTrue(all(not s.startswith('DROP INDEX')
                            for s in record['cleanup_sql']))

    def test_all_object_names_fit_and_dependencies_are_mapped(self):
        record, contract = self.case(run='ABCD', number=999)
        params = record['parameters']
        self.assertEqual(params['TABLESPACE'], 'ABCD0999')
        self.assertEqual(params['PARENT_TABLESPACE'], 'ABCDP999')
        names = record['ofs_validation']['name_map']
        for suffix in ['P', 'U']:
            self.assertEqual(names['QASRC.ABCD0999' + suffix],
                             'QADST.ABCD0999' + suffix)
        self.assertEqual(names['ABCDSDB.ABCDP999'], 'ABCDRDB.ABCDP999')
        self.assertEqual(names['ABCDSDB.ABCD0999'], 'ABCDRDB.ABCD0999')
        self.assertNotIn('{{', json.dumps(record))
        for query in contract['catalog']:
            self.assertNotIn('{{', query['source_sql'])
            self.assertNotIn('{{', query['replay_sql'])

    def test_build_preflight_checks_suffix_objects_on_both_sides(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(model='table-relational',
                profile=ROOT / 'kb/campaigns/profiles/example.json', run='QA',
                budget=1, negative=False, strategy='pairwise',
                out=Path(tmp) / 'case')
            with redirect_stdout(io.StringIO()):
                qa.write_campaign(args)
            preflight = (args.out / 'preflight.sql').read_text()
            self.assertIn("'QA0001P'", preflight)
            self.assertIn("'QA0001U'", preflight)
            self.assertIn("'QAP001'", preflight)
            self.assertIn("CREATOR = 'QASRC'", preflight)
            self.assertIn("CREATOR = 'QADST'", preflight)

    def test_fixture_does_not_restrict_table_payload_to_key_types(self):
        for profile, fragment in [('varchar-min', 'VARCHAR(1)'),
                                  ('varchar-literal', "DEFAULT 'MiXeD  '"),
                                  ('decimal-wide', 'DECIMAL(31,9)'),
                                  ('timestamp-max', 'TIMESTAMP(12)')]:
            selection = self.selection()
            selection['payload'] = profile
            case, _ = self.case(selection)
            self.assertIn(fragment, case['action_sql'][0])
            self.assertIn('REFERENCES QASRC.QA0001P (TENANT_ID, PARENT_ID)',
                          case['action_sql'][0])
            qa.validate_case(case)

    def snapshots(self, contract):
        # Independent synthetic export for the chosen case, not captured Db2 data.
        def column(no, name, kind, length, scale, nullable, default='', value=''):
            return dict(COLNO=no, NAME=name, COLTYPE=kind, LENGTH=length,
                        SCALE=scale, NULLS=nullable, DEFAULT=default,
                        DEFAULTVALUE=value)
        rows = {
            'parent_columns': [
                column(1, 'TENANT_ID', 'INTEGER', 4, 0, 'N'),
                column(2, 'PARENT_ID', 'INTEGER', 4, 0, 'N'),
                column(3, 'EXTERNAL_CODE', 'CHAR', 12, 0, 'N')],
            'child_columns': [
                column(1, 'CHILD_ID', 'INTEGER', 4, 0, 'N'),
                column(2, 'P_TENANT', 'INTEGER', 4, 0, 'N'),
                column(3, 'P_ID', 'INTEGER', 4, 0, 'Y'),
                column(4, 'AMOUNT', 'DECIMAL', 15, 2, 'N'),
                column(5, 'STATUS', 'CHAR', 1, 0, 'N', '1', 'N'),
                column(6, 'VALID_FROM', 'DATE', 4, 0, 'N'),
                column(7, 'VALID_TO', 'DATE', 4, 0, 'Y'),
                column(8, 'QA_VALUE', 'VARCHAR', 1024, 0, 'N', '1', 'MiXeD  ')],
            'relationship': [dict(RELNAME='FK_PARENT', COLCOUNT=2,
                DELETERULE='C', ENFORCED='Y', CHECKEXISTINGDATA='I', PARENT_MATCH=1)],
            'foreign_keys': [dict(RELNAME='FK_PARENT', COLSEQ=1, COLNO=2,
                COLNAME='P_TENANT'), dict(RELNAME='FK_PARENT', COLSEQ=2,
                COLNO=3, COLNAME='P_ID')],
            'parent_primary_index': [dict(UNIQUERULE='P', COLCOUNT=2)],
            'parent_unique_index': [dict(UNIQUERULE='C', COLCOUNT=1)],
            'parent_primary_keys': [dict(COLSEQ=1, COLNO=1, COLNAME='TENANT_ID',
                ORDERING='A'), dict(COLSEQ=2, COLNO=2, COLNAME='PARENT_ID', ORDERING='A')],
            'parent_unique_keys': [dict(COLSEQ=1, COLNO=3,
                COLNAME='EXTERNAL_CODE', ORDERING='A')],
            'checks': [dict(CHECKNAME='CK_VALUE', PERIOD='', CHECKCONDITION=
                "AMOUNT BETWEEN 0.00 AND 9999999999999.99 AND STATUS IN ('N', 'A', 'C')")],
            'parent_table': [dict(TYPE='T', STATUS='X', SPACE_MATCH=1)],
            'child_table': [dict(TYPE='T', STATUS='', SPACE_MATCH=1)],
        }
        source = dict(case_id=contract['case_id'], side='source', catalog=rows)
        replay = copy.deepcopy(source)
        replay['side'] = 'replay'
        return source, replay

    def test_catalog_oracle_rejects_identical_wrong_relationships_and_keys(self):
        _, contract = self.case()
        source, replay = self.snapshots(contract)
        self.assertEqual(qa.compare(contract, source, replay)['status'], 'match')
        corruptions = [
            ('relationship', 0, 'PARENT_MATCH', 0),
            ('relationship', 0, 'DELETERULE', 'R'),
            ('relationship', 0, 'ENFORCED', 'N'),
            ('child_columns', 2, 'NULLS', 'N'),
            ('child_columns', 7, 'DEFAULTVALUE', 'MiXeD'),
            ('parent_primary_index', 0, 'UNIQUERULE', 'U'),
            ('parent_unique_index', 0, 'UNIQUERULE', 'U'),
            ('foreign_keys', 0, 'COLNAME', 'P_ID'),
            ('parent_primary_keys', 0, 'COLNAME', 'PARENT_ID'),
            ('parent_table', 0, 'STATUS', 'I'),
            ('child_table', 0, 'SPACE_MATCH', 0),
        ]
        for query, row, field, value in corruptions:
            with self.subTest(query=query, field=field):
                bad_source, bad_replay = copy.deepcopy(source), copy.deepcopy(replay)
                for snapshot in [bad_source, bad_replay]:
                    snapshot['catalog'][query][row][field] = value
                result = qa.compare(contract, bad_source, bad_replay)
                self.assertEqual(result['status'], 'mismatch')
                self.assertTrue(any('failed_assertion' in diff
                                    for diff in result['differences']))

    def test_text_is_lossless_and_missing_dependency_evidence_fails(self):
        _, contract = self.case()
        source, replay = self.snapshots(contract)
        replay['catalog']['checks'][0]['CHECKCONDITION'] = 'AMOUNT >= 0.00'
        self.assertEqual(qa.compare(contract, source, replay)['status'], 'mismatch')
        source, replay = self.snapshots(contract)
        del replay['catalog']['parent_primary_keys']
        with self.assertRaises(ValueError):
            qa.compare(contract, source, replay)


if __name__ == '__main__':
    unittest.main()
