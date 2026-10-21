import struct
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from psyassets import Reader,skeleton
from psyanim import compressed_quaternion,jan
from psyrig import vertex_skin,bind_globals,matrix
from glb_skin import interpolate


class RigTests(unittest.TestCase):
    def test_palette_bytes_and_zero_influences(self):
        sk={'weights':struct.pack('<I2f',0x010200, .25,.75),'bones':3,'influences':2,'joint_ids':[8,19,3]}
        joints,weights=vertex_skin(sk,[3,8,19])
        self.assertEqual(joints.tolist(),[[2,0,0,0]])
        self.assertEqual(weights.tolist(),[[.25,.75,0,0]])
        sk['weights']=struct.pack('<I2f',0x010200,1,0)
        self.assertEqual(vertex_skin(sk,[3,8,19])[0].tolist(),[[2,0,0,0]])

    def test_invalid_weights_and_palette_rejected(self):
        sk={'weights':struct.pack('<I2f',0x030000,1,0),'bones':1,'influences':1,'joint_ids':[0]}
        with self.assertRaises(ValueError):vertex_skin(sk,[0])
        sk['weights']=struct.pack('<I2f',0,.7,.1)
        with self.assertRaises(ValueError):vertex_skin(sk,[0])
        sk['weights']=struct.pack('<I2f',0,1,0);sk['joint_ids']=[99]
        with self.assertRaises(ValueError):vertex_skin(sk,[0])

    def test_smallest_three_axis_selectors_and_signs(self):
        for axis in range(4):
            q=compressed_quaternion(struct.pack('<IH',axis<<29,0))
            expected=[0,0,0,0];expected[axis]=1
            self.assertEqual(q,expected)
            q=compressed_quaternion(struct.pack('<IH',axis<<29,1));expected[axis]=-1
            self.assertEqual(q,expected)
        with self.assertRaises(ValueError):compressed_quaternion(struct.pack('<IH',7<<29,0))

    def test_bind_hierarchy_and_inverse(self):
        joints=[{'id':0,'parent':None,'position':[2,0,0],'rotation':[0,0,90]},
                {'id':1,'parent':0,'position':[3,0,0],'rotation':[0,0,0]}]
        g=bind_globals(joints)
        np.testing.assert_allclose(g[1][:3,3],[2,3,0],atol=1e-12)
        np.testing.assert_allclose(g[1]@np.linalg.inv(g[1]),np.eye(4),atol=1e-12)

    def test_slerp_shortest_arc_and_clamping(self):
        values=np.array([[0,0,0,1],[0,0,1,0.]])
        q=interpolate([0,2],values,1,True)
        np.testing.assert_allclose(q,[0,0,2**-.5,2**-.5])
        np.testing.assert_allclose(interpolate([0,2],values,-1,True),values[0])
        np.testing.assert_allclose(interpolate([0,2],-values,1,True),-q)

    def test_skeleton_count_mismatch_rejected(self):
        def string(s):return struct.pack('<I',len(s))+s
        raw=string(b'skel')+struct.pack('<I',2)+struct.pack('<H',0)+string(b'root')+struct.pack('<6fHI',*([0]*6),0,0)
        with self.assertRaises(ValueError):skeleton(Reader(raw),319)

    def test_jan_truncated_and_tail_rejected(self):
        head=b'XAJP'+struct.pack('<IHH6B',201,0,0,0,1,0,0,0,0)
        root=struct.pack('<I',4)+b'root'+struct.pack('<HH',0,0)
        self.assertEqual(jan(head+root)['root']['name'],'root')
        with self.assertRaises(ValueError):jan(head+root[:-1])
        with self.assertRaises(ValueError):jan(head+root+b'!')


if __name__=='__main__':unittest.main()
