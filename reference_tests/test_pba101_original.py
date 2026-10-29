"""Optional original-only x86 semantic controls; no redistributed executable."""
import os
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from original_reader_pba import OriginalPba
from pba101_research import decode,local_weights
from test_pba101_research import payload


@unittest.skipUnless(os.environ.get('PSYCHONAUTS_REFERENCE'),'set owned original reference for original-only tests')
class OriginalPbaTests(unittest.TestCase):
    def setUp(self):self.h=OriginalPba(os.environ['PSYCHONAUTS_REFERENCE'])

    def test_versions_share_original_channel_reader(self):
        for v in (100,101):
            r=self.h.load(payload([('AHH',[0,127,255])],v));self.assertTrue(r['returned_success']);self.assertEqual(r['channels'],[dict(name='AHH',weights=[0,127,255])])

    def test_partial_declaration_is_not_success(self):
        r=self.h.load(payload([('A',[0,1])],declared=3));self.assertFalse(r['returned_success']);self.assertEqual(len(r['channels']),1)

    def test_original_mapping_is_case_sensitive_and_first_target_wins(self):
        self.h.load(payload([('A',[0,255]),('a',[127,255]),('missing',[0,1])]))
        self.assertEqual(self.h.bind(['A','A','a']),[0,2,-1])

    def test_variable_lengths_loop_end_and_singleton(self):
        raw=payload([('A',[0,127,255]),('B',[255]),('C',[255,0,127,255])]);d=decode(raw);self.h.load(raw);self.h.bind(['A','B','C'])
        for loop in (False,True):
            for t in (0,.25/30,.5/30,1/30,1.5/30,3/30,4/30,4.5/30,8/30):
                np.testing.assert_allclose(self.h.evaluate(t,loop),local_weights(d,t,['A','B','C'],loop),rtol=0,atol=1e-5)
        self.assertEqual(self.h.evaluate(0)[1],255)

    def test_duplicate_channel_assignment_overwrites(self):
        raw=payload([('A',[0,127]),('A',[255,255])]);self.h.load(raw);self.h.bind(['A'])
        self.assertEqual(self.h.evaluate(0),[1])


if __name__=='__main__':unittest.main()
