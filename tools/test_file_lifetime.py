#!/usr/bin/env python3
"""Original/rebuilt file lifetime chains with mocked allocation and file I/O.

Failed string allocations trace the subsequent invalid memcpy request without
executing it. These fixtures check call behavior, not safe real CRT handling.
Virtual slot +0x18 is checked as raw EDX:EAX; the Win32 implementation
uses it for last-write FILETIME (see test_native_file.py).
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
    UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
OBJECT, FILE, VT = HEAP, HEAP + 0x100, HEAP + 0x200
TEXT, NAME, BUFFER, DEST = (HEAP + n * 0x1000 for n in (1, 2, 3, 4))
ALLOC, FREE, CLOSE, WRITE, SIZE, VF18, READ = (STOP + n * 0x100 for n in range(1, 8))
COPY, MASK = 0x6ed156, 0xffffffff
TARGETS = {
    'StrDup': 0x6a6e50, 'CopyFileName': 0x6a6e10, 'FreeFileName': 0x6a6e30,
    'EReadBufferedFile::EReadBufferedFile': 0x6a9e50,
    'EWriteBufferedFile::EWriteBufferedFile': 0x6a9b30,
    'EReadBufferedFile::~EReadBufferedFile': 0x6aa0f0,
    'EWriteBufferedFile::~EWriteBufferedFile': 0x6a9dd0,
    '?_GDiagnosticFile': 0x6a9940, '?_GEReadBufferedFile': 0x6aa0c0,
    '?_GEWriteBufferedFile': 0x6a9da0,
    'EReadBufferedFile::Vf18': 0x6aa040, 'EWriteBufferedFile::Vf18': 0x6a9c70,
    'EWriteBufferedFile::Read': 0x6a9bc0, 'EWriteBufferedFile::Size': 0x6a9c40,
    'EWriteBufferedFile::Flush': 0x6a9d50,
}
REBUILT = {n: CODE + i * 0x1000 for i, n in enumerate(TARGETS)}
TABLES = {'base': 0x71d8c4, 'reader': 0x71d958, 'writer': 0x71d934}


def initial(s):
    memory = bytearray(b'\xcc' * 0x10000)
    text = bytes.fromhex(s['text']) if s['text'] is not None else None
    if text is not None:
        memory[TEXT - HEAP:TEXT - HEAP + len(text) + 1] = text + b'\0'
    memory[BUFFER - HEAP:BUFFER - HEAP + 16] = bytes(range(16))
    struct.pack_into('<2I', memory, FILE - HEAP, VT, TEXT if text is not None else 0)
    for slot, stub in [(4, CLOSE), (8, READ), (12, WRITE), (20, SIZE), (24, VF18)]:
        struct.pack_into('<I', memory, VT + slot - HEAP, stub)
    if s['kind'] != 'ctor':
        file, name, buffer = (FILE if s['file'] else 0, NAME if s['name'] else 0,
                              BUFFER if s['buffer'] else 0)
        fields = ([TABLES['writer'], name, file, s['capacity'], s['pending'], 42, buffer]
                  if s['writer'] else
                  [TABLES['reader'], name, file, buffer, s['capacity'], 11, 7])
        struct.pack_into('<7I', memory, 0, *fields)
    return memory


def expected(s):
    memory, trace = initial(s), []
    text = bytes.fromhex(s['text']) if s['text'] is not None else None

    def clone():
        if text is None:
            return 0
        p = 0 if s['fail_name'] else NAME
        trace.append(['alloc', len(text) + 1, 16, p])
        trace.append(['copy', p, TEXT, len(text) + 1])
        if p:
            memory[p - HEAP:p - HEAP + len(text) + 1] = text + b'\0'
        return p

    def flush():
        if s['writer'] and s['pending']:
            trace.append(['write', FILE, BUFFER, s['pending'], bytes(range(s['pending'])).hex()])
            struct.pack_into('<2I', memory, 0x10, 0, 0)

    kind = s['kind']
    if kind == 'clone':
        result = clone()
    elif kind == 'free':
        trace.append(['free', NAME if s['name'] else 0])
        result = None
    elif kind == 'ctor':
        name = clone()
        buffer = 0 if s['fail_buffer'] else BUFFER
        trace.append(['alloc', s['capacity'], 16, buffer])
        fields = ([TABLES['writer'], name, FILE, s['capacity'], 0, 0, buffer]
                  if s['writer'] else
                  [TABLES['reader'], name, FILE, buffer, s['capacity'], 0, 0])
        struct.pack_into('<7I', memory, 0, *fields)
        result = OBJECT
    elif kind == 'base_delete':
        struct.pack_into('<I', memory, 0, TABLES['base'])
        if s['flags'] & 1:
            trace.append(['free', OBJECT])
        result = OBJECT
    elif kind in ('dtor', 'delete'):
        flush()
        if s['file']:
            trace.append(['close', FILE])
        if s['buffer']:
            trace.append(['free', BUFFER])
        if s['name']:
            trace.append(['free', NAME])
        struct.pack_into('<I', memory, 0, TABLES['base'])
        if kind == 'delete' and s['flags'] & 1:
            trace.append(['free', OBJECT])
        result = OBJECT if kind == 'delete' else None
    else:
        flush()
        if kind == 'vf18':
            trace.append(['vf18', FILE])
            result = [s['returned'], s['high']]
        elif kind == 'size':
            trace.append(['size', FILE])
            result = s['returned']
        else:
            trace.append(['read', FILE, DEST, s['request']])
            result = s['returned']
    return {'trace': trace, 'result': result, 'memory': memory.hex()}


def execute(pe, objects, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image) + 4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in [(CODE, 0x20000), (HEAP, 0x10000), (STACK, 0x10000), (STOP, 0x1000)]:
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(initial(s)))
    uc.mem_write(STACK, b'\xa5' * 0x10000)
    for address, pop in [(ALLOC, 0), (FREE, 0), (CLOSE, 0), (WRITE, 8),
                         (SIZE, 0), (VF18, 0), (READ, 8), (COPY, 0)]:
        uc.mem_write(address, b'\xc2' + struct.pack('<H', pop) if pop else b'\xc3')
    uc.mem_write(0x700288, struct.pack('<I', ALLOC))
    uc.mem_write(0x700298, struct.pack('<I', FREE))
    if rebuilt:
        symbols = {'__imp___aligned_malloc': 0x700288, '__imp___aligned_free': 0x700298,
                   '_memcpy': COPY, '??_7DiagnosticFile@@6B@': TABLES['base'],
                   '??_7EReadBufferedFile@@6B@': TABLES['reader'],
                   '??_7EWriteBufferedFile@@6B@': TABLES['writer']}
        functions = {}
        for obj in objects:
            for f in obj.functions:
                name = demangle(f.name)
                if name in REBUILT:
                    assert name not in functions, name
                    functions[name] = f
                    symbols[f.name] = REBUILT[name]
        assert functions.keys() == REBUILT.keys()
        for name, f in functions.items():
            uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
    trace, allocations = [], []

    def hook(machine, address, size, context):
        sp = machine.reg_read(UC_X86_REG_ESP)
        def args(n):
            return list(struct.unpack('<' + 'I' * n, machine.mem_read(sp + 4, n * 4)))
        if address == ALLOC:
            is_name = (s['kind'] == 'clone' or
                       s['kind'] == 'ctor' and s['text'] is not None and not allocations)
            p = (0 if s['fail_name'] else NAME) if is_name else (0 if s['fail_buffer'] else BUFFER)
            trace.append(['alloc', *args(2), p])
            allocations.append(p)
            machine.reg_write(UC_X86_REG_EAX, p)
        elif address == COPY:
            dest, source, count = args(3)
            trace.append(['copy', dest, source, count])
            if dest:
                assert dest == NAME and source == TEXT and 0 < count <= 1024
                machine.mem_write(dest, bytes(machine.mem_read(source, count)))
            machine.reg_write(UC_X86_REG_EAX, dest)
        elif address == FREE:
            trace.append(['free', *args(1)])
            machine.reg_write(UC_X86_REG_EAX, 0x1234abcd)
        elif address == CLOSE:
            trace.append(['close', machine.reg_read(UC_X86_REG_ECX)])
            machine.reg_write(UC_X86_REG_EAX, 0x5678abcd)
        elif address == WRITE:
            source, count = args(2)
            assert source == BUFFER and count <= 16
            trace.append(['write', machine.reg_read(UC_X86_REG_ECX), source, count,
                          bytes(machine.mem_read(source, count)).hex()])
            machine.reg_write(UC_X86_REG_EAX, s['returned'])
        elif address in (SIZE, VF18, READ):
            label = {SIZE: 'size', VF18: 'vf18', READ: 'read'}[address]
            trace.append([label, machine.reg_read(UC_X86_REG_ECX)] + (args(2) if address == READ else []))
            machine.reg_write(UC_X86_REG_EAX, s['returned'])
            machine.reg_write(UC_X86_REG_EDX, s['high'])

    uc.hook_add(UC_HOOK_CODE, hook)
    kind = s['kind']
    args = ([TEXT if s['text'] is not None else 0, s['category']] if kind == 'clone' else
            [NAME if s['name'] else 0, s['category'], s['flags']] if kind == 'free' else
            [FILE, s['capacity']] if kind == 'ctor' else
            [s['flags']] if kind in ('delete', 'base_delete') else
            [DEST, s['request']] if kind == 'read' else [])
    pop = len(args) * 4 if kind in ('ctor', 'delete', 'base_delete', 'read') else 0
    sp = STACK + 0x8000
    uc.mem_write(sp, struct.pack('<' + 'I' * (len(args) + 1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for register, value in preserved.items():
        uc.reg_write(register, value)
    uc.reg_write(UC_X86_REG_ECX, OBJECT)
    uc.reg_write(UC_X86_REG_EAX, 0xdeadbeef)
    uc.reg_write(UC_X86_REG_EDX, 0xabcdef01)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start((REBUILT if rebuilt else TARGETS)[s['function']], STOP, count=20000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP
    assert uc.reg_read(UC_X86_REG_ESP) == sp + 4 + pop
    assert all(uc.reg_read(reg) == value for reg, value in preserved.items())
    result = None if kind in ('dtor', 'free') else uc.reg_read(UC_X86_REG_EAX)
    if kind == 'vf18':
        result = [result, uc.reg_read(UC_X86_REG_EDX)]
    return {'trace': trace, 'result': result, 'memory': bytes(uc.mem_read(HEAP, 0x10000)).hex()}


def scenarios():
    defaults = dict(writer=False, file=True, name=True, buffer=True, pending=0,
        capacity=16, text=b'test.dat'.hex(), category=0x18, flags=0,
        fail_name=False, fail_buffer=False, returned=MASK, high=0x12345678, request=7)
    texts = [None, '', b'file.dat'.hex(), b'\xff\x80name'.hex(), (b'a' * 1023).hex()]
    for function, text, fail in itertools.product(['StrDup', 'CopyFileName'], texts, [False, True]):
        yield dict(defaults, function=function, kind='clone', text=text, fail_name=fail)
    for name, category, flags in itertools.product([False, True], [0, 0x18, MASK], [0, 1, MASK]):
        yield dict(defaults, function='FreeFileName', kind='free', name=name, category=category, flags=flags)
    for writer, text, capacity, failure in itertools.product([False, True], texts, [0, 1, 16, MASK], ['none', 'name', 'buffer']):
        cls = 'EWriteBufferedFile' if writer else 'EReadBufferedFile'
        yield dict(defaults, function=cls+'::'+cls, kind='ctor', writer=writer,
            text=text, capacity=capacity, fail_name=failure=='name', fail_buffer=failure=='buffer')
    for writer, file, name, buffer, pending, flags in itertools.product(
            [False, True], [False, True], [False, True], [False, True], [0, 4], [0, 1, 2, 3, 0x80000000, MASK]):
        if pending and (not writer or not file or not buffer):
            continue
        cls = 'EWriteBufferedFile' if writer else 'EReadBufferedFile'
        for kind in ['dtor', 'delete']:
            if kind == 'dtor' and flags != 0:
                continue
            function = cls+'::~'+cls if kind == 'dtor' else '?_G'+cls
            yield dict(defaults, function=function, kind=kind, writer=writer,
                       file=file, name=name, buffer=buffer, pending=pending, flags=flags)
    for flags in [0, 1, 2, 3, 0x80000000, MASK]:
        yield dict(defaults, function='?_GDiagnosticFile', kind='base_delete', flags=flags)
    for writer, pending, value in itertools.product([False, True], [0, 4],
            [(0, 0), (1, 0), (MASK, MASK), (0x89abcdef, 0x01234567), (0, 0x80000000)]):
        if not writer and pending:
            continue
        cls = 'EWriteBufferedFile' if writer else 'EReadBufferedFile'
        yield dict(defaults, function=cls+'::Vf18', kind='vf18', writer=writer,
                   pending=pending, returned=value[0], high=value[1])
    for kind, pending, returned, request in itertools.product(['size', 'read'], [0, 4], [0, 7, MASK], [0, 16, MASK]):
        if kind == 'size' and request:
            continue
        yield dict(defaults, function='EWriteBufferedFile::'+('Size' if kind=='size' else 'Read'),
                   kind=kind, writer=True, pending=pending, returned=returned, request=request)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT / 'build/file-lifetime/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ['build', '.local']):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    paths = [ROOT/'build/game'/n for n in ['file_memory.obj', 'buffered_file.obj']]
    objects = [ObjFile(str(p)) for p in paths]
    cases = []
    for s in scenarios():
        want = expected(s)
        original, rebuilt = execute(pe, objects, s, False), execute(pe, objects, s, True)
        assert original == rebuilt == want, (s, original['trace'], rebuilt['trace'], want['trace'])
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d file lifetime differential cases' % len(cases))


if __name__ == '__main__':
    main()
