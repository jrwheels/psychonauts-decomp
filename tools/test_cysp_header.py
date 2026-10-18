#!/usr/bin/env python3
"""Exercise the original CYSP parser with synthetic headers and dependencies.

There is no rebuilt parser in this test. Stream transfers, TLS/temporary
allocation, diagnostics, resource lookup and the large context reader are
bounded mocks. Optional post-context sections and deferred loads are excluded.
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
from native_index import load_reference

ROOT = Path(__file__).resolve().parents[1]
HEAP, STACK, STOP = 0x2000000, 0x3000000, 0x2100000
MANAGER, CONTEXT, STREAM, TABLE, RESOURCE, NAME, GAME = (
    HEAP+i*0x1000 for i in range(7))
VT = STREAM+0x100
TEXT = b'synthetic.asset\0'
STUBS = {'tls': STOP+0x100, 'name': STOP+0x200, 'read': 0x40aeb0,
    'enter': 0x408d40, 'leave': 0x408db0, 'alloc': 0x408ca0,
    'diagnostic': 0x40a7c0, 'reserve': 0x408960,
    'lookup': 0x47fcc0, 'context': 0x41d510}


def fixture():
    memory = bytearray(0x18000)
    def put(address, value):
        struct.pack_into('<I', memory, address-HEAP, value)
    memory[0x15f] = 1  # Exclude the deferred-load branch explicitly.
    put(STREAM, VT)
    put(VT+4, STUBS['name'])
    put(VT+8, STUBS['read'])
    put(GAME+0x19c, MANAGER)
    memory[NAME-HEAP:NAME-HEAP+10] = b'fixture\0\0\0'
    return memory


def payload(s):
    data = struct.pack('<I', s['magic'])[:s['magic_bytes']]
    if s['magic_bytes']!=4 or s['magic']!=0x50535943:
        return data
    data += struct.pack('<I', s['version'])[:s['version_bytes']]
    if s['version_bytes']!=4:
        return data
    data += struct.pack('<II', 0, s['count'])
    if s['count']==1:
        data += struct.pack('<I', len(TEXT))+TEXT+bytes((s['first'], s['second']))
    return data+struct.pack('<I', 0)


def expected(s):
    memory, trace, data, cursor = fixture(), [['enter']], payload(s), 0
    def read(size):
        nonlocal cursor
        got = data[cursor:cursor+size]
        cursor += len(got)
        trace.append(['read', size, got.hex()])
        if len(got)!=size:
            memory[STREAM-HEAP+0xc] = 1
        return got+b'\xa5'*(size-len(got))
    magic = int.from_bytes(read(4), 'little')
    result, version = False, 0
    if magic==0x50535943:
        version = int.from_bytes(read(4), 'little')
        struct.pack_into('<I', memory, STREAM-HEAP+8, version)
        if not 317 <= version <= 319:
            trace += [['name'], ['diagnostic', version, 317, 319], ['reserve', 1, 0], ['reserve', 0, 0]]
        else:
            read(4)  # Container flags are zero in these fixtures.
            read(4)  # Dependency count.
            trace.append(['alloc', s['count']*4 if s['count'] < 0x40000000 else 0xffffffff, 0])
            if s['count']==1:
                read(4)
                read(len(TEXT))
                read(1)
                read(1)
                flags = {1: 0x10001, 2: 0x20000, 3: 0x30000, 4: 0x40000}.get(s['mode'], 0)
                flags |= 2 if s['first'] else 0
                flags |= 0 if s['second'] else 0x10
                trace += [['name'], ['lookup', TEXT[:-1].decode(), flags, 0]]
                struct.pack_into('<I', memory, TABLE-HEAP, RESOURCE if s['found'] else 0)
            entries = [RESOURCE if s['found'] else 0] if s['count']==1 else []
            trace.append(['context', version, s['mode'], entries])
            if s['context_ok']:
                read(4)  # No optional section follows.
                result = True
            else:
                trace.append(['name'])
    trace.append(['leave'])
    return dict(memory=memory.hex(), trace=trace, result=result)


def execute(pe, s):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in ((HEAP, 0x18000), (STACK, 0x10000), (STOP, 0x1000)):
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(fixture()))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    uc.mem_write(0x78bc20, struct.pack('<I', GAME))
    uc.mem_write(0x7000dc, struct.pack('<I', STUBS['tls']))
    pops = dict(tls=4, name=0, read=8, enter=4, leave=0, alloc=8,
        diagnostic=0, reserve=8, lookup=12, context=20)
    for name, address in STUBS.items():
        uc.mem_write(address, b'\xc2'+struct.pack('<H', pops[name]))
    data, trace, cursor = payload(s), [], 0
    def hook(machine, address, length, user):
        nonlocal cursor
        name = next((n for n, a in STUBS.items() if a==address), None)
        if not name:
            return
        sp = machine.reg_read(UC_X86_REG_ESP)
        def args(n):
            return list(struct.unpack('<'+'I'*n, machine.mem_read(sp+4, n*4)))
        result = 0
        if name=='read':
            dest, size = args(2)
            assert machine.reg_read(UC_X86_REG_ECX)==STREAM and 0 < size <= 260
            got = data[cursor:cursor+size]
            cursor += len(got)
            if got:
                machine.mem_write(dest, got)
            if len(got)!=size:
                machine.mem_write(STREAM+0xc, b'\x01')
            trace.append(['read', size, got.hex()])
        elif name=='name':
            trace.append(['name'])
            result = NAME
        elif name in ('enter', 'leave'):
            trace.append([name])
        elif name=='alloc':
            trace.append(['alloc', *args(2)])
            result = TABLE
        elif name=='diagnostic':
            values = args(7)
            trace.append(['diagnostic', *values[4:]])
            machine.mem_write(values[0], struct.pack('<III', 0, 0, NAME))
            result = values[0]
        elif name=='reserve':
            trace.append(['reserve', *args(2)])
        elif name=='lookup':
            text, flags, zero = args(3)
            text = bytes(machine.mem_read(text, 260)).split(b'\0', 1)[0].decode()
            trace.append(['lookup', text, flags, zero])
            result = RESOURCE if s['found'] else 0
        elif name=='context':
            stream, version, table, boolean, mode = args(5)
            assert machine.reg_read(UC_X86_REG_ECX)==CONTEXT
            assert stream==STREAM and table==TABLE and boolean==1
            entries = [struct.unpack('<I', machine.mem_read(TABLE, 4))[0]] if s['count']==1 else []
            trace.append(['context', version, mode, entries])
            result = int(s['context_ok'])
        machine.reg_write(UC_X86_REG_EAX, result)
    uc.hook_add(UC_HOOK_CODE, hook)
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<IIIII', STOP, CONTEXT, STREAM, 1, s['mode']))
    saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
        UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    uc.reg_write(UC_X86_REG_ECX, MANAGER)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(0x47b980, STOP, count=30000)
    assert uc.reg_read(UC_X86_REG_EIP)==STOP
    assert uc.reg_read(UC_X86_REG_ESP)==sp+20
    assert all(uc.reg_read(reg)==value for reg, value in saved.items())
    return dict(memory=bytes(uc.mem_read(HEAP, 0x18000)).hex(), trace=trace,
        result=bool(uc.reg_read(UC_X86_REG_EAX) & 0xff))


def scenarios():
    base = dict(magic=0x50535943, magic_bytes=4, version=317, version_bytes=4,
        count=0, mode=0, first=0, second=1, found=True, context_ok=True)
    yield dict(base, magic=0)
    for version in (316, 320, 0xffffffff):
        yield dict(base, version=version)
    for version, ok in itertools.product((317, 318, 319), (False, True)):
        yield dict(base, version=version, context_ok=ok)
    for length in range(4):
        yield dict(base, magic_bytes=length)
        yield dict(base, version_bytes=length)
    for mode, first, second in itertools.product(range(6), (0, 1), (0, 1)):
        yield dict(base, count=1, mode=mode, first=first, second=second)
    yield dict(base, count=1, found=False)
    yield dict(base, count=0xffffffff, context_ok=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/resource-parser/header-behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    cases = []
    for i, s in enumerate(scenarios()):
        want, original = expected(s), execute(pe, s)
        assert original==want, (i, s, 'heap/trace/result mismatch')
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'scope': __doc__, 'original_only': True, 'cases': cases}, indent=2)+'\n')
    print('Passed %d original-parser synthetic header cases' % len(cases))


if __name__=='__main__':
    main()
