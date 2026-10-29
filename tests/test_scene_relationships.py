import sys
from pathlib import Path
import struct
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from scene_relationships import geometry_view,analyze


class SceneRelationshipTests(unittest.TestCase):
    def mesh(self):
        return dict(name='static',translation=[100,0,0],rotation=[0,0,0],scale=[1,1,1],bounds=[99,-1,-1,102,2,2],collision=None,children=[],fragments=[dict(vertices=3,posnrm=b''.join(struct.pack('<4f',*v,0) for v in [(100,0,0),(101,0,0),(100,1,0)]),textures=[0],lightmap=1,detail=None,gloss=None,reflection=None)])
    def source(self):
        m=self.mesh();script=dict(name='static',position=[100,0,0],initial_mesh=0,initial_data=0)
        return dict(version=319,trailing_bytes=123,texture_references=[dict(name='base.tga'),dict(name='light.tga')],domain=dict(name='level',meshes=[m],children=[],entity_data=[dict(tag=0)],scripts=[script],runtime_references=['prop.plb']))
    def test_baked_translation_is_not_applied(self):
        m=self.mesh();r=geometry_view(m);self.assertTrue(r['raw_positions_fit_mesh_bounds']);self.assertFalse(r['translation_applied_positions_fit_mesh_bounds']);self.assertEqual(m['translation'],[100,0,0])
    def test_links_require_index_name_and_translation(self):
        d=self.source();r=analyze(d,{}, {'base','light'});self.assertEqual(r['summary']['verified_script_mesh_links'],1)
        d['domain']['scripts'][0]['name']='different';self.assertEqual(analyze(d,{},set())['summary']['verified_script_mesh_links'],0)
        d['domain']['scripts'][0]['initial_mesh']=0xffffffff;self.assertEqual(analyze(d,{},set())['summary']['verified_script_mesh_links'],0)
    def test_material_roles_and_opaque_tail_are_retained(self):
        r=analyze(self.source(),{'prop.plb':{'prop.plb'}},{'base'});self.assertEqual(r['opaque_tail_bytes'],123);self.assertEqual(r['summary']['unresolved_texture_roles'],1);self.assertEqual([x['role'] for x in r['texture_roles']],['base','lightmap']);self.assertEqual(r['domains'][0]['runtime_references'][0]['matched_model_names'],['prop.plb'])


if __name__=='__main__':unittest.main()
