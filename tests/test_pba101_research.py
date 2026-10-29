"""Synthetic PBA research guards; no original data or proposed playback exports."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from pba101_research import decode,local_weights
from psymorph import pba
from check_pba_deformation import delta
from original_reader_pba import OriginalPba


def payload(channels,version=101,declared=None):
    raw=b'ABPE'+struct.pack('<II',version,len(channels) if declared is None else declared)
    for name,weights in channels:
        encoded=name.encode('latin1')+b'\0';raw+=bytes([len(encoded)])+encoded+struct.pack('<I',len(weights))+bytes(weights)
    return raw


class PbaResearchTests(unittest.TestCase):
    def test_100_and_101_layouts_have_equal_channel_content(self):
        for v in (100,101):
            c=decode(payload([('AHH',[0,127,255])],v));self.assertEqual(c['channels'][0]['weights'],[0,127,255]);self.assertEqual(c['version'],v)

    def test_header_and_incomplete_declarations_remain_explicit(self):
        self.assertTrue(decode(b'ABPE'+struct.pack('<I',101))['header_only'])
        self.assertEqual(decode(payload([('A',[0,1])],declared=3))['missing_declared_channels'],2)

    def test_truncation_and_tail_rejected(self):
        raw=payload([('A',[0,1,2])])
        for value in (raw[:-1],raw+b'junk',raw[:13]):
            with self.assertRaises(ValueError):decode(value)

    def test_unknown_versions_and_absurd_counts_rejected(self):
        for raw in (payload([],102),b'ABPE'+struct.pack('<II',101,1000000)):
            with self.assertRaises(ValueError):decode(raw)

    def test_production_decoder_still_rejects_101(self):
        with self.assertRaisesRegex(ValueError,'PBA version'):pba(payload([('A',[0,255])]))

    def test_exact_name_mapping_and_duplicate_channel_overwrite(self):
        d=decode(payload([('A',[255,255]),('A',[0,0]),('a',[127,127])]))
        np.testing.assert_allclose(local_weights(d,0,['A','a']),[0,127/255],atol=3e-8)
        self.assertEqual(local_weights(d,0,['UNKNOWN']),[0])

    def test_fractional_linear_interpolation_and_terminal_clear(self):
        d=decode(payload([('A',[0,255,255])]))
        self.assertAlmostEqual(local_weights(d,.5/30,['A'])[0],.5)
        self.assertEqual(local_weights(d,3/30,['A']),[0])
        self.assertAlmostEqual(local_weights(d,2.5/30,['A'],True)[0],.5,places=5)

    def test_singleton_keeps_observed_native_raw_byte(self):
        d=decode(payload([('A',[255])]))
        self.assertEqual(local_weights(d,0,['A']),[255])

    def test_invalid_time_and_target_aliases_fail_closed(self):
        d=decode(payload([('A',[0,255])]))
        for t in (-1,float('nan')):
            with self.assertRaises(ValueError):local_weights(d,t,['A'])
        with self.assertRaises(ValueError):local_weights(d,0,['A','A'])

    def test_independent_raw_delta_sign_and_sparse_index(self):
        dense=dict(sparse=False,count=1,scale=2,data=struct.pack('<II',1023,0))
        np.testing.assert_array_equal(delta(dense,1),[[2,0,0]])
        sparse=dict(sparse=True,count=1,scale=1,data=struct.pack('<HII',1,1024,0))
        np.testing.assert_allclose(delta(sparse,2),[[0,0,0],[-1024/1023,0,0]])

    def test_wrong_executable_rejected_before_pe_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'wrong.exe';p.write_bytes(b'synthetic invalid reference')
            with self.assertRaisesRegex(ValueError,'wrong original'):OriginalPba(p)


if __name__=='__main__':unittest.main()
