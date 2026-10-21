"""Original PC morph records and PBA weights, with explicit missing-data status."""
import numpy as np
from psyassets import Reader,Unsupported


def packed_vectors(words):
    words=np.asarray(words,dtype='<u4');out=[]
    for shift,bits,denom in [(0,11,1023),(11,11,1023),(22,10,511)]:
        x=((words>>shift)&((1<<bits)-1)).astype(np.int32)
        x=np.where(x&(1<<(bits-1)),x-(1<<bits),x);out.append(x/denom)
    return np.stack(out,axis=-1).astype('<f4')


def morph_delta(b, count):
    if b['sparse']:
        a=np.frombuffer(b['data'],dtype=np.dtype([('i','<u2'),('p','<u4'),('n','<u4')]))
        indices=a['i'].astype(int)
    else:
        a=np.frombuffer(b['data'],dtype=np.dtype([('p','<u4'),('n','<u4')]))
        indices=np.arange(count)
    if len(a)!=b['count'] or (len(indices) and indices.max()>=count) or len(set(indices))!=len(indices):
        raise ValueError('morph indices/count')
    pos=np.zeros((count,3),dtype='<f4');normal=np.zeros_like(pos)
    pos[indices]=packed_vectors(a['p'])*b['scale'];normal[indices]=packed_vectors(a['n'])
    if not np.isfinite(pos).all():raise ValueError('morph delta nonfinite')
    return pos,normal


def pba(raw):
    r=Reader(raw);r.magic(b'ABPE');version=r.u32()
    if version!=100:raise Unsupported('PBA version')
    declared=r.u32() if r.pos<len(raw) else 0;channels=[]
    while r.pos<len(raw) and len(channels)<declared:
        name=r.take(r.u8()).split(b'\0')[0].decode('latin1');values=r.take(r.u32())
        channels.append(dict(name=name,weights=list(values)))
    if r.pos!=len(raw):raise Unsupported('PBA trailing bytes')
    if len({c['name'] for c in channels})!=len(channels):raise ValueError('duplicate PBA name')
    return dict(version=version,declared_channels=declared,channels=channels,missing_declared_channels=declared-len(channels))


def events(raw):
    r=Reader(raw);r.magic(b'EVEP');version=r.u32();objects=r.u32()
    if version not in [100,101] or objects!=1:raise Unsupported('event header')
    tables=[r.string(2).split(' ' if version==100 else '\t') for _ in range(r.u32())];channels=[]
    for i in range(r.u32()):
        keys=[dict(frame=r.u32(),unknown=r.f32()) for _ in range(r.u32())]
        if i<len(tables) and len(tables[i])==len(keys)+1 and tables[i][-1]=='':tables[i]=tables[i][:-1]
        if keys and (i>=len(tables) or len(tables[i])!=len(keys)):raise ValueError('event name/key count')
        for k,name in zip(keys,tables[i]):k['name']=name
        channels.append(dict(index=i,keys=keys))
    if r.pos!=len(raw):raise ValueError('event tail')
    return dict(version=version,channels=channels)


def texture_surfaces(t):
    """Bounded complete mip/face extraction, requiring exact source-record coverage."""
    if t['frames']!=1 or t['type'] not in [0,1]:raise Unsupported('multi-frame/volume texture')
    raw=t['record_data'];at=t['data_offset'];faces=[]
    for face in range(6 if t['type']==1 else 1):
        w,h=t['width'],t['height'];levels=[]
        for mip in range(t['mips']):
            fmt=t['format']
            size=((w+3)//4)*((h+3)//4)*(8 if fmt==9 else 16) if fmt in [9,10,11] else w*h*4 if fmt in [0,1] else -1
            if size<0 or at+size>len(raw):raise ValueError('unsupported/truncated texture surface')
            levels.append(dict(face=face,mip=mip,width=w,height=h,data=raw[at:at+size]));at+=size;w=max(w//2,1);h=max(h//2,1)
        faces.append(levels)
    if at!=len(raw):raise ValueError('texture surfaces do not cover original record')
    return faces
