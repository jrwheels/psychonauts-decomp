#!/usr/bin/env python3
"""Rig math and independently checked palette conversion for original PC data."""
import numpy as np


def flatten(j):
    return [j]+[v for c in j['children'] for v in flatten(c)]


def qmul(a,b):
    return np.r_[a[3]*b[:3]+b[3]*a[:3]+np.cross(a[:3],b[:3]),a[3]*b[3]-np.dot(a[:3],b[:3])]


def bind_quaternion(degrees):
    # RuntimeBone::ReadInput (Steam 0x492010) bypasses Euler conversion only
    # when all three serialized values equal -1; partial sentinels are Euler.
    if list(degrees)==[-1,-1,-1]:
        return np.array([0.,0.,0.,1.])
    # Z Y X product supported by 63 invariant Boyd animation channels.
    q=np.array([0.,0.,0.,1.])
    for axis in [2,1,0]:
        angle=np.deg2rad(degrees[axis])/2
        a=np.zeros(4);a[axis]=np.sin(angle);a[3]=np.cos(angle);q=qmul(q,a)
    return q


def matrix(position, q, scale=(1,1,1)):
    x,y,z,w=np.asarray(q)/np.linalg.norm(q)
    m=np.eye(4);m[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]) @ np.diag(scale)
    m[:3,3]=position;return m


def bind_globals(joints):
    mats={}
    for j in joints:
        local=matrix(j['position'],bind_quaternion(j['rotation']))
        mats[j['id']]=local if j['parent'] is None else mats[j['parent']] @ local
    return mats


def vertex_skin(skin, ids):
    if len(set(ids))!=len(ids):raise ValueError('ambiguous serialized palette labels')
    records=np.frombuffer(skin['weights'],dtype=np.dtype([('p','<u4'),('w','<f4',(2,))]))
    p=records['p'];w=records['w'].copy()
    if np.any(p>>24) or np.any(p&255):raise ValueError('unsupported third/fourth influence')
    palette=np.stack([(p>>16)&255,(p>>8)&255],axis=1)
    if palette.max()>=skin['bones']:raise ValueError('vertex palette index')
    if not np.isfinite(w).all() or np.any(w<0) or np.any(w>1) or not np.allclose(w.sum(1),1,atol=2e-6):
        raise ValueError('invalid source skin weights')
    if skin['influences']==1 and np.any(w[:,1]!=0):raise ValueError('single influence has second weight')
    lookup={ident:i for i,ident in enumerate(ids)}
    if any(v not in lookup for v in skin['joint_ids']):raise ValueError('skin palette absent from skeleton')
    remap=np.array([lookup[v] for v in skin['joint_ids']],dtype='<u2')
    outj=np.zeros((len(p),4),dtype='<u2');outw=np.zeros((len(p),4),dtype='<f4')
    outj[:,:2]=remap[palette];outw[:,:2]=w
    outj[outw==0]=0
    return outj,outw


def joint_name(name):
    return name.rsplit('|',1)[-1]


def compatible_hierarchy(a,b):
    aa,bb=flatten(a),flatten(b)
    return len(aa)==len(bb) and len({joint_name(j['name']) for j in aa})==len(aa) and all(
        joint_name(x['name'])==joint_name(y['name']) and
        [joint_name(c['name']) for c in x['children']]==[joint_name(c['name']) for c in y['children']]
        for x,y in zip(aa,bb))
