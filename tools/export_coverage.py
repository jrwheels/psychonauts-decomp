#!/usr/bin/env python3
"""Bounded, resumable coverage ledger over the established asset survey.

Each attempt is immutable once finished. Incomplete/failed attempts are retained
when explicitly retried. Parsing, export, source checks, glTF and Blender have
separate results; parser counts never imply export coverage.
"""
import argparse
import json
from pathlib import Path
import subprocess
from asset_manifest import ROOT,digest
from asset_survey import survey
from glb_skin import read
from psyexport import pixels
from PIL import Image
import io
import numpy as np
from psyassets import read_archive,scene,normalize
from check_model_export import check

STAGES=('parsing','export','source','textures','animation','gltf','blender')


def save(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def profile(target):
    p=dict(lod_mask=target.get('lod_mask'),animation=bool(target.get('animation')))
    if target.get('animation_path'):
        p.update(animation_path=normalize(target['animation_path']),animation_archive=target.get('animation_archive'))
    return json.dumps(p,sort_keys=True)


def report_model_passed(report,name):
    rows=[m for m in report.get('models',[]) if m.get('file')==name]
    return bool(rows) and all(m.get('status')=='passed' or 'passed' in m.get('result','') for m in rows)


def verified_known(records):
    known=set()
    for record in records:
        p=Path(record['path'])
        if not p.is_file() or digest(p.read_bytes())!=record['sha256']:
            raise ValueError('known-success artifact missing or changed: '+str(p))
        proofs={}
        for stage in ['source','gltf','blender']:
            proof=record['proofs'][stage];path=Path(proof['path'])
            if not path.is_file() or digest(path.read_bytes())!=proof['sha256']:
                raise ValueError('known-success proof missing or changed: '+stage)
            proofs[stage]=json.loads(path.read_text())
        source=proofs['source'];issues=proofs['gltf']['issues']
        if source.get('status')!='passed' or source.get('record_sha256')!=record['asset_id'].split(':',1)[1] or source.get('glb_sha256')!=record['sha256']:
            raise ValueError('known source proof does not bind this asset/output')
        if issues['numErrors'] or issues['numWarnings'] or not report_model_passed(proofs['blender'],p.name):
            raise ValueError('known validation was not successful')
        known.add((record['asset_id'],profile(record['profile'])))
    return known


def preserve_attempt(attempt,directory):
    attempt['evidence_hashes']={str(p.resolve()):digest(p.read_bytes()) for p in directory.rglob('*') if p.is_file()}


def verify_attempt(attempt):
    for name,sha in attempt.get('evidence_hashes',{}).items():
        p=Path(name)
        if not p.is_file() or digest(p.read_bytes())!=sha:
            raise ValueError('completed evidence changed: '+name)
    if attempt['stages']['export']['status']=='passed':
        p=Path(attempt['glb'])
        if not p.is_file() or digest(p.read_bytes())!=attempt['glb_sha256']:
            raise ValueError('completed artifact changed; preserve ledger and investigate')


def check_images(glb,archive,common):
    textures={t['key']:t for t in common['textures']}
    textures.update({t['key']:t for t in archive['textures']})
    g,_=read(glb);raw=glb.read_bytes();length=int.from_bytes(raw[12:16],'little');blob=raw[28+length:]
    for image in g.get('images',[]):
        t=textures[normalize(image['extras']['original_name'])];v=g['bufferViews'][image['bufferView']];at=v.get('byteOffset',0)
        actual=np.asarray(Image.open(io.BytesIO(blob[at:at+v['byteLength']])).convert('RGBA'))
        np.testing.assert_array_equal(actual,np.asarray(pixels(t)))
    return len(g.get('images',[]))


def source_asset(manifest,target):
    name=target.get('model')
    matches=[a for a in manifest['assets'] if a['category'] in ['static_models','skeletal_models','unparsed_models','environment_scenes'] and
        any(o['archive']==target['archive'] and (normalize(o.get('name',''))==normalize(name) if name else a['category']=='environment_scenes') for o in a['occurrences'])]
    if len(matches)!=1:raise ValueError('target must identify exactly one inventory payload')
    return matches[0]


def totals(ledger):
    # Unique source IDs, with stage results from the latest recorded attempt.
    groups={}
    for entry in ledger['entries'].values():
        if not entry['attempts']:continue
        a=entry['attempts'][-1];bucket=groups.setdefault(entry['category'],dict(attempted=0,**{s:0 for s in STAGES}))
        bucket['attempted']+=1
        for stage in STAGES:bucket[stage]+=a['stages'][stage]['status']=='passed'
    return groups


def validate_plan(plan):
    targets=plan['targets']
    if not 1<=len(targets)<=16:raise ValueError('plan must have 1..16 targets')
    labels=[t['label'] for t in targets]
    import re
    if len(set(labels))!=len(labels) or any(not re.fullmatch('[A-Za-z0-9_-]+',n) for n in labels):raise ValueError('labels must be unique safe identifiers')
    if any((t.get('animation_path') or t.get('animation_archive')) and not t.get('animation') for t in targets):
        raise ValueError('named animation selection requires animation=true')
    if any(t.get('animation_archive') and not t.get('animation_path') for t in targets):
        raise ValueError('animation_archive requires an exact animation_path')


def run(args):
    validate_plan(json.loads(args.plan.read_text()))
    args.out.mkdir(parents=True,exist_ok=True);path=args.out/'ledger.json'
    binding=dict(game=str(args.game.resolve()),plan=digest(args.plan.read_bytes()),manifest=digest(args.manifest.read_bytes()),known=digest(args.known.read_bytes()))
    if not path.exists() and any(args.out.iterdir()):raise ValueError('nonempty output without a ledger; use a new directory')
    if path.exists():
        if not args.resume:raise ValueError('existing ledger requires --resume')
        ledger=json.loads(path.read_text())
        if ledger['binding']!=binding:raise ValueError('resume inputs changed; create a separate ledger')
    else:
        if args.resume:raise ValueError('no ledger to resume')
        ledger=dict(schema=1,binding=binding,entries={},skipped=[],invocations=[])
    manifest=json.loads(args.manifest.read_text());plan=json.loads(args.plan.read_text());known=verified_known(json.loads(args.known.read_text()))
    invocation=dict(limit=args.limit,retry_failed=args.retry_failed,processed=0,skipped_completed=0)
    ledger['invocations'].append(invocation)
    seen=set()
    for target in plan['targets']:
        asset=source_asset(manifest,target);key=asset['id']
        if key in seen:continue
        seen.add(key)
        if (key,profile(target)) in known:
            if not any(s['asset_id']==key for s in ledger['skipped']):ledger['skipped'].append(dict(asset_id=key,label=target['label'],reason='verified prior success'))
            continue
        entry=ledger['entries'].get(key)
        if entry and entry['attempts']:
            if profile(target)!=profile(entry['target']):raise ValueError('one export profile per unique asset/ledger; use a separate ledger for another LOD/animation selection')
            last=entry['attempts'][-1]
            if last.get('finished'):
                verify_attempt(last)
                if last.get('successful') or not args.retry_failed:
                    invocation['skipped_completed']+=1;continue
        if invocation['processed']>=args.limit:break
        invocation['processed']+=1
        if entry is None:
            entry=ledger['entries'][key]=dict(asset_id=key,category=asset['category'],target=target,attempts=[])
        n=len(entry['attempts'])+1;directory=args.out/'attempts'/target['label']/('attempt-%03d'%n);directory.mkdir(parents=True)
        attempt=dict(number=n,finished=False,stages={s:dict(status='not_attempted') for s in STAGES},
            tool_hashes={f:digest((ROOT/'tools'/f).read_bytes()) for f in ['export_coverage.py','asset_survey.py','psyexport.py','psyassets.py','check_model_export.py','blender_model_check.py','blender_boyd_check.py','psyrig.py','psyanim.py','psymorph.py','glb_skin.py']})
        entry['attempts'].append(attempt);save(path,ledger)
        try:
            archive=args.game/'WorkResource/PCLevelPackFiles'/target['archive']
            if archive.resolve().parent!=(args.game/'WorkResource/PCLevelPackFiles').resolve():raise ValueError('unsafe archive path')
            a=read_archive(archive);raw=a['scene_data'] if not target.get('model') else next(m['data'] for m in a['models'] if normalize(m['name'])==normalize(target['model']))
            if digest(raw)!=asset['sha256']:raise ValueError('original payload differs from inventory')
            parsed=scene(raw)
            attempt['stages']['parsing']=dict(status='passed',version=parsed['version'],tail_bytes=parsed['trailing_bytes'])
        except Exception as e:
            attempt['stages']['parsing']=dict(status='failed',type=type(e).__name__,reason=str(e)[:1500]);attempt['finished']=True
            preserve_attempt(attempt,directory);save(path,ledger);continue
        save(path,ledger)
        # Legacy survey supplies existing export/dependency logic. Its source and
        # schema results are copied separately, never collapsed into "success".
        try:
            legacy=survey(args.game,manifest,dict(targets=[target]),directory,args.validator)[0]
        except Exception as e:
            attempt['stages']['export']=dict(status='failed',type=type(e).__name__,reason=str(e)[:1500]);attempt['finished']=True
            preserve_attempt(attempt,directory);save(path,ledger);continue
        attempt['legacy']=legacy
        if not legacy['exported']:
            attempt['stages']['export']=dict(status='failed',reason=legacy.get('error','no GLB produced'))
        else:
            glb=Path(legacy['glb']);attempt.update(glb=str(glb),glb_sha256=digest(glb.read_bytes()))
            attempt['stages']['export']=dict(status='passed')
            try:
                if not legacy['source_validated']:
                    result=check(archive,target.get('model'),glb,target.get('lod_mask'))
                    save(directory/'independent-source.json',result)
                    # Source key checks that failed in the established survey
                    # cannot be replaced by geometry-only checks.
                    if legacy.get('animation'):raise ValueError('skeletal-key verification failed; geometry-only retry is insufficient')
                attempt['stages']['source']=dict(status='passed',scope='geometry/material consistency; optional skeletal keys; not original renderer equivalence')
            except Exception as e:attempt['stages']['source']=dict(status='failed',type=type(e).__name__,reason=str(e)[:1500])
            try:
                images=check_images(glb,a,read_archive(args.game/'WorkResource/PCLevelPackFiles/common.ppf',False))
                attempt['stages']['textures']=dict(status='passed',embedded_images=images,scope='selected base mip/frame PNG consistency; original shaders not established')
            except Exception as e:attempt['stages']['textures']=dict(status='failed',type=type(e).__name__,reason=str(e)[:1500])
            attempt['stages']['animation']=dict(status='not_requested')
            if target.get('animation'):
                attempt['stages']['animation']=dict(status='passed' if legacy.get('animation') and legacy['source_validated'] else 'failed',reason='source skeletal keys checked' if legacy.get('animation') and legacy['source_validated'] else 'requested compatible clip/key verification unavailable')
            save(path,ledger)
            try:
                if not legacy['gltf_validated']:
                    with (directory/'independent-gltf.log').open('w') as log:subprocess.run([str(args.validator),'-h','1',str(glb)],stdout=log,stderr=subprocess.STDOUT,check=True)
                report=json.loads(glb.with_suffix('.glb.report.json').read_text());issues=report['issues']
                if issues['numErrors'] or issues['numWarnings']:raise ValueError(str(issues))
                attempt['stages']['gltf']=dict(status='passed',errors=0,warnings=0)
            except Exception as e:attempt['stages']['gltf']=dict(status='failed',type=type(e).__name__,reason=str(e)[:1500])
            save(path,ledger)
            if attempt['stages']['gltf']['status']=='passed':
                try:
                    with (directory/'blender.log').open('w') as log:subprocess.run([str(args.blender),'--background','--threads','2','--python-exit-code','1','--python',str(ROOT/'tools/blender_model_check.py'),'--',str(directory),glb.parent.name],stdout=log,stderr=subprocess.STDOUT,check=True)
                    candidates=list((directory/'validation').glob('blender-*.json'));assert any(report_model_passed(json.loads(p.read_text()),glb.name) for p in candidates),'successful Blender report for this GLB absent'
                    attempt['stages']['blender']=dict(status='passed',reports=[dict(path=str(p),sha256=digest(p.read_bytes())) for p in candidates],scope='import/source-GLB consistency, not Godot/Unity/Unreal portability')
                except Exception as e:attempt['stages']['blender']=dict(status='failed',type=type(e).__name__,reason=str(e)[:1500],log=str(directory/'blender.log'))
        attempt['finished']=True;attempt['successful']=all(attempt['stages'][s]['status']=='passed' or s=='animation' and not target.get('animation') and attempt['stages'][s]['status']=='not_requested' for s in STAGES)
        preserve_attempt(attempt,directory)
        ledger['totals']=totals(ledger);save(path,ledger)
        print(target['label'],{s:attempt['stages'][s]['status'] for s in STAGES},flush=True)
    ledger['totals']=totals(ledger);save(path,ledger);print(json.dumps(ledger['totals']));return ledger


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['game','manifest','plan','known','out','validator','blender']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--limit',type=int,default=3);p.add_argument('--resume',action='store_true');p.add_argument('--retry-failed',action='store_true');a=p.parse_args()
    a.out=a.out.resolve()
    if not a.out.is_relative_to(ROOT/'.local/assets') or not 1<=a.limit<=16:p.error('private output and limit1..16 required')
    run(a)


if __name__=='__main__':main()
