#!/usr/bin/env python3
"""Source Euler bind matrices vs exported node/IBM matrices, without rig helpers.

Uses direct trigonometric Rz*Ry*Rx matrices and original serialized fields. This
checks the documented source convention and export consistency, not execution
of the original engine. It does not infer a new palette-label/runtime mapping.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import numpy as np
from check_model_export import meshes,joints
from psyassets import read_archive,scene,normalize
from glb_skin import read


def source_matrix(position,angles):
    result=np.eye(4);result[:3,3]=position
    if list(angles)==[-1,-1,-1]:return result
    x,y,z=map(math.radians,angles);cx,cy,cz=map(math.cos,(x,y,z));sx,sy,sz=map(math.sin,(x,y,z))
    rx=np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rz=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    result[:3,:3]=rz@ry@rx;return result


def node_matrix(node):
    if 'matrix' in node:raise ValueError('expected exported joint TRS, not a matrix override')
    x,y,z,w=node.get('rotation',[0,0,0,1]);norm=x*x+y*y+z*z+w*w
    if not math.isfinite(norm) or abs(norm-1)>1e-5:raise ValueError('invalid bind quaternion')
    result=np.eye(4);result[:3,3]=node.get('translation',[0,0,0])
    result[:3,:3]=np.array([[1-2*(y*y+z*z)/norm,2*(x*y-z*w)/norm,2*(x*z+y*w)/norm],
        [2*(x*y+z*w)/norm,1-2*(x*x+z*z)/norm,2*(y*z-x*w)/norm],
        [2*(x*z-y*w)/norm,2*(y*z+x*w)/norm,1-2*(x*x+y*y)/norm]])@np.diag(node.get('scale',[1,1,1]))
    return result


def compare(raw,source_joints,skin,g,access):
    ids=[j['id'] for j in source_joints];nodes=skin['joints']
    if len(set(ids))!=len(ids) or len(ids)!=len(nodes):raise ValueError('ambiguous source/skin correspondence')
    inverse=access(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
    if len(inverse)!=len(ids):raise ValueError('inverse bind count differs')
    worlds={};max_local=max_inverse=0.;sentinels=0
    for ordinal,(j,ni) in enumerate(zip(source_joints,nodes)):
        at=j['offset'];label,length=struct.unpack_from('<HI',raw,at);values=struct.unpack_from('<6f',raw,at+6+length)
        if label!=g['nodes'][ni]['extras']['original_joint_id']:raise ValueError('joint label differs')
        local=source_matrix(values[:3],values[3:]);actual=node_matrix(g['nodes'][ni])
        np.testing.assert_allclose(actual,local,rtol=0,atol=2e-7)
        max_local=max(max_local,float(np.max(np.abs(actual-local))));sentinels+=list(values[3:])==[-1,-1,-1]
        worlds[label]=local if j['parent'] is None else worlds[j['parent']]@local
        expected=np.linalg.inv(worlds[label])
        np.testing.assert_allclose(inverse[ordinal],expected,rtol=2e-6,atol=3e-5)
        max_inverse=max(max_inverse,float(np.max(np.abs(inverse[ordinal]-expected))))
    return dict(joints=len(nodes),identity_rotation_sentinels=sentinels,max_local_matrix_error=max_local,max_inverse_bind_error=max_inverse)


def check(archive,model,glb):
    a=read_archive(archive,False);records=[m for m in a['models'] if normalize(m['name'])==normalize(model)]
    if len(records)!=1:raise ValueError('model must identify one source record')
    raw=records[0]['data'];source=scene(raw);g,access=read(Path(glb));rows=[]
    for mesh in meshes(source['domain']):
        js=[j for sk in mesh['skeletons'] for j in joints(sk['root'])]
        if not js:continue
        matches=[n for n in g['nodes'] if 'skin' in n and n.get('name')==mesh['name']]
        if len(matches)!=1:raise ValueError('source mesh/skin correspondence ambiguous')
        rows.append(compare(raw,js,g['skins'][matches[0]['skin']],g,access))
    if not rows:raise ValueError('no source bind poses checked')
    sha=lambda b:hashlib.sha256(b).hexdigest()
    return dict(status='passed',checks=rows,model=model,record_sha256=sha(raw),glb_sha256=sha(Path(glb).read_bytes()),
                archive_sha256=sha(Path(archive).read_bytes()),
                scope='raw serialized bind translation/Euler fields and direct matrix/IBM comparison',
                limitations=['checks documented RzRyRx convention, not original runtime execution','mesh placement and palette/runtime remapping not established'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('glb',type=Path);p.add_argument('--model',required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    if not a.report.resolve().is_relative_to(Path(__file__).resolve().parents[1]/'.local/assets') or a.report.exists():p.error('report must be new and private')
    result=check(a.archive,a.model,a.glb);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n');print(result['checks'])


if __name__=='__main__':main()
