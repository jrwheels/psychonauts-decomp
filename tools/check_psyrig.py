#!/usr/bin/env python3
"""Compare exported glTF rig/animation to owned source records, not gameplay."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from psyassets import read_archive,scene,normalize
from psyanim import apf,jan
from psyrig import flatten,bind_globals,bind_quaternion,matrix
from glb_skin import read,pose,interpolate


def check(archive,model,glb,anim_pack,pkg,animation,lod_mask):
    a=read_archive(archive);raw=next(v['data'] for v in a['models'] if normalize(v['name'])==normalize(model))
    s=scene(raw);m=s['domain']['meshes'][0];joints=[j for sk in m['skeletons'] for j in flatten(sk['root'])]
    stub=next(v for v in apf(anim_pack.read_bytes()) if normalize(v['name'])==normalize(animation))
    with pkg.open('rb') as f:f.seek(stub['pkg_offset']);araw=f.read(stub['pkg_size'])
    anim=jan(araw);ajs=flatten(anim['root'])
    assert anim['header']['joints']==stub['header']['joints']
    assert len(joints)==len(ajs) and all(a['name']==j['name'] for a,j in zip(ajs,joints))
    assert all([c['name'] for c in aj['children']]==[c['name'] for c in j['children']] for aj,j in zip(ajs,joints))
    g,access=read(glb);skin=g['skins'][0];ids=[j['id'] for j in joints]
    assert [g['nodes'][n]['name'] for n in skin['joints']]==[j['name'] for j in joints]
    source_bind=bind_globals(joints);parts=[f for f in m['fragments'] if (not f['lod'] or f['lod']&lod_mask) and f['vertices']]
    primitives=g['meshes'][0]['primitives'];assert len(parts)==len(primitives)
    vertex_checks=0;bounds_checks=0;channel_checks=0;invariant_rotation_checks=0
    # Independently unpack byte-local bone indices, then remap through original IDs.
    for f,p in zip(parts,primitives):
        n=f['vertices'];sr=np.frombuffer(f['skin']['weights'],dtype='<u4').reshape(n,3)
        sw=np.frombuffer(f['skin']['weights'],dtype='<f4').reshape(n,3)[:,1:]
        local=np.c_[(sr[:,0]>>16)&255,(sr[:,0]>>8)&255]
        palette=np.array(f['skin']['joint_ids']);expected=palette[local]
        gw=access(p['attributes']['WEIGHTS_0']);gj=access(p['attributes']['JOINTS_0'])
        assert np.array_equal(gw[:,:2],sw)
        for k in range(2):
            active=sw[:,k]>0
            assert np.array_equal(np.array(ids)[gj[active,k]],expected[active,k])
        source_pos=np.frombuffer(f['posnrm'],dtype='<f4').reshape(n,4)[:,:3]
        assert np.array_equal(source_pos,access(p['attributes']['POSITION']))
        # Per-palette bone bounds provide an independent check on byte-order mapping.
        for b,bb in enumerate(f['skin']['bone_bounds']):
            active=np.any((local==b)&(sw>0),axis=1)
            if active.any():
                pp=source_pos[active];bb=np.array(bb)
                if np.any(pp.min(0)<bb[:3]-.05) or np.any(pp.max(0)>bb[3:]+.05):
                    raise ValueError('weighted vertex outside source bone bounds')
                bounds_checks+=int(active.sum())
        vertex_checks+=n
    tracks=g['animations'][0]['channels'];samplers=g['animations'][0]['samplers']
    ti=0
    for aj,j in zip(ajs,joints):
        for c in aj['channels']:
            t=tracks[ti];sp=samplers[t['sampler']];ti+=1
            assert g['nodes'][t['target']['node']]['name']==j['name']
            assert np.allclose(access(sp['input']).ravel()*30,[k['frame'] for k in c['keys']],atol=2e-5)
            source=np.array([k['value'] for k in c['keys']]);out=access(sp['output'])
            if c['type'] in [1,3]:
                assert np.allclose(np.abs(np.sum(source*out,axis=1)),1,atol=3e-7)
                if len(source)==1 and 1-abs(np.dot(source[0],bind_quaternion(j['rotation'])))<1e-5:
                    invariant_rotation_checks+=1
            else:assert np.array_equal(source.astype('<f4'),out)
            channel_checks+=1
    errors=[]
    frames=np.linspace(0,stub['header']['frames'],9).tolist()
    for frame in frames:
        world={}
        for aj,j in zip(ajs,joints):
            pos=j['position'];q=bind_quaternion(j['rotation']);scale=[1,1,1]
            for c in aj['channels']:
                v=interpolate(np.array([k['frame'] for k in c['keys']]),np.array([k['value'] for k in c['keys']]),frame,c['type'] in [1,3])
                if c['type']==0:pos=v
                elif c['type']==2:scale=v
                else:q=v
            localmat=matrix(pos,q,scale);world[j['id']]=localmat if j['parent'] is None else world[j['parent']]@localmat
        exported=pose(g,access,frame/30)
        for pi,f in enumerate(parts):
            n=f['vertices'];v=np.frombuffer(f['posnrm'],dtype='<f4').reshape(n,4)[:,:3];h=np.c_[v,np.ones(n)]
            words=np.frombuffer(f['skin']['weights'],dtype='<u4').reshape(n,3)[:,0]
            sw=np.frombuffer(f['skin']['weights'],dtype='<f4').reshape(n,3)[:,1:];out=np.zeros_like(h)
            for k,shift in enumerate([16,8]):
                indices=(words>>shift)&255
                for b in np.unique(indices):
                    mask=indices==b;ident=f['skin']['joint_ids'][b]
                    transform=world[ident]@np.linalg.inv(source_bind[ident])
                    out[mask]+=(h[mask]@transform.T)*sw[mask,k,None]
            err=float(np.abs(out[:,:3]-exported[(0,pi)]).max());errors.append(err)
    if max(errors)>.003:raise ValueError('source/export pose mismatch %g'%max(errors))
    return dict(model=model,animation=animation,joints=len(joints),vertices_compared=vertex_checks,
                weighted_bone_bound_checks=bounds_checks,channels_compared=channel_checks,
                invariant_bind_rotation_channels=invariant_rotation_checks,frames_compared=frames,
                max_pose_position_error=max(errors),source_scene_sha256=hashlib.sha256(raw).hexdigest(),
                source_jan_sha256=hashlib.sha256(araw).hexdigest(),glb_sha256=hashlib.sha256(glb.read_bytes()).hexdigest(),
                scope='original-data comparison and CPU skin evaluation, not original engine execution')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for v in ['archive','glb','anim-pack','pkg','report']:ap.add_argument('--'+v,type=Path,required=True)
    ap.add_argument('--model',required=True);ap.add_argument('--animation',required=True);ap.add_argument('--lod-mask',type=int,default=1)
    args=ap.parse_args();root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in args.report.resolve().parents:ap.error('report must remain under .local/assets/')
    result=check(args.archive,args.model,args.glb,args.anim_pack,args.pkg,args.animation,args.lod_mask)
    args.report.write_text(json.dumps(result,indent=2)+'\n');print(result)


if __name__=='__main__':main()
