#!/usr/bin/env python3
"""Bounded readers for PC animation record layouts, verified on owned files.

Research references describe numerical layouts only; no GPL implementation is
incorporated. Keep decoded original data under ignored .local/assets/.
"""
import math
from psyassets import Reader, Unsupported


def compressed_quaternion(raw):
    """48-bit smallest-three: selector, three sign/magnitude pairs, omitted sign."""
    a=int.from_bytes(raw[:4],'little');b=int.from_bytes(raw[4:],'little')
    selector=a>>29
    if selector>3:raise ValueError('compressed quaternion selector')
    vals=[((a>>14)&16383)/8192, (a&8191)/8192, ((b>>1)&8191)/8192]
    signs=[(a>>28)&1,(a>>13)&1,(b>>14)&1]
    vals=[-v if sign else v for v,sign in zip(vals,signs)]
    remainder=1-sum(v*v for v in vals)
    if remainder<-.0005:raise ValueError('compressed quaternion length')
    q=vals[:];q.insert(selector,(-1 if b&1 else 1)*math.sqrt(max(0,remainder)))
    return q


def header(r):
    magic=r.take(4)
    if magic not in [b'XAJP',b'NAJP']:raise ValueError('animation magic')
    version=r.u32()
    if version==200:
        r.take(28);joints,a,b,c=r.unpack('4I');counts=list(r.unpack('3I'))
        constants=list(r.unpack('3i'));flags=r.u32()
        return dict(version=version,flags=flags,joints=joints,values=[a,b,c],counts=counts,constant_counts=constants)
    if version!=201:raise Unsupported('animation version %d'%version)
    flags,length=r.unpack('HH');translate,joints,a,b,c,pad=r.unpack('6B')
    return dict(version=version,flags=flags,frames=length,translate_mode=translate,joints=joints,
                values=[a,b,c,pad])


def channel(r, uint_time=False, has_time=True):
    kind,count=r.unpack('HH')
    if kind>3:raise Unsupported('animation channel %d'%kind)
    keys=[]
    for _ in range(count or 1):
        frame=(r.u32() if uint_time else r.u16()) if count and has_time else 0
        value=compressed_quaternion(r.take(6)) if kind==3 else r.vec(4 if kind==1 else 3)
        if not all(math.isfinite(v) for v in value):raise ValueError('nonfinite key')
        keys.append(dict(frame=frame,value=value))
    if any(a['frame']>=b['frame'] for a,b in zip(keys,keys[1:])):raise ValueError('key order: '+repr([(a,b) for a,b in zip(keys,keys[1:]) if a['frame']>=b['frame']][:1]))
    return dict(type=kind,constant=not count,keys=keys)


def animation_joint(r, depth=0, uint_time=False, has_time=True):
    if depth>128:raise ValueError('animation depth')
    name=r.string();channels=[channel(r,uint_time,has_time) for _ in range(r.u16())]
    children=[animation_joint(r,depth+1,uint_time,has_time) for _ in range(r.u16())]
    return dict(name=name,channels=channels,children=children)


def jan(raw):
    r=Reader(raw);h=header(r);root=animation_joint(r,uint_time=h['version']==200)
    def merge(a,b):
        if a['name']!=b['name'] or len(a['children'])!=len(b['children']):raise ValueError('constant hierarchy differs')
        existing={c['type'] for c in a['channels']}
        for c in b['channels']:
            if c['type'] in existing:raise ValueError('duplicate constant channel')
            a['channels'].append(c)
        for ca,cb in zip(a['children'],b['children']):merge(ca,cb)
    if h['version']==200 and r.pos<len(raw) and sum(h['constant_counts']):
        merge(root,animation_joint(r,has_time=False))
    if r.pos!=len(raw):raise Unsupported('unparsed JAN tail %d'%(len(raw)-r.pos))
    def flatten(j):return [j]+[v for c in j['children'] for v in flatten(c)]
    joints=flatten(root)
    if len(joints)!=h['joints']:raise ValueError('JAN joint count')
    return dict(header=h,root=root)


def apf(raw):
    r=Reader(raw);r.magic(b'KAPA');records=[]
    for _ in range(r.u32()):
        start=r.pos;r.magic(b'BTSA');name=r.string(2);offset,size=r.unpack('II');root=r.string(2);h=header(r)
        pos=channel(r) if (h['flags']|h['translate_mode'])&3 in [1,2] else None
        chunks=[]
        tag=r.u32()
        while tag!=0x656e645f:
            if tag not in [0x65766e74,0x626c6e64]:raise ValueError('APF chunk tag %x'%tag)
            size_chunk=r.u32();at=r.pos;r.take(size_chunk);chunks.append(dict(tag=tag,offset=at,size=size_chunk));tag=r.u32()
        records.append(dict(offset=start,name=name,pkg_offset=offset,pkg_size=size,root=root,header=h,position_channel=pos,chunks=chunks))
    if r.pos!=len(raw):raise ValueError('APF tail')
    return records
