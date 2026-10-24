#!/usr/bin/env python3
"""Skeleton input differential fixtures; real constructors, mocked dependencies."""
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
OBJECT,STREAM,VTABLE,NAME=(HEAP+x for x in (0x100,0x300,0x400,0x500))
DATA,RUNTIME,INFO=(HEAP+x for x in (0x1000,0x2000,0x20000))
ROOT_BONE,INFO_ARRAY=RUNTIME+16,INFO+16
IDENTITY,ALLOC_IMPORT=0x7933e0,0x700288
ALLOC,READ=CODE+0x1000,CODE+0x1100
NAME_LOADER,RECURSIVE,TRANSFORM=0x6a5a10,0x492010,0x4923d0
FUNCTIONS={'Skeleton::ReadInput':0x49a040,'SkeletonData::SkeletonData':0x499ac0,
           'RuntimeBone::RuntimeBone':0x491b00,'BoneInfo::BoneInfo':0x491a10}
MATRIX=struct.pack('<16f',*(1. if i//4==i%4 else 0. for i in range(16)))


def expected(memory,count,success):
    result=bytearray(memory);offset=OBJECT-HEAP
    struct.pack_into('<III',result,offset,DATA,INFO_ARRAY,ROOT_BONE)
    struct.pack_into('<I',result,offset+0x10,ROOT_BONE)
    result[offset+0x3c]&=0xfd
    struct.pack_into('<III',result,DATA-HEAP,NAME,INFO_ARRAY,count)
    struct.pack_into('<I',result,RUNTIME-HEAP,count)
    struct.pack_into('<I',result,INFO-HEAP,count)
    bone=(MATRIX+MATRIX+struct.pack('<ffff',0.,0.,0.,1.)+
          struct.pack('<fff',1.,1.,1.)+b'\0'*16+b'\xff\xff\xff\x01')
    info=MATRIX+b'\0'*12+struct.pack('<ffff',0.,0.,0.,1.)+b'\0'*4
    assert len(bone)==0xb0 and len(info)==0x60
    for i in range(count):
        start=ROOT_BONE-HEAP+i*0xb0
        result[start:start+0xb0]=bone
        result[start+0xac]=i&255
        start=INFO_ARRAY-HEAP+i*0x60
        result[start:start+0x60]=info
    if success:result[ROOT_BONE-HEAP+0xaf]|=2
    trace=[('alloc',12,16),('name',),('read-count',count),
           ('alloc',count*0xb0+16,16),('alloc',count*0x60+16,16),
           ('read-id',),('recursive',)]
    if success:trace.append(('transform',))
    return bytes(result),trace


class Runner:
    def __init__(self,pe,functions,rebuilt):
        self.uc=uc=Uc(UC_ARCH_X86,UC_MODE_32)
        image,base=pe.get_memory_mapped_image(),pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base,(len(image)+4095)&~4095);uc.mem_write(base,image)
        for address,size in ((CODE,0x2000),(HEAP,0x40000),(STACK,0x10000),(STOP,0x1000)):
            uc.mem_map(address,size)
        self.entry=FUNCTIONS['Skeleton::ReadInput']
        if rebuilt:
            symbols={'?g_identityMatrix@@3UEMatrix@@A':IDENTITY,'__imp___aligned_malloc':ALLOC_IMPORT}
            for name,f in functions.items():symbols[f.name]=FUNCTIONS[name]
            for f in functions.values():
                for _,_,symbol,_ in f.relocs():
                    text=demangle(symbol)
                    if text=='ReadSkeletonName':symbols[symbol]=NAME_LOADER
                    elif text=='RuntimeBone::ReadInput':symbols[symbol]=RECURSIVE
                    elif text=='RuntimeBone::Transform':symbols[symbol]=TRANSFORM
                uc.mem_write(FUNCTIONS[demangle(f.name)],relocate(f,FUNCTIONS[demangle(f.name)],symbols))
        uc.mem_write(ALLOC_IMPORT,struct.pack('<I',ALLOC))
        for address,code in ((ALLOC,b'\xc3'),(READ,b'\xc2\x08\x00'),(NAME_LOADER,b'\xc3'),
                             (RECURSIVE,b'\xc2\x0c\x00'),(TRANSFORM,b'\xc2\x04\x00')):
            uc.mem_write(address,code)
        uc.hook_add(UC_HOOK_CODE,self.callback)

    def callback(self,uc,address,size,user):
        if address not in (ALLOC,READ,NAME_LOADER,RECURSIVE,TRANSFORM):return
        sp=uc.reg_read(UC_X86_REG_ESP)
        args=lambda n:struct.unpack('<'+'I'*n,uc.mem_read(sp+4,n*4))
        if address==ALLOC:
            amount,alignment=args(2)
            expected_sizes=(12,self.count*0xb0+16,self.count*0x60+16)
            assert (amount,alignment)==(expected_sizes[self.allocations],16)
            result=(DATA,RUNTIME,INFO)[self.allocations];self.allocations+=1
            self.trace.append(('alloc',amount,alignment))
            uc.reg_write(UC_X86_REG_EAX,result)
        elif address==NAME_LOADER:
            assert args(2)==(STREAM,DATA)
            assert bytes(uc.mem_read(DATA,12))==b'\0'*12
            assert uc.mem_read(OBJECT+0x3c,1)[0]&2==0
            uc.mem_write(DATA,struct.pack('<I',NAME));self.trace.append(('name',))
        elif address==READ:
            assert uc.reg_read(UC_X86_REG_ECX)==STREAM
            destination,amount=args(2)
            if amount==4:
                assert destination==DATA+8
                uc.mem_write(destination,struct.pack('<I',self.count));self.trace.append(('read-count',self.count))
            else:
                assert amount==2
                uc.mem_write(destination,struct.pack('<H',self.root_id));self.trace.append(('read-id',))
        elif address==RECURSIVE:
            assert uc.reg_read(UC_X86_REG_ECX)==ROOT_BONE
            assert args(3)==(STREAM,self.version,OBJECT)
            assert uc.mem_read(ROOT_BONE+0xac,1)==b'\0'
            self.trace.append(('recursive',));uc.reg_write(UC_X86_REG_EAX,self.return_pointer)
        else:
            assert uc.reg_read(UC_X86_REG_ECX)==ROOT_BONE
            assert args(1)==(IDENTITY,)
            assert uc.mem_read(ROOT_BONE+0xaf,1)[0]&2
            self.trace.append(('transform',))
        uc.reg_write(UC_X86_REG_ECX,0xdeadbeef);uc.reg_write(UC_X86_REG_EDX,0x12345678)

    def run(self,memory,count,version,root_id,return_pointer):
        self.count,self.version,self.root_id,self.return_pointer=count,version,root_id,return_pointer
        self.trace=[];self.allocations=0;uc=self.uc
        uc.mem_write(HEAP,memory);uc.mem_write(STACK,b'\xa5'*0x10000);uc.mem_write(IDENTITY,MATRIX)
        sp=STACK+0x8000;uc.mem_write(sp,struct.pack('<III',STOP,STREAM,version))
        saved={UC_X86_REG_EBX:0x12345678,UC_X86_REG_ESI:0x23456789,UC_X86_REG_EDI:0x3456789a,UC_X86_REG_EBP:0x456789ab}
        for reg,value in saved.items():uc.reg_write(reg,value)
        uc.reg_write(UC_X86_REG_ECX,OBJECT);uc.reg_write(UC_X86_REG_ESP,sp);uc.reg_write(UC_X86_REG_EFLAGS,2)
        uc.emu_start(self.entry,STOP,count=250000)
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+12
        assert uc.reg_read(UC_X86_REG_EAX)&255==bool(return_pointer)
        assert all(uc.reg_read(reg)==value for reg,value in saved.items())
        assert bytes(uc.mem_read(IDENTITY,64))==MATRIX
        return bytes(uc.mem_read(HEAP,0x40000)),self.trace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe',type=Path)
    ap.add_argument('--object',type=Path,default=ROOT/'build/game/skeleton_input.obj')
    ap.add_argument('--report',type=Path,default=ROOT/'build/skeleton-input/behavior.json')
    args=ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):ap.error('report must stay private')
    raw,pe=load_reference(args.exe);obj=ObjFile(str(args.object));functions={}
    for name in FUNCTIONS:
        found=[f for f in obj.functions if demangle(f.name)==name]
        assert len(found)==1,name
        functions[name]=found[0]
    runners=[Runner(pe,functions,rebuilt) for rebuilt in (False,True)]
    rng=random.Random(0x49a040);cases=[]
    fixtures=[]
    for count in (1,2,3,16):
        for version in (0,0x126,0x127,0xffffffff):
            for root_id in (0,0xffff):
                for result in (0,ROOT_BONE+0xb0,0xffffffff):fixtures.append((count,version,root_id,result))
    for count in (255,256,257):
        for root_id in (0,0xffff):
            for result in (0,ROOT_BONE+count*0xb0):fixtures.append((count,0x127,root_id,result))
    for count,version,root_id,result in fixtures:
        memory=bytearray(rng.randbytes(0x40000))
        struct.pack_into('<I',memory,STREAM-HEAP,VTABLE)
        struct.pack_into('<I',memory,VTABLE+8-HEAP,READ)
        want=expected(bytes(memory),count,bool(result))
        assert all(r.run(bytes(memory),count,version,root_id,result)==want for r in runners),(count,version,root_id,result)
        cases.append(dict(count=count,version=version,serialized_root_id=root_id,recursive_return=result,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),object_sha256={args.object.name:hashlib.sha256(args.object.read_bytes()).hexdigest()},scope=__doc__,mocks=['aligned malloc','ReadSkeletonName','virtual stream Read','RuntimeBone::ReadInput','RuntimeBone::Transform'],exclusions=['zero counts','allocation failures/overflow','real recursive topology and transforms','string ownership','physical I/O','gameplay'],cases=cases),indent=2)+'\n')
    print('Passed %d skeleton-input differential cases'%len(cases))


if __name__=='__main__':main()
