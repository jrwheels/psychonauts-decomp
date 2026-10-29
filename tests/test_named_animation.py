"""Exact APF selection guards; synthetic inputs, no original assets."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from asset_survey import referenced_clip,digest
from export_coverage import profile,validate_plan


class NamedAnimationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.game=Path(self.temp.name)
        packs=self.game/'WorkResource/PCLevelPackFiles';packs.mkdir(parents=True);(packs/'A.apf').write_bytes(b'synthetic APF')
        self.raw=b'synthetic JAN';(self.game/'data.pkg').write_bytes(b'pad'+self.raw)
        self.name='anims/campkids/crying_crystal.jan';self.tree=dict(name='root',children=[])
        self.stub=dict(name=self.name,pkg_offset=3,pkg_size=len(self.raw),position_channel=None,header=dict(joints=1))
        self.ref=dict(category='animation_references',details=dict(pkg_offset=3,pkg_size=len(self.raw)),occurrences=[dict(name=self.name,archive='A.apf',record=0)])
        self.asset=dict(id='clip',category='skeletal_animations',parse_status='parsed',sha256=digest(self.raw),occurrences=[dict(archive='data.pkg',offset=3,size=len(self.raw))])
        self.manifest=dict(assets=[self.ref,self.asset]);self.animation=dict(root=self.tree,header=dict(joints=1))

    def resolve(self,name=None):
        with patch('asset_survey.apf',return_value=[self.stub]),patch('asset_survey.jan',return_value=self.animation):
            return referenced_clip(self.manifest,self.game,[self.tree],name or self.name,'A.apf')

    def test_exact_reference_preserves_original_path_and_hashes(self):
        asset,clip=self.resolve();self.assertIs(asset,self.asset)
        self.assertEqual(clip['name'],self.name);self.assertEqual(clip['source']['sha256'],digest(self.raw))
        self.assertEqual(clip['source']['apf_sha256'],digest(b'synthetic APF'))

    def test_missing_name_does_not_fall_back_to_compatible_clip(self):
        with self.assertRaisesRegex(ValueError,'one original payload'):self.resolve('anims/campkids/wrong.jan')

    def test_changed_original_reference_is_rejected(self):
        self.stub['pkg_offset']=4
        with self.assertRaisesRegex(ValueError,'APF record differs'):self.resolve()

    def test_root_motion_cannot_be_silently_dropped(self):
        self.stub['position_channel']={}
        with self.assertRaisesRegex(ValueError,'root motion'):self.resolve()

    def test_changed_original_payload_is_rejected(self):
        (self.game/'data.pkg').write_bytes(b'padWRONG')
        with self.assertRaisesRegex(ValueError,'JAN payload differs'):self.resolve()

    def test_wrong_tree_is_rejected(self):
        self.animation=dict(root=dict(name='wrong',children=[]),header=dict(joints=1))
        with self.assertRaisesRegex(ValueError,'hierarchy'):self.resolve()

    def test_conflicting_references_are_ambiguous(self):
        other=copy.deepcopy(self.ref);other['details']['pkg_offset']=7;self.manifest['assets'].append(other)
        with self.assertRaisesRegex(ValueError,'one original payload'):self.resolve()

    def test_named_and_generic_profiles_do_not_collide(self):
        target=dict(label='Crystal',animation=True,animation_path=self.name)
        self.assertNotEqual(profile(target),profile(dict(label='Crystal',animation=True)))
        self.assertEqual(profile(target),profile(dict(target,animation_path=self.name.replace('/','\\'))))
        with self.assertRaisesRegex(ValueError,'requires animation'):validate_plan(dict(targets=[dict(target,animation=False)]))


if __name__=='__main__':unittest.main()
