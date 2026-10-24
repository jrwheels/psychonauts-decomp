#!/usr/bin/env python3
"""Bounded manifest-driven export survey; writes only new private artifacts.

Coverage is per unique source resource, not per GLB/LOD. Validation stages remain
separate. This does not bulk-export the inventory or install/launch a game.
"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from PIL import Image
from asset_manifest import ROOT,digest,derived,material_view,mesh_walk,encoded_texture
from psyassets import read_archive,scene,normalize
from psyexport import Exporter,export_collision,pixels
from psyrig import flatten,compatible_hierarchy
from psyanim import jan
from glb_skin import read
from check_model_export import check


def compatible_clip(manifest,game,joints):
    motion={(a['details']['pkg_offset'],a['details']['pkg_size']) for a in manifest['assets']
            if a['category']=='animation_references' and a['details']['root_motion']}
    candidates=[a for a in manifest['assets'] if a['category']=='skeletal_animations' and
                a['parse_status']=='parsed' and a['details']['joints']==len(joints)]
    candidates.sort(key=lambda a:('idle' not in a['occurrences'][0]['name'].lower(),a['id']))
    attempted=0
    for a in candidates:
        o=a['occurrences'][0]
        if (o['offset'],o['size']) in motion:continue
        attempted+=1
        if attempted>40:break
        with (game/o['archive']).open('rb') as f:f.seek(o['offset']);raw=f.read(o['size'])
        assert digest(raw)==a['sha256']
        animation=jan(raw)
        if compatible_hierarchy(joints[0],animation['root']):
            return a,dict(name='pkg-record-%d/%s'%(o['record'],o['name']),data=animation,
                          source=dict(archive=o['archive'],record=o['record'],sha256=a['sha256'],frame_rate=30))
    return None,None


def check_keys(glb,clip):
    g,access=read(glb);animation=g['animations'][0]
    channels=[(j,c) for j in flatten(clip['data']['root']) for c in j['channels']]
    assert len(channels)==len(animation['channels']);keys=0
    for (j,c),target in zip(channels,animation['channels']):
        sampler=animation['samplers'][target['sampler']]
        assert g['nodes'][target['target']['node']]['name'].rsplit('|',1)[-1]==j['name'].rsplit('|',1)[-1]
        assert target['target']['path']=={0:'translation',1:'rotation',2:'scale',3:'rotation'}[c['type']]
        np.testing.assert_allclose(access(sampler['input']).ravel()*30,[k['frame'] for k in c['keys']],atol=.0002)
        values=np.asarray([k['value'] for k in c['keys']]);out=access(sampler['output'])
        if c['type'] in [1,3]:np.testing.assert_allclose(abs(np.sum(values*out,axis=1)),1,atol=3e-7)
        else:np.testing.assert_array_equal(out,values.astype('<f4'))
        keys+=len(values)
    return keys


def record(asset,path,report,validated):
    scope={'textures':'base mip/frame PNG and selected-source codec consistency',
           'materials':'base parameters and texture assignment; original shader incomplete',
           'skeletal_animations':'JAN skeletal keys only',
           'collision_meshes':'positions and indices; no collision behavior',
           'environment_scenes':'serialized visual snapshot; dynamic placement unverified'}.get(asset['category'],'source-data geometry/attribute comparison')
    evidence=dict(path=str(path),sha256=digest(path.read_bytes()),report=str(report),scope=scope)
    if not any(v['path']==evidence['path'] and v['sha256']==evidence['sha256'] for v in asset['exports']):asset['exports'].append(evidence)
    if validated and not any(v['path']==evidence['path'] and v['sha256']==evidence['sha256'] for v in asset['validations']):asset['validations'].append(evidence)


def survey(game,manifest,plan,out,validator):
    if len(plan['targets'])>16:raise ValueError('bounded survey permits at most 16 targets')
    assets={a['id']:a for a in manifest['assets']};packs=game/'WorkResource/PCLevelPackFiles'
    archives={};rows=[]
    def archive(name):
        path=(packs/name).resolve()
        if path.parent!=packs.resolve():raise ValueError('archive must be directly in PCLevelPackFiles')
        if name not in archives:archives[name]=read_archive(path)
        return archives[name]
    common={t['key']:t for t in archive('common.ppf')['textures']}
    for target in plan['targets']:
        label=target['label']
        if not re.fullmatch('[A-Za-z0-9_-]+',label):raise ValueError('unsafe output label')
        row=dict(target=target,stage='source',exported=False,source_validated=False,gltf_validated=False)
        try:
            a=archive(target['archive']);model=target.get('model');lod=target.get('lod_mask')
            raw=a['scene_data'] if model is None else next(m['data'] for m in a['models'] if normalize(m['name'])==normalize(model))
            sha=digest(raw);asset=next(a for a in assets.values() if a['sha256']==sha and a['category'] in ['static_models','skeletal_models','unparsed_models','environment_scenes'])
            row['asset_id']=asset['id'];s=scene(raw);all_meshes=list(mesh_walk(s['domain']))
            group='environments' if model is None else 'rigged' if any(m['skeletons'] for m in all_meshes) else 'static'
            directory=out/group;directory.mkdir(exist_ok=True);path=directory/(label+'.glb');row['glb']=str(path)
            tex=dict(common);tex.update({t['key']:t for t in a['textures']})
            clip_asset=clip=None
            if target.get('animation'):
                joint_list=[j for m in all_meshes for sk in m['skeletons'] for j in flatten(sk['root'])]
                clip_asset,clip=compatible_clip(manifest,game,joint_list)
                row['animation']=clip_asset['id'] if clip_asset else None
                row['animation_scope']='skeletal keys only; no APF root-motion-only references, facial companions or events'
            s['source']=dict(archive=target['archive'],model=model,record_sha256=sha)
            row['stage']='export'
            with (out/(label+'-export.log')).open('w') as log,contextlib.redirect_stdout(log):
                Exporter(s,tex,path,lod,clip).write()
            row['exported']=True
            source_report=out/(label+'-source.json');row['stage']='source_validation'
            source=check(packs/target['archive'],model,path,lod)
            if clip:source['animation_keys_compared']=check_keys(path,clip)
            source_report.write_text(json.dumps(source,indent=2)+'\n');row['source_validated']=True
            row['stage']='gltf_validation'
            with (out/(label+'-validator.log')).open('w') as log:
                subprocess.run([str(validator),'-h','1',str(path)],stdout=log,stderr=subprocess.STDOUT,check=True)
            validation=json.loads(path.with_suffix('.glb.report.json').read_text())
            assert validation['issues']['numErrors']==0 and validation['issues']['numWarnings']==0
            row['gltf_validated']=True;row['stage']='complete';record(asset,path,source_report,True)
            if clip_asset:record(clip_asset,path,source_report,True)
            for m in all_meshes:
                for sk in m['skeletons']:
                    child=assets['skeletons:'+digest(derived(sk))];record(child,path,source_report,True)
                for f in m['fragments']:
                    if not f['vertices'] or lod is not None and f['lod'] and not f['lod']&lod:continue
                    child=assets['materials:'+digest(derived(material_view(f,s['texture_references'])))];record(child,path,source_report,True)
            row['stage']='texture_validation'
            # Compare embedded PNGs to the selected original texture surfaces.
            g,access=read(path);bytes_=path.read_bytes();json_size=int.from_bytes(bytes_[12:16],'little');blob=bytes_[28+json_size:]
            for image in g.get('images',[]):
                t=tex[normalize(image['extras']['original_name'])];v=g['bufferViews'][image['bufferView']]
                png=blob[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
                np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(png)).convert('RGBA')),np.asarray(pixels(t)))
                identity=encoded_texture(t)
                child=assets['textures:'+digest(identity)];record(child,path,source_report,True)
            # Collision is separate; check original scalar records and GLB buffers.
            if any(m['collision'] and m['collision']['record_words'] for m in all_meshes):
                row['stage']='collision_validation'
                directory=out/'collision';directory.mkdir(exist_ok=True);cp=directory/(label+'.glb')
                with (out/(label+'-collision.log')).open('w') as log,contextlib.redirect_stdout(log):export_collision(s,cp)
                cg,ac=read(cp);ci=0
                for m in all_meshes:
                    c=m['collision']
                    if not c or not c['record_words']:continue
                    prim=cg['meshes'][ci]['primitives'][0];ci+=1
                    expected=[[(r[1]&65535),(r[1]>>16),(r[2]&65535)] for r in c['record_words']]
                    np.testing.assert_array_equal(ac(prim['indices']).reshape(-1,3),expected)
                    np.testing.assert_array_equal(ac(prim['attributes']['POSITION']),c['vertices'])
                    child=assets['collision_meshes:'+digest(derived(c))];record(child,cp,source_report,True)
                subprocess.run([str(validator),'-h','1',str(cp)],stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,check=True)
                row['collision_glb']=str(cp)
            row['stage']='complete'
        except (ValueError,KeyError,IndexError,AssertionError,StopIteration,subprocess.CalledProcessError) as e:
            row['error_type']=type(e).__name__;row['error']=str(e)[:500]
            if row['exported'] and row.get('asset_id'):
                asset=assets[row['asset_id']]
                if not any(x['path']==row['glb'] for x in asset['exports']):record(asset,Path(row['glb']),out/(label+'-source.json'),False)
        rows.append(row);print(label,row['stage'],row.get('error','passed'),flush=True)
        (out/'survey.json').write_text(json.dumps(dict(targets=rows),indent=2)+'\n')
    return rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ['game','manifest','plan','out','validator']:ap.add_argument('--'+arg,type=Path,required=True)
    args=ap.parse_args()
    if not args.out.resolve().is_relative_to(ROOT/'.local/assets') or args.out.exists():ap.error('output must be new and private')
    args.out.mkdir(parents=True);manifest=json.loads(args.manifest.read_text());plan=json.loads(args.plan.read_text())
    survey(args.game,manifest,plan,args.out,args.validator)
    from asset_manifest import Manifest
    state=Manifest();state.assets={a['id']:a for a in manifest['assets']};state.archives=manifest['archives'];state.archive_failures=manifest['archive_failures']
    (args.out/'coverage.json').write_text(json.dumps(state.summary(),indent=2)+'\n')
    (args.out/'manifest.json').write_text(json.dumps(state.result(),indent=2)+'\n')


if __name__=='__main__':main()
