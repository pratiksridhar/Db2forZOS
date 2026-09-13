from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import qa
from sqltext import inspect_sql


class RoutineCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = {name: qa.models()[name] for name in ('trigger-basic', 'procedure-native')}
        cls.profile = qa.read(ROOT / 'kb/campaigns/profiles/example.json')
        cls.payload = "  MiXeD; 'quoted'  tail "

    def test_restrictions_have_independent_positive_denominators_and_isolated_negatives(self):
        for name, model in self.models.items():
            raw, valid = qa.candidates(model)
            if name == 'trigger-basic':
                expected = [s for s in raw if s['activation'] == 'no-cascade-before']
                self.assertEqual((len(raw), len(expected)), (40, 20))
            else:
                expected = [s for s in raw if s['access'] in {'contains', 'reads', 'modifies'}]
                self.assertEqual((len(raw), len(expected)), (60, 45))
            self.assertEqual(valid, expected)
            constraint = model['constraints'][0]['id']
            isolated = [s for s in raw if qa.violations(model, s) == [constraint]]
            self.assertTrue(isolated)
            case, _ = qa.make_case(model, isolated[0], self.profile, 'RN', 1, constraint)
            self.assertIsNone(case['expected']['sqlcode'])
            self.assertIsNone(case['expected']['sqlstate'])
            self.assertEqual(case['expected']['outcome'], 'sql_error')

    def test_every_valid_body_retains_literal_comments_and_internal_statement_count(self):
        literal = "'" + self.payload.replace("'", "''") + "'"
        for name, model in self.models.items():
            qa.validate_model(model, qa.kb())
            for selection in qa.candidates(model)[1]:
                case, contract = qa.make_case(model, selection, self.profile, 'RN', 1)
                qa.validate_case(case)
                action = case['action_sql'][0]
                body = model['dimensions']['body'][selection['body']]['sql']
                self.assertIn(body, action)
                self.assertIn(literal, action)
                self.assertEqual(len(inspect_sql(action)['semicolon_positions']), 1 if name == 'trigger-basic' else 4)
                self.assertEqual(case['status'], 'design')
                self.assertEqual(contract['statement_terminator'], '@')
                if selection['body'] == 'long-comment':
                    self.assertGreater(len(body), 6000)
                if name == 'trigger-basic':
                    self.assertIn('NO CASCADE BEFORE', action)
                    self.assertIn('MODE DB2SQL', action)
                    self.assertIn('REFERENCING NEW AS N', action)
                else:
                    self.assertNotIn('BEGIN ATOMIC', action)
                    self.assertIn('SPECIFIC QASRC.RN0001', action)
                    self.assertIn('APPLCOMPAT ' + self.profile['product_context']['applcompat'], action)
                    self.assertNotIn('FENCED', action)
                    self.assertNotIn('EXTERNAL', action)

    def test_trigger_cleanup_has_one_owner_for_the_fixture_table(self):
        model = self.models['trigger-basic']
        case, contract = qa.make_case(model, qa.candidates(model)[1][0], self.profile, 'RN', 1)
        self.assertEqual(case['cleanup_sql'], ['DROP TRIGGER QASRC.RN0001', 'DROP TABLESPACE RNSDB.RN0001'])
        self.assertEqual(contract['replay_cleanup_sql'], ['DROP TRIGGER QADST.RN0001', 'DROP TABLESPACE RNRDB.RN0001'])
        self.assertIn('RNSDB.RN0001', case['ofs_validation']['name_map'])

    def test_text_is_captured_losslessly_without_comparing_relocated_full_definitions(self):
        for name, model in self.models.items():
            _, contract = qa.make_case(model, qa.candidates(model)[1][0], self.profile, 'RN', 1)
            self.assertTrue(all(not {'TEXT', 'STATEMENT'} & set(q['fields']) for q in contract['catalog']))
            capture = next(p for p in contract['probes'] if p['id'].startswith('capture-'))
            self.assertIn('Lossless full CLOB', capture['expected']['export'])
            self.assertNotEqual(capture['source_sql'], capture['replay_sql'])
            self.assertIn('QASRC', capture['source_sql'])
            self.assertIn('QADST', capture['replay_sql'])
            if name == 'trigger-basic':
                self.assertIn('SELECT STATEMENT FROM SYSIBM.SYSTRIGGERS', capture['source_sql'])
            else:
                self.assertIn('SELECT TEXT FROM SYSIBM.SYSROUTINES', capture['source_sql'])

    def test_behavior_contract_preserves_payload_and_native_null_branch(self):
        trigger = self.models['trigger-basic']
        readback = next(p for p in trigger['probes'] if p['id'] == 'verify-exact-payload')
        expected = readback['expected']['rows'][0]
        self.assertEqual(expected['QA_VALUE'], self.payload)
        self.assertEqual(expected['VALUE_LENGTH'], 24)
        procedure = self.models['procedure-native']
        calls = {p['id']: p for p in procedure['probes'] if p['id'].startswith('call-')}
        self.assertEqual(calls['call-true']['expected']['output_parameters']['2'], self.payload)
        self.assertEqual(calls['call-false']['expected']['output_parameters']['2'], 'other')
        self.assertEqual(calls['call-null']['expected']['output_parameters']['2'], 'other')
        self.assertIn('(?, ?)', calls['call-null']['sql'])
        self.assertIsNone(calls['call-null']['bindings'][0]['value'])
        self.assertEqual(calls['call-true']['bindings'][0]['value'], 1)
        self.assertEqual(calls['call-false']['bindings'][0]['value'], 0)
        for call in calls.values():
            self.assertEqual(call['bindings'][0]['position'], 1)
            self.assertEqual(call['bindings'][0]['mode'], 'IN')
            self.assertEqual(call['bindings'][0]['type'], 'INTEGER')
            self.assertEqual(call['bindings'][1], {'position': 2, 'mode': 'OUT', 'type': 'VARCHAR', 'length': 64})

    def test_corrupted_procedure_parameter_mode_cannot_pass_comparison(self):
        model = self.models['procedure-native']
        selection = {'access': 'contains', 'determinism': 'omitted', 'body': 'compact'}
        case, contract = qa.make_case(model, selection, self.profile, 'RN', 1)
        source = {'case_id': case['id'], 'side': 'source', 'catalog': {
            'routine': [{'ROUTINETYPE': 'P', 'ORIGIN': 'N', 'LANGUAGE': 'SQL', 'PARM_COUNT': 2,
                         'DETERMINISTIC': 'N', 'SQL_DATA_ACCESS': 'C', 'NULL_CALL': 'Y',
                         'RESULT_SETS': 0, 'COMMIT_ON_RETURN': 'N', 'VERSION': 'V1',
                         'ACTIVE': 'Y', 'DEBUG_MODE': 'N', 'PARAMETER_CCSID': 1208}],
            'parameters': [
                {'ORDINAL': 1, 'PARMNAME': 'P_FLAG', 'ROWTYPE': 'P', 'TYPENAME': 'INTEGER', 'LENGTH': 4, 'SCALE': 0, 'CCSID': 0},
                {'ORDINAL': 2, 'PARMNAME': 'P_TEXT', 'ROWTYPE': 'O', 'TYPENAME': 'VARCHAR', 'LENGTH': 64, 'SCALE': 0, 'CCSID': 1208}],
            'package': [{'TYPE': 'N', 'VERSION': 'V1', 'APPLCOMPAT': self.profile['product_context']['applcompat']}]}}
        replay = copy.deepcopy(source)
        replay['side'] = 'replay'
        self.assertEqual(qa.compare(contract, source, replay)['status'], 'match')
        replay['catalog']['parameters'][1]['ROWTYPE'] = 'B'
        self.assertEqual(qa.compare(contract, source, replay)['status'], 'mismatch')
        source['catalog']['parameters'][1]['ROWTYPE'] = 'B'
        self.assertEqual(qa.compare(contract, source, replay)['status'], 'mismatch')

    def test_cli_writes_intact_sql_pl_and_separate_never_run_probes(self):
        for name in self.models:
            with tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp) / name
                result = subprocess.run([sys.executable, str(ROOT / 'tools/qa.py'), 'build',
                    '--model', name, '--profile', str(ROOT / 'kb/campaigns/profiles/example.json'),
                    '--run', 'RN', '--budget', '1', '--out', str(destination)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                folder = next((destination / 'cases').iterdir())
                case = json.loads((folder / 'case.json').read_text())
                action = case['action_sql'][0]
                emitted = (folder / 'action.sql').read_text()
                self.assertIn(action + '\n@\n', emitted)
                probes = json.loads((folder / 'behavior-probes.json').read_text())
                self.assertEqual(probes['status'], 'design')
                self.assertTrue(probes['probes'])
                preflight = (destination / 'preflight.sql').read_text()
                self.assertIn('SYSIBM.SYSPACKAGE', preflight)
                self.assertIn('QASRC', preflight)
                self.assertIn('QADST', preflight)


if __name__ == '__main__':
    unittest.main()
