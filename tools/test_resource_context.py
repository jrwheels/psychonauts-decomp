#!/usr/bin/env python3
"""Check resource context/container lifetimes with bounded cleanup callbacks.

Execute original and rebuilt x86 against independent expected heap and traces.
Context cleanup, association destruction, pool release and aligned free are
mocked. No resource parser, asset data or real allocator is exercised.
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
ITEMS, NAME, POOL = HEAP+0x1000, HEAP+0x2000, HEAP+0x3000
ORIGINAL = {'ContextListBase::ContextListBase': 0x6a5030,
    'ContextListBase::~ContextListBase': 0x6a50e0,
    'ContextListBase::Clear': 0x6a5090,
    'ResourceContext::~ResourceContext': 0x41c720,
    'UContextAssociation::?$TArray::Clear': 0x41ffa0,
    'EArrayBase::Reserve': 0x408960,
    'ResourceContext::SetName': 0x41f670}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}
STUBS = {'cleanup': 0x41c790, 'entry': 0x420320, 'pool': 0x6a4fe0,
    'free': STOP+0x100, 'copy': 0x6a6e10}


def fixture(s):
    memory = bytearray(b'\xcc'*0x4000)
    def put(offset, value):
        struct.pack_into('<I', memory, offset, value)
    for offset in (4, 0x1c, 0x6c):
        for member in (0, 4, 8, 12, 16, 20):
            put(offset+member, (POOL if s['pool'] else 0) if member==4 else 0x11223344)
    put(0x34, s['count']*32+s['category'])
    put(0x38, s['count']*2+s['flag'])
    put(0x3c, ITEMS if s['data'] else 0)
    put(0x44, NAME if s['named'] else 0)
    return memory


def expected(s):
    memory, trace = fixture(s), []
    def put(offset, value):
        struct.pack_into('<I', memory, offset, value)
    def clear_list(offset):
        for member in (0, 20, 16, 12):
            put(offset+member, 0)
        trace.append(['pool', POOL if s['pool'] else 0])
        put(offset+4, 0)
    def clear_array():
        for i in range(s['count']):
            trace.append(['entry', ITEMS+i*16+4])
        trace.append(['free', ITEMS if s['data'] else 0])
        put(0x34, s['category'])
        put(0x38, s['flag'])
        put(0x3c, 0)
    name = s['function']
    if name=='ContextListBase::ContextListBase':
        for member in (0, 20, 16, 12, 4):
            put(4+member, 0)
        put(12, 10)
    elif name in ('ContextListBase::~ContextListBase', 'ContextListBase::Clear'):
        clear_list(4)
    elif name=='ResourceContext::SetName':
        if s['named']:
            trace.append(['free', NAME])
        trace.append(['copy', s['source'], 0x1a])
        put(0x44, s['allocated'])
    elif name=='ResourceContext::~ResourceContext':
        trace.append(['cleanup', HEAP])
        trace.append(['free', NAME if s['named'] else 0])
        clear_list(0x6c)
        clear_array()
        trace.append(['free', 0])
        clear_list(0x1c)
        clear_list(4)
    else:
        clear_array()
    return dict(memory=memory.hex(), trace=trace)


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in [(CODE, 0x10000), (HEAP, 0x4000),
            (STACK, 0x10000), (STOP, 0x1000)]:
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(fixture(s)))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    for address in STUBS.values():
        uc.mem_write(address, b'\xc3')
    uc.mem_write(0x700298, struct.pack('<I', STUBS['free']))
    if rebuilt:
        symbols = {'?Cleanup@ResourceContext@@QAEXXZ': STUBS['cleanup'],
            '?FreeFileName@@YAXPADHH@Z': 0x6a6e30,
            '?CopyFileName@@YAPADPBDH@Z': STUBS['copy'],
            '?Clear@ContextListBase@@QAEXXZ': 0x6a5090,
            '??1Entry@ContextAssociation@@QAE@XZ': STUBS['entry'],
            '?Release@ContextPool@@QAEXXZ': STUBS['pool'],
            '__imp___aligned_free': 0x700298,
            '__imp___aligned_malloc': 0x700288,
            '_memcpy': 0x6ed156}
        functions = {demangle(f.name): f for f in obj.functions if demangle(f.name) in REBUILT}
        assert functions.keys()==REBUILT.keys()
        symbols.update({f.name: REBUILT[n] for n, f in functions.items()})
        for name, f in functions.items():
            uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
    trace = []
    def hook(machine, address, length, user):
        name = next((n for n, a in STUBS.items() if a==address), None)
        if name:
            value = machine.reg_read(UC_X86_REG_ECX)
            if name=='free':
                sp = machine.reg_read(UC_X86_REG_ESP)
                value = struct.unpack('<I', machine.mem_read(sp+4, 4))[0]
            if name=='copy':
                sp = machine.reg_read(UC_X86_REG_ESP)
                source, category = struct.unpack('<II', machine.mem_read(sp+4, 8))
                trace.append(['copy', source, category])
                machine.reg_write(UC_X86_REG_EAX, s['allocated'])
            else:
                trace.append([name, value])
                machine.reg_write(UC_X86_REG_EAX, 0)
    uc.hook_add(UC_HOOK_CODE, hook)
    args = ([s['mode']] if s['function']=='ContextListBase::ContextListBase' else
        [s['source']] if s['function']=='ResourceContext::SetName' else [])
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
    saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
        UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    receiver = HEAP if s['function'] in ('ResourceContext::~ResourceContext', 'ResourceContext::SetName') else (
        HEAP+0x34 if 'TArray::Clear' in s['function'] else HEAP+4)
    uc.reg_write(UC_X86_REG_ECX, receiver)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start((REBUILT if rebuilt else ORIGINAL)[s['function']], STOP, count=30000)
    assert uc.reg_read(UC_X86_REG_EIP)==STOP
    assert uc.reg_read(UC_X86_REG_ESP)==sp+4+len(args)*4
    assert all(uc.reg_read(reg)==value for reg, value in saved.items())
    if s['function']=='ContextListBase::ContextListBase':
        assert uc.reg_read(UC_X86_REG_EAX)==receiver
    return dict(memory=bytes(uc.mem_read(HEAP, 0x4000)).hex(), trace=trace)


def scenarios():
    base = dict(mode=1, pool=False, count=0, category=0,
        flag=0, data=False, named=False)
    # Copy is mocked: alias cases verify ordering, not validity after free.
    for named, source, allocated in itertools.product((False, True),
            (0, NAME, NAME+0x100), (0, NAME+0x200)):
        yield dict(base, function='ResourceContext::SetName', named=named,
            source=source, allocated=allocated)
    for mode in (0, 1, 2, 0xffffffff):
        yield dict(base, function='ContextListBase::ContextListBase', mode=mode)
    for name, pool in itertools.product(('ContextListBase::~ContextListBase',
            'ContextListBase::Clear'), (False, True)):
        yield dict(base, function=name, pool=pool)
    for count, category, flag, named, pool in itertools.product(
            (0, 1, 3), (0, 31), (0, 1), (False, True), (False, True)):
        yield dict(base, function='ResourceContext::~ResourceContext',
            count=count, category=category, flag=flag, data=True, named=named, pool=pool)
    for count, category, flag in itertools.product((0, 1, 3), (0, 31), (0, 1)):
        yield dict(base, function='UContextAssociation::?$TArray::Clear',
            count=count, category=category, flag=flag, data=True)
    for name in ('ResourceContext::~ResourceContext', 'UContextAssociation::?$TArray::Clear'):
        yield dict(base, function=name)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/resource-context/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/resource_context.obj'
    obj, cases = ObjFile(str(path)), []
    for i, s in enumerate(scenarios()):
        want, original, rebuilt = expected(s), execute(pe, obj, s, False), execute(pe, obj, s, True)
        assert original==rebuilt==want, (i, s, 'heap/trace mismatch')
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d resource-context differential cases' % len(cases))


if __name__=='__main__':
    main()
