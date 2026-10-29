"""Collision checks against independently packed original-record fixtures."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from check_model_export import check_collision


class CollisionExportTests(unittest.TestCase):
    def fixture(self,bad=False):
        raw=struct.pack('<I',1)+struct.pack('<I3HHfI',7,0,1,2,0,.5,0)+struct.pack('<I9f',3,0,0,0,1,0,0,0,1,0)
        source=dict(version=319,domain=dict(meshes=[dict(children=[],collision=dict(offset=0,record_words=[[7,65536,2,0,0]]))],children=[]))
        arrays=[np.array([[0,1,1 if bad else 2]],dtype='u4'),np.array([[0,0,0],[1,0,0],[0,1,0]],dtype='f4')]
        g=dict(meshes=[dict(primitives=[dict(indices=0,attributes=dict(POSITION=1))])])
        return raw,source,g,arrays
    def run_case(self,bad=False):
        raw,s,g,a=self.fixture(bad)
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'source';archive.write_bytes(raw);out=Path(temp)/'out.glb';out.write_bytes(b'synthetic')
            with patch('check_model_export.read_archive',return_value=dict(scene_data=raw)),patch('check_model_export.scene',return_value=s),patch('check_model_export.read',return_value=(g,lambda i:a[i])):
                return check_collision(archive,None,out)
    def test_original_record_positions_and_indices(self):self.assertEqual(self.run_case()['checks'][0]['triangles'],1)
    def test_changed_export_indices_rejected(self):
        with self.assertRaises(AssertionError):self.run_case(True)


if __name__=='__main__':unittest.main()
