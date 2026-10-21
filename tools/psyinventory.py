#!/usr/bin/env python3
"""Inventory owned archives without extracting or writing into the game."""
import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path

from psyassets import read_archive, scene


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('game',type=Path)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    if root/'.local/assets' not in args.output.resolve().parents:ap.error('inventory belongs under .local/assets/')
    entries=[]
    for p in sorted(args.game.rglob('*.ppf')):
        a=read_archive(p);models=[{k:v for k,v in m.items() if k!='data'} for m in a['models']]
        v={'archive':str(p.relative_to(args.game)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
           'bytes':p.stat().st_size,'models':models,'textures':len(a['textures']),'scene_offset':a['scene_offset']}
        if a['scene_data']:
            try:
                s=scene(a['scene_data']);v.update(scene_version=s['version'],parsed_bytes=s['parsed_bytes'],
                         tail_bytes=s['trailing_bytes'],static_scene='supported')
            except ValueError as exc:v['static_scene']=str(exc)
        else:v['static_scene']='absent'
        entries.append(v)
    spec=importlib.util.spec_from_file_location('psypkg',root/'third_party/psypkg.py')
    pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
    packages=[]
    for p in sorted(args.game.glob('*.pkg')):
        with p.open('rb') as f:records=list(pkg.read_index(f))
        packages.append({'archive':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                         'reported_names_unverified':True,'entries':[{'id':i,'reported_name':name,'offset':off,'size':size}
                                                                    for i,(name,off,size) in enumerate(records)]})
    files=[p for p in args.game.rglob('*') if p.is_file()]
    result={'file_extensions':dict(collections.Counter(p.suffix.lower() for p in files)),
            'ppf':entries,'pkg':packages,'apf':[{'name':str(p.relative_to(args.game)),'bytes':p.stat().st_size,
                     'header_hex':p.open('rb').read(16).hex()} for p in sorted(args.game.rglob('*.apf'))]}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('PPF archives',len(entries),'model records',sum(len(v['models']) for v in entries),
          'PKG entries',sum(len(v['entries']) for v in packages))


if __name__=='__main__':main()
