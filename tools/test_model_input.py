#!/usr/bin/env python3
"""Differential x86 fixtures for model names and allocating stream strings.

Aligned allocation/free, filename copying and stream transfers are mocked.
Large requests and aliases are traced without unsafe dereferences. Synthetic
partial headers use poisoned stack bytes; no actual asset or game is used.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
TABLE, BUFFER, OLD = HEAP+0x100, HEAP+0x1000, HEAP+0x2000
FREE, COPY, ALLOC, READ = STOP+0x100, STOP+0x200, STOP+0x300, STOP+0x400
ORIGINAL = {'EModel::SetName': 0x455900, 'EStream::ReadAllocatedString': 0x6a5de0}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}

def fixture(s):
    memory = bytearray(b'\xcc'*0x3000)
    struct.pack_into('<I', memory, 0, OLD if s['old'] else 0)
    if s['function']=='EStream::ReadAllocatedString':
        struct.pack_into('<II', memory, 0, TABLE, s['mode'])
        struct.pack_into('<I', memory, TABLE-HEAP+8, READ)
    return memory

def decoded(s):
    word = struct.pack('<I', s['length'])[:s['header']]
    value = int.from_bytes(word+b'\xa5'*(4-len(word)), 'little')
    return word, value

def expected(s):
    memory, trace = fixture(s), []
    result = None
    if s['function']=='EModel::SetName':
        if s['old']:
            trace.append(['free', OLD, 7, 1])
            struct.pack_into('<I', memory, 0, 0)
        if s['source']:
            trace.append(['copy', s['source'], 7, 0])
            struct.pack_into('<I', memory, 0, s['allocated'])
    else:
        word, size = decoded(s)
        trace.append(['header', word.hex()])
        if 1 < size < 0x80000000:
            trace.append(['alloc', size, 16])
            result = s['allocated']
            dest = result
        else:
            result, dest = 0, 0
        trace.append(['transfer', dest, size])
        if dest and size <= 128:
            count = min(size, s['transfer'])
            memory[dest-HEAP:dest-HEAP+count] = b'Z'*count
    return dict(memory=memory.hex(), trace=trace, result=result)

def execute(pe, function, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095)&~4095)
    uc.mem_write(base, image)
    for address, size in ((CODE,0x10000),(HEAP,0x3000),(STACK,0x10000),(STOP,0x1000)):
        uc.mem_map(address,size)
    uc.mem_write(HEAP,bytes(fixture(s)))
    uc.mem_write(STACK,b'\xa5'*0x10000)
    for address in (FREE,COPY,ALLOC): uc.mem_write(address,b'\xc3')
    uc.mem_write(READ,b'\xc2\x08\x00')
    uc.mem_write(0x700288,struct.pack('<I',ALLOC))
    if rebuilt:
        symbols={'?FreeFileName@@YAXPADHH@Z':FREE,
            '?CopyFileName@@YAPADPBDH@Z':COPY,'__imp___aligned_malloc':0x700288}
        uc.mem_write(REBUILT[s['function']],relocate(function,REBUILT[s['function']],symbols))
    # Trap the original wrappers at their entries to observe all arguments.
    free_address = FREE if rebuilt else 0x6a6e30
    copy_address = COPY if rebuilt else 0x6a6e10
    uc.mem_write(free_address,b'\xc3')
    uc.mem_write(copy_address,b'\xc3')
    trace=[]
    def hook(machine,address,length,user):
        sp=machine.reg_read(UC_X86_REG_ESP)
        if address==free_address:
            args=struct.unpack('<III',machine.mem_read(sp+4,12))
            trace.append(['free',*args])
        elif address==copy_address:
            args=struct.unpack('<II',machine.mem_read(sp+4,8))
            value=struct.unpack('<I',machine.mem_read(HEAP,4))[0]
            trace.append(['copy',*args,value])
            machine.reg_write(UC_X86_REG_EAX,s['allocated'])
        elif address==ALLOC:
            args=struct.unpack('<II',machine.mem_read(sp+4,8))
            trace.append(['alloc',*args])
            machine.reg_write(UC_X86_REG_EAX,s['allocated'])
        elif address==READ:
            assert machine.reg_read(UC_X86_REG_ECX)==HEAP
            dest,size=struct.unpack('<II',machine.mem_read(sp+4,8))
            if not trace:
                assert size==4 and STACK<=dest<STACK+0x10000
                word,_=decoded(s)
                machine.mem_write(dest,word)
                trace.append(['header',word.hex()])
            else:
                trace.append(['transfer',dest,size])
                if dest and size<=128:
                    machine.mem_write(dest,b'Z'*min(size,s['transfer']))
            machine.reg_write(UC_X86_REG_EAX,0xdeadbeef)
    uc.hook_add(UC_HOOK_CODE,hook)
    sp=STACK+0x8000
    argument=s['source'] if s['function']=='EModel::SetName' else s['category']
    uc.mem_write(sp,struct.pack('<II',STOP,argument))
    saved={UC_X86_REG_EBP:0x12345678,UC_X86_REG_EBX:0x23456789,
        UC_X86_REG_ESI:0x3456789a,UC_X86_REG_EDI:0x456789ab}
    for reg,value in saved.items():uc.reg_write(reg,value)
    uc.reg_write(UC_X86_REG_ESP,sp)
    uc.reg_write(UC_X86_REG_ECX,HEAP)
    uc.emu_start((REBUILT if rebuilt else ORIGINAL)[s['function']],STOP,count=10000)
    assert uc.reg_read(UC_X86_REG_EIP)==STOP
    assert uc.reg_read(UC_X86_REG_ESP)==sp+8
    assert all(uc.reg_read(reg)==value for reg,value in saved.items())
    result=uc.reg_read(UC_X86_REG_EAX) if s['function']=='EStream::ReadAllocatedString' else None
    return dict(memory=bytes(uc.mem_read(HEAP,0x3000)).hex(),trace=trace,result=result)

def scenarios():
    base=dict(old=False,source=0,allocated=0,length=0,header=4,transfer=128,mode=0,category=0x1a)
    for old,source,allocated in itertools.product((False,True),(0,OLD,OLD+128),(0,BUFFER)):
        yield dict(base,function='EModel::SetName',old=old,source=source,allocated=allocated)
    for length,allocated,mode,category,transfer in itertools.product(
            (0,1,2,5,128,129,0x7fffffff,0x80000000,0xffffffff),
            (0,BUFFER),(0,1,2),(0,0x1a,0xffffffff),(0,128)):
        yield dict(base,function='EStream::ReadAllocatedString',length=length,
            allocated=allocated,mode=mode,category=category,transfer=transfer)
    for header,length in itertools.product((0,1,2,3),(0,1,5,0x7fffffff)):
        yield dict(base,function='EStream::ReadAllocatedString',header=header,length=length,allocated=BUFFER)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe',type=Path)
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):
        ap.error('reports must stay private')
    data,pe=load_reference(args.exe)
    paths=[ROOT/'build/game/mesh.obj',ROOT/'build/game/resource_stream.obj']
    functions={demangle(f.name):f for path in paths for f in ObjFile(str(path)).functions if demangle(f.name) in ORIGINAL}
    assert functions.keys()==ORIGINAL.keys()
    cases=[]
    for i,s in enumerate(scenarios()):
        want=expected(s);original=execute(pe,functions[s['function']],s,False)
        rebuilt=execute(pe,functions[s['function']],s,True)
        assert original==rebuilt==want,(i,s,'state/trace/result mismatch')
        cases.append(dict(s,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(data).hexdigest(),
        object_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        cases=cases,scope=__doc__),indent=2)+'\n')
    print('Passed %d model-input differential cases'%len(cases))
if __name__=='__main__':main()
