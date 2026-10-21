#!/usr/bin/env python3
"""Original/rebuilt mesh-unload policy with independent expected heap/call/ABI checks.

Extends the external audit's 768 original-only fixtures to reconstructed C++.
The global cleanup and two virtual endpoints are mocks, not real deletion.
Field names/count/ownership interpretations and actual gameplay remain unresolved.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EDX, UC_X86_REG_EIP,
    UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EFLAGS)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
MESH, OWNER, TABLE, MANAGER = (HEAP+n for n in (0x100,0x400,0x700,0x900))
DTOR, CLEAN = STOP+0x100, STOP+0x110
ORIGINAL, GLOBAL = 0x454f70, 0x40eea0
SYMBOL = 'EMeshManager::Destroy'


def fixture(s):
    memory = bytearray(b'\xa5'*0x1000)
    def put(a,n): struct.pack_into('<I', memory, a-HEAP, n)
    mask = s['mask']
    put(MESH,TABLE)
    put(MESH+8,0xffffffff if mask&1 else s['initial'])
    put(MESH+0x18,OWNER)
    high = 0x80000000 if s['low']==31 else 32
    put(MESH+0x3c,(high if mask&2 else 0)|s['low'])
    put(MESH+0x48,(high if mask&4 else 0)|s['low'])
    put(OWNER+0x80,1 if mask&8 else 0)
    put(MESH+0x60,1 if mask&16 else 0)
    put(OWNER+0xa0,1 if mask&32 else 0)
    put(TABLE,DTOR)
    put(TABLE+8,CLEAN)
    return memory


def expected(s):
    memory = fixture(s)
    if not s['mask']:
        events = ['delete(1)']
    else:
        events = ['global-cleanup','virtual+8']
        struct.pack_into('<I',memory,MESH+8-HEAP,s['post'])
        if s['post'] not in (0,0xffffffff):
            events.append('delete(1)')
    return bytes(memory),events


class Runner:
    def __init__(self,pe,function,rebuilt):
        self.uc = uc = Uc(UC_ARCH_X86,UC_MODE_32)
        image,base = pe.get_memory_mapped_image(),pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base,(len(image)+4095)&~4095)
        uc.mem_write(base,image)
        for a,n in ((CODE,0x1000),(HEAP,0x1000),(STACK,0x10000),(STOP,0x1000)):
            uc.mem_map(a,n)
        self.entry = CODE if rebuilt else ORIGINAL
        if rebuilt:
            uc.mem_write(CODE,relocate(function,CODE,{'?DetachMeshForUnload@@YAXPAVETriggerA8@@@Z':GLOBAL}))
        uc.mem_write(DTOR,b'\xc2\x04\x00')
        uc.mem_write(CLEAN,b'\xc3')
        uc.mem_write(GLOBAL,b'\xc3')
        uc.hook_add(UC_HOOK_CODE,self.callback)

    def callback(self,uc,address,size,user):
        if address not in (GLOBAL,DTOR,CLEAN):
            return
        sp = uc.reg_read(UC_X86_REG_ESP)
        if address==GLOBAL:
            assert struct.unpack('<I',uc.mem_read(sp+4,4))[0]==MESH
            self.events.append('global-cleanup')
        elif address==CLEAN:
            assert uc.reg_read(UC_X86_REG_ECX)==MESH
            self.events.append('virtual+8')
            uc.mem_write(MESH+8,struct.pack('<I',self.s['post']))
        else:
            assert uc.reg_read(UC_X86_REG_ECX)==MESH
            assert struct.unpack('<I',uc.mem_read(sp+4,4))[0]==1
            self.events.append('delete(1)')
        for reg,n in [(UC_X86_REG_EAX,0x12345678),(UC_X86_REG_ECX,0x87654321),(UC_X86_REG_EDX,0x24681357)]:
            uc.reg_write(reg,n)

    def run(self,s):
        self.s,self.events = s,[]
        uc = self.uc
        uc.mem_write(HEAP,bytes(fixture(s)))
        uc.mem_write(STACK,b'\xa5'*0x10000)
        sp = STACK+0x8000
        uc.mem_write(sp,struct.pack('<II',STOP,MESH))
        saved = {UC_X86_REG_EBX:0x11223344,UC_X86_REG_ESI:0x55667788,
            UC_X86_REG_EDI:0x99aabbcc,UC_X86_REG_EBP:0xddeeff00}
        for r,v in saved.items(): uc.reg_write(r,v)
        uc.reg_write(UC_X86_REG_ESP,sp)
        uc.reg_write(UC_X86_REG_ECX,MANAGER)
        uc.reg_write(UC_X86_REG_EFLAGS,2)
        uc.emu_start(self.entry,STOP,count=1000)
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+8
        assert all(uc.reg_read(r)==v for r,v in saved.items())
        return bytes(uc.mem_read(HEAP,0x1000)),self.events


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe',type=Path)
    ap.add_argument('--report',type=Path,default=ROOT/'build/mesh-unload/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):
        ap.error('report must stay under ignored build/ or .local/')
    raw,pe = load_reference(args.exe)
    path = ROOT/'build/game/mesh.obj'
    fns = [f for f in ObjFile(str(path)).functions if demangle(f.name)==SYMBOL]
    assert len(fns)==1
    original,rebuilt = Runner(pe,fns[0],False),Runner(pe,fns[0],True)
    cases = []
    for mask,initial,post,low in itertools.product(range(64),(0,HEAP+0xb00),(0,0xffffffff,HEAP+0xc00),(0,31)):
        s = dict(mask=mask,initial=initial,post=post,low=low)
        want,a,b = expected(s),original.run(s),rebuilt.run(s)
        assert a==b==want,(s,a[1],b[1],want[1])
        cases.append(dict(s,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest()},scope=__doc__,cases=cases),indent=2)+'\n')
    print('Passed %d mesh-unload differential cases'%len(cases))


if __name__=='__main__': main()
