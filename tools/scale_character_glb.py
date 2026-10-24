#!/usr/bin/env python3
"""Explicit uniform-unit conversion, preserving rig/morph/animation consistency.

The factor is a destination design choice, not a recovered metre/unit constant.
"""
import argparse
import json
import struct
from pathlib import Path
import numpy as np


def convert(source, output, factor):
    if not np.isfinite(factor) or factor<=0:raise ValueError('positive finite scale required')
    raw=source.read_bytes();n=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+n]);blob=bytearray(raw[28+n:]);positions=set();inverse=set()
    for m in g.get('meshes',[]):
        for p in m['primitives']:
            positions.add(p['attributes']['POSITION']);positions.update(t['POSITION'] for t in p.get('targets',[]))
    for a in g.get('animations',[]):
        for c in a['channels']:
            if c['target']['path']=='translation':positions.add(a['samplers'][c['sampler']]['output'])
    for sk in g.get('skins',[]):inverse.add(sk['inverseBindMatrices'])
    for i in positions|inverse:
        a=g['accessors'][i];v=g['bufferViews'][a['bufferView']];assert a['componentType']==5126
        width=16 if i in inverse else 3;values=np.frombuffer(blob,dtype='<f4',count=a['count']*width,offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,width)
        if i in inverse:values[:,12:15]*=factor
        else:values*=factor
        for key in ['min','max']:
            if key in a:a[key]=(values.min(0) if key=='min' else values.max(0)).tolist()
    for node in g['nodes']:
        if 'translation' in node:node['translation']=(np.array(node['translation'])*factor).tolist()
    g['asset'].setdefault('extras',{})['unit_conversion']={'uniform_scale':factor,'source_metre_scale_known':False,'policy':'explicit destination choice; source Y-up retained'}
    js=json.dumps(g,separators=(',',':')).encode();js+=b' '*((-len(js))%4)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(struct.pack('<III',0x46546c67,2,28+len(js)+len(blob))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(blob),0x004e4942)+blob)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--factor',type=float,required=True);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in args.output.resolve().parents:ap.error('converted assets remain private')
    convert(args.source,args.output,args.factor)


if __name__=='__main__':main()
