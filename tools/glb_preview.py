#!/usr/bin/env python3
"""Offline orthographic GLB inspection: textures, triangles and depth buffer.

Inspection aid, not the game's renderer. It can evaluate exported skeletal animation and skins on CPU. Original material
effects, vertex colors and lighting remain outside this inspection scope.
"""
import argparse
import io
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image


def load(path, frame=None, lightmaps=False, clip=0):
    data=path.read_bytes();magic,version,size=struct.unpack_from('<III',data)
    if (magic,version,size)!=(0x46546c67,2,len(data)):raise ValueError('invalid GLB')
    n,kind=struct.unpack_from('<II',data,12);g=json.loads(data[20:20+n]);off=20+n
    length,kind=struct.unpack_from('<II',data,off);blob=data[off+8:off+8+length]
    def access(index):
        a=g['accessors'][index];v=g['bufferViews'][a['bufferView']]
        dtype={5121:'u1',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        return np.frombuffer(blob,dtype=dtype,count=a['count']*width,
                             offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,width)
    images=[]
    for im in g.get('images',[]):
        v=g['bufferViews'][im['bufferView']];o=v.get('byteOffset',0)
        images.append(np.array(Image.open(io.BytesIO(blob[o:o+v['byteLength']])).convert('RGBA')))
    from glb_skin import read,pose
    gg,aa=read(path);posed=pose(gg,aa,frame/30,clip) if frame is not None else None
    parts=[]
    for mi,m in enumerate(g['meshes']):
        for pi,p in enumerate(m['primitives']):
            attrs=p['attributes'];mat=g['materials'][p['material']];tex=None
            ti=mat['pbrMetallicRoughness'].get('baseColorTexture')
            if ti:tex=images[g['textures'][ti['index']]['source']]
            lm=mat.get('extras',{}).get('lightmap_texture')
            if lightmaps and lm is not None:
                if 'TEXCOORD_1' not in attrs:raise ValueError('lightmap lacks second UV set')
                mat=dict(mat);mat['_preview_lightmap']=images[g['textures'][lm]['source']]
                mat['_preview_lightmap_uv']=access(attrs['TEXCOORD_1'])
            parts.append((posed[(mi,pi)] if posed is not None else access(attrs['POSITION']),access(p['indices']).reshape(-1,3),
                          access(attrs['TEXCOORD_0']) if 'TEXCOORD_0' in attrs else None,tex,mat))
    return parts


def render(parts, output, yaw=0, size=720):
    angle=np.deg2rad(yaw);right=np.array([np.cos(angle),0,-np.sin(angle)])
    forward=np.array([np.sin(angle)*.9,-.35,np.cos(angle)*.9]);forward/=np.linalg.norm(forward)
    up=np.cross(forward,right);up/=np.linalg.norm(up)
    basis=np.stack([right,up,forward],axis=1)
    allpos=np.concatenate([p[0] for p in parts]);center=(allpos.min(0)+allpos.max(0))/2
    projected=(allpos-center)@basis;span=np.ptp(projected[:,:2],axis=0).max();scale=(size-60)/span
    canvas=np.zeros((size,size,4),np.uint8);canvas[:]=[32,35,42,255];depth=np.full((size,size),np.inf)
    for pos,tri,uv,tex,mat in parts:
        v=(pos-center)@basis;screen=v[:,:2]*scale+size/2;screen[:,1]=size-screen[:,1]
        for indices in tri:
            xy=screen[indices];z=v[indices,2]
            lo=np.maximum(np.floor(xy.min(0)).astype(int),0);hi=np.minimum(np.ceil(xy.max(0)).astype(int),size-1)
            if np.any(hi<lo):continue
            x,y=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
            a,b,c=xy;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den)<1e-9:continue
            w0=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
            w1=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den;w2=1-w0-w1
            zz=w0*z[0]+w1*z[1]+w2*z[2];sl=np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            mask=(w0>=0)&(w1>=0)&(w2>=0)&(zz<depth[sl])
            if not mask.any():continue
            color=np.broadcast_to(np.array(mat['pbrMetallicRoughness']['baseColorFactor']),(*x.shape,4)).copy()
            if tex is not None and uv is not None:
                t=uv[indices];u=(w0*t[0,0]+w1*t[1,0]+w2*t[2,0])%1;vv=(w0*t[0,1]+w1*t[1,1]+w2*t[2,1])%1
                rgba=tex[(vv*tex.shape[0]).astype(int),(u*tex.shape[1]).astype(int)]/255
                color*=rgba
            if '_preview_lightmap' in mat:
                lm=mat['_preview_lightmap'];t=mat['_preview_lightmap_uv'][indices]
                u=(w0*t[0,0]+w1*t[1,0]+w2*t[2,0])%1;vv=(w0*t[0,1]+w1*t[1,1]+w2*t[2,1])%1
                color[:,:,:3]*=lm[(vv*lm.shape[0]).astype(int),(u*lm.shape[1]).astype(int),:3]/255
            if mat.get('alphaMode') in ['MASK','BLEND']:mask&=color[:,:,3]>=mat.get('alphaCutoff',.05)
            face=np.cross(pos[indices[1]]-pos[indices[0]],pos[indices[2]]-pos[indices[0]])
            length=np.linalg.norm(face);lighting=.5+.5*abs(np.dot(face/length,[.4,.8,.44])) if length else 1
            color[:,:,:3]*=lighting;color=np.clip(color*255,0,255).astype(np.uint8)
            canvas[sl][mask]=color[mask];depth[sl][mask]=zz[mask]
    Image.fromarray(canvas).save(output)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('glb',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--yaw',type=float,default=0)
    ap.add_argument('--clip',type=int,default=0,help='zero-based independent animation index')
    ap.add_argument('--lightmaps',action='store_true',help='inspect base RGB times retained lightmap RGB; shader approximation')
    ap.add_argument('--frame',type=float,help='evaluate first animation at a 30-fps source frame')
    ap.add_argument('--center',help='optional source-space inspection region x,y,z')
    ap.add_argument('--radius',type=float,default=3000)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in args.output.resolve().parents:ap.error('preview must remain under .local/assets/')
    parts=load(args.glb,args.frame,args.lightmaps,args.clip)
    if args.center:
        center=np.array([float(v) for v in args.center.split(',')]);filtered=[]
        for pos,tri,uv,tex,mat in parts:
            keep=np.linalg.norm(pos[tri].mean(axis=1)-center,axis=1)<args.radius
            if keep.any():
                # Retain the complete primitive's original indices/UVs, but
                # remap referenced vertices for accurate regional framing.
                selected=tri[keep];used,remap=np.unique(selected,return_inverse=True)
                if '_preview_lightmap_uv' in mat:
                    mat=dict(mat);mat['_preview_lightmap_uv']=mat['_preview_lightmap_uv'][used]
                filtered.append((pos[used],remap.reshape(-1,3),uv[used] if uv is not None else None,tex,mat))
        parts=filtered
    if not parts:ap.error('no geometry in inspection region')
    render(parts,args.output,args.yaw)


if __name__=='__main__':main()
