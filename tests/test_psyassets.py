import struct
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from psyassets import Reader, normalize, collision
from psyexport import normals, triangles


class AssetDecoderTests(unittest.TestCase):
    def test_bounds_fail_closed(self):
        r=Reader(b'\x01\x00')
        with self.assertRaises(ValueError):r.u32()
        with self.assertRaises(ValueError):r.take(-1)

    def test_strings_and_texture_identity(self):
        raw=b'Abc\0';r=Reader(struct.pack('<I',len(raw))+raw)
        self.assertEqual(r.string(),'Abc')
        self.assertEqual(normalize('C:\\Psychonauts\\Resource\\Textures\\Test.DDS'),'textures/test')

    def test_triangle_strip_parity_and_degenerates(self):
        f={'flags':0x1000000,'indices':struct.pack('<6H',0,1,2,2,3,4)}
        self.assertEqual(triangles(f).tolist(),[[0,1,2],[3,2,4]])

    def test_triangle_list_keeps_orientation(self):
        f={'flags':0,'indices':struct.pack('<6H',2,1,0,1,1,2)}
        self.assertEqual(triangles(f).tolist(),[[2,1,0]])

    def test_packed_normal_axis_signs(self):
        packed=[1023,1023<<11,511<<22,1025,1025<<11,513<<22]
        raw=b''.join(struct.pack('<3fI',0,0,0,p) for p in packed)
        result,zeros=normals(raw)
        np.testing.assert_array_equal(result,[[1,0,0],[0,1,0],[0,0,1],[-1,0,0],[0,-1,0],[0,0,-1]])
        self.assertEqual(zeros,0)

    def test_empty_collision_has_no_octree(self):
        bounds=[-1.,-2.,-3.,1.,2.,3.]
        r=Reader(struct.pack('<II6f',0,0,*bounds))
        c=collision(r)
        self.assertEqual(c['record_words'],[])
        self.assertEqual(c['bounds'],bounds)
        self.assertEqual(r.pos,len(r.data))


if __name__=='__main__':unittest.main()
