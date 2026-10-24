"""Synthetic classifier checks; no original bytes or third-party fixtures."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from near_match import classify, rank_key


class NearMatchTests(unittest.TestCase):
    def compare(self, left, right, relocs=(), known=None):
        return classify(bytes.fromhex(left), bytes.fromhex(right), 0x400000, relocs, known)

    def test_identical(self):
        result = self.compare('8b45fc c3', '8b45fc c3')
        self.assertEqual(sum(result['counts'].values()), 0)
        self.assertFalse(result['establishes_match'])

    def test_stack_slot(self):
        result = self.compare('8b45fc c3', '8b45f8 c3')
        self.assertEqual(result['counts']['stack_local'], 1)
        self.assertEqual(result['counts']['structural_instruction'], 0)
        self.assertTrue(result['stack_correspondence']['consistent'])

    def test_register(self):
        result = self.compare('8bc1 c3', '8bd1 c3')
        self.assertEqual(result['counts']['register_allocation'], 1)

    def test_structural_constant(self):
        result = self.compare('83c001 c3', '83c002 c3')
        self.assertEqual(result['counts']['structural_instruction'], 1)

    def test_inserted_instruction(self):
        result = self.compare('90 c3', '90 40 c3')
        self.assertEqual(result['counts']['structural_instruction'], 1)

    def test_branch_targets(self):
        result = self.compare('eb00 90 c3', 'eb01 90 c3')
        self.assertEqual(result['counts']['structural_instruction'], 1)

    def test_relocation_known(self):
        result = self.compare('e8fb0f0000 c3', 'e800000000 c3', [(1, 4, 'callee', 20)],
                              {'callee': 0x401000})
        self.assertEqual(sum(result['counts'].values()), 0)
        self.assertEqual(result['unresolved_relocations'], [])

    def test_relocation_conflict(self):
        result = self.compare('e8fb0f0000 c3', 'e800000000 c3', [(1, 4, 'callee', 20)],
                              {'callee': 0x402000})
        self.assertEqual(result['counts']['relocation'], 1)

    def test_absolute_relocation(self):
        result = self.compare('a100104000 c3', 'a100000000 c3', [(1, 4, 'global', 6)],
                              {'global': 0x401000})
        self.assertEqual(sum(result['counts'].values()), 0)

    def test_unsupported_relocation(self):
        result = self.compare('e8fb0f0000 c3', 'e800000000 c3', [(1, 4, 'callee', 7)])
        self.assertEqual(result['counts']['relocation'], 1)

    def test_extent_ranking(self):
        base = dict(diagnostic=self.compare('c3', 'c3'), comparison=dict(extent_compatible=True, mapped_bytes=10))
        bad = dict(base, comparison=dict(extent_compatible=False, mapped_bytes=1000))
        self.assertLess(rank_key(base), rank_key(bad))

    def test_unknown_relocation(self):
        result = self.compare('e8fb0f0000 c3', 'e800000000 c3', [(1, 4, 'callee', 20)])
        self.assertEqual(len(result['unresolved_relocations']), 1)
        self.assertEqual(result['counts']['relocation'], 0)

    def test_conflicting_slots(self):
        result = self.compare('8b45fc 8b45fc c3', '8b45f8 8b45f4 c3')
        self.assertFalse(result['stack_correspondence']['consistent'])

    def test_identity_slot_collision(self):
        result = self.compare('8b45fc 8b45f8 c3', '8b45f8 8b45f8 c3')
        self.assertFalse(result['stack_correspondence']['consistent'])

    def test_nonstack_displacement(self):
        result = self.compare('8b4104 c3', '8b4108 c3')
        self.assertEqual(result['counts']['structural_instruction'], 1)
        self.assertEqual(result['counts']['stack_local'], 0)

    def test_incomplete_decode(self):
        with self.assertRaises(ValueError):
            self.compare('0f', 'c3')

    def test_dependency_ranking(self):
        base = dict(diagnostic=self.compare('c3', 'c3'), comparison=dict(extent_compatible=True,
                                                                        mapped_bytes=10))
        useful = dict(base, unmatched_caller_bytes=900, unmatched_callers=2)
        self.assertLess(rank_key(useful), rank_key(base))


if __name__ == '__main__':
    unittest.main()
