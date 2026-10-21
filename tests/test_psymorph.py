import struct
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from psymorph import morph_delta,pba,packed_vectors,texture_surfaces,events
from psyrig import compatible_hierarchy


class MorphTests(unittest.TestCase):
    def test_signed_delta_and_scale(self):
        b={'sparse':False,'count':2,'scale':4.,'data':struct.pack('<4I',1023,0,1025,0)}
        pos,n=morph_delta(b,2)
        np.testing.assert_array_equal(pos,[[4,0,0],[-4,0,0]])
        np.testing.assert_array_equal(n,np.zeros((2,3)))

    def test_sparse_expansion_and_invalid_index(self):
        b={'sparse':True,'count':1,'scale':2.,'data':struct.pack('<HII',1,511<<22,0)}
        np.testing.assert_array_equal(morph_delta(b,3)[0],[[0,0,0],[0,0,2],[0,0,0]])
        with self.assertRaises(ValueError):morph_delta(b,1)

    def test_pba_preserves_missing_declarations(self):
        raw=b'ABPE'+struct.pack('<II',100,2)+b'\x05Smile'+struct.pack('<I',3)+bytes([0,127,255])
        result=pba(raw)
        self.assertEqual(result['missing_declared_channels'],1)
        self.assertEqual(result['channels'][0]['weights'],[0,127,255])
        with self.assertRaises(ValueError):pba(raw[:-1])

    def test_cube_faces_cover_record_exactly(self):
        t={'frames':1,'type':1,'format':9,'mips':1,'width':4,'height':4,'data_offset':3,'record_data':b'hdr'+b'12345678'*6}
        self.assertEqual(len(texture_surfaces(t)),6)
        t['record_data']+=b'!'
        with self.assertRaises(ValueError):texture_surfaces(t)

    def test_event_terminal_separator(self):
        text=b'ChalkWrite\t'
        raw=b'EVEP'+struct.pack('<3I',101,1,1)+struct.pack('<H',len(text))+text+struct.pack('<2IIf',1,1,33,0.)
        e=events(raw)
        self.assertEqual(e['channels'][0]['keys'][0]['name'],'ChalkWrite')
        self.assertEqual(e['channels'][0]['keys'][0]['frame'],33)

    def test_joint_alias_requires_entire_hierarchy(self):
        a={'name':'parent|eye','children':[{'name':'tip','children':[]}]}
        b={'name':'eye','children':[{'name':'tip','children':[]}]}
        self.assertTrue(compatible_hierarchy(a,b))
        b['children'][0]['name']='different'
        self.assertFalse(compatible_hierarchy(a,b))


if __name__=='__main__':unittest.main()
