"""Synthetic ledger/validation tests; no copyrighted inputs or Blender required."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import export_coverage as c


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.raw=b'synthetic original';self.sha=c.digest(self.raw)
        self.target=dict(label='Test',archive='A.ppf',model='model.plb')
        self.asset=dict(id='static_models:'+self.sha,sha256=self.sha,category='static_models',occurrences=[dict(archive='A.ppf',name='model.plb')])
        self.args=SimpleNamespace(game=self.root/'game',plan=self.root/'plan.json',manifest=self.root/'manifest.json',known=self.root/'known.json',out=self.root/'out',limit=1,resume=False,retry_failed=False,validator=Path('fake-validator'),blender=Path('fake-blender'))
        self.args.plan.write_text(json.dumps(dict(targets=[self.target])))
        self.args.manifest.write_text(json.dumps(dict(assets=[self.asset])))
        self.args.known.write_text('[]');self.legacy_calls=0;self.invalid=False

    def legacy(self,game,manifest,plan,out,validator):
        self.legacy_calls+=1;target=plan['targets'][0];folder=out/'static';folder.mkdir();glb=folder/(target['label']+'.glb');glb.write_bytes(b'synthetic output')
        glb.with_suffix('.glb.report.json').write_text(json.dumps(dict(issues=dict(numErrors=int(self.invalid),numWarnings=0))))
        return [dict(exported=True,source_validated=True,gltf_validated=not self.invalid,glb=str(glb),animation=None,stage='complete')]

    def process(self,command,**kwargs):
        if str(command[0])=='fake-validator' and self.invalid:raise subprocess.CalledProcessError(1,command)
        if str(command[0])=='fake-blender':
            directory=Path(command[command.index('--')+1]);name=next((directory/'static').glob('*.glb')).name
            (directory/'validation').mkdir();(directory/'validation/blender-static.json').write_text(json.dumps(dict(models=[dict(file=name,status='passed')])))
        return SimpleNamespace(returncode=0)

    def run_fixture(self):
        archive=dict(scene_data=self.raw,models=[dict(name='model.plb',data=self.raw)],textures=[])
        with patch.object(c,'read_archive',return_value=archive),patch.object(c,'scene',return_value=dict(version=319,trailing_bytes=4)),patch.object(c,'survey',side_effect=self.legacy),patch.object(c,'check_images',return_value=2),patch.object(c.subprocess,'run',side_effect=self.process),contextlib.redirect_stdout(io.StringIO()):
            return c.run(self.args)

    def test_generation_is_not_validation(self):
        self.invalid=True;j=self.run_fixture();a=j['entries'][self.asset['id']]['attempts'][0]
        self.assertEqual(a['stages']['export']['status'],'passed');self.assertEqual(a['stages']['gltf']['status'],'failed')
        self.assertEqual(a['stages']['blender']['status'],'not_attempted');self.assertFalse(a['successful'])

    def test_requested_animation_must_be_verified(self):
        self.target['animation']=True;self.args.plan.write_text(json.dumps(dict(targets=[self.target])))
        a=self.run_fixture()['entries'][self.asset['id']]['attempts'][0]
        self.assertEqual(a['stages']['blender']['status'],'passed');self.assertEqual(a['stages']['animation']['status'],'failed');self.assertFalse(a['successful'])

    def test_resume_skips_verified_complete_asset(self):
        j=self.run_fixture();self.assertTrue(j['entries'][self.asset['id']]['attempts'][0]['successful'])
        self.args.resume=True;j=self.run_fixture();self.assertEqual(self.legacy_calls,1);self.assertEqual(j['invocations'][-1]['processed'],0)

    def test_retry_preserves_failed_attempt(self):
        self.invalid=True;j=self.run_fixture();first=j['entries'][self.asset['id']]['attempts'][0];old=Path(first['glb']);sha=c.digest(old.read_bytes())
        self.invalid=False;self.args.resume=True;self.args.retry_failed=True;j=self.run_fixture();attempts=j['entries'][self.asset['id']]['attempts']
        self.assertEqual(len(attempts),2);self.assertFalse(attempts[0]['successful']);self.assertTrue(attempts[1]['successful']);self.assertNotEqual(attempts[0]['glb'],attempts[1]['glb']);self.assertEqual(c.digest(old.read_bytes()),sha)

    def test_corrupt_report_blocks_resume(self):
        j=self.run_fixture();a=j['entries'][self.asset['id']]['attempts'][0];Path(a['stages']['blender']['reports'][0]['path']).write_text('{}');self.args.resume=True
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.run_fixture()

    def test_changed_plan_blocks_resume(self):
        self.run_fixture();self.args.resume=True;self.args.plan.write_text(json.dumps(dict(targets=[dict(self.target,label='Changed')])))
        with self.assertRaisesRegex(ValueError,'inputs changed'):self.run_fixture()

    def test_duplicate_source_not_counted_twice(self):
        self.args.limit=2;self.args.plan.write_text(json.dumps(dict(targets=[self.target,dict(self.target,label='Alias')])))
        j=self.run_fixture();self.assertEqual(len(j['entries']),1);self.assertEqual(self.legacy_calls,1)

    def test_changed_original_does_not_export(self):
        self.raw=b'changed original';j=self.run_fixture()
        a=j['entries'][self.asset['id']]['attempts'][0];self.assertEqual(a['stages']['parsing']['status'],'failed');self.assertEqual(self.legacy_calls,0)

    def proof_record(self):
        path=self.root/'known.glb';path.write_bytes(b'known output');h=c.digest(path.read_bytes());proofs={}
        for name,value in [('source',dict(status='passed',record_sha256=self.sha,glb_sha256=h)),('gltf',dict(issues=dict(numErrors=0,numWarnings=0))),('blender',dict(models=[dict(file=path.name,status='passed')]))]:
            p=self.root/(name+'.json');p.write_text(json.dumps(value));proofs[name]=dict(path=str(p),sha256=c.digest(p.read_bytes()))
        return dict(asset_id=self.asset['id'],path=str(path),sha256=h,profile={},proofs=proofs)

    def test_known_requires_bound_validation_evidence(self):
        r=self.proof_record();self.assertIn((self.asset['id'],c.profile({})),c.verified_known([r]))
        r.pop('proofs')
        with self.assertRaises(KeyError):c.verified_known([r])

    def test_known_report_must_bind_asset(self):
        r=self.proof_record();p=Path(r['proofs']['source']['path']);j=json.loads(p.read_text());j['record_sha256']='wrong';p.write_text(json.dumps(j));r['proofs']['source']['sha256']=c.digest(p.read_bytes())
        with self.assertRaisesRegex(ValueError,'does not bind'):c.verified_known([r])

    def test_validated_known_is_not_reexported(self):
        r=self.proof_record();self.args.known.write_text(json.dumps([r]));j=self.run_fixture();self.assertEqual(j['entries'],{});self.assertEqual(len(j['skipped']),1);self.assertEqual(self.legacy_calls,0)

    def test_nonempty_orphan_output_preserved(self):
        self.args.out.mkdir();p=self.args.out/'orphan';p.write_text('retain')
        with self.assertRaisesRegex(ValueError,'nonempty output'):self.run_fixture()
        self.assertEqual(p.read_text(),'retain')


if __name__=='__main__':unittest.main()
