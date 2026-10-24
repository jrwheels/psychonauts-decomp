#!/usr/bin/env python3
"""Animation header/budget differential fixtures; stream and file Seek are mocks."""
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

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
OBJECT, READER, FILE, VTABLE = (HEAP+x for x in (0x100,0x300,0x400,0x500))
READ, SEEK = 0x40aeb0, HEAP+0x800
TARGETS = {'AnimationStub::ReadHeader':0x4962c0, 'AnimationStub::RecalculateBytes':0x496430}


def expected_header(memory, chunks):
    """Decode only the serialized format; untouched bytes retain fixture values."""
    result = bytearray(memory)
    version = struct.unpack('<I', (chunks[1]+b'\xa5'*4)[:4])[0]
    start = OBJECT-HEAP
    if version == 200:
        tail = (chunks[2]+b'\xa5'*72)[:72]
        fields = bytes(tail[p-8] for p in (0x24,0x28,0x2c,0x30))
        result[start:start+24] = struct.pack('<I',200)+fields+tail[0x38:0x48]
    elif version == 201:
        tail = (chunks[2]+b'\xa5'*10)[:10]
        flags, field26 = struct.unpack('<HH',tail[:4])
        result[start:start+24] = struct.pack('<I',201)+tail[5:9]+b'\0'*12+struct.pack('<I',flags|tail[4])
        result[start+0x26:start+0x28] = struct.pack('<H',field26)
    return bytes(result)


class Runner:
    def __init__(self, pe, function, name, rebuilt):
        self.name = name
        self.uc = uc = Uc(UC_ARCH_X86,UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base,(len(image)+4095)&~4095); uc.mem_write(base,image)
        for address,size in ((CODE,0x2000),(HEAP,0x1000),(STACK,0x10000),(STOP,0x1000)):
            uc.mem_map(address,size)
        self.entry = CODE if rebuilt else TARGETS[name]
        if rebuilt:
            symbols = {}
            for _,_,symbol,_ in function.relocs():
                assert 'ReadBytes' in demangle(symbol), symbol
                symbols[symbol] = READ
            uc.mem_write(CODE,relocate(function,CODE,symbols))
        uc.mem_write(READ,b'\xc2\x08\x00'); uc.mem_write(SEEK,b'\xc2\x08\x00')
        uc.hook_add(UC_HOOK_CODE,self.callback)

    def callback(self,uc,address,size,user):
        if address not in (READ,SEEK): return
        sp = uc.reg_read(UC_X86_REG_ESP)
        first,second = struct.unpack('<II',uc.mem_read(sp+4,8))
        if address == SEEK:
            assert uc.reg_read(UC_X86_REG_ECX)==FILE
            assert (first,second)==(0,1)
            self.trace.append(('seek',first,second))
            uc.reg_write(UC_X86_REG_EAX,0xface1234)
        else:
            assert uc.reg_read(UC_X86_REG_ECX)==READER
            assert self.trace and self.trace[0]==('seek',0,1)
            index = sum(item[0]=='read' for item in self.trace)
            expected_size = 4 if index<2 else (72 if self.version==200 else 10)
            assert second == expected_size
            payload = self.chunks[index]
            assert len(payload)<=second
            uc.mem_write(first,payload) if payload else None
            self.trace.append(('read',second,len(payload)))
            uc.reg_write(UC_X86_REG_EAX,len(payload))
        uc.reg_write(UC_X86_REG_ECX,0xdeadbeef)
        uc.reg_write(UC_X86_REG_EDX,0x12345678)

    def run(self,memory,chunks=None):
        uc=self.uc; self.chunks=chunks; self.trace=[]
        self.version=struct.unpack('<I',(chunks[1]+b'\xa5'*4)[:4])[0] if chunks else None
        uc.mem_write(HEAP,memory)
        uc.mem_write(SEEK,b'\xc2\x08\x00')
        uc.mem_write(STACK,b'\xa5'*0x10000)
        sp=STACK+0x8000
        uc.mem_write(sp,struct.pack('<II',STOP,READER))
        saved={UC_X86_REG_EBX:0x12345678,UC_X86_REG_ESI:0x23456789,UC_X86_REG_EDI:0x3456789a,UC_X86_REG_EBP:0x456789ab}
        for reg,value in saved.items(): uc.reg_write(reg,value)
        uc.reg_write(UC_X86_REG_ECX,OBJECT); uc.reg_write(UC_X86_REG_ESP,sp); uc.reg_write(UC_X86_REG_EFLAGS,2)
        uc.emu_start(self.entry,STOP,count=3000)
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+(8 if chunks else 4)
        assert all(uc.reg_read(reg)==value for reg,value in saved.items())
        if chunks:
            sizes=[4,4]+([72 if self.version==200 else 10] if self.version in (200,201) else [])
            assert self.trace==[('seek',0,1)]+[('read',n,len(chunks[i])) for i,n in enumerate(sizes)]
        else: assert not self.trace
        return bytes(uc.mem_read(HEAP,0x1000))


def fixture(rng):
    memory=bytearray(rng.randbytes(0x1000))
    struct.pack_into('<I',memory,READER+0x10-HEAP,FILE)
    struct.pack_into('<I',memory,FILE-HEAP,VTABLE)
    struct.pack_into('<I',memory,VTABLE+0x10-HEAP,SEEK)
    memory[SEEK-HEAP:SEEK-HEAP+3]=b'\xc2\x08\x00'
    return bytes(memory)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe',type=Path)
    ap.add_argument('--object',type=Path,default=ROOT/'build/game/animation_stub.obj')
    ap.add_argument('--report',type=Path,default=ROOT/'build/animation-header/behavior.json')
    args=ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')): ap.error('report must stay private')
    raw,pe=load_reference(args.exe)
    functions={}
    for name in TARGETS:
        found=[f for f in ObjFile(str(args.object)).functions if demangle(f.name)==name]
        assert len(found)==1,name
        functions[name]=[Runner(pe,found[0],name,rebuilt) for rebuilt in (False,True)]
    rng=random.Random(0x4962c0); cases=[]
    versions=(0,1,199,200,201,202,0xffffffff,0x80000000)
    for version in versions:
        for variant in range(32):
            memory=fixture(rng)
            tail=rng.randbytes(72 if version==200 else 10)
            # Boundaries include all-zero/all-one fields; magic remains arbitrary.
            if variant<2: tail=bytes([variant*255])*len(tail)
            chunks=[struct.pack('<I',rng.getrandbits(32)),struct.pack('<I',version),tail]
            want=expected_header(memory,chunks)
            assert all(r.run(memory,chunks)==want for r in functions['AnimationStub::ReadHeader'])
            cases.append(dict(kind='header',version=version,variant=variant,passed=True))
    for version in (200,201):
        size=72 if version==200 else 10
        for length in range(size):
            memory=fixture(rng); chunks=[b'',struct.pack('<I',version),rng.randbytes(length)]
            want=expected_header(memory,chunks)
            assert all(r.run(memory,chunks)==want for r in functions['AnimationStub::ReadHeader'])
            cases.append(dict(kind='short-tail',version=version,length=length,passed=True))
    for length in range(4):
        memory=fixture(rng); chunks=[b'\x99'*length,b'\0'*length,b'']
        want=expected_header(memory,chunks)
        assert all(r.run(memory,chunks)==want for r in functions['AnimationStub::ReadHeader'])
        cases.append(dict(kind='short-version',length=length,passed=True))
    boundaries=(0,1,2,0xffff,0xfffffff,0x10000000,0x1fffffff,0x40000000,0x7fffffff)
    capacities=[(a,b,c) for a in boundaries for b,c in ((a,a),(0,0),(0x7fffffff,1))]
    capacities += [tuple(rng.getrandbits(31) for _ in range(3)) for _ in range(256)]
    for index,values in enumerate(capacities):
        memory=bytearray(fixture(rng))
        for offset,capacity in zip((0x38,0x44,0x50),values):
            struct.pack_into('<I',memory,OBJECT+offset-HEAP,(capacity<<1)|rng.randrange(2))
        want=bytearray(memory)
        struct.pack_into('<I',want,OBJECT+0x20-HEAP,(16*values[0]+8*values[1]+values[2]+108)&0xffffffff)
        assert all(r.run(bytes(memory))==bytes(want) for r in functions['AnimationStub::RecalculateBytes'])
        cases.append(dict(kind='budget',capacities=values,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),object_sha256={args.object.name:hashlib.sha256(args.object.read_bytes()).hexdigest()},scope=__doc__,mocks=['EFileReader::ReadBytes','file virtual Seek'],exclusions=['physical I/O','actual file format validity','unread stack values outside poisoned fixture','ReadStub','gameplay'],cases=cases),indent=2)+'\n')
    print('Passed %d animation-header/budget differential cases' % len(cases))


if __name__=='__main__': main()
