#!/usr/bin/env python3
"""Compare raw-source vs existing-GLB linear morph deformation, no new tracks.

Consumes hash-bound original-code weight reports. Does not execute the original
vertex deformer or establish actor/audio/skeletal synchronization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from psyassets import read_archive,scene,normalize
from check_model_export import meshes
from glb_skin import read


def delta(stream,count):
    result=np.zeros((count,3));sparse=stream['sparse'];stride=10 if sparse else 8
    for i in range(stream['count']):
        at=i*stride;index=struct.unpack_from('<H',stream['data'],at)[0] if sparse else i
        word=struct.unpack_from('<I',stream['data'],at+(2 if sparse else 0))[0];xyz=[]
        for shift,bits,denom in ((0,11,1023),(11,11,1023),(22,10,511)):
            v=(word>>shift)&((1<<bits)-1)
            if v&(1<<(bits-1)):v-=1<<bits
            xyz.append(v/denom*stream['scale'])
        result[index]=xyz
    return result


def run(game,plan,report,out):
    out.mkdir(parents=True);cache={};cases=[]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,m in plan['models'].items():
        a=read_archive(game/'WorkResource/PCLevelPackFiles'/m['archive']);raw=next(x['data'] for x in a['models'] if normalize(x['name'])==normalize(m['model']))
        s=scene(raw);source_meshes=list(meshes(s['domain']));assert len(source_meshes)==1
        g,access=read(Path(m['glb']));names=g['meshes'][0]['extras']['targetNames'];fragments=[f for f in source_meshes[0]['fragments'] if f['vertices'] and (not f['lod'] or f['lod']&1)]
        assert sha(Path(m['glb']))==report['models'][name]['glb_sha256']
        assert hashlib.sha256(raw).hexdigest()==report['models'][name]['model_record_sha256']
        assert len(fragments)==len(g['meshes'][0]['primitives']);parts=[]
        for f,p in zip(fragments,g['meshes'][0]['primitives']):
            base=np.array([struct.unpack_from('<3f',f['posnrm'],i*16) for i in range(f['vertices'])]);streams={b['name']:b for b in f['blendshapes']}
            original=[delta(streams[n],f['vertices']) if n in streams else np.zeros_like(base) for n in names]
            exported=[access(t['POSITION']) for t in p['targets']];parts.append((base,original,access(p['attributes']['POSITION']),exported))
        cache[name]=parts
    for c in report['cases']:
        samples=[s for s in c['samples'] if not s['loop'] and any(v!=0 for v in s['original'])][:4];max_error=0.;vertices=0
        for s in samples:
            weights=np.asarray(s['original'])
            for base,deltas,gbase,gdeltas in cache[c['model']]:
                original=base+np.einsum('i,ijk->jk',weights,np.asarray(deltas));exported=gbase+np.einsum('i,ijk->jk',weights,np.asarray(gdeltas))
                np.testing.assert_allclose(original,exported,atol=3e-5,rtol=0)
                max_error=max(max_error,float(np.max(np.abs(original-exported))));vertices+=len(base)
        cases.append(dict(label=c['label'],version=c['version'],model=c['model'],stage='source_vs_existing_glb_linear_morph_consistency' if samples else 'not_observable_zero_weights',sampled_poses=len(samples),vertex_comparisons=vertices,max_position_error=max_error))
    result=dict(cases=cases,limitations=['linear source-delta/GLB comparison; original vertex deformer not executed','no skeletal deformation in this check','no new glTF facial animation or Blender playback generated'])
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('game','plan','original-report','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]/'.local/assets'
    if not a.out.resolve().is_relative_to(root) or a.out.exists():p.error('new private output required')
    r=run(a.game,json.loads(a.plan.read_text()),json.loads(a.original_report.read_text()),a.out)
    print('Cases',len(r['cases']),'observable',sum(c['sampled_poses']>0 for c in r['cases']))


if __name__=='__main__':main()
