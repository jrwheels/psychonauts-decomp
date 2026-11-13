"""Synthetic cross-provider coverage checks; no reference executable needed."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from analysis_coverage import compare


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.index = {'binary_sha256': 'a'*64, 'function': {'address': '0x1000', 'size': '4'},
                      'instructions': [{'va': 0x1000}, {'va': 0x1001}, {'va': 0x1003}]}
        self.ca = {'subject': {'sha256': 'a'*64}, 'id': 'ev-test', 'operation': 'native_function_study',
                   'result': {'function': {'entry': '0x1000', 'instructions': 2, 'truncated': False},
                              'assembly': [{'address': '0x1000'}, {'address': '0x1003'}]}}

    def test_reports_omission_without_claiming_match(self):
        r = compare(self.index, self.ca)
        self.assertEqual(r['index_only'], ['0x00001001'])
        self.assertEqual(r['provider_only'], [])
        self.assertFalse(r['establishes_match'])

    def test_rejects_wrong_binary_or_function(self):
        ca = copy.deepcopy(self.ca); ca['subject']['sha256'] = 'b'*64
        with self.assertRaises(ValueError): compare(self.index, ca)
        ca = copy.deepcopy(self.ca); ca['result']['function']['entry'] = '0x2000'
        with self.assertRaises(ValueError): compare(self.index, ca)

    def test_rejects_partial_duplicate_and_out_of_range(self):
        for mutate in ('partial', 'duplicate', 'outside', 'truncated'):
            ca = copy.deepcopy(self.ca)
            if mutate == 'truncated': ca['result']['function']['truncated'] = True
            if mutate == 'partial': ca['result']['function']['instructions'] = 3
            if mutate == 'duplicate': ca['result']['assembly'][1]['address'] = '0x1000'
            if mutate == 'outside': ca['result']['assembly'][1]['address'] = '0x1004'
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): compare(self.index, ca)

    def test_rea_dossier_and_bad_assembly(self):
        evidence = {'operation': 'analyze_function', 'evidence_id': 'rea-test',
                    'subject': {'digest': {'sha256': 'a'*64}}, 'provider': {'id': 'ghidra'},
                    'normalized_result': {'procedure': {'address': '0x1000', 'body': {
                        'available': True, 'ranges': [{'start': '0x1000', 'end': '0x1003'}]}},
                        'facet_availability': {'assembly': {'available': True}},
                        'assembly': ['0x1000: NOP', '0x1003: RET']}}
        result = compare(self.index, {'result': {'structuredContent': evidence}})
        self.assertEqual(result['index_only'], ['0x00001001'])
        self.assertEqual(result['provider'], 'ghidra')
        evidence['normalized_result']['assembly'][0] = 'malformed'
        with self.assertRaises(ValueError): compare(self.index, evidence)

    def test_provider_only_is_reported(self):
        self.ca['result']['assembly'][1]['address'] = '0x1002'
        r = compare(self.index, self.ca)
        self.assertEqual(r['provider_only'], ['0x00001002'])
        self.assertEqual(r['index_only'], ['0x00001001', '0x00001003'])


if __name__ == '__main__': unittest.main()
