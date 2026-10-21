#!/usr/bin/env python3
"""Read-only Steam PPAK/CYSP extraction. Scene decoder adapted from noclip.

Copyright (c) 2018 Jasper St. Pierre; adaptations (c) 2026 Codex contributors.
MIT; see third_party/noclip-LICENSE.txt. Unsupported data fails closed.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


class Unsupported(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError("truncated at 0x%x reading %d" % (self.pos, n))
        b = self.data[self.pos:self.pos+n]
        self.pos += n
        return b

    def unpack(self, fmt):
        return struct.unpack('<'+fmt, self.take(struct.calcsize('<'+fmt)))

    def u32(self): return self.unpack('I')[0]
    def u16(self): return self.unpack('H')[0]
    def u8(self): return self.unpack('B')[0]
    def f32(self): return self.unpack('f')[0]
    def vec(self, n): return list(self.unpack('f'*n))
    def string(self, width=4):
        n = self.u32() if width == 4 else self.u16()
        return self.take(n).split(b'\0')[0].decode('latin1')
    def magic(self, expected):
        got = self.take(len(expected))
        if got != expected:
            raise ValueError('expected %r, got %r at 0x%x' % (expected, got, self.pos-len(expected)))


def normalize(name):
    s = name.lower().replace('\\', '/')
    for prefix in ['c:/psychonauts/resource/', 'workresource/']:
        if s.startswith(prefix): s = s[len(prefix):]
    for suffix in ['.dds', '.tga']:
        if s.endswith(suffix): s = s[:-4]
    return s


def texture(data):
    r = Reader(data); r.pos = 0x28
    name = r.string(2) if struct.unpack_from('<I', data, 12)[0] else ''
    frames = 1
    if struct.unpack_from('<I', data, 16)[0]:
        frames = r.u32(); r.take(24)
    ident, fmt, kind, flags, w, h, mips = r.unpack('7I'); r.take(16)
    if not mips:
        mips = min(w.bit_length(), h.bit_length())
    bpp = {0:4,1:4,2:2,3:2,4:2,5:2,6:1,7:1,8:1,12:2,13:4,14:1}
    if fmt in [9,10,11]: size = ((w+3)//4)*((h+3)//4)*(8 if fmt==9 else 16)
    elif fmt in bpp: size = w*h*bpp[fmt]
    else: raise Unsupported('texture format %d' % fmt)
    data_offset=r.pos
    return {'name':name, 'key':normalize(name), 'format':fmt, 'type':kind, 'data_offset':data_offset,
            'width':w, 'height':h, 'frames':frames, 'mips':mips, 'data':r.take(size), 'record_data':data}


def read_archive(path, scene=True):
    r = Reader(Path(path).read_bytes()); r.magic(b'PPAK')
    marker = r.u16(); version = 0
    if marker == 0xfdfd: version = r.u16(); marker = r.u16()
    if version != 1: raise Unsupported('PPAK texture version %d' % version)
    textures = []
    def textures_read(count):
        for _ in range(count):
            r.magic(b' XT1'); size=r.u32(); textures.append(texture(r.take(size)))
    while marker == 0xffff:
        language,size=r.unpack('HI'); end=r.pos+size
        if language == 0: textures_read(r.u16())
        else: r.take(size)
        if r.pos != end: raise ValueError('localized texture block length mismatch')
        marker=r.u16()
    textures_read(marker); r.magic(b'MPAK'); models=[]
    for _ in range(r.u16()):
        name=r.string(2); kind=r.u16(); size=r.u32(); offset=r.pos
        models.append({'name':name,'type':kind,'offset':offset,'size':size,'data':r.take(size)})
    # Two script groups, not geometry.
    count=r.u16(); names=0
    if count==0xfcfc: names=r.u16(); count=r.u16()
    for _ in range(count): r.string(2); r.take(r.u32())
    for _ in range(r.u16()):
        if names: r.string(2)
        r.take(r.u32())
    return {'textures':textures,'models':models,'scene_offset':r.pos,
            'scene_data':r.data[r.pos:] if scene else None,'bytes':len(r.data)}


def trigger(r):
    name=r.string()
    if name=='PLANE': r.vec(3); name=r.string()
    return {'name':name,'vectors':[r.vec(3) for _ in range(4)],'bounds':r.vec(6)}


def light(r):
    kind,flags=r.unpack('II'); name=r.string(); params=[r.vec(3) for _ in range(3)]
    if kind==3: r.vec(3)
    elif kind==4: r.vec(3); r.vec(2)
    elif kind==5: r.string(); r.take(48)
    if flags&0x200:
        n=1 if kind==3 else 6; a=[r.u16() for _ in range(n)]; b=[r.u16() for _ in range(n)]
        if kind==3:r.take(0x58)
        for x,y in zip(a,b):r.take(x*(1 if y<=256 else 2));r.take(y*(16 if kind==3 else 6))
    return {'name':name,'type':kind,'flags':flags,'parameters':params}


def joint(r, version, parent=None, depth=0):
    """Numerical record layout independently checked against MPAK data."""
    if depth>128:raise ValueError('joint hierarchy too deep')
    offset=r.pos; ident=r.u16(); name=r.string(); position=r.vec(3); rotation=r.vec(3)
    if not all(math.isfinite(v) for v in position+rotation):raise ValueError("nonfinite bind transform")
    unknown=r.u16() if version>294 else 0
    children=[joint(r,version,ident,depth+1) for _ in range(r.u32())]
    return dict(offset=offset,id=ident,joint_index=ident&4095,skeleton_index=ident>>12,
                name=name,position=position,rotation=rotation,unknown=unknown,parent=parent,children=children)


def skeleton(r, version):
    start=r.pos;name=r.string();count=r.u32();root=joint(r,version)
    def flatten(j):return [j]+[v for c in j['children'] for v in flatten(c)]
    joints=flatten(root)
    if len(joints)!=count or len({j['id'] for j in joints})!=count:
        raise ValueError('skeleton joint count/IDs disagree')
    return dict(offset=start,name=name,joint_count=count,root=root)


def skin(r, version, n):
    if version<308:raise Unsupported('old skin layout')
    start=r.pos;unknown,bones,influences=r.unpack('HHH')
    if not bones or influences not in [1,2]:raise Unsupported('skin influence count')
    ids=list(r.unpack('H'*bones));max_weights=[list(r.unpack('4f4i')) for _ in range(bones)]
    bounds=[r.vec(6) for _ in range(bones)];weights=r.take(n*12)
    return dict(offset=start,unknown=unknown,bones=bones,influences=influences,joint_ids=ids,
                max_weights=max_weights,bone_bounds=bounds,weights=weights)


def fragment(r, version):
    start=r.pos; bounds=r.vec(6); model_flags=r.u32() if version>317 else 0
    flags,unused=r.unpack('II'); lod,blend=r.unpack('BB'); color=r.vec(4)
    textures=[r.u32() for _ in range(r.u32())]; lm=None; detail=None
    if flags&0x20:
        lm,lm2=r.unpack('II')
        if lm2!=0xffffffff:r.string()
    if flags&8:r.u32()
    gloss=r.u32()
    specular_params=r.vec(4) if flags&0x20000 else None
    reflection=r.u32(); specular=r.vec(3)
    detail_factor=None
    if flags&0x40000000:detail=r.u32();detail_factor=r.vec(2)
    glare=r.f32(); velocity=r.vec(2);r.u32()
    n=r.u32(); posnrm=r.take(n*16); colors=r.take(n*4) if r.u32() else None
    uv_count=r.u32(); uv_scale=r.f32() if uv_count else 0
    uv=r.take(n*4*uv_count) if uv_count else None
    if r.u32():r.take(n*12)
    polys,degens=r.unpack('II'); indices=r.take(2*(polys+2 if flags&0x1000000 else polys*3))
    anim=skin(r,version,n) if flags&4 else None
    blends=[]
    if blend&1 or model_flags&1:
        r.magic(b'SBPS')
        for _ in range(r.u8()):
            name=r.string();count=r.u32() if version>=319 and blend&2 else n
            scale=r.f32();stride=10 if version>=319 and blend&2 else 8
            blends.append(dict(name=name,scale=scale,count=count,sparse=stride==10,data=r.take(count*stride)))
        r.magic(b'SBPE')
    return dict(offset=start,bounds=bounds,flags=flags,model_flags=model_flags,lod=lod,blend=blend,
                color=color,textures=textures,lightmap=lm,detail=detail,gloss=gloss,reflection=reflection,
                vertices=n,polygons=polys,degenerates=degens,posnrm=posnrm,colors=colors,
                uv_count=uv_count,uv_scale=uv_scale,uv=uv,indices=indices,velocity=velocity,skin=anim,blendshapes=blends,
                specular_parameters=specular_params,material_vector=specular,detail_factor=detail_factor)


def collision(r):
    start=r.pos; count=r.u32(); records=[list(r.unpack('5I')) for _ in range(count)]
    vertices=[r.vec(3) for _ in range(r.u32())]
    cube=[];leaves=stored=0
    if count:
        unknown=r.u32(); cube=r.vec(4); leaves,boxes=r.unpack('II');r.take(24*boxes)
        stored=r.u32();r.take(4*leaves);r.take(4*r.u32())
    bounds=r.vec(6)
    return {'offset':start,'record_words':records,'vertices':vertices,'bounds':bounds,
            'cube':cube,'leaves':leaves,'stored':stored,'interpretation':'raw collision records; topology not exported'}


def mesh(r, version):
    result={'name':r.string(),'translation':r.vec(3),'rotation':r.vec(3),'scale':r.vec(3),'bounds':r.vec(6)}
    result['triggers']=[trigger(r) for _ in range(r.u32())]; flags=r.u32();result['entity_flags']=flags
    if flags&1:result['entity_mesh_info']={'script_class':r.string(),'edit_vars':r.string()}
    result['lod_thresholds']=[]
    if flags&2:
        count=r.u8()
        if not count:raise ValueError('zero LOD count')
        result['lod_thresholds']=r.vec(count-1)
    result['lights']=[light(r) for _ in range(r.u32())]
    result['skeletons']=[skeleton(r,version) for _ in range(r.u32())]
    result['fragments']=[fragment(r,version) for _ in range(r.u32())]
    for _ in range(r.u32()):
        kind=r.u32()
        if kind!=0:raise Unsupported('affector type %d' % kind)
        r.take(28)
    result['collision']=collision(r) if r.u32() else None
    result['children']=[mesh(r,version) for _ in range(r.u32())]
    return result


def domain(r, version):
    result={'name':r.string(),'bounds':r.vec(6)};r.magic(b'HSEM')
    result['meshes']=[mesh(r,version) for _ in range(r.u32())];r.magic(b'TADE')
    result['entity_data']=[]
    for _ in range(r.u32()):
        tag,size=r.unpack('II');offset=r.pos;r.take(size);result['entity_data'].append({'tag':tag,'size':size,'offset':offset})
    r.magic(b'PRCS');result['scripts']=[]
    for _ in range(r.u32()):
        v={'name':r.string(),'class':r.string()};v['edit_vars']=r.string() if r.u32() else None
        v.update(position=r.vec(3),rotation=r.vec(3),scale=r.vec(3));v['flags'],v['initial_mesh'],v['initial_data']=r.unpack('III');result['scripts'].append(v)
    r.magic(b'FRTR');result['runtime_references']=[r.string() for _ in range(r.u32())]
    result['children']=[domain(r,version) for _ in range(r.u32())];return result


def scene(data):
    r=Reader(data);r.magic(b'CYSP');version=r.u32();unknown=r.u32()
    if version<317:raise Unsupported('scene version %d' % version)
    refs=[{'name':r.string(),'flags':r.u16()} for _ in range(r.u32())]
    d=domain(r,version)
    return {'version':version,'texture_references':refs,'domain':d,'parsed_bytes':r.pos,'total_bytes':len(data),'trailing_bytes':len(data)-r.pos}


def metadata(value):
    if isinstance(value,bytes):return {'byte_count':len(value),'sha256':hashlib.sha256(value).hexdigest()}
    if isinstance(value,list):return [metadata(v) for v in value]
    if isinstance(value,dict):return {k:metadata(v) for k,v in value.items()}
    return value


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('archive',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in args.output.resolve().parents:ap.error('output must be under project .local/assets/')
    a=read_archive(args.archive);a['scene']=scene(a.pop('scene_data'))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(metadata(a),indent=2)+'\n')
    print('textures',len(a['textures']),'models',len(a['models']),'scene bytes',a['scene']['parsed_bytes'],'trailing',a['scene']['trailing_bytes'])


if __name__=='__main__':main()
