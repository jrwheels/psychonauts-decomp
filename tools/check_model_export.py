#!/usr/bin/env python3
"""Compare GLB geometry, hierarchy and palette weights with an original MPAK record.

Read-only inputs; writes a private JSON report. Scalar decoding below deliberately
does not reuse exporter triangle, normal or skin conversion helpers.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from psyassets import read_archive,scene,normalize
from glb_skin import read


def meshes(domain):
    def walk(mesh):
        yield mesh
        for child in mesh['children']:yield from walk(child)
    for mesh in domain['meshes']:yield from walk(mesh)
    for child in domain['children']:yield from meshes(child)


def joints(root):
    yield root
    for child in root['children']:yield from joints(child)


def check(archive,model,glb,lod_mask):
    a=read_archive(archive,model is None)
    if model is None:raw=a['scene_data']
    else:
        records=[m for m in a['models'] if normalize(m['name'])==normalize(model)]
        if len(records)!=1:raise ValueError('model must identify exactly one source record')
        raw=records[0]['data']
    source=scene(raw);g,access=read(glb)
    # Scene mesh names are not unique. Both source and export retain traversal
    # order; compare every entry and fail on missing/extra geometry.
    rows=[];checked=0
    for mesh in meshes(source['domain']):
        fs=[f for f in mesh['fragments'] if f['vertices'] and
            (lod_mask is None or not f['lod'] or f['lod']&lod_mask)]
        if not fs:continue
        gm=g['meshes'][checked];mesh_index=checked;checked+=1
        assert gm['name']==mesh['name']
        assert len(fs)==len(gm['primitives'])
        source_joints=[j for sk in mesh['skeletons'] for j in joints(sk['root'])]
        ids=[j['id'] for j in source_joints]
        node=next(n for n in g['nodes'] if n.get('mesh')==mesh_index)
        if source_joints:
            skin=g['skins'][node['skin']];node_ids=skin['joints']
            assert len(node_ids)==len(ids)
            parents={c:i for i,n in enumerate(g['nodes']) for c in n.get('children',[])}
            for ordinal,(j,ni) in enumerate(zip(source_joints,node_ids)):
                # Re-read raw serialized fields using retained source offset.
                label=struct.unpack_from('<H',raw,j['offset'])[0]
                length=struct.unpack_from('<I',raw,j['offset']+2)[0]
                posrot=struct.unpack_from('<6f',raw,j['offset']+6+length)
                n=g['nodes'][ni]
                assert label==j['id']==n['extras']['original_joint_id']
                np.testing.assert_array_equal(n['translation'],posrot[:3])
                if j['parent'] is not None:
                    assert parents[ni]==node_ids[ids.index(j['parent'])]
                if list(posrot[3:])==[-1,-1,-1]:
                    np.testing.assert_array_equal(n['rotation'],[0,0,0,1])
        for f,p in zip(fs,gm['primitives']):
            material=g['materials'][p['material']]
            np.testing.assert_array_equal(material['pbrMetallicRoughness']['baseColorFactor'],f['color'])
            assert material['doubleSided']==bool(f['flags']&16)
            assert material.get('alphaMode','OPAQUE')==('MASK' if f['flags']&0x400 else 'BLEND' if f['flags']&1 else 'OPAQUE')
            if f['textures']:
                ref=source['texture_references'][f['textures'][0]]['name']
                tex=material['pbrMetallicRoughness']['baseColorTexture']['index']
                image=g['images'][g['textures'][tex]['source']]
                assert normalize(image['extras']['original_name'])==normalize(ref)
            vertices=[struct.unpack_from('<3fI',f['posnrm'],i*16) for i in range(f['vertices'])]
            positions=np.array([v[:3] for v in vertices],dtype='<f4')
            np.testing.assert_array_equal(access(p['attributes']['POSITION']),positions)
            normal=[]
            for v in vertices:
                xyz=[]
                for shift,bits,denom in ((0,11,1023),(11,11,1023),(22,10,511)):
                    value=(v[3]>>shift)&((1<<bits)-1)
                    if value&(1<<(bits-1)):value-=1<<bits
                    xyz.append(value/denom)
                normal.append(xyz)
            normal=np.array(normal);length=np.linalg.norm(normal,axis=1)
            if (length>1e-8).all():
                np.testing.assert_allclose(access(p['attributes']['NORMAL']),normal/length[:,None],atol=2e-7)
            source_indices=struct.unpack('<'+'H'*(len(f['indices'])//2),f['indices'])
            expected=[]
            if f['flags']&0x1000000:
                for i in range(len(source_indices)-2):
                    x,y,z=source_indices[i:i+3]
                    if i&1:x,y=y,x
                    if len({x,y,z})==3:expected.append((x,z,y))
            else:
                for i in range(0,len(source_indices),3):
                    x,y,z=source_indices[i:i+3]
                    if len({x,y,z})==3:expected.append((x,z,y))
            tri=access(p['indices']).reshape(-1,3)
            np.testing.assert_array_equal(tri,expected)
            if f['uv_count']:
                uv=np.frombuffer(f['uv'],dtype='<i2').reshape(-1,f['uv_count'],2)/32767*f['uv_scale']
                for i in range(f['uv_count']):
                    np.testing.assert_allclose(access(p['attributes']['TEXCOORD_%d'%i]),uv[:,i,:],atol=2e-6)
            if f.get('skin'):
                js=access(p['attributes']['JOINTS_0']);ws=access(p['attributes']['WEIGHTS_0'])
                sk=f['skin']
                for i in range(f['vertices']):
                    packed,w0,w1=struct.unpack_from('<I2f',sk['weights'],12*i)
                    for channel,(shift,weight) in enumerate(((16,w0),(8,w1))):
                        label=sk['joint_ids'][(packed>>shift)&255]
                        assert float(ws[i,channel])==weight
                        if weight:assert ids[int(js[i,channel])]==label
                    assert not js[i,2:].any() and not ws[i,2:].any()
            face=np.cross(positions[tri[:,1]]-positions[tri[:,0]],positions[tri[:,2]]-positions[tri[:,0]])
            dot=np.einsum('ij,ij->i',face,normal[tri].mean(axis=1))
            rows.append(dict(vertices=f['vertices'],triangles=len(tri),
                             normal_agreements=int((dot>1e-6).sum()),normal_oppositions=int((dot< -1e-6).sum())))
    assert rows and checked==len(g['meshes']),'empty or unverified exported geometry'
    return dict(model=model,archive_sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
                record_sha256=hashlib.sha256(raw).hexdigest(),glb_sha256=hashlib.sha256(Path(glb).read_bytes()).hexdigest(),
                source_version=source['version'],checks=rows,status='passed',
                limitations=['palette labels validated against source; nonidentity label-to-runtime mapping not established',
                             'generic non-sentinel Euler math not independently checked here',
                             'no original-game rendering or shader equivalence'])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('archive',type=Path);ap.add_argument('glb',type=Path)
    ap.add_argument('--model',help='MPAK model identifier; omitted for the main scene')
    ap.add_argument('--lod-mask',type=int);ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args();root=Path(__file__).resolve().parents[1]
    if not any(args.report.resolve().is_relative_to(root/d) for d in ('.local','build')):
        ap.error('report must remain private')
    result=check(args.archive,args.model,args.glb,args.lod_mask)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(args.model,'passed',sum(r['vertices'] for r in result['checks']),'vertices')


if __name__=='__main__':main()
