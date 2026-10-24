#!/usr/bin/env python3
"""Array-storage swap differential fixtures; no dependencies or mocked calls.

Checks packed category/count and flag/capacity fields, arbitrary data-pointer
values, self aliasing, complete fixture memory and the cdecl preserved ABI.
Invalid pointers and partially overlapping objects are excluded.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP,
    UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EDX,
    UC_X86_REG_EFLAGS, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
FIRST, SECOND, ORIGINAL = HEAP+0x100, HEAP+0x240, 0x41f450


def record(category, count, flag, capacity, data):
    """Independent serialization of the documented complete 12-byte layout."""
    assert 0 <= category < 32 and 0 <= count < 1 << 27
    assert flag in (0, 1) and 0 <= capacity < 1 << 31
    return struct.pack('<III', category+count*32, flag+capacity*2, data)


def fixture(first, second, alias):
    before = bytearray(b'\xa5'*0x1000)
    before[FIRST-HEAP:FIRST-HEAP+12] = first
    before[SECOND-HEAP:SECOND-HEAP+12] = second
    expected = bytearray(before)
    if not alias:
        # The specification exchanges complete storage descriptors. All bits of
        # both packed words belong to fields, so no unowned padding is involved.
        expected[FIRST-HEAP:FIRST-HEAP+12] = second
        expected[SECOND-HEAP:SECOND-HEAP+12] = first
    return bytes(before), bytes(expected)


class Runner:
    def __init__(self, pe, function, rebuilt):
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base, (len(image)+4095)&~4095)
        uc.mem_write(base, image)
        for address, size in ((CODE, 0x1000), (HEAP, 0x1000),
                              (STACK, 0x10000), (STOP, 0x1000)):
            uc.mem_map(address, size)
        self.entry = CODE if rebuilt else ORIGINAL
        if rebuilt:
            assert not list(function.relocs()), 'swap must have no relocations'
            uc.mem_write(CODE, function.code)

    def run(self, before, expected, alias):
        uc = self.uc
        uc.mem_write(HEAP, before)
        uc.mem_write(STACK, b'\xa5'*0x10000)
        sp = STACK+0x8000
        arguments = struct.pack('<II', FIRST, FIRST if alias else SECOND)
        uc.mem_write(sp, struct.pack('<I', STOP)+arguments)
        saved = {UC_X86_REG_EBX: 0x11223344, UC_X86_REG_ESI: 0x55667788,
                 UC_X86_REG_EDI: 0x99aabbcc, UC_X86_REG_EBP: 0xddeeff00}
        for reg, value in saved.items():
            uc.reg_write(reg, value)
        for reg, value in ((UC_X86_REG_EAX, 0x12345678),
                           (UC_X86_REG_ECX, 0x87654321),
                           (UC_X86_REG_EDX, 0xfedcba98)):
            uc.reg_write(reg, value)
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_EFLAGS, 2)
        uc.emu_start(self.entry, STOP, count=1000)
        assert uc.reg_read(UC_X86_REG_EIP) == STOP
        assert uc.reg_read(UC_X86_REG_ESP) == sp+4, 'cdecl caller owns arguments'
        assert all(uc.reg_read(reg) == value for reg, value in saved.items())
        assert bytes(uc.mem_read(sp+4, 8)) == arguments
        assert bytes(uc.mem_read(HEAP, 0x1000)) == expected
        # void return: volatile registers and stack-local residue are unspecified.


def scenarios():
    for values in itertools.product((0, 1, 16, 31), (0, 1, 1 << 26, (1 << 27)-1),
                                   (0, 1), (0, 1, 1 << 30, (1 << 31)-1),
                                   (0, 1, 0xffffffff, HEAP+0x800)):
        category, count, flag, capacity, data = values
        first = record(*values)
        second = record(31-category, (1 << 27)-1-count, 1-flag,
                        (1 << 31)-1-capacity, data ^ 0xffffffff)
        for alias in (False, True):
            yield 'boundary', first, second, alias
    rng = random.Random(0x41f450)
    for _ in range(128):
        descriptors = [record(rng.randrange(32), rng.randrange(1 << 27),
                              rng.randrange(2), rng.randrange(1 << 31),
                              rng.randrange(1 << 32)) for _ in range(2)]
        for alias in (False, True):
            yield 'random', *descriptors, alias


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--object', type=Path, default=ROOT/'build/game/resource_array.obj')
    ap.add_argument('--report', type=Path, default=ROOT/'build/resource-array/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    raw, pe = load_reference(args.exe)
    functions = [f for f in ObjFile(str(args.object)).functions
                 if demangle(f.name) == 'SwapResourceArrays']
    assert len(functions) == 1
    runners = [Runner(pe, functions[0], rebuilt) for rebuilt in (False, True)]
    cases = []
    for kind, first, second, alias in scenarios():
        before, expected = fixture(first, second, alias)
        for runner in runners:
            runner.run(before, expected, alias)
        cases.append(dict(kind=kind, first=first.hex(), second=second.hex(),
                          alias=alias, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={args.object.name: hashlib.sha256(args.object.read_bytes()).hexdigest()},
        scope=__doc__, cases=cases), indent=2)+'\n')
    print('Passed %d resource-array-swap differential cases' % len(cases))


if __name__ == '__main__':
    main()
