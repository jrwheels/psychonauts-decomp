#!/usr/bin/env python3
"""Private, content-addressed inventory of owned PC archives; never bulk-exports.

Record occurrences, byte-identical payloads and normalized named families are
separate counts. Derived skeleton/collision/material identities use canonical
metadata, explicitly distinct from original serialized payload hashes.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
from psyassets import read_archive,scene,normalize,metadata
from psyanim import apf,jan
from psymorph import pba,events,texture_surfaces

ROOT=Path(__file__).resolve().parents[1]


def digest(raw):return hashlib.sha256(raw).hexdigest()


def canonical(value):
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items() if k!='offset' and not k.startswith('runtime_')}
    if isinstance(value,list):return [canonical(v) for v in value]
    return value


def derived(value):return json.dumps(canonical(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def encoded_texture(t):
    # Archive-local headers vary independently of image data. Preserve their
    # original record hashes in occurrences; identity here is encoded imagery.
    return derived({k:t[k] for k in ['format','type','frames','width','height','mips']})+t['record_data'][t['data_offset']:]


def mesh_walk(domain):
    def walk(m):
        yield m
        for c in m['children']:yield from walk(c)
    for m in domain['meshes']:yield from walk(m)
    for c in domain['children']:yield from mesh_walk(c)


def material_view(fragment,refs):
    fields=['flags','blend','color','textures','lightmap','detail','gloss','reflection','velocity',
            'specular_parameters','material_vector','detail_factor']
    value={k:fragment.get(k) for k in fields}
    def ref(i):return None if i is None or i==0xffffffff else normalize(refs[i]['name'])
    value['textures']=[ref(i) for i in fragment['textures']]
    for k in ['lightmap','detail','gloss','reflection']:
        if isinstance(value[k],int) or value[k] is None:value[k]=ref(value[k])
    return value


def failure_group(message):
    if message.startswith('key order:'):return 'non-increasing key times'
    if message.startswith('truncated at '):return 'truncated/unknown record layout'
    if message.startswith('unparsed JAN tail'):return 'unparsed JAN tail'
    return message.split(':',1)[0]


def add_animation_chunk(manifest,raw,occurrence):
    """APF-embedded chunks share payload identities with matching PKG records."""
    kind,parser=('facial_animations',pba) if raw[:4]==b'ABPE' else ('animation_events',events) if raw[:4]==b'EVEP' else ('other_resources',None)
    key=kind+':'+digest(raw)
    if key in manifest.assets:
        manifest.assets[key]['occurrences'].append(occurrence);return
    status,details,error='not_attempted',{},None
    if len(raw)>=8:details['format_version']=struct.unpack_from('<I',raw,4)[0]
    if parser:
        try:
            value=parser(raw);status='parsed'
            if kind=='facial_animations':details.update(channels=len(value['channels']),missing_declared_channels=value['missing_declared_channels'])
        except (ValueError,IndexError,struct.error) as e:status,error='unsupported',str(e)[:220]
    manifest.add(kind,raw,occurrence,status,details,error)


class Manifest:
    def __init__(self):self.assets={};self.archives=[];self.archive_failures=[]
    def add(self,kind,raw,occurrence,status='not_attempted',details=None,error=None,identity='payload_sha256'):
        sha=digest(raw);key=kind+':'+sha
        if key not in self.assets:
            self.assets[key]=dict(id=key,category=kind,sha256=sha,identity=identity,bytes=len(raw),
                parse_status=status,details=details or {},failure=error,occurrences=[],exports=[],validations=[])
        a=self.assets[key]
        # One occurrence is one actual archive record or derived owner attachment.
        a['occurrences'].append(occurrence)
        return a
    def summary(self):
        groups=defaultdict(list)
        for a in self.assets.values():groups[a['category']].append(a)
        result={}
        for kind,assets in sorted(groups.items()):
            names={normalize(o['name']) for a in assets for o in a['occurrences'] if o.get('name')}
            result[kind]=dict(records=sum(len(a['occurrences']) for a in assets),unique_assets=len(assets),
                named_families=None if kind in ['materials','skeletons','collision_meshes','environment_scenes'] else len(names),parsed=sum(a['parse_status']=='parsed' for a in assets),
                parse_failed=sum(a['parse_status']=='unsupported' for a in assets),
                parse_not_attempted=sum(a['parse_status']=='not_attempted' for a in assets),
                exported=sum(bool(a['exports']) for a in assets),validated=sum(bool(a['validations']) for a in assets),
                failures=dict(Counter(a['failure'] for a in assets if a['failure'])),
                failure_groups=dict(Counter(failure_group(a['failure']) for a in assets if a['failure'])))
        return result
    def result(self):
        return dict(schema_version=1,identity_policy='SHA256 of complete original record; derived identities explicitly marked; LOD exports do not create new source assets; PPF texture identity uses encoded surfaces and known dimensions/format, retaining each original record hash',
            texture_scope='PPF locale-0/shared texture records plus PKG DDS; other localized PPF payloads skipped by existing reader',
            parse_scope='Current decoder completion, not original-engine fidelity. Parsed CYSP tails remain opaque. Texture parse requires complete mip/face coverage when supported.',
            dds_scope='Pillow base-image decode only; full DDS mip/face coverage unverified',
            pkg_names='Upstream reader paths unverified; numeric ID, offset and payload hash authoritative',
            archives=self.archives,archive_failures=self.archive_failures,summary=self.summary(),assets=list(self.assets.values()))


def scene_details(s):
    ms=list(mesh_walk(s['domain']))
    return dict(version=s['version'],meshes=len(ms),vertices=sum(f['vertices'] for m in ms for f in m['fragments']),
        skeletons=sum(len(m['skeletons']) for m in ms),joints=sum(sk['joint_count'] for m in ms for sk in m['skeletons']),
        collision_meshes=sum(bool(m['collision'] and m['collision']['record_words']) for m in ms),
        trailing_bytes=s['trailing_bytes'],lod_masks=sorted({f['lod'] for m in ms for f in m['fragments']}))


def add_scene(manifest,raw,occurrence,environment=False):
    sha=digest(raw)
    # Classifications can be reused across duplicate occurrences without parsing.
    existing=next((manifest.assets[k] for k in ['static_models:'+sha,'skeletal_models:'+sha,'unparsed_models:'+sha,'environment_scenes:'+sha] if k in manifest.assets),None)
    if existing:
        # Derived attachment record counts must still include repeated owners.
        existing['occurrences'].append(occurrence)
        for attachment in existing.get('derived_attachments',[]):
            fields={k:v for k,v in attachment.items() if k!='id'}
            manifest.assets[attachment['id']]['occurrences'].append(dict(occurrence,**fields))
        return
    try:s=scene(raw);details=scene_details(s)
    except (ValueError,IndexError,struct.error,RecursionError) as e:
        manifest.add('environment_scenes' if environment else 'unparsed_models',raw,occurrence,'unsupported',error=str(e)[:220]);return
    kind='environment_scenes' if environment else 'skeletal_models' if details['skeletons'] else 'static_models'
    asset=manifest.add(kind,raw,occurrence,'parsed',details)
    asset['derived_attachments']=[]
    def attach(kind,raw,occ,status,details,identity):
        child=manifest.add(kind,raw,occ,status,details,identity=identity)
        asset['derived_attachments'].append(dict(id=child['id'],**{k:occ[k] for k in ['parent','mesh_index','subindex','name'] if k in occ}))
    for mi,m in enumerate(mesh_walk(s['domain'])):
        for si,sk in enumerate(m['skeletons']):
            attach('skeletons',derived(sk),dict(occurrence,parent=asset['id'],mesh_index=mi,subindex=si,name=sk['name']),
                         'parsed',dict(joints=sk['joint_count']),identity='canonical_metadata_sha256')
        c=m['collision']
        if c and c['record_words']:
            attach('collision_meshes',derived(c),dict(occurrence,parent=asset['id'],mesh_index=mi,name=m['name']),
                         'parsed',dict(vertices=len(c['vertices']),triangles=len(c['record_words'])),identity='canonical_metadata_sha256')
        for fi,f in enumerate(m['fragments']):
            mat=material_view(f,s['texture_references'])
            attach('materials',derived(mat),dict(occurrence,parent=asset['id'],mesh_index=mi,subindex=fi),
                         'parsed',dict(source_parameters=mat,shader_reproduction='incomplete'),identity='canonical_metadata_sha256')


def scan(game):
    manifest=Manifest()
    packs=game/'WorkResource/PCLevelPackFiles'
    for path in sorted(packs.glob('*.ppf')):
        manifest.archives.append(dict(path=str(path.relative_to(game)),sha256=digest(path.read_bytes()),kind='PPF'))
        try:a=read_archive(path)
        except (ValueError,IndexError,struct.error) as e:manifest.archive_failures.append(dict(archive=path.name,error=str(e)));continue
        for i,t in enumerate(a['textures']):
            occ=dict(archive=path.name,record=i,name=t['name'],record_sha256=digest(t['record_data']))
            encoded=encoded_texture(t)
            key='textures:'+digest(encoded)
            if key in manifest.assets:manifest.assets[key]['occurrences'].append(occ);continue
            try:texture_surfaces(t);status,error='parsed',None
            except ValueError as e:status,error='unsupported',str(e)
            manifest.add('textures',encoded,occ,status,dict(format=t['format'],type=t['type'],frames=t['frames'],
                width=t['width'],height=t['height'],mips=t['mips'],base_png_candidate=t['type']==0 and t['format'] in [0,1,9,10,11]),error,identity='encoded_texture_surfaces_sha256')
        for i,m in enumerate(a['models']):
            add_scene(manifest,m['data'],dict(archive=path.name,record=i,name=m['name'],offset=m['offset'],size=m['size'],type=m['type']))
        if a['scene_data']:add_scene(manifest,a['scene_data'],dict(archive=path.name,name='main scene',offset=a['scene_offset'],size=len(a['scene_data'])),True)
        print('Indexed',path.name,flush=True)
    for path in sorted(packs.glob('*.apf')):
        raw=path.read_bytes();manifest.archives.append(dict(path=str(path.relative_to(game)),sha256=digest(raw),kind='APF'))
        try:stubs=apf(raw)
        except (ValueError,IndexError,struct.error) as e:manifest.archive_failures.append(dict(archive=path.name,error=str(e)));continue
        for i,stub in enumerate(stubs):
            manifest.add('animation_references',derived(stub),dict(archive=path.name,record=i,name=stub['name']),'parsed',
                dict(pkg_offset=stub['pkg_offset'],pkg_size=stub['pkg_size'],joints=stub['header']['joints'],root_motion=stub['position_channel'] is not None),identity='canonical_metadata_sha256')
            for ci,chunk in enumerate(stub['chunks']):
                data=raw[chunk['offset']:chunk['offset']+chunk['size']]
                if len(data)!=chunk['size']:raise ValueError('truncated APF chunk')
                add_animation_chunk(manifest,data,dict(archive=path.name,record=i,chunk=ci,
                    name=stub['name'],offset=chunk['offset'],size=chunk['size']))
    spec=importlib.util.spec_from_file_location('psypkg',ROOT/'third_party/psypkg.py');pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
    for path in sorted(game.glob('*.pkg')):
        manifest.archives.append(dict(path=path.name,sha256=digest(path.read_bytes()),kind='PKG'))
        with path.open('rb') as stream:
            records=list(pkg.read_index(stream))
            for i,(name,offset,size) in enumerate(records):
                stream.seek(offset);raw=stream.read(size)
                if len(raw)!=size:raise ValueError('truncated indexed PKG record')
                occ=dict(archive=path.name,record=i,name=name,offset=offset,size=size,reported_name_unverified=True)
                if raw[:4]==b'CYSP':add_scene(manifest,raw,occ);continue
                kind,parser=('skeletal_animations',jan) if raw[:4] in [b'XAJP',b'NAJP'] else ('facial_animations',pba) if raw[:4]==b'ABPE' else ('animation_events',events) if raw[:4]==b'EVEP' else ('textures_dds',None) if raw[:4]==b'DDS ' else ('other_resources',None)
                key=kind+':'+digest(raw)
                if key in manifest.assets:manifest.assets[key]['occurrences'].append(occ);continue
                status,details,error='not_attempted',dict(reported_extension=Path(name).suffix.lower()),None
                try:
                    if parser:
                        v=parser(raw);status='parsed'
                        if kind=='skeletal_animations':details.update(joints=v['header']['joints'],frames=v['header'].get('frames'),version=v['header']['version'])
                        elif kind=='facial_animations':details.update(channels=len(v['channels']),missing_declared_channels=v['missing_declared_channels'])
                    elif kind=='textures_dds':
                        from PIL import Image
                        import io
                        with Image.open(io.BytesIO(raw)) as image:image.load();details.update(width=image.width,height=image.height)
                        status='parsed'
                except (ValueError,IndexError,struct.error,RecursionError,OSError) as e:status,error='unsupported',str(e)[:220]
                manifest.add(kind,raw,occ,status,details,error)
        print('Indexed',path.name,flush=True)
    return manifest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('game',type=Path);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'.local/assets') or args.output.exists():ap.error('output must be new and private')
    args.output.parent.mkdir(parents=True,exist_ok=True);result=scan(args.game).result()
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
