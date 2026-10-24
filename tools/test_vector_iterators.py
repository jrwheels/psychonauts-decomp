#!/usr/bin/env python3
"""Original/rebuilt compiler-generated vector iterator behavioral fixtures.

Constructor/destructor endpoints are mocked and clobber volatile registers.
Checks cover bounded signed counts, callback order/receiver, strides and ABI.
Element construction, destruction, exceptions/unwinding, huge counts, arithmetic
wraparound and gameplay are excluded. These are compiler-generated helpers,
not independently reconstructed engine methods; void return values are ignored.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EDI, UC_X86_REG_EIP,
    UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EFLAGS)
from coff import ObjFile
from native_index import load_reference

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
CALLBACK = STOP+0x100
HELPERS = {
    'constructor': (0x401820, '??_H@YGXPAXIHP6EPAX0@Z@Z'),
    'destructor': (0x4011f0, '??_I@YGXPAXIHP6EX0@Z@Z')}


class Runner:
    def __init__(self, pe, functions, rebuilt):
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base, (len(image)+4095) & ~4095)
        uc.mem_write(base, image)
        for address, size in ((CODE, 0x2000), (HEAP, 0x4000),
                              (STACK, 0x10000), (STOP, 0x1000)):
            uc.mem_map(address, size)
        self.entries = {}
        for index, (kind, (original, symbol)) in enumerate(HELPERS.items()):
            self.entries[kind] = CODE+index*0x1000 if rebuilt else original
            if rebuilt:
                function = functions[symbol]
                assert not list(function.relocs())
                uc.mem_write(self.entries[kind], function.code)
        uc.mem_write(CALLBACK, b'\xc3')
        uc.hook_add(UC_HOOK_CODE, self.hook)

    def hook(self, uc, address, size, user):
        if address == CALLBACK:
            self.trace.append(uc.reg_read(UC_X86_REG_ECX))
            sp = uc.reg_read(UC_X86_REG_ESP)
            assert STACK <= sp < STACK+0x10000
            uc.reg_write(UC_X86_REG_EAX, 0xdeadbeef)
            uc.reg_write(UC_X86_REG_ECX, 0x87654321)
            uc.reg_write(UC_X86_REG_EDX, 0xfedcba98)

    def run(self, kind, pointer, stride, count):
        uc = self.uc
        self.trace = []
        memory = bytes(range(256))*64
        uc.mem_write(HEAP, memory)
        uc.mem_write(STACK, b'\xa5'*0x10000)
        sp = STACK+0x8000
        uc.mem_write(sp, struct.pack('<IIIiI', STOP, pointer, stride, count, CALLBACK))
        saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
        for reg, value in saved.items():
            uc.reg_write(reg, value)
        uc.reg_write(UC_X86_REG_ECX, 0xaabbccdd)
        uc.reg_write(UC_X86_REG_EAX, 0x11223344)
        uc.reg_write(UC_X86_REG_EDX, 0x55667788)
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_EFLAGS, 2)
        uc.emu_start(self.entries[kind], STOP, count=2000)
        assert uc.reg_read(UC_X86_REG_EIP) == STOP
        assert uc.reg_read(UC_X86_REG_ESP) == sp+20
        assert all(uc.reg_read(reg) == value for reg, value in saved.items())
        assert bytes(uc.mem_read(HEAP, len(memory))) == memory
        return self.trace


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--object', type=Path, default=ROOT/'build/game/skeleton_input.obj')
    ap.add_argument('--report', type=Path, default=ROOT/'build/vector-iterators/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    raw, pe = load_reference(args.exe)
    symbols = {symbol for original, symbol in HELPERS.values()}
    functions = {f.name: f for f in ObjFile(str(args.object)).functions if f.name in symbols}
    assert functions.keys() == symbols
    runners = [Runner(pe, functions, rebuilt) for rebuilt in (False, True)]
    cases = []
    for kind, pointer, stride, count in itertools.product(HELPERS,
            (HEAP+0x100, HEAP+0x2000), (0, 1, 4, 12, 68), (-3, -1, 0, 1, 2, 5, 17)):
        # Independent closed-form expected addresses, not a transcription of the
        # helper's mutable pointer/count loops. Negative counts call no endpoint.
        indices = list(range(max(0, count)))
        if kind == 'destructor':
            indices.reverse()
        expected = [pointer+i*stride for i in indices]
        assert all(runner.run(kind, pointer, stride, count) == expected for runner in runners)
        cases.append(dict(kind=kind, pointer=pointer, stride=stride,
                          count=count, expected_callbacks=expected, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={args.object.name: hashlib.sha256(args.object.read_bytes()).hexdigest()},
        scope=__doc__, cases=cases), indent=2)+'\n')
    print('Passed %d vector-iterator differential cases' % len(cases))


if __name__ == '__main__':
    main()
