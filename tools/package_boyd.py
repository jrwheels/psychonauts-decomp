#!/usr/bin/env python3
"""Build a private portable Boyd library from verified model/animation records."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
from psyassets import read_archive,scene,normalize,metadata
from psyanim import apf,jan
from psymorph import pba,events,texture_surfaces
from psyrig import flatten,compatible_hierarchy
from psyexport import Exporter,pixels


def digest(raw):return hashlib.sha256(raw).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('game',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    if root/'.local/assets' not in args.output.resolve().parents:ap.error('private package must be under .local/assets/')
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    for name in ['models','metadata','animations','textures','validation','previews','props','source_records']: (out/name).mkdir(exist_ok=True)
    packs=args.game/'WorkResource/PCLevelPackFiles';source=read_archive(packs/'ASGR.ppf');common=read_archive(packs/'common.ppf',False)
    textures={t['key']:t for t in common['textures']};textures.update({t['key']:t for t in source['textures']})
    variants={};manifest={'models':{},'clips':[],'unsupported':[],'association_policy':'exact full skeleton name/hierarchy compatibility; APF and PKG offsets preserved','native_source_unchanged':True}
    for name,ident in [('Boyd','characters/boyd.plb'),('BoydMilkCrate','characters/boydandmilkcrate.plb')]:
        raw=next(v['data'] for v in source['models'] if normalize(v['name'])==normalize(ident));s=scene(raw)
        s['source']={'archive':'ASGR.ppf','model':ident,'scene_sha256':digest(raw)}
        variants[name]=s;manifest['models'][name]={'source':s['source'],'joint_count':len(flatten(s['domain']['meshes'][0]['skeletons'][0]['root']))}
    # Search every APF; do not silently ignore unsupported packs.
    associations={}
    for path in sorted(packs.glob('*.apf')):
        raw=path.read_bytes()
        try:stubs=apf(raw)
        except ValueError as e:manifest['unsupported'].append({'archive':path.name,'reason':str(e)});continue
        for stub in stubs:
            if stub['header']['joints'] not in [v['joint_count'] for v in manifest['models'].values()] and not normalize(stub['name']).startswith('anims/boyd/'):continue
            extras={}
            for c in stub['chunks']:
                data=raw[c['offset']:c['offset']+c['size']]
                try:extras['pba' if c['tag']==0x626c6e64 else 'events']=pba(data) if c['tag']==0x626c6e64 else events(data)
                except ValueError as e:extras.setdefault('unsupported_chunks',[]).append({'tag':c['tag'],'reason':str(e)})
            associations.setdefault((stub['pkg_offset'],stub['pkg_size']),[]).append({'archive':path.name,'stub':stub,'extras':extras})
    spec=importlib.util.spec_from_file_location('psypkg',root/'third_party/psypkg.py');pkgreader=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkgreader)
    clips={name:[] for name in variants}
    pkg=args.game/'PsychonautsData2.pkg'
    with pkg.open('rb') as f:
        records=list(pkgreader.read_index(f));manifest['pkg_entries_searched']=len(records)
        for record_id,(reported,offset,size) in enumerate(records):
            if not reported.lower().endswith('.jan'):continue
            f.seek(offset);head=f.read(min(size,80))
            if len(head)<14 or head[:4] not in [b'XAJP',b'NAJP']:continue
            version=struct.unpack_from('<I',head,4)[0]
            count=head[13] if version==201 else struct.unpack_from('<I',head,36)[0] if version==200 and len(head)>=40 else -1
            candidates=[name for name,v in manifest['models'].items() if v['joint_count']==count]
            if (offset,size) in associations and any(normalize(v['stub']['name']).startswith('anims/boyd/') for v in associations[(offset,size)]):candidates=list(variants)
            if not candidates:continue
            f.seek(offset);raw=f.read(size)
            try:anim=jan(raw)
            except ValueError as e:
                if (offset,size) in associations or 'boyd' in reported.lower() or reported.startswith('yd/'):
                    (out/'source_records'/('unsupported-%05d.jan'%record_id)).write_bytes(raw)
                    manifest['unsupported'].append({'pkg_record':record_id,'reported_name':reported,'reason':str(e)})
                continue
            aj=flatten(anim['root']);matched=[];target_roots={}
            for name in candidates:
                sj=flatten(variants[name]['domain']['meshes'][0]['skeletons'][0]['root'])
                roots=[j for j in sj if compatible_hierarchy(j,anim['root'])]
                if len(roots)==1:matched.append(name);target_roots[name]=roots[0]['id']
            if not matched:continue
            (out/'source_records'/('clip-%05d.jan'%record_id)).write_bytes(raw)
            refs=associations.get((offset,size),[]);best=max(refs,key=lambda v:len(v['extras']),default=None)
            ident=best['stub']['name'] if best else 'pkg-record-%d/%s'%(record_id,reported)
            extras=best['extras'] if best else {}
            # Companion PBA association uses the same indexed path stem, checked against model target names.
            if 'pba' not in extras:
                paired=next(((off,sz) for nm,off,sz in records if nm==reported[:-4]+'.pba'),None)
                if paired:
                    f.seek(paired[0]);br=f.read(paired[1])
                    try:extras=dict(extras,pba=pba(br))
                    except ValueError as e:manifest['unsupported'].append({'animation':ident,'reason':'companion PBA: '+str(e)})
            st=best['stub'] if best else None;root_status='none'
            if st and st['position_channel']:
                jc=next((c for c in anim['root']['channels'] if c['type']==0),None)
                if jc and jc['keys']==st['position_channel']['keys']:root_status='APF root position duplicates JAN root translation; exported once'
                else:root_status='APF separate root channel preserved in metadata; runtime composition unresolved'
            meta={'pkg_record':record_id,'reported_pkg_name_unverified':reported,'pkg_offset':offset,'pkg_size':size,'jan_sha256':digest(raw),
                  'apf_references':[{'archive':v['archive'],'name':v['stub']['name'],'offset':v['stub']['offset']} for v in refs],
                  'root_motion':root_status,'apf_root_channel':st['position_channel'] if st else None,'events':extras.get('events'),
                  'unsupported_chunks':extras.get('unsupported_chunks',[])}
            last=max((k['frame'] for j in aj for c in j['channels'] for k in c['keys']),default=0)
            entry={'name':ident,'variants':matched,'frames':last,'seconds':last/30,'channels':sum(len(j['channels']) for j in aj),'root_motion':root_status,
                   'facial_channels':len(extras.get('pba',{}).get('channels',[])), 'missing_declared_facial_channels':extras.get('pba',{}).get('missing_declared_channels',0),**meta}
            manifest['clips'].append(entry)
            clip={'name':ident,'data':anim,'source':meta,'pba':extras.get('pba')}
            for name in matched:clips[name].append(dict(clip,target_root_id=target_roots[name]))
            leaf='clip-%05d'%record_id;(out/'animations'/ (leaf+'.json')).write_text(json.dumps({'manifest':entry,'animation':anim,'pba':extras.get('pba')},indent=2)+'\n')
    for name,s in variants.items():
        m=s['domain']['meshes'][0];lods=sorted({f['lod'] for f in m['fragments'] if f['lod']}) or [1]
        manifest['models'][name]['lod_masks']=lods;manifest['models'][name]['clips']=len(clips[name])
        manifest['models'][name]['morph_names']=sorted({b['name'] for f in m['fragments'] for b in f['blendshapes']})
        for lod in lods:
            dest=out/'models'/('%s_LOD%d.glb'%(name,lod))
            Exporter(s,textures,dest,lod,clips[name]).write()
    texture_manifest=[]
    refs={normalize(t['name']) for s in variants.values() for t in s['texture_references']}
    for key in sorted(refs):
        if key not in textures:
            texture_manifest.append({'name':key,'status':'missing archive texture'});continue
        t=textures[key];leaf=key.rsplit('/',1)[-1];raw=t['record_data']
        (out/'textures'/(leaf+'.psytexture')).write_bytes(raw)
        rec={k:v for k,v in t.items() if k not in ['data','record_data']};rec['record_sha256']=digest(raw)
        try:
            faces=texture_surfaces(t);directory=out/'textures'/leaf;directory.mkdir(exist_ok=True)
            for face in faces:
                for level in face:
                    pixels(dict(t,type=0,width=level['width'],height=level['height'],data=level['data'])).save(directory/('face%d_mip%d.png'%(level['face'],level['mip'])))
            rec['faces']=len(faces);rec['decoded_mip_surfaces']=sum(len(f) for f in faces)
            if t['type']==0:pixels(t).save(out/'textures'/(leaf+'.png'))
            if t['format'] in [9,10,11]:
                code={9:b'DXT1',10:b'DXT3',11:b'DXT5'}[t['format']]
                header=struct.pack('<7I11I8I5I',124,0xa1007,t['height'],t['width'],len(faces[0][0]['data']),0,t['mips'],*([0]*11),
                    32,4,struct.unpack('<I',code)[0],0,0,0,0,0,0x401008,0xfe00 if t['type']==1 else 0,0,0,0)
                (out/'textures'/(leaf+'.dds')).write_bytes(b'DDS '+header+b''.join(l['data'] for f in faces for l in f))
            rec['status']='all original mip/face surfaces, PNGs, compressed DDS when supported, and complete original record'
        except ValueError as err:rec['status']='original texture record only: '+str(err)
        texture_manifest.append(rec)
    manifest['textures']=texture_manifest
    prop=next(v for v in source['models'] if normalize(v['name'])=='characters/characterprops/boydchalk.plb');s=scene(prop['data']);s['source']={'archive':'ASGR.ppf','model':prop['name'],'sha256':digest(prop['data'])}
    Exporter(s,textures,out/'props/BoydChalk.glb').write()
    (out/'metadata/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('VERIFIED',len(manifest['clips']),'clips',[(k,len(v)) for k,v in clips.items()],'UNSUPPORTED',manifest['unsupported'])


if __name__=='__main__':main()
