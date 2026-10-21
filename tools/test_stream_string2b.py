#!/usr/bin/env python3
"""Original/rebuilt two-byte stream strings against independent expectations.

Only virtual transfers are mocked. Tests retain partial headers, signed bounds,
16-bit strlen narrowing, null pointer faults, and absent termination/allocation.
All buffers are synthetic; this is not physical I/O or gameplay verification.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_INVALID, UC_MEM_READ_UNMAPPED, UC_MEM_WRITE_UNMAPPED
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
TABLE, BUFFER, TRANSFER = HEAP+0x100, HEAP+0x1000, STOP+0x100
SIZE = 0x24000
SYMBOL = 'EStream::ReadString2b'
ORIGINAL = 0x6a5c30


def fixture(s):
    memory = bytearray(b'\xcc'*SIZE)
    struct.pack_into('<II', memory, 0, TABLE, s['mode'])
    struct.pack_into('<I', memory, TABLE-HEAP+8, TRANSFER)
    length = s.get('text_length', 5)
    memory[BUFFER-HEAP:BUFFER-HEAP+length+1] = b'Q'*length+b'\0'
    return memory


def signed(n):
    return n if n < 0x80000000 else n-0x100000000


def expected(s):
    memory, trace = fixture(s), []
    if s['mode']==1 and s.get('null'):
        return memory, [['fault', 'read', 0, 1]]
    if s['mode']==1:
        word = struct.pack('<H', (s.get('text_length', 5)+1)&0xffff)
        length = int.from_bytes(word, 'little')
    else:
        word = struct.pack('<H', s['length'])[:s['header_bytes']]
        length = int.from_bytes(word+b'\xa5'*(2-len(word)), 'little')
    trace.append(['header', word.hex()])
    fits = length!=0 and length < signed(s['capacity'])
    dest = 0 if s.get('null') or not fits else BUFFER
    trace.append(['transfer', dest, length])
    if dest and s['mode']!=1:
        count = min(length, s['payload_bytes'])
        memory[dest-HEAP:dest-HEAP+count] = b'Z'*count
    if not fits and s['mode']==0:
        if s.get('null'):
            trace.append(['fault', 'write', 0, 1])
        else:
            memory[BUFFER-HEAP] = 0
    return memory, trace


def execute(pe, function, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095)&~4095)
    uc.mem_write(base, image)
    for address, size in ((CODE, 0x1000), (HEAP, SIZE), (STACK, 0x10000), (STOP, 0x1000)):
        uc.mem_map(address, size)
    uc.mem_write(HEAP, bytes(fixture(s)))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    uc.mem_write(TRANSFER, b'\xc2\x08\x00')
    if rebuilt:
        uc.mem_write(CODE, relocate(function, CODE, {}))
    trace = []
    def transfer(machine, address, size, user):
        sp = machine.reg_read(UC_X86_REG_ESP)
        dest, count = struct.unpack('<II', machine.mem_read(sp+4, 8))
        assert machine.reg_read(UC_X86_REG_ECX)==HEAP
        if not trace:
            assert count==2 and STACK<=dest<STACK+0x10000
            if s['mode']==1:
                word = bytes(machine.mem_read(dest, 2))
            else:
                word = struct.pack('<H', s['length'])[:s['header_bytes']]
                if word:
                    machine.mem_write(dest, word)
            trace.append(['header', word.hex()])
        else:
            assert dest in (0, BUFFER) and count<=0xffff
            trace.append(['transfer', dest, count])
            if dest and s['mode']!=1:
                n = min(count, s['payload_bytes'])
                if n:
                    machine.mem_write(dest, b'Z'*n)
        machine.reg_write(UC_X86_REG_EAX, 0xdeadbeef)
    def fault(machine, access, address, size, value, user):
        assert address==0 and access in (UC_MEM_READ_UNMAPPED, UC_MEM_WRITE_UNMAPPED)
        trace.append(['fault', 'read' if access==UC_MEM_READ_UNMAPPED else 'write', address, size])
        return False
    uc.hook_add(UC_HOOK_CODE, transfer, begin=TRANSFER, end=TRANSFER)
    uc.hook_add(UC_HOOK_MEM_INVALID, fault)
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<III', STOP, 0 if s.get('null') else BUFFER, s['capacity']))
    saved = {UC_X86_REG_EBP:0x12345678, UC_X86_REG_EBX:0x23456789,
        UC_X86_REG_ESI:0x3456789a, UC_X86_REG_EDI:0x456789ab}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    uc.reg_write(UC_X86_REG_ECX, HEAP)
    uc.reg_write(UC_X86_REG_ESP, sp)
    try:
        uc.emu_start(CODE if rebuilt else ORIGINAL, STOP, count=1500000)
    except UcError:
        assert trace and trace[-1][0]=='fault'
    else:
        assert not trace or trace[-1][0]!='fault'
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+12
        assert all(uc.reg_read(reg)==value for reg, value in saved.items())
    return bytes(uc.mem_read(HEAP, SIZE)), trace


def scenarios():
    defaults = dict(mode=0, length=6, capacity=16, header_bytes=2, payload_bytes=6)
    for mode, length, capacity in itertools.product((0,2,0xffffffff),
            (0,1,5,6,255,256,32767,32768,65535),
            (0,1,5,6,7,65535,65536,0x7fffffff,0x80000000,0xffffffff)):
        yield dict(defaults, mode=mode, length=length, capacity=capacity)
    for mode, header, payload in itertools.product((0,2), (0,1), (0,1,4)):
        yield dict(defaults, mode=mode, header_bytes=header, payload_bytes=payload)
    for text, capacity in itertools.product((0,1,5,65534,65535,65536,131071), (0,1,6,7,65535,65536,0xffffffff)):
        yield dict(defaults, mode=1, text_length=text, capacity=capacity)
    for mode, length, capacity in itertools.product((0,2), (0,1,6), (0,1,6,7)):
        yield dict(defaults, mode=mode, length=length, capacity=capacity, null=True)
    yield dict(defaults, mode=1, null=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/stream-string2b/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):
        ap.error('report must stay under ignored build/ or .local/')
    raw, pe = load_reference(args.exe)
    path = ROOT/'build/game/resource_stream.obj'
    functions = [f for f in ObjFile(str(path)).functions if demangle(f.name)==SYMBOL]
    assert len(functions)==1
    cases = []
    for i, s in enumerate(scenarios()):
        memory, trace = expected(s)
        original = execute(pe, functions[0], s, False)
        rebuilt = execute(pe, functions[0], s, True)
        assert original==rebuilt==(memory, trace), (i,s,original[1],rebuilt[1],trace)
        cases.append(dict(s, passed=True, fault=bool(trace and trace[-1][0]=='fault')))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest()}, scope=__doc__, cases=cases),indent=2)+'\n')
    print('Passed %d two-byte string differential cases' % len(cases))


if __name__=='__main__':
    main()
