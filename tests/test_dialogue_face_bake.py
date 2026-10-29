"""Synthetic GLB probe integrity; no production animation decoder promotion."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_dialogue_face import bake
from glb_skin import read,interpolate


class DialogueBakeTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        g=dict(asset=dict(version='2.0'),buffers=[dict(byteLength=4)],bufferViews=[],accessors=[],nodes=[dict(mesh=0)],meshes=[dict(weights=[0,0])],animations=[dict(name='old')])
        js=json.dumps(g).encode();js+=b' '*(-len(js)%4);source=root/'source.glb';source.write_bytes(struct.pack('<III',0x46546c67,2,28+len(js)+4)+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',4,0x004e4942)+b'KEEP')
        return source,g,root/'new/output.glb'

    def test_new_probe_preserves_source_file_and_input_metadata(self):
        src,g,out=self.fixture();before=src.read_bytes();metadata=copy.deepcopy(g)
        bake(src,out,g,np.array([0,.5,1]),np.array([[0,0],[1,.5],[0,0]]),dict(resource=dict(path='synthetic.pba')))
        self.assertEqual(src.read_bytes(),before);self.assertEqual(g,metadata);self.assertIn(b'KEEP',out.read_bytes())

    def test_weight_shape_times_and_endpoint_are_preserved(self):
        src,g,out=self.fixture();times=np.array([0,.5,1],dtype='<f4');values=np.array([[0,0],[1,.5],[0,0]],dtype='<f4')
        bake(src,out,g,times,values,dict(resource=dict(path='synthetic.pba')));result,access=read(out);a=result['animations'][0];s=a['samplers'][0]
        self.assertEqual(a['channels'][0]['target']['path'],'weights');self.assertEqual(s['interpolation'],'LINEAR')
        np.testing.assert_array_equal(access(s['output']).reshape(3,2),values)
        np.testing.assert_allclose(interpolate(access(s['input']).ravel(),values,.25),[.5,.25])
        np.testing.assert_array_equal(interpolate(times,values,2),[0,0])

    def test_old_animation_is_separate_from_new_facial_only_clip(self):
        src,g,out=self.fixture();bake(src,out,g,np.array([0,1]),np.zeros((2,2)),dict(resource=dict(path='synthetic.pba')))
        result,_=read(out);self.assertEqual(len(result['animations']),1)
        self.assertTrue(all(c['target']['path']=='weights' for c in result['animations'][0]['channels']))
        self.assertEqual(g['animations'],[dict(name='old')])


if __name__=='__main__':unittest.main()
