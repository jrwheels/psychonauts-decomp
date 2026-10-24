"""Synthetic format/geometry invariants independent of original game assets."""
import struct
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from psyassets import Reader,skeleton
from psyexport import triangles
from psyrig import bind_quaternion,vertex_skin


class ModelExportTests(unittest.TestCase):
    def test_clockwise_source_becomes_outward_ccw(self):
        positions=np.array([[0,0,0],[0,1,0],[1,0,0]])
        for flags in (0,0x1000000):
            original=struct.pack('<3H',0,1,2)
            tri=triangles(dict(flags=flags,indices=original))[0]
            a,b,c=positions[tri]
            self.assertGreater(np.dot(np.cross(b-a,c-a),[0,0,1]),0)
            self.assertEqual(original,struct.pack('<3H',0,1,2))

    def test_sentinel_is_exact_triplet(self):
        np.testing.assert_array_equal(bind_quaternion([-1,-1,-1]),[0,0,0,1])
        np.testing.assert_array_equal(bind_quaternion([0,0,0]),[0,0,0,1])
        for v in ([-1,-1,0],[-1,0,-1],[0,-1,-1],[-1,-1,-.999]):
            self.assertGreater(np.linalg.norm(bind_quaternion(v)[:3]),.001)

    def test_serialized_labels_do_not_define_runtime_tree(self):
        def string(s):return struct.pack('<I',len(s))+s
        def joint(label,name,children):
            return (struct.pack('<H',label)+string(name)+struct.pack('<6fHI',
                    0,0,0,-1,-1,-1,0,len(children))+b''.join(children))
        raw=string(b'skel')+struct.pack('<I',4)+joint(0xffff,b'root',[
            joint(77,b'a',[joint(77,b'grandchild',[])]),joint(1234,b'b',[])])
        sk=skeleton(Reader(raw),319);root=sk['root'];a,b=root['children'];g=a['children'][0]
        self.assertEqual([j['id'] for j in (root,a,g,b)],[65535,77,77,1234])
        self.assertEqual([j['runtime_index'] for j in (root,a,g,b)],[0,1,2,3])
        self.assertEqual([j['runtime_parent_index'] for j in (root,a,g,b)],[None,0,1,0])
        self.assertEqual(a['runtime_next_sibling_index'],3)
        self.assertIsNone(g['runtime_next_sibling_index'])
        self.assertEqual(sk['root']['serialized_id'],65535)

    def test_duplicate_palette_labels_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            vertex_skin({},[7,7])


if __name__=='__main__':unittest.main()
