#!/usr/bin/env python3
"""Decode original scene navigation and visibility tails without placing actors."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from psyassets import Reader,read_archive,scene,metadata
from psyexport import Exporter


def tail(raw, start):
    r=Reader(raw);r.pos=start;nav=[]
    for ni in range(r.u32()):
        at=r.pos;count=r.u32();m={'id':ni,'offset':at,'polygons':[]}
        for _ in range(count):
            flags,ref,*indices=r.unpack('II6i')
            m['polygons'].append(dict(flags=flags,collision_triangle=ref&0xffffff,
                collision_selector=ref>>24,neighbors=indices[:3],vertices=indices[3:]))
        if count:
            m['vertices']=[r.vec(3) for _ in range(r.u32())];n=r.u32()
            m['extra_vectors_1']=[r.vec(3) for _ in range(n)];m['extra_vectors_2']=[r.vec(3) for _ in range(n)]
            tables=r.u32();size=r.u32() if tables else 0;m['tables']=[]
            for _ in range(tables):m['tables'].append(dict(index=r.u32(),data=r.take(size)))
            m['links']=[]
            for _ in range(r.u32()):
                flags,index=r.unpack('Ii');m['links'].append(dict(flags=flags,polygon=index,name=r.string()))
            pos=np.array(m['vertices']);idx=np.array([p['vertices'] for p in m['polygons']]);neighbors=np.array([p['neighbors'] for p in m['polygons']])
            if not np.isfinite(pos).all() or idx.min()<-1 or idx.max()>=len(pos):raise ValueError('nav vector-reference bounds')
            if neighbors.min()<-1 or neighbors.max()>=count:raise ValueError('nav adjacency range')
        nav.append(m)
    visibility=None
    if struct.unpack_from('<I',raw,8)[0]&1:
        at=r.pos;unknown=r.u32();cube=r.vec(4);leaves,nodes=r.unpack('II')
        records=r.take(nodes*24);stored=r.u32();leafdata=r.take(stored*4)
        if stored not in [0,leaves]:raise ValueError('visibility leaf count')
        primitives=r.take(r.u32()*4);words=(leaves+31)//32;flags=r.take(leaves*words*4)
        visibility=dict(offset=at,unknown=unknown,cube=cube,leaves=leaves,nodes=nodes,
            node_records=records,stored_leaves=stored,leaf_records=leafdata,primitives=primitives,
            visibility_words_per_leaf=words,visibility_bits=flags)
    return dict(navigation=nav,visibility=visibility,tail_offset=start,tail_bytes=len(raw)-start,unparsed_bytes=len(raw)-r.pos,
                remainder_offset=r.pos,remainder_sha256=hashlib.sha256(raw[r.pos:]).hexdigest())


def export_navigation(data, scene_data, output):
    e=Exporter({}, {}, output);counts=[]
    collisions=[]
    def visit_mesh(m):
        if m['collision']:collisions.append((m['name'],m['collision']))
        for c in m['children']:visit_mesh(c)
    def visit_domain(d):
        for m in d['meshes']:visit_mesh(m)
        for c in d['children']:visit_domain(c)
    visit_domain(scene_data['domain'])
    for m in data['navigation']:
        if not m['polygons']:continue
        # Nav vector indices address direction vectors, not XYZ mesh positions.
        # Export geometry only when collision references have unique reciprocal links.
        points=[];linked=[]
        for pi,p in enumerate(m['polygons']):
            candidates=[];ci=p['collision_triangle']
            for name,c in collisions:
                if ci<len(c['record_words']):
                    words=c['record_words'][ci]
                    if words[4]>>8==pi and words[4]&255==m['id']:
                        vi=[words[1]&65535,words[1]>>16,words[2]&65535]
                        if max(vi)>=len(c['vertices']):raise ValueError('collision triangle indices')
                        candidates.append((name,[c['vertices'][v] for v in vi]))
            if len(candidates)!=1:raise ValueError('ambiguous/absent reciprocal navigation collision reference')
            name,tri=candidates[0];points.extend(tri);linked.append({'nav_polygon':pi,'collision_mesh':name,'collision_triangle':ci})
        pos=np.array(points,dtype='<f4');idx=np.arange(len(pos),dtype='<u4').reshape(-1,3)
        m['verified_collision_links']=linked
        i=e.node('Navigation_%d'%m['id'],None,{'original_nav_id':m['id'],'source_offset':m['offset']})
        e.g['materials'].append({'name':'Navigation','doubleSided':True,'extensions':{'KHR_materials_unlit':{}},
             'pbrMetallicRoughness':{'baseColorFactor':[.6,.9,.2,1],'metallicFactor':0,'roughnessFactor':1}})
        e.g['meshes'].append({'name':'Navigation_%d'%m['id'],'primitives':[{'attributes':{'POSITION':e.accessor(pos,'VEC3',5126,True)},
            'indices':e.accessor(idx.ravel(),'SCALAR',5125),'material':len(e.g['materials'])-1,'mode':4}]})
        e.g['nodes'][i]['mesh']=len(e.g['meshes'])-1;counts.append(dict(id=m['id'],vertices=len(pos),triangles=len(idx)))
    if not counts:return counts
    e.g['buffers']=[{'byteLength':len(e.binary)}];e.g={k:v for k,v in e.g.items() if not isinstance(v,list) or v}
    js=json.dumps(e.g,separators=(',',':')).encode();js+=b' '*((-len(js))%4);blob=bytes(e.binary);blob+=b'\0'*((-len(blob))%4)
    output.write_bytes(struct.pack('<III',0x46546c67,2,28+len(js)+len(blob))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(blob),0x004e4942)+blob)
    return counts


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('archive',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in args.output.resolve().parents:ap.error('navigation exports belong under .local/assets/')
    raw=read_archive(args.archive)['scene_data'];s=scene(raw);data=tail(raw,s['parsed_bytes'])
    data['source']=dict(archive=args.archive.name,scene_sha256=hashlib.sha256(raw).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True);data['exported_meshes']=export_navigation(data,s,args.output)
    args.output.with_suffix('.json').write_text(json.dumps(metadata(data),indent=2)+'\n')
    print('nav',data['exported_meshes'],'visibility',None if data['visibility'] is None else (data['visibility']['leaves'],data['visibility']['nodes']),'unparsed',data['unparsed_bytes'])


if __name__=='__main__':main()
