"""Independent bind checks reject wrong local rotations and inverse matrices."""
from pathlib import Path
import struct
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from check_bind_pose import compare,source_matrix


class BindPoseCheckTests(unittest.TestCase):
    def fixture(self):
        def record(label,name,values):return struct.pack('<HI',label,len(name))+name+struct.pack('<6f',*values)
        root=record(7,b'root',[2,0,0,0,0,90]);child=record(19,b'child',[3,0,0,-1,-1,-1])
        js=[dict(id=7,parent=None,offset=0),dict(id=19,parent=7,offset=len(root))]
        g=dict(nodes=[dict(translation=[2,0,0],rotation=[0,0,2**-.5,2**-.5],extras=dict(original_joint_id=7)),dict(translation=[3,0,0],rotation=[0,0,0,1],extras=dict(original_joint_id=19))])
        world0=np.array([[0,-1,0,2],[1,0,0,0],[0,0,1,0],[0,0,0,1.]])
        world1=world0.copy();world1[:3,3]=[2,3,0]
        inverses=np.array([np.linalg.inv(m).T.reshape(16) for m in (world0,world1)],dtype='<f4')
        return root+child,js,dict(joints=[0,1],inverseBindMatrices=0),g,inverses

    def test_hierarchical_bind_and_sentinel_match_known_world_matrices(self):
        raw,js,skin,g,ibm=self.fixture();r=compare(raw,js,skin,g,lambda i:ibm)
        self.assertEqual(r['joints'],2);self.assertEqual(r['identity_rotation_sentinels'],1)

    def test_wrong_local_rotation_rejected_even_if_translation_matches(self):
        raw,js,skin,g,ibm=self.fixture();g['nodes'][0]['rotation']=[0,0,0,1]
        with self.assertRaises(AssertionError):compare(raw,js,skin,g,lambda i:ibm)

    def test_wrong_inverse_bind_rejected(self):
        raw,js,skin,g,ibm=self.fixture();ibm[1,12]+=1
        with self.assertRaises(AssertionError):compare(raw,js,skin,g,lambda i:ibm)

    def test_partial_sentinel_remains_euler(self):
        np.testing.assert_array_equal(source_matrix([0,0,0],[-1,-1,-1]),np.eye(4))
        self.assertGreater(np.max(abs(source_matrix([0,0,0],[-1,-1,0])-np.eye(4))),.01)

    def test_noncommuting_euler_axes_follow_documented_order(self):
        expected=np.array([[0,1,0],[0,0,-1],[-1,0,0]])
        np.testing.assert_allclose(source_matrix([0,0,0],[90,90,0])[:3,:3],expected,atol=1e-15)


if __name__=='__main__':unittest.main()
