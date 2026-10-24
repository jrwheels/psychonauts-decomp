#!/usr/bin/env python3
"""Original-data validation of packaged morph deltas and every animation key."""
import argparse
import json
from pathlib import Path
import numpy as np
from psyassets import read_archive,scene,normalize
from glb_skin import read
from psyrig import flatten,joint_name


def main():
    ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);ap.add_argument('package',type=Path);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in args.package.resolve().parents:ap.error('private package required')
    a=read_archive(args.archive);manifest=json.loads((args.package/'metadata/manifest.json').read_text());report={}
    for path in sorted((args.package/'models').glob('*.glb')):
        variant=path.stem.split('_LOD')[0];mask=int(path.stem.split('_LOD')[1])
        ident=manifest['models'][variant]['source']['model'];s=scene(next(m['data'] for m in a['models'] if normalize(m['name'])==ident))
        mesh=s['domain']['meshes'][0];frags=[f for f in mesh['fragments'] if not f['lod'] or f['lod']&mask]
        g,acc=read(path);names=g['meshes'][0]['extras']['targetNames'];checks=0;keychecks=0;weightchecks=0
        assert len(frags)==len(g['meshes'][0]['primitives'])
        for f,p in zip(frags,g['meshes'][0]['primitives']):
            for name,target in zip(names,p['targets']):
                b=next((b for b in f['blendshapes'] if b['name']==name),None);expected=np.zeros((f['vertices'],3),dtype='<f4')
                if b:
                    stride=10 if b['sparse'] else 8
                    for ri in range(b['count']):
                        off=ri*stride;vi=int.from_bytes(b['data'][off:off+2],'little') if b['sparse'] else ri
                        at=off+2 if b['sparse'] else off;word=int.from_bytes(b['data'][at:at+4],'little')
                        values=[]
                        for shift,width,denom in [(0,11,1023),(11,11,1023),(22,10,511)]:
                            v=(word>>shift)&((1<<width)-1);v=v-(1<<width) if v&(1<<(width-1)) else v;values.append(v/denom)
                        expected[vi]=np.array(values,dtype='<f4')*b['scale']
                np.testing.assert_allclose(acc(target['POSITION']),expected,atol=2e-6);checks+=len(expected)
        entries=[v for v in manifest['clips'] if variant in v['variants']]
        assert len(g['animations'])==len(entries)
        for ga,e in zip(g['animations'],entries):
            source=json.loads((args.package/'animations'/('clip-%05d.json'%e['pkg_record'])).read_text())
            channels=[(j,c) for j in flatten(source['animation']['root']) for c in j['channels']];tracks=ga['channels']
            for (j,c),t in zip(channels,tracks):
                sp=ga['samplers'][t['sampler']];keys=c['keys'];values=np.array([k['value'] for k in keys]);out=acc(sp['output'])
                assert joint_name(g['nodes'][t['target']['node']]['name'])==joint_name(j['name'])
                np.testing.assert_allclose(acc(sp['input']).ravel()*30,[k['frame'] for k in keys],atol=1e-4)
                if c['type'] in [1,3]:np.testing.assert_allclose(np.abs(np.sum(out*values,axis=1)),1,atol=3e-7)
                else:np.testing.assert_array_equal(out,values.astype('<f4'))
                keychecks+=len(keys)
            if source['pba'] and source['pba']['channels']:
                t=tracks[-1];assert t['target']['path']=='weights';sp=ga['samplers'][t['sampler']];values=acc(sp['output']).reshape(-1,len(names))
                for c in source['pba']['channels']:
                    np.testing.assert_allclose(values[:len(c['weights']),names.index(c['name'])],np.array(c['weights'])/255,atol=3e-8);weightchecks+=len(c['weights'])
        report[path.name]={'morph_vertex_checks':checks,'skeletal_keys_compared':keychecks,'facial_samples_compared':weightchecks,'clips':len(entries),'status':'passed'}
    (args.package/'validation/original-data.json').write_text(json.dumps(report,indent=2)+'\n');print(report)


if __name__=='__main__':main()
