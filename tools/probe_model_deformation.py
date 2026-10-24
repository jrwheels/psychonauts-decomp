#!/usr/bin/env python3
"""Create private GLB deformation probes from real exported rigs.

Adds synthetic rotation channels for importer validation. These are explicitly
diagnostic fixtures, never recovered game animations. Original GLBs stay intact.
"""
import argparse
import copy
import json
from pathlib import Path
import struct
import numpy as np
from glb_skin import read
from psyrig import qmul


def make(source,output):
    g,_=read(source);g=copy.deepcopy(g);raw=source.read_bytes()
    length=struct.unpack_from('<I',raw,12)[0]
    blob=bytearray(raw[28+length:28+length+g['buffers'][0]['byteLength']])
    def accessor(values,kind):
        while len(blob)%4:blob.append(0)
        a=np.asarray(values,dtype='<f4');view=len(g['bufferViews'])
        g['bufferViews'].append(dict(buffer=0,byteOffset=len(blob),byteLength=a.nbytes));blob.extend(a.tobytes())
        result=len(g['accessors']);entry=dict(bufferView=view,componentType=5126,count=len(a),type=kind)
        if kind=='SCALAR':entry.update(min=[0],max=[1])
        g['accessors'].append(entry);return result
    times=accessor([0,1],'SCALAR');animations=[]
    for skin in g.get('skins',[]):
        nodes=skin['joints'];selected=sorted(set([nodes[0],nodes[min(1,len(nodes)-1)],nodes[len(nodes)//2],nodes[-1]]+
                      [i for i in nodes if g['nodes'][i].get('extras',{}).get('rotation_identity_sentinel')]))
        for node in selected:
            base=np.array(g['nodes'][node].get('rotation',[0,0,0,1]))
            for axis in range(3):
                delta=np.zeros(4);delta[axis]=np.sin(.3);delta[3]=np.cos(.3)
                values=accessor([base,qmul(base,delta)],'VEC4')
                animations.append(dict(name='DIAGNOSTIC_node%d_axis%d'%(node,axis),
                    samplers=[dict(input=times,output=values,interpolation='LINEAR')],
                    channels=[dict(sampler=0,target=dict(node=node,path='rotation'))]))
    g['animations']=animations;g['asset']['generator']='Synthetic importer deformation probe; not original animation'
    g['buffers']=[dict(byteLength=len(blob))]
    js=json.dumps(g,separators=(',',':')).encode();js+=b' '*(-len(js)%4);blob+=b'\0'*(-len(blob)%4)
    output.write_bytes(struct.pack('<III',0x46546c67,2,28+len(js)+len(blob))+
        struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(blob),0x004e4942)+blob)
    return len(animations)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source',type=Path);ap.add_argument('output',type=Path)
    args=ap.parse_args();root=Path(__file__).resolve().parents[1]/'.local/assets'
    if not args.output.resolve().is_relative_to(root) or args.output.exists():ap.error('output must be new and private')
    args.output.parent.mkdir(parents=True,exist_ok=True);print(make(args.source,args.output),'diagnostic animations')


if __name__=='__main__':main()
