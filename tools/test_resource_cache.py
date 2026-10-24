#!/usr/bin/env python3
"""Cache lookup differential fixtures; Find is mocked, hash/ownership/I/O excluded."""
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
CACHE, HANDLE, ENTRIES, NAME = [HEAP+n for n in (0x100, 0x200, 0x300, 0x800)]
FIND, ORIGINAL = 0x6a66a0, 0x6a6510


def fixture(index, flag):
    memory = bytearray(b'\xa5'*0x1000)
    struct.pack_into('<I', memory, CACHE+8-HEAP, ENTRIES)
    struct.pack_into('<I', memory, HANDLE-HEAP, index | flag << 31)
    for i in range(16):
        struct.pack_into('<III', memory, ENTRIES+i*12-HEAP,
                         0x11110000+i, (0, 1, 0xffffffff, HEAP+0x900)[i % 4], 0xdddd0000+i)
    memory[NAME-HEAP:NAME-HEAP+5] = b'name\0'
    return bytes(memory)


class Runner:
    def __init__(self, pe, function, rebuilt):
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base, (len(image)+4095)&~4095)
        uc.mem_write(base, image)
        for address, size in ((CODE, 0x1000), (HEAP, 0x1000), (STACK, 0x10000), (STOP, 0x1000)):
            uc.mem_map(address, size)
        self.entry = CODE if rebuilt else ORIGINAL
        if rebuilt:
            symbols = {name:FIND for _,_,name,_ in function.relocs()}
            uc.mem_write(CODE, relocate(function, CODE, symbols))
        uc.mem_write(FIND, b'\xc2\x08\x00')
        uc.hook_add(UC_HOOK_CODE, self.callback)

    def callback(self, uc, address, size, user):
        if address != FIND:
            return
        sp = uc.reg_read(UC_X86_REG_ESP)
        assert uc.reg_read(UC_X86_REG_ECX) == CACHE
        assert struct.unpack('<II', uc.mem_read(sp+4, 8)) == (self.name, 0)
        self.calls += 1
        uc.reg_write(UC_X86_REG_EAX, HANDLE if self.hit else 0)
        uc.reg_write(UC_X86_REG_ECX, 0xdeadbeef)
        uc.reg_write(UC_X86_REG_EDX, 0x87654321)

    def run(self, hit, index, flag, fallback, name):
        self.hit, self.name, self.calls = hit, name, 0
        uc = self.uc
        memory = fixture(index, flag)
        uc.mem_write(HEAP, memory)
        uc.mem_write(STACK, b'\xa5'*0x10000)
        sp = STACK+0x8000
        uc.mem_write(sp, struct.pack('<III', STOP, name, fallback))
        saved = {UC_X86_REG_EBX:0x11223344, UC_X86_REG_ESI:0x55667788,
                 UC_X86_REG_EDI:0x99aabbcc, UC_X86_REG_EBP:0xddeeff00}
        for reg, value in saved.items():
            uc.reg_write(reg, value)
        uc.reg_write(UC_X86_REG_ECX, CACHE)
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_EFLAGS, 2)
        uc.emu_start(self.entry, STOP, count=1000)
        assert uc.reg_read(UC_X86_REG_EIP) == STOP
        assert uc.reg_read(UC_X86_REG_ESP) == sp+12
        assert all(uc.reg_read(reg) == value for reg, value in saved.items())
        assert self.calls == 1
        assert bytes(uc.mem_read(HEAP, 0x1000)) == memory
        return uc.reg_read(UC_X86_REG_EAX)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/cache-lookup/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    raw, pe = load_reference(args.exe)
    path = ROOT/'build/game/resource_cache.obj'
    functions = [f for f in ObjFile(str(path)).functions if demangle(f.name) == 'ResourceCache::Lookup']
    assert len(functions) == 1
    runners = [Runner(pe, functions[0], rebuilt) for rebuilt in (False, True)]
    cases = []
    for hit,index,flag,fallback,name in itertools.product((False,True),range(16),(0,1),(0,1,0xffffffff,HEAP+0xa00),(0,NAME)):
        # Independent expected values distinguish hit-null from miss-fallback.
        want = (0,1,0xffffffff,HEAP+0x900)[index % 4] if hit else fallback
        assert all(r.run(hit,index,flag,fallback,name) == want for r in runners)
        cases.append(dict(hit=hit,index=index,flag=flag,fallback=fallback,name=name,passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest()},
        scope=__doc__, cases=cases), indent=2)+'\n')
    print('Passed %d resource-cache differential cases' % len(cases))


if __name__ == '__main__':
    main()
