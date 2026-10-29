#!/usr/bin/env python3
"""Observed scene/resource relationships; never applies inferred transforms."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from psyassets import read_archive,scene,normalize

ROOT=Path(__file__).resolve().parents[1]


def geometry_view(mesh):
    arrays=[np.frombuffer(f['posnrm'],dtype='<f4').reshape(-1,4)[:,:3] for f in mesh['fragments'] if f['vertices']]
    out=dict(name=mesh['name'],serialized_translation=mesh['translation'],serialized_rotation=mesh['rotation'],serialized_scale=mesh['scale'],collision=bool(mesh['collision']))
    if not arrays:return out
    pos=np.concatenate(arrays);bounds=np.asarray(mesh['bounds']);lo,hi=bounds[:3],bounds[3:]
    fits=lambda p:bool(np.all(p.min(0)>=lo-.05) and np.all(p.max(0)<=hi+.05))
    out.update(vertices=len(pos),raw_extent=[pos.min(0).tolist(),pos.max(0).tolist()],raw_positions_fit_mesh_bounds=fits(pos),translation_applied_positions_fit_mesh_bounds=fits(pos+mesh['translation']),
               transform_evidence='numeric bounds heuristic only; mesh-bounds frame and runtime transforms remain unproven')
    if mesh['collision'] and mesh['collision']['vertices']:
        collision=np.asarray(mesh['collision']['vertices']);out['collision_extent']=[collision.min(0).tolist(),collision.max(0).tolist()]
        out['collision_positions_fit_mesh_bounds']=fits(collision)
    return out


def analyze(data,models,textures):
    domains=[];mesh_rows=[];roles=[]
    def visit_mesh(m,path):
        mesh_rows.append(dict(path=path,**geometry_view(m)))
        for fi,f in enumerate(m['fragments']):
            fields=[('base' if i==0 else 'secondary',n) for i,n in enumerate(f['textures'])]
            fields += [(k,f[k]) for k in ['lightmap','detail','gloss','reflection'] if isinstance(f.get(k),int)]
            for role,ident in fields:
                if ident is None or ident==0xffffffff:continue
                valid=0<=ident<len(data['texture_references']);name=data['texture_references'][ident]['name'] if valid else None
                roles.append(dict(mesh=path,fragment=fi,role=role,serialized_index=ident,name=name,resolved=bool(valid and normalize(name) in textures),glb_usage='base PNG' if role=='base' else 'retained lightmap' if role=='lightmap' else 'metadata; original shader not reproduced'))
        for i,c in enumerate(m['children']):visit_mesh(c,path+'/'+str(i))
    def visit(d,path):
        links=[]
        for i,s in enumerate(d['scripts']):
            index=s['initial_mesh'];valid=0<=index<len(d['meshes']);m=d['meshes'][index] if valid else None
            name=bool(valid and s['name']==m['name']);translation=bool(valid and np.allclose(s['position'],m['translation'],atol=.001,rtol=0))
            links.append(dict(script=i,name=s['name'],mesh_index=index,index_in_local_domain=valid,exact_name=name,translation_equal=translation,verified_link=name and translation,entity_data_index=s['initial_data'],entity_data_index_in_range=0<=s['initial_data']<len(d['entity_data'])))
        refs=[dict(name=n,matched_model_names=sorted(models.get(normalize(n),[]))) for n in d['runtime_references']]
        domains.append(dict(path=path,name=d['name'],mesh_entries=len(d['meshes']),scripts=links,entity_records=len(d['entity_data']),runtime_references=refs))
        for i,m in enumerate(d['meshes']):visit_mesh(m,path+'/mesh'+str(i))
        for i,c in enumerate(d['children']):visit(c,path+'/domain'+str(i))
    visit(data['domain'],'root')
    return dict(version=data['version'],domains=domains,meshes=mesh_rows,texture_roles=roles,opaque_tail_bytes=data['trailing_bytes'],
        summary=dict(mesh_entries=len(mesh_rows),script_records=sum(len(d['scripts']) for d in domains),verified_script_mesh_links=sum(s['verified_link'] for d in domains for s in d['scripts']),nonidentity_mesh_records=sum(m['serialized_translation']!=[0,0,0] or m['serialized_rotation']!=[0,0,0] or m['serialized_scale']!=[1,1,1] for m in mesh_rows),unresolved_texture_roles=sum(not r['resolved'] for r in roles),collision_meshes=sum(m['collision'] for m in mesh_rows)),
        policy='Export baked source positions with identity mesh nodes; preserve serialized transforms/hierarchy and references as metadata. Exact index/name/translation agreement permits a link, not dynamic actor reconstruction.',
        limitations=['no inferred TRS application','bounds comparisons are diagnostic, not frame proof','references only resolved by exact normalized identifiers in this pack/common','original material/lightmap composition and runtime instantiation unverified'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--common',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if not args.out.resolve().is_relative_to(ROOT/'.local/assets') or args.out.exists():p.error('output must be new and private')
    a=read_archive(args.archive);common=read_archive(args.common,False);textures={t['key'] for t in a['textures']+common['textures']};models={}
    for group in [a,common]:
        for m in group['models']:models.setdefault(normalize(m['name']),set()).add(m['name'])
    result=analyze(scene(a['scene_data']),models,textures);result['archive_sha256']=hashlib.sha256(args.archive.read_bytes()).hexdigest();args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n');print(args.archive.name,result['summary'])


if __name__=='__main__':main()
