"""Inventory accounting without copyrighted fixtures or game files."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import struct
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from asset_manifest import Manifest,add_scene,derived,encoded_texture,add_animation_chunk


class ManifestTests(unittest.TestCase):
    def test_apf_and_pkg_animation_payloads_deduplicate(self):
        m=Manifest();raw=b'ABPE'+struct.pack('<II',100,0)
        a=m.add('facial_animations',raw,dict(archive='owned.pkg'),'parsed')
        add_animation_chunk(m,raw,dict(archive='owned.apf'))
        self.assertEqual(len(m.assets),1);self.assertEqual(len(a['occurrences']),2)

    def test_unsupported_embedded_animation_remains_explicit(self):
        m=Manifest();add_animation_chunk(m,b'ABPE'+struct.pack('<II',101,0),{})
        a=next(iter(m.assets.values()))
        self.assertEqual(a['parse_status'],'unsupported');self.assertEqual(a['details']['format_version'],101)

    def test_records_payloads_and_families_are_distinct(self):
        m=Manifest()
        for raw,name in [(b'a','A\\Prop.PLB'),(b'a','a/prop.plb'),(b'b','a/prop.plb')]:
            m.add('static_models',raw,dict(name=name),'parsed')
        r=m.summary()['static_models']
        self.assertEqual((r['records'],r['unique_assets'],r['named_families'],r['parsed']),(3,2,1,2))

    def test_lod_exports_do_not_double_count_source_asset(self):
        m=Manifest();a=m.add('skeletal_models',b'fixture',{},'parsed')
        a['exports']=[dict(lod=1),dict(lod=2)];a['validations']=[dict(lod=1)]
        self.assertEqual(m.summary()['skeletal_models']['exported'],1)
        self.assertEqual(m.summary()['skeletal_models']['validated'],1)

    def test_unattempted_is_not_success_or_failure(self):
        m=Manifest();m.add('other_resources',b'1',{});m.add('other_resources',b'2',{},'unsupported',error='unknown kind')
        r=m.summary()['other_resources'];self.assertEqual((r['parsed'],r['parse_not_attempted'],r['parse_failed']),(0,1,1))

    def test_derived_identity_ignores_storage_offsets(self):
        self.assertEqual(derived(dict(offset=1,child=dict(offset=2,id=3))),derived(dict(offset=99,child=dict(offset=7,id=3))))
        self.assertNotEqual(derived(dict(id=3)),derived(dict(id=4)))

    def test_texture_headers_and_aliases_do_not_inflate_image_count(self):
        t=dict(format=9,type=0,frames=1,width=4,height=4,mips=1,
               record_data=b'headerA'+b'12345678',data_offset=7)
        other=dict(t,record_data=b'headerB'+b'12345678')
        self.assertEqual(encoded_texture(t),encoded_texture(other))
        self.assertNotEqual(encoded_texture(t),encoded_texture(dict(t,width=8)))
        self.assertNotEqual(encoded_texture(t),encoded_texture(dict(t,record_data=b'headerA87654321')))

    def test_duplicate_owners_retain_attachment_occurrences(self):
        sk=dict(name='skel',joint_count=1,root=dict(name='root',id=0,children=[]))
        mesh=dict(skeletons=[sk],fragments=[],collision=None,children=[])
        source=dict(version=319,domain=dict(meshes=[mesh],children=[]),trailing_bytes=4,texture_references=[])
        m=Manifest()
        with patch('asset_manifest.scene',return_value=source) as parser:
            add_scene(m,b'scene',dict(archive='A.ppf',name='model'))
            add_scene(m,b'scene',dict(archive='B.ppf',name='model'))
            self.assertEqual(parser.call_count,1)
        self.assertEqual(m.summary()['skeletons']['records'],2)
        self.assertEqual(m.summary()['skeletons']['unique_assets'],1)


if __name__=='__main__':unittest.main()
