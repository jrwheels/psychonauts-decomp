import json
import struct
import sys
import tempfile
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from scale_character_glb import convert
from glb_skin import read


class CharacterScaleTests(unittest.TestCase):
    def test_float_bounds_inverse_bind_and_shared_position(self):
        pos=np.array([[1.234567,2.345678,3.456789]],dtype='<f4');ib=np.eye(4,dtype='<f4');ib[3,:3]=[-5,-6,-7]
        blob=pos.tobytes()+ib.tobytes()
        g={'asset':{'version':'2.0'},'nodes':[{'translation':[1,2,3]}],
           'meshes':[{'primitives':[{'attributes':{'POSITION':0},'targets':[{'POSITION':0}]}]}],
           'skins':[{'inverseBindMatrices':1}],
           'accessors':[{'bufferView':0,'componentType':5126,'count':1,'type':'VEC3','min':pos[0].tolist(),'max':pos[0].tolist()},
                        {'bufferView':1,'componentType':5126,'count':1,'type':'MAT4'}],
           'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':12},{'buffer':0,'byteOffset':12,'byteLength':64}],
           'buffers':[{'byteLength':76}]}
        js=json.dumps(g).encode();js+=b' '*((-len(js))%4)
        raw=struct.pack('<III',0x46546c67,2,28+len(js)+len(blob))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(blob),0x004e4942)+blob
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'input.glb',Path(d)/'output.glb';a.write_bytes(raw);convert(a,b,.01);out,access=read(b)
            np.testing.assert_array_equal(access(0),pos*np.float32(.01))
            self.assertEqual(out['accessors'][0]['min'],access(0)[0].tolist())
            np.testing.assert_allclose(access(1)[0,12:15],[-.05,-.06,-.07])
            np.testing.assert_allclose(out['nodes'][0]['translation'],[.01,.02,.03])
            with self.assertRaises(ValueError):convert(a,b,0)


if __name__=='__main__':unittest.main()
