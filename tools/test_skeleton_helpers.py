#!/usr/bin/env python3
"""Bone name ownership and parent lookup against independent x86 fixtures.

String allocation/free are mocked; alias cases establish call ordering without
dereferencing freed storage. Parent lookup uses record-relative byte indices,
not the owner pointer. No original asset or running game is needed.
"""
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

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
OBJECT, OLD, SOURCE, COPIED = HEAP+0x10000, HEAP+0x200, HEAP+0x400, HEAP+0x600
FREE, COPY = STOP+0x100, STOP+0x200
TARGETS = {'BoneInfo::SetName': 0x491ab0, 'RuntimeBone::GetParent': 0x492720}


class Runner:
    def __init__(self, pe, name, function=None):
        self.name = name
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base, (len(image)+4095)&~4095)
        uc.mem_write(base, image)
        for address, size in ((CODE, 0x1000), (HEAP, 0x20000),
                              (STACK, 0x10000), (STOP, 0x1000)):
            uc.mem_map(address, size)
        self.entry = CODE if function else TARGETS[name]
        self.free = FREE if function else 0x6a6e30
        self.copy = COPY if function else 0x6a6e10
        if function:
            symbols = {}
            for _, _, symbol, _ in function.relocs():
                target = {'FreeFileName': FREE, 'CopyFileName': COPY}.get(demangle(symbol))
                assert target is not None, symbol
                symbols[symbol] = target
            uc.mem_write(CODE, relocate(function, CODE, symbols))
        uc.mem_write(self.free, b'\xc3')
        uc.mem_write(self.copy, b'\xc3')
        uc.hook_add(UC_HOOK_CODE, self.callback)

    def callback(self, uc, address, size, user):
        if address not in (self.free, self.copy):
            return
        assert self.name == 'BoneInfo::SetName'
        sp = uc.reg_read(UC_X86_REG_ESP)
        current = struct.unpack('<I', uc.mem_read(OBJECT+0x5c, 4))[0]
        if address == self.free:
            args = struct.unpack('<III', uc.mem_read(sp+4, 12))
            self.trace.append(['free', *args, current])
        else:
            args = struct.unpack('<II', uc.mem_read(sp+4, 8))
            self.trace.append(['copy', *args, current])
        # Callers may not rely on volatile registers surviving either helper.
        uc.reg_write(UC_X86_REG_EAX, self.allocated if address == self.copy else 0xdeadc0de)
        uc.reg_write(UC_X86_REG_ECX, 0x11223344)
        uc.reg_write(UC_X86_REG_EDX, 0x55667788)

    def run(self, memory, source=0, allocated=0):
        self.trace, self.allocated = [], allocated
        uc = self.uc
        uc.mem_write(HEAP, memory)
        uc.mem_write(STACK, b'\xa5'*0x10000)
        sp = STACK+0x8000
        uc.mem_write(sp, struct.pack('<II', STOP, source))
        saved = {UC_X86_REG_EBX: 0x12345678, UC_X86_REG_ESI: 0x23456789,
                 UC_X86_REG_EDI: 0x3456789a, UC_X86_REG_EBP: 0x456789ab}
        for reg, value in saved.items():
            uc.reg_write(reg, value)
        uc.reg_write(UC_X86_REG_ECX, OBJECT)
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_EFLAGS, 2)
        uc.emu_start(self.entry, STOP, count=200)
        assert uc.reg_read(UC_X86_REG_EIP) == STOP
        assert uc.reg_read(UC_X86_REG_ESP) == sp+(8 if self.name == 'BoneInfo::SetName' else 4)
        assert all(uc.reg_read(reg) == value for reg, value in saved.items())
        result = uc.reg_read(UC_X86_REG_EAX) if self.name == 'RuntimeBone::GetParent' else None
        return bytes(uc.mem_read(HEAP, 0x20000)), self.trace, result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--object', type=Path, default=ROOT/'build/game/skeleton_input.obj')
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('reports must stay private')
    raw, pe = load_reference(args.exe)
    obj = ObjFile(str(args.object))
    runners = {}
    for name in TARGETS:
        functions = [f for f in obj.functions if demangle(f.name) == name]
        assert len(functions) == 1, name
        runners[name] = [Runner(pe, name), Runner(pe, name, functions[0])]
    rng = random.Random(0x492720)
    cases = []
    for old, source, allocated, poison in itertools.product(
            (0, OLD), (0, OLD, OLD+1, SOURCE), (0, COPIED, OLD), (0, 0xff, None)):
        memory = bytearray(rng.randbytes(0x20000) if poison is None else bytes([poison])*0x20000)
        struct.pack_into('<I', memory, OBJECT-HEAP+0x5c, old)
        want = bytearray(memory)
        struct.pack_into('<I', want, OBJECT-HEAP+0x5c, allocated if source else 0)
        trace = []
        if old:
            trace.append(['free', old, 8, 1, old])
        if source:
            trace.append(['copy', source, 8, 0])
        expected = bytes(want), trace, None
        for runner in runners['BoneInfo::SetName']:
            assert runner.run(bytes(memory), source, allocated) == expected, (old, source, allocated, poison)
        cases.append(dict(kind='name', old=old, source=source, allocated=allocated, poison=poison, passed=True))
    for index, parent in itertools.product((0, 1, 127, 254, 255), range(256)):
        memory = bytearray(rng.randbytes(0x20000))
        # Deliberately unusable owner proves that lookup does not follow it.
        struct.pack_into('<I', memory, OBJECT-HEAP+0xa8, 0xdeadbeef)
        memory[OBJECT-HEAP+0xac] = index
        memory[OBJECT-HEAP+0xad] = parent
        result = 0 if parent == 255 else OBJECT+(parent-index)*0xb0
        expected = bytes(memory), [], result
        for runner in runners['RuntimeBone::GetParent']:
            assert runner.run(bytes(memory)) == expected, (index, parent)
        cases.append(dict(kind='parent', index=index, parent=parent, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(
        binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={args.object.name: hashlib.sha256(args.object.read_bytes()).hexdigest()},
        scope=__doc__, cases=cases,
        mocks=['FreeFileName', 'CopyFileName'],
        exclusions=['actual allocation/free/copy', 'dereference of freed aliases',
                    'invalid object pointers', 'actual skeleton loading', 'gameplay']), indent=2)+'\n')
    print('Passed %d skeleton-helper differential cases' % len(cases))


if __name__ == '__main__':
    main()
