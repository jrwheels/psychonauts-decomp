#!/usr/bin/env python3
"""Original/rebuilt CYSP string and dependency-list operations.

Stream transfers are bounded mocks, including incomplete length words and
oversized requests. These fixtures establish callback/heap/ABI behavior, not
complete CYSP parsing or filesystem behavior. All payloads are synthetic.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
TABLE, BUFFER, NODES, TRANSFER = HEAP+0x100, HEAP+0x1000, HEAP+0x2000, STOP+0x100
ORIGINAL = {'EStream::ReadString': 0x6a5d10, 'ResourceList::GetFromBack': 0x6a5620}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}


def signed(value):
    return value if value < 0x80000000 else value-0x100000000


def fixture(s):
    memory = bytearray(b'\xcc'*0x4000)
    if s['function']=='EStream::ReadString':
        struct.pack_into('<II', memory, 0, TABLE, s['mode'])
        struct.pack_into('<I', memory, TABLE-HEAP+8, TRANSFER)
        memory[BUFFER-HEAP:BUFFER-HEAP+6] = b'abcde\0'
    else:
        struct.pack_into('<I', memory, 0, s['count'])
        struct.pack_into('<I', memory, 0x10, NODES+(s['count']-1)*16 if s['count'] else 0)
        for i in range(s['count']):
            struct.pack_into('<III', memory, NODES-HEAP+i*16,
                NODES+(i-1)*16 if i else 0, NODES+(i+1)*16, 0x12340000+i)
    return memory


def expected(s):
    memory, trace, result = fixture(s), [], None
    if s['function']=='ResourceList::GetFromBack':
        result = NODES+(s['count']-1-s['index'])*16 if s['index'] < s['count'] else 0
    else:
        word = struct.pack('<I', s['length'])[:s['header_bytes']]
        if s['mode']==1:
            word = struct.pack('<I', 6)
            length = 6
        else:
            length = int.from_bytes(word+b'\xa5'*(4-len(word)), 'little')
        trace.append(['word', word.hex()])
        fits = length!=0 and signed(length) < signed(s['capacity'])
        trace.append(['data' if fits else 'skip', length])
        if fits and s['mode']!=1 and length <= 260:
            memory[BUFFER-HEAP:BUFFER-HEAP+length] = b'Z'*length
        if not fits and s['mode']==0:
            memory[BUFFER-HEAP] = 0
    return dict(memory=memory.hex(), trace=trace, result=result)


def execute(pe, functions, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in ((CODE, 0x10000), (HEAP, 0x4000),
            (STACK, 0x10000), (STOP, 0x1000)):
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(fixture(s)))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    uc.mem_write(TRANSFER, b'\xc2\x08\x00')
    if rebuilt:
        for name, function in functions.items():
            uc.mem_write(REBUILT[name], relocate(function, REBUILT[name], {}))
    trace = []
    def hook(machine, address, length, user):
        if address!=TRANSFER:
            return
        sp = machine.reg_read(UC_X86_REG_ESP)
        dest, size = struct.unpack('<II', machine.mem_read(sp+4, 8))
        assert machine.reg_read(UC_X86_REG_ECX)==HEAP
        if not trace:
            assert size==4 and STACK <= dest < STACK+0x10000
            if s['mode']==1:
                word = bytes(machine.mem_read(dest, 4))
            else:
                word = struct.pack('<I', s['length'])[:s['header_bytes']]
                if word:
                    machine.mem_write(dest, word)
            trace.append(['word', word.hex()])
        else:
            assert dest in (0, BUFFER)
            trace.append(['data' if dest else 'skip', size])
            if dest and s['mode']!=1 and 0 < size <= 260:
                machine.mem_write(dest, b'Z'*size)
    uc.hook_add(UC_HOOK_CODE, hook)
    args = [BUFFER, s['capacity']] if s['function']=='EStream::ReadString' else [s['index']]
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
    saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
        UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    uc.reg_write(UC_X86_REG_ECX, HEAP)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start((REBUILT if rebuilt else ORIGINAL)[s['function']], STOP, count=30000)
    assert uc.reg_read(UC_X86_REG_EIP)==STOP
    assert uc.reg_read(UC_X86_REG_ESP)==sp+4+len(args)*4
    assert all(uc.reg_read(reg)==value for reg, value in saved.items())
    result = uc.reg_read(UC_X86_REG_EAX) if len(args)==1 else None
    return dict(memory=bytes(uc.mem_read(HEAP, 0x4000)).hex(), trace=trace, result=result)


def scenarios():
    for mode, length, capacity in itertools.product((0, 1, 2, 0xffffffff),
            (0, 1, 6, 16, 0xffffffff), (0, 1, 6, 16)):
        yield dict(function='EStream::ReadString', mode=mode, length=length,
            capacity=capacity, header_bytes=4)
    for mode, header_bytes in itertools.product((0, 2), (0, 1, 2, 3)):
        yield dict(function='EStream::ReadString', mode=mode, length=5,
            capacity=16, header_bytes=header_bytes)
    for count, index in itertools.product((0, 1, 2, 3), (0, 1, 2, 3, 0xffffffff)):
        yield dict(function='ResourceList::GetFromBack', count=count, index=index)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/resource-parser/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/resource_stream.obj'
    obj = ObjFile(str(path))
    functions = {demangle(f.name): f for f in obj.functions if demangle(f.name) in ORIGINAL}
    assert functions.keys()==ORIGINAL.keys()
    cases = []
    for i, s in enumerate(scenarios()):
        want, original, rebuilt = expected(s), execute(pe, functions, s, False), execute(pe, functions, s, True)
        assert original==rebuilt==want, (i, s, 'heap/trace/result mismatch')
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d resource-parser dependency differential cases' % len(cases))


if __name__=='__main__':
    main()
