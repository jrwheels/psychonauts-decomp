#!/usr/bin/env python3
"""Animation array Resize differential fixtures; Reserve/allocation are mocks."""
import argparse
import hashlib
import itertools
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
ARRAY,OLD,NEW=HEAP+0x100,HEAP+0x1000,HEAP+0x3000
RESERVE=0x408960
TARGETS=[('UAnimationTrackSet::?$AnimationArray::Resize',0x498f50,16,True),
         ('UAnimationTrack::?$AnimationArray::Resize',0x4991c0,8,True),
         ('E::?$AnimationArray::Resize',0x499920,1,False)]


def reserve_model(memory,element_size,requested):
    """Mock ownership operation: fresh poisoned buffer, bounded preserved prefix."""
    memory=bytearray(memory)
    word,capacity,pointer=struct.unpack_from('<III',memory,ARRAY-HEAP)
    previous_count=word>>5
    count=min(previous_count,requested)
    # Huge byte-only requests have zero old count; no inaccessible bytes copied.
    assert count*element_size<=0x1000
    allocated=min(requested*element_size,0x1000)
    memory[NEW-HEAP:NEW-HEAP+allocated]=b'\xcd'*allocated
    preserved=memory[pointer-HEAP:pointer-HEAP+count*element_size]
    memory[NEW-HEAP:NEW-HEAP+len(preserved)]=preserved
    struct.pack_into('<III',memory,ARRAY-HEAP,(word&31)|((count&0x7ffffff)<<5),
                     (capacity&1)|((requested&0x7fffffff)<<1),NEW if requested else 0)
    return bytes(memory)


def expected(memory,element_size,is_class,requested,exact):
    """Compute branch effects from the public container state, independently."""
    word,capacity,_=struct.unpack_from('<III',memory,ARRAY-HEAP)
    old_count=word>>5; old_capacity=capacity>>1
    needs_reserve=False; reserve_count=None
    if not is_class or requested>old_count:
        needs_reserve=bool(exact) or requested>old_capacity
        if needs_reserve:
            spare=0 if exact else ((((requested*3)&0xffffffff)>>3)+16)
            reserve_count=(requested+spare)&0xffffffff
    elif requested<old_count and exact:
        needs_reserve=True; reserve_count=requested
        # Class shrinking stores the smaller count before Reserve.
        memory=bytearray(memory)
        struct.pack_into('<I',memory,ARRAY-HEAP,(word&31)|((requested&0x7ffffff)<<5))
        memory=bytes(memory)
    trace=[]
    if needs_reserve:
        trace=[(element_size,reserve_count)]
        memory=reserve_model(memory,element_size,reserve_count)
    if not is_class or requested!=old_count:
        memory=bytearray(memory)
        current=struct.unpack_from('<I',memory,ARRAY-HEAP)[0]
        struct.pack_into('<I',memory,ARRAY-HEAP,(current&31)|((requested&0x7ffffff)<<5))
        memory=bytes(memory)
    return memory,trace


class Runner:
    def __init__(self,pe,function,target,rebuilt):
        self.target=target; self.uc=uc=Uc(UC_ARCH_X86,UC_MODE_32)
        image,base=pe.get_memory_mapped_image(),pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base,(len(image)+4095)&~4095); uc.mem_write(base,image)
        for address,size in ((CODE,0x2000),(HEAP,0x8000),(STACK,0x10000),(STOP,0x1000)):
            uc.mem_map(address,size)
        self.entry=CODE if rebuilt else target[1]
        if rebuilt:
            symbols={}
            for _,_,name,_ in function.relocs():
                assert demangle(name)=='EArrayBase::Reserve',name
                symbols[name]=RESERVE
            uc.mem_write(CODE,relocate(function,CODE,symbols))
        uc.mem_write(RESERVE,b'\xc2\x08\x00')
        uc.hook_add(UC_HOOK_CODE,self.callback)

    def callback(self,uc,address,size,user):
        if address!=RESERVE:return
        assert uc.reg_read(UC_X86_REG_ECX)==ARRAY
        sp=uc.reg_read(UC_X86_REG_ESP)
        element_size,count=struct.unpack('<II',uc.mem_read(sp+4,8))
        assert element_size==self.target[2]
        self.trace.append((element_size,count))
        actual=bytes(uc.mem_read(HEAP,0x8000))
        uc.mem_write(HEAP,reserve_model(actual,element_size,count))
        uc.reg_write(UC_X86_REG_EAX,0xdeadbeef)
        uc.reg_write(UC_X86_REG_ECX,0x12345678)
        uc.reg_write(UC_X86_REG_EDX,0x87654321)

    def run(self,memory,count,exact):
        uc=self.uc;self.trace=[]
        uc.mem_write(HEAP,memory);uc.mem_write(STACK,b'\xa5'*0x10000)
        sp=STACK+0x8000;uc.mem_write(sp,struct.pack('<III',STOP,count,exact))
        saved={UC_X86_REG_EBX:0x12345678,UC_X86_REG_ESI:0x23456789,UC_X86_REG_EDI:0x3456789a,UC_X86_REG_EBP:0x456789ab}
        for reg,value in saved.items():uc.reg_write(reg,value)
        uc.reg_write(UC_X86_REG_ECX,ARRAY);uc.reg_write(UC_X86_REG_ESP,sp);uc.reg_write(UC_X86_REG_EFLAGS,2)
        uc.emu_start(self.entry,STOP,count=15000)
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+12
        assert all(uc.reg_read(reg)==value for reg,value in saved.items())
        return bytes(uc.mem_read(HEAP,0x8000)),self.trace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe',type=Path)
    ap.add_argument('--object',type=Path,default=ROOT/'build/game/animation_stub.obj')
    ap.add_argument('--report',type=Path,default=ROOT/'build/animation-resize/behavior.json')
    args=ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):ap.error('report must stay private')
    raw,pe=load_reference(args.exe);obj=ObjFile(str(args.object));rng=random.Random(0x499920);cases=[]
    for target in TARGETS:
        found=[f for f in obj.functions if demangle(f.name)==target[0]]
        assert len(found)==1,target[0]
        runners=[Runner(pe,found[0],target,rebuilt) for rebuilt in (False,True)]
        fixtures=[]
        for old_count,capacity in ((0,0),(0,8),(1,1),(3,8),(8,8),(8,16),(16,8)):
            for requested in sorted({0,1,old_count,max(0,old_count-1),old_count+1,capacity,capacity+1,31}):
                for exact in (0,1):fixtures.append((old_count,capacity,requested,exact))
        fixtures += [(rng.randrange(33),rng.randrange(65),rng.randrange(65),rng.randrange(2)) for _ in range(64)]
        if not target[3]:
            fixtures += [(0,0,value,exact) for value in (0x7ffffff,0x8000000,0x1fffffff,0x55555555,0x7fffffff,0x80000000,0xffffffff) for exact in (0,1)]
        for index,(old_count,capacity,requested,exact) in enumerate(fixtures):
            memory=bytearray(rng.randbytes(0x8000))
            struct.pack_into('<III',memory,ARRAY-HEAP,(old_count<<5)|rng.randrange(32),(capacity<<1)|rng.randrange(2),OLD)
            want=expected(bytes(memory),target[2],target[3],requested,exact)
            assert all(r.run(bytes(memory),requested,exact)==want for r in runners),(target,old_count,capacity,requested,exact)
            cases.append(dict(kind=target[0],old_count=old_count,capacity=capacity,requested=requested,exact=exact,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),object_sha256={args.object.name:hashlib.sha256(args.object.read_bytes()).hexdigest()},scope=__doc__,mocks=['EArrayBase::Reserve','aligned allocation/free'],exclusions=['real allocator failures/physical ownership','nontrivial constructors/destructors','huge class loops','huge allocations beyond bounded poisoned prefix','gameplay'],cases=cases),indent=2)+'\n')
    print('Passed %d animation-array Resize differential cases'%len(cases))


if __name__=='__main__':main()
