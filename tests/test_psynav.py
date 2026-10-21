import struct
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from psynav import tail,export_navigation


class NavigationTests(unittest.TestCase):
    def test_empty_tail_and_unknown_remainder(self):
        raw=b'CYSP'+struct.pack('<II',317,0)+struct.pack('<I',0)
        self.assertEqual(tail(raw,12)['unparsed_bytes'],0)
        self.assertEqual(tail(raw+b'unknown',12)['unparsed_bytes'],7)

    def test_direction_reference_sentinel_and_invalid_neighbor(self):
        # A navigation polygon's vector fields may be -1; not vertex XYZ indices.
        poly=struct.pack('<II6i',1,0,*([-1]*6))
        body=struct.pack('<II',1,1)+poly+struct.pack('<4I',0,0,0,0)
        raw=b'CYSP'+struct.pack('<II',317,0)+body
        result=tail(raw,12)
        self.assertEqual(result['navigation'][0]['polygons'][0]['vertices'],[-1]*3)
        broken=bytearray(raw);struct.pack_into('<i',broken,28,3)
        with self.assertRaises(ValueError):tail(broken,12)

    def test_nav_requires_reciprocal_collision(self):
        data={'navigation':[{'id':0,'offset':0,'polygons':[{'collision_triangle':0}]}]}
        with self.assertRaises(ValueError):export_navigation(data,{'domain':{'meshes':[],'children':[]}},Path('/tmp/not-written.glb'))


if __name__=='__main__':unittest.main()
