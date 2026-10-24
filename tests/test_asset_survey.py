"""Synthetic portability regression for a legitimate textureless source prop."""
import contextlib
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from psyexport import Exporter
from glb_skin import read


class TexturelessPropTests(unittest.TestCase):
    def test_valid_geometry_without_texture_collections(self):
        fragment=dict(flags=0,lod=0,blend=0,color=[1,1,1,1],textures=[],lightmap=None,
            detail=None,gloss=None,reflection=None,velocity=None,vertices=3,
            bounds=[0,0,0,1,1,0],indices=struct.pack('<3H',0,1,2),
            posnrm=b''.join(struct.pack('<3fI',*v,511<<22) for v in [(0,0,0),(0,1,0),(1,0,0)]),
            uv_count=0,colors=b'')
        mesh=dict(name='untextured',translation=[0,0,0],rotation=[0,0,0],scale=[1,1,1],
            bounds=fragment['bounds'],entity_flags=0,triggers=[],lights=[],collision=None,
            lod_thresholds=[],skeletons=[],fragments=[fragment],children=[])
        domain=dict(name='root',bounds=fragment['bounds'],scripts=[],entity_data=[],runtime_references=[],meshes=[mesh],children=[])
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            path=Path(directory)/'prop.glb'
            Exporter(dict(domain=domain,texture_references=[],trailing_bytes=0),{},path).write()
            g,access=read(path)
            self.assertNotIn('images',g);self.assertNotIn('textures',g)
            self.assertTrue(all(value for value in g.values() if isinstance(value,list)))
            self.assertEqual(access(g['meshes'][0]['primitives'][0]['indices']).ravel().tolist(),[0,2,1])
            self.assertEqual(len(g['materials']),1)


if __name__=='__main__':unittest.main()
