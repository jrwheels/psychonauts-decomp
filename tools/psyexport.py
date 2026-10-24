#!/usr/bin/env python3
"""Export decoded static Psychonauts scenes to self-contained glTF 2.0 GLB.

Uses the MIT-attributed psyassets decoder; does not modify original resources.
Geometry uses noclip's identity placement policy; serialized TRS is preserved
in node extras pending validation of the game's baked/dynamic transform rules.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from psyassets import read_archive, scene, metadata, normalize
from psyrig import flatten, bind_quaternion, bind_globals, vertex_skin, compatible_hierarchy
from psymorph import morph_delta


def pixels(t):
    w,h,fmt=t['width'],t['height'],t['format']
    if t['type']!=0:raise ValueError('non-2D texture '+t['name'])
    if fmt in [9,10,11]:
        fourcc={9:b'DXT1',10:b'DXT3',11:b'DXT5'}[fmt]
        header=struct.pack('<7I11I8I5I',124,0x81007,h,w,len(t['data']),0,1,*([0]*11),32,4,
                           struct.unpack('<I',fourcc)[0],0,0,0,0,0,0x1000,0,0,0,0)
        return Image.open(io.BytesIO(b'DDS '+header+t['data'])).convert('RGBA')
    if fmt in [0,1]:
        a=np.frombuffer(t['data'],np.uint8).reshape(h,w,4)[:,:,[2,1,0,3]].copy()
        if fmt==1:a[:,:,3]=255
        return Image.fromarray(a)
    raise ValueError('unsupported texture pixel format %d' % fmt)


def triangles(f):
    idx=np.frombuffer(f['indices'],dtype='<u2').astype(np.uint32)
    if f['flags']&0x1000000:
        if len(idx)<3:return np.empty((0,3),dtype='<u4')
        tris=np.stack([idx[:-2],idx[1:-1],idx[2:]],axis=1)
        tris[1::2]=tris[1::2][:,[1,0,2]]
    else:tris=idx.reshape(-1,3)
    keep=(tris[:,0]!=tris[:,1])&(tris[:,1]!=tris[:,2])&(tris[:,0]!=tris[:,2])
    # Original PC visual streams use clockwise front faces (noclip render.ts).
    # glTF uses counterclockwise front faces. Keep positions/normals unchanged.
    return np.ascontiguousarray(tris[keep][:,[0,2,1]],dtype='<u4')


def normals(raw):
    p=np.frombuffer(raw,dtype='<u4').reshape(-1,4)[:,3]
    values=[]
    for shift,width,denom in [(0,11,1023),(11,11,1023),(22,10,511)]:
        v=((p>>shift)&((1<<width)-1)).astype(np.int32)
        v=np.where(v&(1<<(width-1)),v-(1<<width),v)
        values.append(v/denom)
    a=np.stack(values,axis=1).astype('<f4');length=np.linalg.norm(a,axis=1)
    valid=length>1e-8;a[valid]/=length[valid,None]
    return a,int((~valid).sum())


class Exporter:
    def __init__(self, data, textures, output, lod_mask=None, animation=None):
        self.data,self.textures,self.output=data,textures,output
        self.lod_mask,self.animation=lod_mask,animation
        self.rig_reports=[]
        self.binary=bytearray();self.image_cache={};self.stats={'meshes':0,'fragments':0,'vertices':0,'triangles':0,
            'script_placements':0,'mesh_script_links_verified':0,
            'missing_textures':[],'zero_normals':0,'nonidentity_serialized_transforms':0,'collision_meshes':0}
        self.g={'asset':{'version':'2.0','generator':'psychonauts-decomp static asset exporter'},'scene':0,
                'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'materials':[],'bufferViews':[],
                'accessors':[],'images':[],'textures':[],'samplers':[{'wrapS':10497,'wrapT':10497}],
                'extensionsUsed':['KHR_materials_unlit']}

    def view(self, raw, target=None):
        while len(self.binary)%4:self.binary.append(0)
        v={'buffer':0,'byteOffset':len(self.binary),'byteLength':len(raw)}
        if target:v['target']=target
        self.binary.extend(raw);self.g['bufferViews'].append(v);return len(self.g['bufferViews'])-1

    def accessor(self, a, kind, component, bounds=False, normalized=False):
        a=np.ascontiguousarray(a);v={'bufferView':self.view(a.tobytes(),34963 if kind=='SCALAR' else 34962),
                                  'componentType':component,'count':len(a),'type':kind}
        if kind=='MAT4':self.g['bufferViews'][v['bufferView']].pop('target',None)
        if normalized:v['normalized']=True
        if bounds:v.update(min=np.atleast_1d(a.min(axis=0)).tolist(),max=np.atleast_1d(a.max(axis=0)).tolist())
        self.g['accessors'].append(v);return len(self.g['accessors'])-1

    def texture(self, ident):
        if ident==0xffffffff:return None
        if not 0<=ident<len(self.data['texture_references']):raise ValueError('texture id out of range')
        original=self.data['texture_references'][ident]['name'];name=normalize(original)
        if name in self.image_cache:return self.image_cache[name]
        if name not in self.textures:
            self.stats['missing_textures'].append(original);return None
        t=self.textures[name];im=pixels(t);stream=io.BytesIO();im.save(stream,format='PNG')
        png_dir=self.output.parent/(self.output.stem+'-textures');png_dir.mkdir(exist_ok=True)
        leaf=name.rsplit('/',1)[-1].replace(':','_')
        png_path=png_dir/(leaf+'-'+hashlib.sha256(name.encode()).hexdigest()[:8]+'.png')
        png_path.write_bytes(stream.getvalue())
        index=len(self.g['textures']);self.g['images'].append({'name':original,'bufferView':self.view(stream.getvalue()),'mimeType':'image/png',
            'extras':{'original_name':t['name'],'normalized_name':name,'png_file':str(png_path.relative_to(self.output.parent)),
                      'first_frame_only':t['frames']>1}})
        self.g['textures'].append({'source':len(self.g['images'])-1,'sampler':0,'name':original});self.image_cache[name]=index
        return index

    def node(self, name, parent, extras):
        i=len(self.g['nodes']);self.g['nodes'].append({'name':name,'extras':extras})
        if parent is None:self.g['scenes'][0]['nodes'].append(i)
        else:self.g['nodes'][parent].setdefault('children',[]).append(i)
        return i

    def mesh(self, m, parent):
        self.stats['meshes']+=1
        if m['translation']!=[0,0,0] or m['rotation']!=[0,0,0] or m['scale']!=[1,1,1]:
            self.stats['nonidentity_serialized_transforms']+=1
        i=self.node(m['name'],parent,{k:metadata(m[k]) for k in ['translation','rotation','scale','bounds','entity_flags','triggers','lights','collision','lod_thresholds']})
        if m['collision']:self.stats['collision_meshes']+=1
        rig=None
        if m.get('skeletons'):
            joints=[j for sk in m['skeletons'] for j in flatten(sk['root'])]
            ids=[j['id'] for j in joints]
            if len(set(ids))!=len(ids):raise ValueError('duplicate mesh joint IDs')
            globals_=bind_globals(joints);nodes={}
            for j in joints:
                # Joints and skinned mesh are siblings: mesh remains identity.
                node=self.node(j['name'],parent if j['parent'] is None else nodes[j['parent']],
                    {'original_joint_id':j['id'],'source_offset':j['offset'],'bind_euler_degrees':j['rotation'],
                     'runtime_index':j['runtime_index'],'runtime_index_u8':j['runtime_index_u8'],
                     'runtime_parent_index':j['runtime_parent_index'],
                     'runtime_next_sibling_index':j['runtime_next_sibling_index'],
                     'rotation_identity_sentinel':j['rotation']==[-1,-1,-1]})
                self.g['nodes'][node].update(translation=j['position'],rotation=bind_quaternion(j['rotation']).tolist())
                nodes[j['id']]=node
            inverse=np.array([np.linalg.inv(globals_[v]).T.reshape(16) for v in ids],dtype='<f4')
            ibm=self.accessor(inverse,'MAT4',5126)
            self.g.setdefault('skins',[]).append({'name':m['name']+'/skin','joints':[nodes[v] for v in ids],'inverseBindMatrices':ibm})
            self.g['nodes'][i]['skin']=len(self.g['skins'])-1
            rig=(ids,globals_,nodes,joints)
            if parent is not None:
                self.g['nodes'][parent]['children'].remove(i)
                self.g['scenes'][0]['nodes'].append(i)
                self.g['nodes'][i]['extras']['original_parent_node']=parent
            self.rig_reports.append({'mesh':m['name'],'joints':len(ids),'skinned_vertices':0,'max_bind_error':0.})
        morph_names=sorted({b['name'] for f in m['fragments'] for b in f.get('blendshapes',[])})
        primitives=[]
        for f in m['fragments']:
            self.stats['fragments']+=1
            if self.lod_mask is not None and f['lod'] and not f['lod']&self.lod_mask:continue
            if not f['vertices']:continue
            pos=np.frombuffer(f['posnrm'],dtype='<f4').reshape(-1,4)[:,:3].copy()
            if not np.isfinite(pos).all():raise ValueError('nonfinite vertex')
            lo,hi=np.array(f['bounds'][:3]),np.array(f['bounds'][3:])
            if np.any(pos.min(axis=0)<lo-.05) or np.any(pos.max(axis=0)>hi+.05):raise ValueError('vertices outside fragment bounds')
            tri=triangles(f)
            if f['flags']&0x1000000 and len(tri)!=f['polygons']-f['degenerates']:
                raise ValueError('triangle-strip degenerates disagree with source count')
            if tri.size and tri.max()>=len(pos):raise ValueError('index out of range')
            if not tri.size:continue
            attrs={'POSITION':self.accessor(pos,'VEC3',5126,True)}
            if f.get('skin'):
                if rig is None:raise ValueError('skin without skeleton')
                ids,globals_,nodes,joints=rig
                joint_indices,weights=vertex_skin(f['skin'],ids)
                attrs['JOINTS_0']=self.accessor(joint_indices,'VEC4',5123)
                attrs['WEIGHTS_0']=self.accessor(weights,'VEC4',5126)
                h=np.c_[pos,np.ones(len(pos))];restored=np.zeros_like(h)
                for k in range(2):
                    for jid in np.unique(joint_indices[:,k]):
                        mask=joint_indices[:,k]==jid;g=globals_[ids[jid]]
                        inv=np.linalg.inv(g).astype('<f4').astype(float)
                        restored[mask]+=(h[mask]@(g@inv).T)*weights[mask,k,None]
                err=float(np.abs(restored[:,:3]-pos).max())
                if err>.002:raise ValueError('bind roundtrip error')
                self.rig_reports[-1]['max_bind_error']=max(self.rig_reports[-1]['max_bind_error'],err)
                self.rig_reports[-1]['skinned_vertices']+=len(pos)
            n,zero=normals(f['posnrm']);self.stats['zero_normals']+=zero
            if not zero:attrs['NORMAL']=self.accessor(n,'VEC3',5126)
            if f['colors']:
                colors=np.frombuffer(f['colors'],np.uint8).reshape(-1,4)[:,[2,1,0,3]].copy()
                attrs['COLOR_0']=self.accessor(colors,'VEC4',5121,normalized=True)
            if f['uv_count']:
                uv=np.frombuffer(f['uv'],dtype='<i2').reshape(-1,f['uv_count'],2).astype('<f4')/32767*f['uv_scale']
                for j in range(f['uv_count']):attrs['TEXCOORD_%d'%j]=self.accessor(uv[:,j,:],'VEC2',5126)
            mat={'name':m['name']+'/fragment'+str(len(primitives)),
                 'pbrMetallicRoughness':{'baseColorFactor':f['color'],'metallicFactor':0,'roughnessFactor':1},
                 'doubleSided':bool(f['flags']&16),'extensions':{'KHR_materials_unlit':{}},
                 'extras':{k:f[k] for k in ['flags','lod','blend','textures','lightmap','detail','gloss','reflection','velocity']}}
            if f['flags']&0x400:mat.update(alphaMode='MASK',alphaCutoff=.5)
            elif f['flags']&1:mat['alphaMode']='BLEND'
            if f['textures']:
                tex=self.texture(f['textures'][0])
                if tex is not None:mat['pbrMetallicRoughness']['baseColorTexture']={'index':tex}
            lm=self.texture(f['lightmap']) if f['lightmap'] is not None else None
            if lm is not None:mat['extras']['lightmap_texture']=lm
            self.g['materials'].append(mat)
            primitive={'attributes':attrs,'indices':self.accessor(tri.ravel(),'SCALAR',5125),
                               'material':len(self.g['materials'])-1,'mode':4}
            if morph_names:
                streams={b['name']:b for b in f.get('blendshapes',[])};targets=[]
                for name in morph_names:
                    delta,nd=morph_delta(streams[name],len(pos)) if name in streams else (np.zeros_like(pos),np.zeros_like(pos))
                    target={'POSITION':self.accessor(delta,'VEC3',5126,True)}
                    if 'NORMAL' in attrs:target['NORMAL']=self.accessor(nd,'VEC3',5126)
                    targets.append(target)
                primitive['targets']=targets
            primitives.append(primitive)
            self.stats['vertices']+=len(pos);self.stats['triangles']+=len(tri)
        if primitives:
            gm={'name':m['name'],'primitives':primitives}
            if morph_names:gm.update(weights=[0]*len(morph_names),extras={'targetNames':morph_names})
            self.g['meshes'].append(gm);self.g['nodes'][i]['mesh']=len(self.g['meshes'])-1
        for clip in (([self.animation] if isinstance(self.animation,dict) else self.animation) or []) if rig else []:
            from psyanim import jan
            anim=clip['data'];ajs=flatten(anim['root']);sj=rig[3]
            target_root=next((j for j in sj if j['id']==clip.get('target_root_id',sj[0]['id'])),None)
            if target_root is None or not compatible_hierarchy(target_root,anim['root']):
                raise ValueError('animation names/hierarchy do not match target rig')
            tracks=[];samplers=[]
            for a,j in zip(ajs,flatten(target_root)):
                for ch in a['channels']:
                    kind=ch['type'];path={0:'translation',1:'rotation',2:'scale',3:'rotation'}[kind]
                    times=np.array([k['frame']/30 for k in ch['keys']],dtype='<f4')
                    values=np.array([k['value'] for k in ch['keys']],dtype='<f4')
                    if path=='rotation':
                        if np.max(np.abs(np.linalg.norm(values,axis=1)-1))>.001:raise ValueError('animation quaternion norm')
                        values/=np.linalg.norm(values,axis=1)[:,None]
                        for n in range(1,len(values)):
                            if np.dot(values[n-1],values[n])<0:values[n]*=-1
                    inp=self.accessor(times,'SCALAR',5126,True)
                    self.g['bufferViews'][self.g['accessors'][inp]['bufferView']].pop('target',None)
                    out=self.accessor(values,'VEC4' if path=='rotation' else 'VEC3',5126)
                    self.g['bufferViews'][self.g['accessors'][out]['bufferView']].pop('target',None)
                    samplers.append({'input':inp,'output':out,'interpolation':'LINEAR'})
                    tracks.append({'sampler':len(samplers)-1,'target':{'node':rig[2][j['id']],'path':path}})
            if clip.get('pba') and morph_names:
                channels=clip['pba']['channels']
                unknown=[c['name'] for c in channels if c['name'] not in morph_names]
                if unknown:raise ValueError('PBA has unmapped targets '+repr(unknown))
                frames=max((len(c['weights']) for c in channels),default=0)
                if frames:
                    values=np.zeros((frames,len(morph_names)),dtype='<f4')
                    for c in channels:
                        w=np.array(c['weights'],dtype='<f4')/255
                        values[:len(w),morph_names.index(c['name'])]=w
                        values[len(w):,morph_names.index(c['name'])]=w[-1] if len(w) else 0
                    inp=self.accessor(np.arange(frames,dtype='<f4')/30,'SCALAR',5126,True)
                    out=self.accessor(values.ravel(),'SCALAR',5126)
                    for acc in [inp,out]:self.g['bufferViews'][self.g['accessors'][acc]['bufferView']].pop('target',None)
                    samplers.append({'input':inp,'output':out,'interpolation':'LINEAR'})
                    tracks.append({'sampler':len(samplers)-1,'target':{'node':i,'path':'weights'}})
            self.g.setdefault('animations',[]).append({'name':clip['name'],'channels':tracks,'samplers':samplers,
                'extras':clip['source']})
        for child in m['children']:self.mesh(child,i)
        return i

    def domain(self, d, parent=None):
        i=self.node(d['name'],parent,{k:metadata(d[k]) for k in ['bounds','scripts','entity_data','runtime_references']})
        mesh_nodes=[self.mesh(m,i) for m in d['meshes']]
        links=[]
        for script_index,s in enumerate(d['scripts']):
            self.stats['script_placements']+=1
            idx=s['initial_mesh']
            if 0<=idx<len(d['meshes']):
                m=d['meshes'][idx]
                if s['name']==m['name'] and np.allclose(s['position'],m['translation'],atol=.001,rtol=0):
                    links.append({'script_index':script_index,'mesh_node':mesh_nodes[idx],
                                  'evidence':'serialized index, exact name and matching translation'})
                    self.stats['mesh_script_links_verified']+=1
        self.g['nodes'][i]['extras']['verified_mesh_script_links']=links
        for c in d['children']:self.domain(c,i)

    def write(self):
        self.domain(self.data['domain'])
        if not self.stats['triangles']:raise ValueError('no supported triangle geometry; refusing empty export')
        self.g['buffers']=[{'byteLength':len(self.binary)}]
        # Optional glTF arrays have minItems=1. Textureless props legitimately
        # have no images/textures; omit those properties rather than emitting [].
        self.g={k:v for k,v in self.g.items() if not isinstance(v,list) or v}
        js=json.dumps(self.g,separators=(',',':'),allow_nan=False).encode();js+=b' '*((-len(js))%4)
        blob=bytes(self.binary);blob+=b'\0'*((-len(blob))%4)
        self.output.write_bytes(struct.pack('<III',0x46546c67,2,12+8+len(js)+8+len(blob))+
                                struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(blob),0x004e4942)+blob)
        self.stats.update(rigs=self.rig_reports,lod_mask=self.lod_mask,animations=len(self.g.get('animations',[])),images=len(self.g.get('images',[])),nodes=len(self.g['nodes']),scene_trailing_bytes=self.data['trailing_bytes'],
                          placement_policy='identity, compatible with noclip; source TRS retained as extras',
                          limitations=['dynamic/script object instantiation unresolved','lightmaps retained but not combined',
                                       'collision exported separately; physics behavior not reconstructed','navigation/visibility tail undecoded'])
        self.output.with_suffix('.validation.json').write_text(json.dumps(self.stats,indent=2)+'\n')
        self.output.with_suffix('.metadata.json').write_text(json.dumps(metadata(self.data),indent=2)+'\n')
        print(self.output,self.stats)


def export_collision(data, output):
    """Independent collision scene; never merge collision into visual meshes.

    20-byte records: surface DWORD, three u16 vertex indices, u16 padding,
    float plane factor, byte nav selector, three-byte nav polygon index.
    Record layout cross-checked against PsychoPortal's format definitions.
    """
    e=Exporter(data,{},output);summary=[]
    def visit(d, parent=None):
        node=e.node(d['name'],parent,{})
        def visit_mesh(m, parent):
            owner=e.node(m['name'],parent,{})
            c=m['collision']
            if c and c['record_words']:
                pos=np.asarray(c['vertices'],dtype='<f4');records=np.asarray(c['record_words'],dtype='<u4')
                tri=np.stack([records[:,1]&65535,records[:,1]>>16,records[:,2]&65535],axis=1).astype('<u4')
                if tri.max()>=len(pos):raise ValueError('collision index out of range')
                if not np.isfinite(pos).all():raise ValueError('nonfinite collision vertex')
                bounds=np.asarray(c['bounds'])
                if np.any(pos.min(0)<bounds[:3]-.05) or np.any(pos.max(0)>bounds[3:]+.05):
                    raise ValueError('collision vertices outside source bounds')
                e.g['materials'].append({'name':'Collision','doubleSided':True,'extensions':{'KHR_materials_unlit':{}},
                     'pbrMetallicRoughness':{'baseColorFactor':[.15,.65,.85,1],'metallicFactor':0,'roughnessFactor':1}})
                primitive={'attributes':{'POSITION':e.accessor(pos,'VEC3',5126,True)},
                           'indices':e.accessor(tri.ravel(),'SCALAR',5125),'material':len(e.g['materials'])-1,'mode':4}
                e.g['meshes'].append({'name':m['name']+'/collision','primitives':[primitive]})
                e.g['nodes'][owner]['mesh']=len(e.g['meshes'])-1
                summary.append({'name':m['name'],'vertices':len(pos),'triangles':len(tri),
                                'source_offset':c['offset'],'surface_flags':records[:,0].tolist(),
                                'nav_selectors':(records[:,4]&255).tolist(),'nav_polygon_ids':(records[:,4]>>8).tolist()})
            for child in m['children']:visit_mesh(child,owner)
        for m in d['meshes']:visit_mesh(m,node)
        for child in d['children']:visit(child,node)
    visit(data['domain'])
    if not summary:return
    e.g['buffers']=[{'byteLength':len(e.binary)}]
    # Optional glTF arrays must be omitted when empty (schema minItems=1).
    e.g={k:v for k,v in e.g.items() if not isinstance(v,list) or v}
    js=json.dumps(e.g,separators=(',',':')).encode();js+=b' '*((-len(js))%4)
    b=bytes(e.binary);b+=b'\0'*((-len(b))%4)
    output.write_bytes(struct.pack('<III',0x46546c67,2,28+len(js)+len(b))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(b),0x004e4942)+b)
    output.with_suffix('.json').write_text(json.dumps({'kind':'collision only','meshes':summary},indent=2)+'\n')
    print('collision',output,'triangles',sum(v['triangles'] for v in summary))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('archive',type=Path)
    ap.add_argument('--lod-mask',type=int);ap.add_argument('--animation');ap.add_argument('--anim-pack',type=Path);ap.add_argument('--pkg',type=Path);ap.add_argument('--common',type=Path);ap.add_argument('--model');ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in args.output.resolve().parents:ap.error('proprietary exports must remain under .local/assets/')
    a=read_archive(args.archive);textures={}
    if args.common:textures.update({t['key']:t for t in read_archive(args.common,False)['textures']})
    textures.update({t['key']:t for t in a['textures']})
    raw=a['scene_data']
    if args.model:
        matches=[m for m in a['models'] if normalize(m['name'])==normalize(args.model)]
        if len(matches)!=1:ap.error('model name must identify exactly one MPAK entry')
        raw=matches[0]['data']
    s=scene(raw);s['source']={'archive':args.archive.name,'archive_sha256':hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                            'model':args.model,'scene_sha256':hashlib.sha256(raw).hexdigest()}
    animation=None
    if args.animation:
        from psyanim import apf,jan
        if not args.anim_pack or not args.pkg:ap.error('animation requires --anim-pack and --pkg')
        stubs=apf(args.anim_pack.read_bytes());matches=[v for v in stubs if normalize(v['name'])==normalize(args.animation)]
        if len(matches)!=1:ap.error('animation must identify exactly one APF record')
        stub=matches[0]
        with args.pkg.open('rb') as f:
            f.seek(stub['pkg_offset']);raw=f.read(stub['pkg_size'])
        parsed=jan(raw)
        if parsed['header']['joints']!=stub['header']['joints']:raise ValueError('APF/JAN joint-count disagreement')
        if stub['position_channel'] is not None:raise ValueError('root motion channel not yet exported')
        animation={'name':stub['name'],'data':parsed,'source':{'apf':args.anim_pack.name,'pkg_offset':stub['pkg_offset'],
                   'pkg_size':stub['pkg_size'],'jan_sha256':hashlib.sha256(raw).hexdigest(),'frame_rate':30,'events_and_blends_exported':False}}
    args.output.parent.mkdir(parents=True,exist_ok=True);Exporter(s,textures,args.output,args.lod_mask,animation).write()
    export_collision(s,args.output.with_name(args.output.stem+'-collision.glb'))


if __name__=='__main__':main()
