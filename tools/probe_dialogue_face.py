#!/usr/bin/env python3
"""One bounded Milla dialogue/face proof, source evidence and private GLB candidate.

No production support. The controlled original-code path assumes ready resource,
mode0, no competing layers, wait=false/full-volume audio service. The clip is
facial-only on the source bind skeleton; FMOD and original rendering untested.
"""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from psyassets import Reader,read_archive,scene,normalize
from luaformat import load_chunk
from glb_skin import read,interpolate
from pba101_research import decode,local_weights
from original_dialogue_pba import DialoguePba
from check_model_export import meshes


def script_records(path):
    raw=path.read_bytes();a=read_archive(path,False);r=Reader(raw);r.pos=max(m['offset']+m['size'] for m in a['models']);n=r.u16();named=0
    if n==0xfcfc:named=r.u16();n=r.u16()
    rows=[]
    for _ in range(n):
        name=r.string(2);size=r.u32();at=r.pos;rows.append(dict(name=name,offset=at,raw=r.take(size)))
    for i in range(r.u16()):
        name=r.string(2) if named else 'anonymous-%d'%i;size=r.u32();at=r.pos;rows.append(dict(name=name,offset=at,raw=r.take(size)))
    return rows


def source_evidence(game,source_glb):
    sha=lambda b:hashlib.sha256(b).hexdigest()
    actor=next(x for x in script_records(game/'WorkResource/PCLevelPackFiles/MIFL.ppf') if x['name'].lower().endswith('millacamera'))
    proto=load_chunk(actor['raw']);ctor=proto.kproto[0];assignments={}
    # Cross-check literal object assignments directly from original 16-bit words,
    # separately from the exploratory decompiled source view.
    for i in range(len(ctor.raw)-3):
        a,b,c,d=ctor.raw[i:i+4]
        if a&63==11 and a>>6==0 and b&63==7 and c&63==7 and d&63==20:
            assignments[ctor.kstr[b>>6]]=ctor.kstr[c>>6]
    assert assignments['animsDir']=='Milla/MITU' and normalize(assignments['meshName'])=='characters/milla.plb'
    def strings(p):return p.kstr+[s for child in p.kproto for s in strings(child)]
    assert '/MITU066MI/' in strings(proto)
    model=next(x for x in read_archive(game/'WorkResource/PCLevelPackFiles/MIFL.ppf',False)['models'] if normalize(x['name'])=='characters/milla.plb')
    g,access=read(source_glb);assert g['nodes'] and g['meshes']
    proof_path=source_glb.parent.parent/'validation'/(source_glb.stem+'-source.json')
    proof=json.loads(proof_path.read_text())
    assert proof['status']=='passed' and proof['record_sha256']==sha(model['data']) and proof['glb_sha256']==sha(source_glb.read_bytes())
    target_names=sorted({b['name'] for m in meshes(scene(model['data'])['domain']) for f in m['fragments'] for b in f['blendshapes']})
    assert len(g['meshes'])==1 and g['meshes'][0]['extras']['targetNames']==target_names
    package=game/'PsychonautsData2.pkg';directory='anims/milla/mitu/lipsync'
    with package.open('rb') as f:
        h=struct.unpack('<4s7I',f.read(32));assert h[0]==b'ZPKG' and h[1]==1
        f.seek(h[4]);nodes=f.read(h[5]*12);i=at=0;visited=[]
        for _ in range(h[5]+len(directory)):
            ch,pad,less,greater,same,start,end=struct.unpack_from('<BB5H',nodes,12*i);assert pad==0;visited.append(i);v=ord(directory[at])
            if v==ch:
                at+=1
                if at==len(directory):break
                i=same
            else:i=less if v<ch else greater
            if not i or i>=h[5]:raise ValueError('original directory path not found')
        else:raise ValueError('directory cycle')
        found=[]
        for record in range(start,end):
            f.seek(512+16*record);_,typ,_,nameoff,offset,size=struct.unpack('<BHBIII',f.read(16));f.seek(h[6]+nameoff);name=f.read(64).split(b'\0')[0];f.seek(h[7]+typ);extension=f.read(16).split(b'\0')[0]
            if name.lower()==b'mitu066mi' and extension.lower()==b'pba':found.append((record,offset,size))
        if len(found)!=1:raise ValueError('original directory/filename reference ambiguous')
        record,offset,size=found[0];f.seek(offset);raw=f.read(size)
    assert decode(raw)['version']==101
    base=next(x for x in script_records(game/'WorkResource/PCLevelPackFiles/common.ppf') if x['name']=='ScriptBase')
    def protos(p):
        yield p
        for child in p.kproto:yield from protos(child)
    sayline=next(p for p in protos(load_chunk(base['raw'])) if 'PlaySoundWithBabble' in p.kstr)
    assert 'animsDir' in sayline.kstr
    evidence=dict(actor_script=dict(archive='MIFL.ppf',name=actor['name'],offset=actor['offset'],size=len(actor['raw']),sha256=sha(actor['raw']),literal_assignments=assignments,line='/MITU066MI/',constructor_code_sha256=sha(struct.pack('<'+'H'*len(ctor.raw),*ctor.raw))),
        sayline_script=dict(archive='common.ppf',name='ScriptBase',offset=base['offset'],size=len(base['raw']),sha256=sha(base['raw']),function_code_sha256=sha(struct.pack('<'+'H'*len(sayline.raw),*sayline.raw)),scope='original constants/opcodes plus existing decompiler static dataflow; full Lua VM not executed'),
        resource=dict(path='Anims/Milla/MITU/LipSync/MITU066MI.pba',record=record,offset=offset,size=size,sha256=sha(raw),directory_nodes=visited,directory_range=[start,end]),
        model_record_sha256=sha(model['data']),source_glb_sha256=sha(source_glb.read_bytes()),source_proof_sha256=sha(proof_path.read_bytes()))
    return raw,g,access,evidence


def bake(source,out,g,times,values,evidence):
    g=copy.deepcopy(g);raw=source.read_bytes();length=struct.unpack_from('<I',raw,12)[0];blob=bytearray(raw[28+length:28+length+g['buffers'][0]['byteLength']])
    def add(a,kind):
        while len(blob)%4:blob.append(0)
        a=np.asarray(a,dtype='<f4');v=len(g['bufferViews']);g['bufferViews'].append(dict(buffer=0,byteOffset=len(blob),byteLength=a.nbytes));blob.extend(a.tobytes());i=len(g['accessors']);entry=dict(bufferView=v,componentType=5126,count=len(a),type=kind)
        if kind=='SCALAR':entry.update(min=[float(a.min())],max=[float(a.max())])
        g['accessors'].append(entry);return i
    inp=add(times,'SCALAR');output=add(values.ravel(),'SCALAR');node=next(i for i,n in enumerate(g['nodes']) if n.get('mesh')==0)
    g['animations']=[dict(name='MITU066MI_ready_mode0_face_only',channels=[dict(sampler=0,target=dict(node=node,path='weights'))],samplers=[dict(input=inp,output=output,interpolation='LINEAR')],extras=dict(source=evidence['resource'],conditions='ready resource; mode0; active standalone; fade0.1s; no other layers; bind skeleton; audio not included',sampling='dense approximation during quadratic fade; independently tolerance-tested'))]
    g['asset']['generator']='Bounded original-code dialogue facial probe; not general PBA101 support';g['buffers']=[dict(byteLength=len(blob))]
    js=json.dumps(g,separators=(',',':')).encode();js+=b' '*(-len(js)%4);blob+=b'\0'*(-len(blob)%4)
    out.parent.mkdir(parents=True);out.write_bytes(struct.pack('<III',0x46546c67,2,28+len(js)+len(blob))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(blob),0x004e4942)+blob)


def run(game,executable,source,out):
    out.mkdir(parents=True);raw,g,access,evidence=source_evidence(game,source);d=decode(raw);names=g['meshes'][0]['extras']['targetNames']
    if any(c['name'] not in names for c in d['channels']):raise ValueError('unmapped original facial channels')
    h=DialoguePba(executable,raw,names,evidence['resource']['path']);initial=h.babble();assert initial['skeletal_owner']==0 and initial['loop']==0 and initial['bound']==1 and initial['fade_rate']==10
    events=copy.deepcopy(h.events);assert events[0]['path']==evidence['resource']['path'];assert next(e for e in events if e['event']=='audio-start')['facial_count']==1
    times=np.asarray(sorted(set([i/1920 for i in range(193)]+[i/30 for i in range(4,22)])),dtype='<f4')
    values=np.asarray([np.asarray(local_weights(d,float(t),names))*min(float(t)*10,1) for t in times],dtype='<f4')
    glb=out/'rigged/Milla-MITU066MI.glb';bake(source,glb,g,times,values,evidence)
    gg,aa=read(glb);s=gg['animations'][0]['samplers'][0];gt=aa(s['input']).ravel();gv=aa(s['output']).reshape(len(gt),len(names))
    observations=[];validation_times=sorted(set([i/3840 for i in range(385)]+[i/240 for i in range(25,177)]+[.56666666,.5666667,.6666667]))
    for t in validation_times:
        h.call(0x48e2c0,h.manager,(0,));h.babble();actual=h.step(t)['weights'];predicted=interpolate(gt,gv,t);error=float(np.max(np.abs(predicted-actual)))
        if error>1e-5:raise ValueError('facial curve/original discrepancy at %g: %g'%(t,error))
        observations.append(dict(seconds=t,original=actual,glb=predicted.tolist(),max_weight_error=error))
    # A separate regular update schedule checks that output does not depend
    # materially on replacing elapsed time by a single update in this case.
    h.call(0x48e2c0,h.manager,(0,));h.babble();schedule=[]
    for index in range(48):
        result=h.step(1/60);t=(index+1)/60
        expected=interpolate(gt,gv,t);error=float(np.max(np.abs(expected-result['weights'])))
        if error>1e-5:raise ValueError('60Hz replay discrepancy')
        schedule.append(dict(seconds=t,state=result['state'],original=result['weights'],max_weight_error=error))
    sizes={row['address']:int(row['size']) for row in csv.DictReader((Path(__file__).resolve().parents[1]/'engine/functions.csv').open())}
    hashes={a:hashlib.sha256(bytes(h.uc.mem_read(int(a,16),sizes['0x%08x'%int(a,16)]))).hexdigest() for a in h.executed}
    report=dict(status='bounded facial-only original-code comparison passed',source=evidence,initial_state=initial,start_events=events,validation=observations,schedule_60hz=schedule,max_weight_error=max(x['max_weight_error'] for x in observations+schedule),key_count=len(gt),glb=str(glb.resolve()),glb_sha256=hashlib.sha256(glb.read_bytes()).hexdigest(),executed_functions=h.executed,function_hashes=hashes,service_adapters={hex(a):kind for a,(kind,_) in h.adapters.items()},limits=['ready resource service; no real file scheduling','Lua argument adapters from statically inspected script; Lua VM not executed','audio-start/actor-notification adapters; no FMOD latency or sound duration proof','no competing facial layers; mode0 only','skeletal animation intentionally absent from facial-only export','LINEAR approximation independently bounded at tested subframes; not a bit-exact continuous curve'])
    (out/'runtime-report.json').write_text(json.dumps(report,indent=2)+'\n');return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('game','executable','source','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]/'.local/assets'
    if not a.out.resolve().is_relative_to(root) or a.out.exists():p.error('new private output required')
    r=run(a.game,a.executable,a.source,a.out);print(r['status'],'samples',len(r['validation']),'max error',r['max_weight_error'])


if __name__=='__main__':main()
