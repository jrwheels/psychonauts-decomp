#!/usr/bin/env python3
"""Bounded original-code PBA investigation; never generates animation exports."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from psyassets import read_archive,scene,normalize
from check_model_export import meshes
from glb_skin import read
from psyanim import apf,jan
from pba101_research import decode,local_weights
from original_reader_pba import OriginalPba


def run(game,manifest,plan,executable,out):
    if len(plan['cases'])>32 or len(plan.get('controls',[]))>8:raise ValueError('bounded plan limit')
    out.mkdir(parents=True);assets={a['id']:a for a in manifest['assets']};models={};archive_cache={}
    sha=lambda b:hashlib.sha256(b).hexdigest()
    for name,model in plan['models'].items():
        archive=model['archive']
        if archive not in archive_cache:archive_cache[archive]=read_archive(game/'WorkResource/PCLevelPackFiles'/archive)
        a=archive_cache[archive];records=[m for m in a['models'] if normalize(m['name'])==normalize(model['model'])]
        if len(records)!=1:raise ValueError('ambiguous original model')
        raw=records[0]['data'];s=scene(raw)
        names=sorted({b['name'] for mesh in meshes(s['domain']) for f in mesh['fragments'] for b in f.get('blendshapes',[])})
        g,_=read(Path(model['glb']));assert len(g['meshes'])==1 and g['meshes'][0].get('extras',{}).get('targetNames',[])==names
        models[name]=dict(target_names=names,model_record_sha256=sha(raw),glb_sha256=sha(Path(model['glb']).read_bytes()))
    original=OriginalPba(executable);cases=[]
    def investigate(raw,label,model,origin,paired=None):
        d=decode(raw);targets=models[model]['target_names'];r=dict(label=label,model=model,version=d['version'],source=origin,bytes=len(raw),sha256=sha(raw),declared_channels=d['declared_channels'],channels=[dict(name=c['name'],samples=len(c['weights']),min_weight=min(c['weights'],default=0),max_weight=max(c['weights'],default=0)) for c in d['channels']],stages=dict(structural='passed',target_identification='not_tested',timing='not_tested',deformation='not_attempted',gltf_export='not_attempted',blender_playback='not_attempted'),actor_association='not_established' if not paired else 'original APF container paired to named skeletal action')
        observed=original.load(raw);expected=[dict(name=c['name'],weights=c['weights']) for c in d['channels']]
        if observed['channels']!=expected:raise AssertionError('original reader/channel mismatch: '+label)
        r['original_reader_success']=observed['returned_success'];r['original_duration']=observed['duration'];r['missing_declared_channels']=d['missing_declared_channels']
        mapping=original.bind(targets);expected_map=[targets.index(c['name']) if c['name'] in targets else -1 for c in d['channels']];assert mapping==expected_map
        r['target_mapping']=mapping;r['unmapped_names']=[c['name'] for c,i in zip(d['channels'],mapping) if i<0];r['stages']['target_identification']='original_exact_name_binding_verified' if all(i>=0 for i in mapping) else 'original_partial_binding_verified'
        duration=observed['duration'];times=sorted(set([0.,.25/30,.5/30,1/30,1.5/30]+[duration*f for f in (.25,.5,.9,1,1.1)]+[max(0,duration-.5/30),duration+.5/30]))
        samples=[];max_error=0.
        for loop in (False,True):
            for t in times:
                actual=original.evaluate(t,loop);predicted=local_weights(d,t,targets,loop);error=max((abs(x-y) for x,y in zip(actual,predicted)),default=0);max_error=max(max_error,error)
                if error>1e-5:raise AssertionError('local timing mismatch %s t=%g loop=%s error=%g'%(label,t,loop,error))
                samples.append(dict(seconds=t,loop=loop,original=actual,predicted=predicted,max_error=error))
        r['stages']['timing']='original_active_full_weight_local_controller_verified';r['samples']=samples;r['max_weight_error']=max_error
        r['single_sample_nonzero_channels']=[c['name'] for c in d['channels'] if len(c['weights'])==1 and c['weights'][0]!=0]
        if paired:
            r['skeletal_pair']=paired;r['sample_counts_minus_jan_frames']=sorted({len(c['weights'])-paired['jan_frames'] for c in d['channels']})
        cases.append(r);(out/('case-%02d.json'%len(cases))).write_text(json.dumps(r,indent=2)+'\n')
    for c in plan['cases']:
        asset=assets[c['asset_id']];o=next(o for o in asset['occurrences'] if o['archive'].endswith('.pkg'))
        with (game/o['archive']).open('rb') as f:f.seek(o['offset']);raw=f.read(o['size'])
        if sha(raw)!=asset['sha256']:raise ValueError('original PBA differs from inventory')
        investigate(raw,c.get('reported_name',asset['id']),c['model'],dict(asset_id=asset['id'],occurrence=o,selection_hint=c['selection_hint']))
    for c in plan.get('controls',[]):
        path=game/'WorkResource/PCLevelPackFiles'/c['archive'];raw=path.read_bytes();stubs=[s for s in apf(raw) if normalize(s['name'])==normalize(c['path'])]
        if len(stubs)!=1:raise ValueError('ambiguous APF control')
        stub=stubs[0];chunk=next(x for x in stub['chunks'] if x['tag']==0x626c6e64 and x['offset']==c['offset'] and x['size']==c['size'])
        with (game/'PsychonautsData2.pkg').open('rb') as f:f.seek(stub['pkg_offset']);jraw=f.read(stub['pkg_size'])
        animation=jan(jraw);paired=dict(original_path=stub['name'],jan_sha256=sha(jraw),pkg_offset=stub['pkg_offset'],pkg_size=stub['pkg_size'],jan_frames=animation['header']['frames'])
        investigate(raw[chunk['offset']:chunk['offset']+chunk['size']],c['path'],c['model'],dict(apf=c['archive'],apf_sha256=sha(raw),offset=chunk['offset'],size=chunk['size']),paired)
    result=dict(scope=plan['scope'],models=models,cases=cases,function_hashes=original.function_hashes,mocks=original.mock_calls,limits=['original local controller state synthesized; allocator/free and unused stream destructor mocked','actor ownership and skeletal/audio clocks not established for standalone files','no model deformation, glTF facial track or Blender playback claimed','original model packages unchanged'])
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('game','manifest','plan','executable','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]/'.local/assets'
    if not a.out.resolve().is_relative_to(root) or a.out.exists():p.error('output must be new and private')
    r=run(a.game,json.loads(a.manifest.read_text()),json.loads(a.plan.read_text()),a.executable,a.out)
    print('Cases',len(r['cases']),'101',sum(c['version']==101 for c in r['cases']),'samples',sum(len(c['samples']) for c in r['cases']))


if __name__=='__main__':main()
