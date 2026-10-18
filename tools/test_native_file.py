#!/usr/bin/env python3
"""Original/rebuilt Win32 file methods with mocked Win32 and filename helpers.

Checks isolated x86 calls and real Close/deleting-destructor/Size/Seek chains.
No actual handles, filesystem operations or streaming threads are used.
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
OBJECT, NAME, DATA, TEXT = HEAP, HEAP + 0x1000, HEAP + 0x2000, HEAP + 0x3000
COUNT, BASE_VT, FILE_VT, MASK = 0x795a30, 0x71d8c4, 0x71d8a0, 0xffffffff
TARGETS = {'DiagnosticFile::Close': 0x6a9660,
    'EWin32File::EWin32File': 0x6a8580, '?_GEWin32File': 0x6a85e0,
    'EWin32File::~EWin32File': 0x6a8610, 'EWin32File::Read': 0x6a8680,
    'EWin32File::Write': 0x6a86e0, 'EWin32File::Seek': 0x6a8730,
    'EWin32File::Size': 0x6a87b0, 'EWin32File::Vf18': 0x6a8800,
    'EWin32File::Vf1c': 0x6a8840, 'CreateParentDirectories': 0x6a8440}
REBUILT = {n: CODE + i * 0x1000 for i, n in enumerate(TARGETS)}
# Symbol, import slot (or direct callee), and stdcall argument bytes.
CALLEES = {
    'close': ('__imp__CloseHandle@4', 0x7000f4, 4),
    'error': ('__imp__GetLastError@0', 0x7000f8, 0),
    'read': ('__imp__ReadFile@20', 0x7000fc, 20),
    'write': ('__imp__WriteFile@20', 0x700048, 20),
    'seek': ('__imp__SetFilePointer@16', 0x700100, 16),
    'gettime': ('__imp__GetFileTime@16', 0x700038, 16),
    'settime': ('__imp__SetFileTime@16', 0x700058, 16),
    'mkdir': ('__imp__CreateDirectoryA@8', 0x700040, 8),
    'strrchr': ('__imp__strrchr', 0x7002e8, 0),
    'free': ('__imp___aligned_free', 0x700298, 0),
    'copyname': ('?CopyFileName@@YAPADPBDH@Z', 0x6a6e10, 0),
    'freename': ('?FreeFileName@@YAXPADHH@Z', 0x6a6e30, 0)}
STUBS = {n: STOP + (i + 1) * 0x100 for i, n in enumerate(CALLEES)}


def initial(s):
    memory = bytearray(b'\xcc' * 0x10000)
    if s['kind'] != 'ctor':
        struct.pack_into('<3I', memory, 0, FILE_VT, NAME if s['name'] else 0, s['handle'])
    memory[DATA-HEAP:DATA-HEAP+32] = bytes(range(32))
    text = bytes.fromhex(s['text'])
    memory[TEXT-HEAP:TEXT-HEAP+len(text)+1] = text + b'\0'
    return memory


def expected(s):
    memory, trace, count, result = initial(s), [], s['count'], None
    kind = s['kind']
    if kind == 'ctor':
        struct.pack_into('<I', memory, 0, FILE_VT)
        struct.pack_into('<I', memory, 8, s['handle'])
        count = (count + 1) & MASK
        if s['name']:
            trace.append(['copyname', TEXT, s['text'], 0x18])
            struct.pack_into('<I', memory, 4, 0 if s['fail_name'] else NAME)
        result = OBJECT
    elif kind in ('dtor', 'delete', 'close'):
        if s['name']:
            trace.append(['freename', NAME, 0x18, 1])
        count = (count - 1) & MASK
        if s['handle']:
            trace.append(['close', s['handle']])
            struct.pack_into('<I', memory, 8, 0)
        struct.pack_into('<I', memory, 0, BASE_VT)
        if kind == 'close' or kind == 'delete' and s['flags'] & 1:
            trace.append(['free', OBJECT])
        if kind == 'delete':
            result = OBJECT
    elif kind in ('read', 'write'):
        trace.append([kind, s['handle'], DATA, s['request'], 0])
        if kind == 'read':
            if s['ok']:
                memory[DATA-HEAP:DATA-HEAP+s['transferred']] = b'\x7b' * s['transferred']
            else:
                trace.append(['error'])
        else:
            trace[-1].append(bytes(range(s['request'])).hex())
        result = s['transferred'] if s['ok'] else MASK
    elif kind == 'seek':
        method = s['origin'] if s['origin'] in (0, 1, 2) else 0
        trace.append(['seek', s['handle'], s['offset'], 0, method])
        result = s['returns'][0]
    elif kind == 'size':
        position, result, restored = s['returns']
        trace = [['seek', s['handle'], 0, 0, 1], ['seek', s['handle'], 0, 0, 2],
                 ['seek', s['handle'], position, 0, 0]]
    elif kind == 'gettime':
        trace.append(['gettime', s['handle'], 0, 0])
        result = s['time'] if s['ok'] else [0, 0]
    elif kind == 'settime':
        trace.append(['settime', s['handle'], 0, 0, *s['time']])
        result = int(s['ok'] != 0)
    else:
        def parents(path, skip):
            i = path.rfind(b'\\')
            if i < 0:
                return
            parents(path[:i], False)
            if not skip:
                trace.append(['mkdir', path.hex(), 0])
        parents(bytes.fromhex(s['text']), s['skip'])
    return dict(trace=trace, result=result, memory=memory.hex(), count=count)


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image) + 4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in [(CODE, 0x10000), (HEAP, 0x10000), (STACK, 0x10000), (STOP, 0x1000)]:
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(initial(s)))
    uc.mem_write(STACK, b'\xa5' * 0x10000)
    uc.mem_write(COUNT, struct.pack('<I', s['count']))
    symbols = {'?g_win32FileCount@@3IA': COUNT,
               '??_7EWin32File@@6B@': FILE_VT, '??_7DiagnosticFile@@6B@': BASE_VT}
    for label, (symbol, slot, pop) in CALLEES.items():
        stub = STUBS[label]
        uc.mem_write(stub, b'\xc2' + struct.pack('<H', pop) if pop else b'\xc3')
        if symbol.startswith('__imp_'):
            uc.mem_write(slot, struct.pack('<I', stub))
            symbols[symbol] = slot
        else:
            uc.mem_write(slot, b'\xe9' + struct.pack('<i', stub-slot-5))
            symbols[symbol] = stub
    addresses = REBUILT if rebuilt else TARGETS
    if rebuilt:
        functions = {demangle(f.name): f for f in obj.functions if demangle(f.name) in TARGETS}
        assert functions.keys() == TARGETS.keys()
        symbols.update({f.name: REBUILT[n] for n, f in functions.items()})
        for n, f in functions.items():
            uc.mem_write(REBUILT[n], relocate(f, REBUILT[n], symbols))
        for slot, name in [(0, '?_GEWin32File'), (4, 'DiagnosticFile::Close'),
                           (16, 'EWin32File::Seek')]:
            uc.mem_write(FILE_VT+slot, struct.pack('<I', REBUILT[name]))
    trace, seek_results = [], iter(s['returns'])

    def string(p):
        return bytes(uc.mem_read(p, 2048)).split(b'\0', 1)[0]

    def hook(machine, address, length, user):
        labels = [n for n, a in STUBS.items() if a == address]
        if not labels:
            return
        label = labels[0]
        sp = machine.reg_read(UC_X86_REG_ESP)
        def args(n):
            return list(struct.unpack('<'+'I'*n, machine.mem_read(sp+4, n*4)))
        value = s['ok']
        if label == 'copyname':
            p, category = args(2)
            trace.append([label, p, string(p).hex(), category])
            value = 0 if s['fail_name'] else NAME
        elif label == 'freename':
            trace.append([label, *args(3)])
        elif label in ('close', 'free'):
            trace.append([label, *args(1)])
        elif label == 'error':
            trace.append([label])
            value = 5
        elif label in ('read', 'write'):
            handle, data, size, out, overlapped = args(5)
            assert data == DATA and size <= 32
            trace.append([label, handle, data, size, overlapped])
            machine.mem_write(out, struct.pack('<I', s['transferred']))
            if label == 'read' and s['ok']:
                machine.mem_write(data, b'\x7b' * s['transferred'])
            elif label == 'write':
                trace[-1].append(bytes(machine.mem_read(data, size)).hex())
        elif label == 'seek':
            trace.append([label, *args(4)])
            value = next(seek_results)
        elif label in ('gettime', 'settime'):
            handle, creation, access, write = args(4)
            trace.append([label, handle, creation, access])
            if label == 'gettime':
                machine.mem_write(write, struct.pack('<2I', *s['time']))
            else:
                trace[-1].extend(struct.unpack('<2I', machine.mem_read(write, 8)))
        elif label == 'strrchr':
            p, char = args(2)
            i = string(p).rfind(bytes([char]))
            value = p+i if i >= 0 else 0
        elif label == 'mkdir':
            p, security = args(2)
            trace.append([label, string(p).hex(), security])
        machine.reg_write(UC_X86_REG_EAX, value)

    uc.hook_add(UC_HOOK_CODE, hook)
    kind = s['kind']
    args = ([s['handle'], TEXT if s['name'] else 0] if kind == 'ctor' else
            [s['flags']] if kind == 'delete' else
            [DATA, s['request']] if kind in ('read', 'write') else
            [s['offset'], s['origin']] if kind == 'seek' else
            s['time'] if kind == 'settime' else
            [TEXT, int(s['skip'])] if kind == 'parents' else [])
    sp = STACK + 0x8000
    uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for register, value in preserved.items():
        uc.reg_write(register, value)
    uc.reg_write(UC_X86_REG_ECX, OBJECT)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(addresses[s['function']], STOP, count=20000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP
    pop = 0 if kind == 'parents' else len(args)*4
    assert uc.reg_read(UC_X86_REG_ESP) == sp + 4 + pop
    assert all(uc.reg_read(reg) == value for reg, value in preserved.items())
    result = None if kind in ('dtor', 'close', 'parents') else uc.reg_read(UC_X86_REG_EAX)
    if kind == 'gettime':
        result = [result, uc.reg_read(UC_X86_REG_EDX)]
    return dict(trace=trace, result=result, memory=bytes(uc.mem_read(HEAP, 0x10000)).hex(),
                count=struct.unpack('<I', uc.mem_read(COUNT, 4))[0])


def scenarios():
    defaults = dict(handle=0x12345678, count=7, name=True, text=b'file.dat'.hex(),
        fail_name=False, flags=0, ok=1, request=16, transferred=7, origin=0,
        offset=0, returns=[42], time=[0x89abcdef, 0x1234567], skip=False)
    def case(kind, method, **kw):
        return dict(defaults, kind=kind, function='EWin32File::'+method, **kw)
    for handle, count, name, fail in itertools.product([0, 5, MASK], [0, MASK], [False, True], [False, True]):
        yield case('ctor', 'EWin32File', handle=handle, count=count, name=name, fail_name=fail)
    for kind, handle, count, name, flags, ok in itertools.product(
            ['dtor', 'delete', 'close'], [0, 5, MASK], [0, 7], [False, True], [0, 1, 2, 3, MASK], [0, 1]):
        if kind != 'delete' and flags:
            continue
        method = 'EWin32File::~EWin32File' if kind == 'dtor' else '?_GEWin32File' if kind == 'delete' else 'DiagnosticFile::Close'
        yield dict(defaults, kind=kind, function=method, handle=handle, count=count, name=name, flags=flags, ok=ok)
    for kind, ok, request in itertools.product(['read', 'write'], [0, 1, MASK], [0, 1, 16]):
        for transferred in sorted({0, request//2, request}):
            yield case(kind, kind.title(), ok=ok, request=request, transferred=transferred)
    for origin, offset, returned in itertools.product([0, 1, 2, 3, MASK], [0, 1, MASK, 0x80000000], [0, 42, MASK]):
        yield case('seek', 'Seek', origin=origin, offset=offset, returns=[returned])
    for values in itertools.product([0, 42, MASK], repeat=3):
        yield case('size', 'Size', returns=list(values))
    for kind, ok, time in itertools.product(['gettime', 'settime'], [0, 1, MASK],
            [[0, 0], [MASK, MASK], [0x89abcdef, 0x1234567], [0, 0x80000000]]):
        yield case(kind, 'Vf18' if kind == 'gettime' else 'Vf1c', ok=ok, time=time)
    for path, skip, ok in itertools.product([b'', b'file', b'C:\\one\\two\\file', b'one/two/file',
            b'one\\two', b'\\server\\share\\file', b'one\\\\two\\', b'\xff\\\x80\\name'], [False, True], [0, 1]):
        yield dict(defaults, kind='parents', function='CreateParentDirectories', text=path.hex(), skip=skip, ok=ok)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/native-file/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ['build', '.local']):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/native_file.obj'
    obj, cases = ObjFile(str(path)), []
    for s in scenarios():
        want = expected(s)
        original, rebuilt = execute(pe, obj, s, False), execute(pe, obj, s, True)
        assert original == rebuilt == want, (s, original, rebuilt, want)
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d native file differential cases' % len(cases))


if __name__ == '__main__':
    main()
