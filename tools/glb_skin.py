#!/usr/bin/env python3
"""CPU evaluation of exported glTF skins for inspection and differential checks."""
import json
import struct
import numpy as np
from psyrig import matrix


def read(path):
    raw=path.read_bytes();n=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+n]);blob=raw[28+n:]
    def access(i):
        a=g['accessors'][i];v=g['bufferViews'][a['bufferView']]
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
        dtype={5121:'u1',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]
        return np.frombuffer(blob,dtype=dtype,count=width*a['count'],offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,width)
    return g,access


def interpolate(times, values, time, rotation=False):
    if time<=times[0]:return values[0]
    if time>=times[-1]:return values[-1]
    n=np.searchsorted(times,time)-1;t=(time-times[n])/(times[n+1]-times[n]);a,b=values[n],values[n+1]
    if rotation:
        dot=np.dot(a,b)
        if dot<0:b=-b;dot=-dot
        if dot<.9995:
            angle=np.arccos(np.clip(dot,-1,1));return (np.sin((1-t)*angle)*a+np.sin(t*angle)*b)/np.sin(angle)
        value=a*(1-t)+b*t;return value/np.linalg.norm(value)
    return a*(1-t)+b*t


def pose(g, access, seconds=None, animation_index=0):
    trs=[dict(translation=n.get('translation',[0,0,0]),rotation=n.get('rotation',[0,0,0,1]),scale=n.get('scale',[1,1,1])) for n in g['nodes']]
    if seconds is not None and g.get('animations'):
        a=g['animations'][animation_index]
        for c in a['channels']:
            s=a['samplers'][c['sampler']];target=c['target'];path=target['path']
            values=access(s['output'])
            if path=='weights':values=values.reshape(len(access(s['input'])),len(g['meshes'][g['nodes'][target['node']]['mesh']]['weights']))
            trs[target['node']][path]=interpolate(access(s['input']).ravel(),values,seconds,path=='rotation')
    parents={child:i for i,n in enumerate(g['nodes']) for child in n.get('children',[])};world={}
    def visit(i):
        if i not in world:
            t=trs[i]
            if 'matrix' in g['nodes'][i]:
                if seconds is not None and g.get('animations') and any(c['target']['node']==i and c['target']['path']!='weights' for c in g['animations'][animation_index]['channels']):
                    raise ValueError('TRS animation cannot target a matrix node')
                local=np.asarray(g['nodes'][i]['matrix'],dtype=float).reshape(4,4).T
            else:local=matrix(t['translation'],t['rotation'],t['scale'])
            world[i]=visit(parents[i])@local if i in parents else local
        return world[i]
    for i in range(len(trs)):visit(i)
    result={}
    for ni,n in enumerate(g['nodes']):
        if 'mesh' not in n:continue
        for pi,p in enumerate(g['meshes'][n['mesh']]['primitives']):
            attr=p['attributes'];pos=access(attr['POSITION']).copy()
            weights=trs[ni].get('weights',g['meshes'][n['mesh']].get('weights',[]))
            for target,w in zip(p.get('targets',[]),weights):pos+=access(target['POSITION'])*w
            h=np.c_[pos,np.ones(len(pos))]
            if 'skin' in n:
                skin=g['skins'][n['skin']];inverse=access(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
                transforms=np.array([world[j]@ib for j,ib in zip(skin['joints'],inverse)])
                joints=access(attr['JOINTS_0']);weights=access(attr['WEIGHTS_0']);out=np.zeros_like(h)
                for k in range(4):out+=np.einsum('nij,nj->ni',transforms[joints[:,k]],h)*weights[:,k,None]
            else:out=h@world[ni].T
            result[(n['mesh'],pi)]=out[:,:3]
    return result
