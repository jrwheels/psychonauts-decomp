#!/usr/bin/env python3
"""Skeleton construction/destruction fixtures; destructor SetName dependency mocked."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT=Path(__file__).resolve().parents[1]
CODE,HEAP,STACK,STOP=0x1000000,0x2000000,0x3000000,0x2100000
OBJECT,IDENTITY=HEAP+0x100,0x7933e0
SET_NAME=0x491ab0
TARGETS=[('RuntimeBone::RuntimeBone',0x491b00,0xb0),('BoneInfo::BoneInfo',0x491a10,0x60),('SkeletonData::SkeletonData',0x499ac0,12)]


def expected(memory,name,matrix):
    result=bytearray(memory);base=OBJECT-HEAP
    if name.startswith('SkeletonData'):
        result[base:base+12]=b'\0'*12
    else:
        result[base:base+64]=matrix
        identity_rotation=struct.pack('<ffff',0.,0.,0.,1.)
        if name.startswith('BoneInfo'):
            result[base+0x40:base+0x4c]=b'\0'*12
            result[base+0x4c:base+0x5c]=identity_rotation
            result[base+0x5c:base+0x60]=b'\0'*4
        else:
            result[base+0x40:base+0x80]=matrix
            result[base+0x80:base+0x90]=identity_rotation
            result[base+0x90:base+0x9c]=struct.pack('<fff',1.,1.,1.)
            result[base+0x9c:base+0xa8]=b'\0'*12
            result[base+0xa8:base+0xac]=b'\0'*4
            result[base+0xac:base+0xb0]=b'\xff\xff\xff\x01'
    return bytes(result)


class Runner:
    def __init__(self,pe,function,target,rebuilt):
        self.target=target
        self.uc=uc=Uc(UC_ARCH_X86,UC_MODE_32)
        image,base=pe.get_memory_mapped_image(),pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base,(len(image)+4095)&~4095);uc.mem_write(base,image)
        for address,size in ((CODE,0x2000),(HEAP,0x1000),(STACK,0x10000),(STOP,0x1000)):
            uc.mem_map(address,size)
        self.entry=CODE if rebuilt else target[1]
        if rebuilt:
            symbols={}
            for _,_,name,_ in function.relocs():
                if demangle(name)=='g_identityMatrix':symbols[name]=IDENTITY
                else:
                    assert demangle(name)=='BoneInfo::SetName',name
                    symbols[name]=SET_NAME
            uc.mem_write(CODE,relocate(function,CODE,symbols))
        uc.mem_write(SET_NAME,b'\xc2\x04\x00')
        uc.hook_add(UC_HOOK_CODE,self.callback)

    def callback(self,uc,address,size,user):
        if address!=SET_NAME:return
        assert self.target[0]=='BoneInfo::~BoneInfo'
        assert uc.reg_read(UC_X86_REG_ECX)==OBJECT
        sp=uc.reg_read(UC_X86_REG_ESP)
        assert struct.unpack('<I',uc.mem_read(sp+4,4))[0]==0
        uc.mem_write(OBJECT+0x5c,b'\0'*4)
        self.calls+=1
        uc.reg_write(UC_X86_REG_EAX,0xdeadbeef)
        uc.reg_write(UC_X86_REG_ECX,0x12345678)
        uc.reg_write(UC_X86_REG_EDX,0x87654321)

    def run(self,memory,matrix):
        self.calls=0
        uc=self.uc;uc.mem_write(HEAP,memory);uc.mem_write(IDENTITY,matrix);uc.mem_write(STACK,b'\xa5'*0x10000)
        sp=STACK+0x8000;uc.mem_write(sp,struct.pack('<I',STOP))
        saved={UC_X86_REG_EBX:0x12345678,UC_X86_REG_ESI:0x23456789,UC_X86_REG_EDI:0x3456789a,UC_X86_REG_EBP:0x456789ab}
        for reg,value in saved.items():uc.reg_write(reg,value)
        uc.reg_write(UC_X86_REG_ECX,OBJECT);uc.reg_write(UC_X86_REG_ESP,sp);uc.reg_write(UC_X86_REG_EFLAGS,2)
        uc.emu_start(self.entry,STOP,count=1000)
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+4
        if '::~' not in self.target[0]:assert uc.reg_read(UC_X86_REG_EAX)==OBJECT
        assert self.calls==int(self.target[0]=='BoneInfo::~BoneInfo')
        assert all(uc.reg_read(reg)==value for reg,value in saved.items())
        assert bytes(uc.mem_read(IDENTITY,64))==matrix
        return bytes(uc.mem_read(HEAP,0x1000))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe',type=Path)
    ap.add_argument('--object',type=Path,default=ROOT/'build/game/skeleton_input.obj')
    ap.add_argument('--report',type=Path,default=ROOT/'build/skeleton-construction/behavior.json')
    args=ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):ap.error('report must stay private')
    raw,pe=load_reference(args.exe);obj=ObjFile(str(args.object));rng=random.Random(0x491b00);cases=[]
    actual_matrix=struct.pack('<16f',*(1.0 if i//4==i%4 else 0.0 for i in range(16)))
    matrices=[actual_matrix,b'\0'*64,b'\xff'*64,bytes(range(64))]+[rng.randbytes(64) for _ in range(28)]
    for target in TARGETS:
        found=[f for f in obj.functions if demangle(f.name)==target[0]]
        assert len(found)==1,target[0]
        runners=[Runner(pe,found[0],target,rebuilt) for rebuilt in (False,True)]
        for matrix_index,matrix in enumerate(matrices):
            for poison in (0,0xff,None):
                memory=bytearray(bytes([poison])*0x1000 if poison is not None else rng.randbytes(0x1000))
                want=expected(bytes(memory),target[0],matrix)
                assert all(r.run(bytes(memory),matrix)==want for r in runners),(target,matrix_index,poison)
                cases.append(dict(kind=target[0],matrix=matrix_index,poison=poison,passed=True))
    for target in [('BoneInfo::~BoneInfo',0x491a90,0x60),('RuntimeBone::~RuntimeBone',0x491cb0,0xb0)]:
        found=[f for f in obj.functions if demangle(f.name)==target[0]]
        assert len(found)==1,target[0]
        runners=[Runner(pe,found[0],target,rebuilt) for rebuilt in (False,True)]
        for index in range(32):
            memory=rng.randbytes(0x1000);want=bytearray(memory)
            if target[0].startswith('BoneInfo'):want[OBJECT-HEAP+0x5c:OBJECT-HEAP+0x60]=b'\0'*4
            assert all(r.run(memory,actual_matrix)==bytes(want) for r in runners)
            cases.append(dict(kind=target[0],fixture=index,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),object_sha256={args.object.name:hashlib.sha256(args.object.read_bytes()).hexdigest()},scope=__doc__,mocks=['BoneInfo::SetName for destructor only'],exclusions=['array allocation/cookies','actual string free','skeleton input','gameplay'],cases=cases),indent=2)+'\n')
    print('Passed %d skeleton-construction/destruction differential cases'%len(cases))


if __name__=='__main__':main()
