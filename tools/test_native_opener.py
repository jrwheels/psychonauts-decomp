#!/usr/bin/env python3
"""Original/rebuilt native opener and streaming lifetime/producer chains.

Win32, filename helpers, allocation and scheduling are mocked. Large/invalid
buffer requests are traced without dereferencing them. No threads are started;
the consumer and real concurrent/file behavior remain unverified.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE,
                     UC_HOOK_MEM_READ_UNMAPPED)
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EDI, UC_X86_REG_EIP,
    UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
OBJECT, NAME, BUFFER, TEXT = HEAP, HEAP+0x1000, HEAP+0x2000, HEAP+0x4000
COUNT, BASE_VT, FILE_VT, STREAM_VT = 0x795a30, 0x71d8c4, 0x71d8a0, 0x71d874
MASK = 0xffffffff
TARGETS = {'OpenNativeFile': 0x6a8180, 'CreateParentDirectories': 0x6a8440,
    'EWin32File::EWin32File': 0x6a8580, 'EWin32File::~EWin32File': 0x6a8610,
    'NativeStreamingThread': 0x6a79c0, 'EWin32StreamingFile::Vf24': 0x6a7990,
    'EWin32StreamingFile::Vf20': 0x6a78a0,
    'EWin32StreamingFile::EWin32StreamingFile': 0x6a79e0,
    'EWin32StreamingFile::~EWin32StreamingFile': 0x6a7ad0,
    'EWin32StreamingFile::Write': 0x6a7a90, '?_GEWin32StreamingFile': 0x6a7aa0}
REBUILT = {n: CODE+i*0x1000 for i, n in enumerate(TARGETS)}
CALLEES = {
    'open': ('__imp__CreateFileA@28', 0x700110, 28),
    'error': ('__imp__GetLastError@0', 0x7000f8, 0),
    'alloc': ('__imp___aligned_malloc', 0x700288, 0),
    'free': ('__imp___aligned_free', 0x700298, 0),
    'close': ('__imp__CloseHandle@4', 0x7000f4, 4),
    'start': ('__imp__CreateThread@24', 0x70008c, 24),
    'exit': ('__imp__GetExitCodeThread@8', 0x700088, 8),
    'sleep': ('__imp__Sleep@4', 0x7000a4, 4),
    'init': ('__imp__InitializeCriticalSection@4', 0x700068, 4),
    'destroy': ('__imp__DeleteCriticalSection@4', 0x700064, 4),
    'enter': ('__imp__EnterCriticalSection@4', 0x7000b0, 4),
    'leave': ('__imp__LeaveCriticalSection@4', 0x7000b4, 4),
    'read': ('__imp__ReadFile@20', 0x7000fc, 20),
    'mkdir': ('__imp__CreateDirectoryA@8', 0x700040, 8),
    'strrchr': ('__imp__strrchr', 0x7002e8, 0),
    'copyname': ('?CopyFileName@@YAPADPBDH@Z', 0x6a6e10, 0),
    'freename': ('?FreeFileName@@YAXPADHH@Z', 0x6a6e30, 0)}
STUBS = {n: STOP+(i+1)*0x100 for i, n in enumerate(CALLEES)}


def signed(n):
    n &= MASK
    return n if n < 0x80000000 else n-0x100000000


def initial(s):
    memory = bytearray(b'\xcc'*0x10000)
    text = bytes.fromhex(s['text'])
    memory[TEXT-HEAP:TEXT-HEAP+len(text)+1] = text+b'\0'
    if s['kind'] not in ('open', 'ctor'):
        struct.pack_into('<4I', memory, 0, STREAM_VT, NAME if s['name'] else 0,
                         s['handle'], s['thread'])
        struct.pack_into('<7I', memory, 0x28, s['block'], s['blocks'],
                         BUFFER if s['buffer'] else 0, s['capacity'],
                         s['position'], 3, s['available'])
        memory[0x44] = int(s['stop'])
    return memory


def expected(s):
    memory, trace, count, result, fault = initial(s), [], s['count'], None, None
    def put(offset, value):
        struct.pack_into('<I', memory, offset, value & MASK)
    def construct(stream, handle, block, blocks):
        nonlocal count
        put(0, FILE_VT)
        put(8, handle)
        count = (count+1) & MASK
        if s['name']:
            trace.append(['copyname', TEXT, s['text'], 0x18])
            put(4, 0 if s['fail']=='name' else NAME)
        if stream:
            capacity = (block*blocks) & MASK
            put(0, STREAM_VT)
            for off, value in [(12, 0), (0x28, block), (0x2c, blocks), (0x34, capacity),
                               (0x38, 0), (0x3c, 0), (0x40, 0)]:
                put(off, value)
            memory[0x44] = 0
            allocated = 0 if s['fail']=='buffer' else BUFFER
            trace.append(['alloc', capacity, 16, allocated])
            put(0x30, allocated)
            trace.append(['init', OBJECT+0x10])
            memory[0x10:0x28] = b'\x1c'*24
    def start():
        trace.append(['start', 0, 0, 'NativeStreamingThread', OBJECT, 0, OBJECT+12])
        if s['thread_id'] is not None:
            put(12, s['thread_id'])
    def parents(path):
        i = path.rfind(b'\\')
        if i >= 0:
            prefix = path[:i]
            parents(prefix)
            if b'\\' in prefix:
                trace.append(['mkdir', prefix.hex(), 0])
    kind = s['kind']
    if kind == 'open':
        flags = s['options']
        result = 0
        if flags & 0xc00 and not (flags & 0x800 and flags & 0x1000):
            access = (0x80000000 if flags & 0x400 else 0) | (0x40000000 if flags & 0x800 else 0)
            share, creation = int(bool(flags & 0x4000)), [3, 4, 5, 2][(flags >> 8) & 3]
            attributes = 0x60000001 if flags & 0x8000 else 0x80
            for i, handle in enumerate(s['handles']):
                trace.append(['open', TEXT if s['name'] else 0, s['text'] if s['name'] else None,
                              access, share, 0, creation, attributes, 0])
                if handle != MASK:
                    stream = bool(flags & 0x1000)
                    p = 0 if s['fail']=='object' else OBJECT
                    trace.append(['alloc', 72 if stream else 12, 16, p])
                    if p:
                        construct(stream, handle, 0x8000, 12)
                        if stream:
                            start()
                        result = p
                    elif stream:
                        fault = ['read', 0, 4]
                        result = None
                    break
                trace.append(['error'])
                if i == 0 and flags & 0x100 and s['error']==3:
                    parents(bytes.fromhex(s['text']))
                else:
                    break
            else:
                raise AssertionError('fixture exhausted open results')
    elif kind == 'ctor':
        construct(True, s['handle'], s['block'], s['blocks'])
        result = OBJECT
    elif kind in ('dtor', 'delete'):
        put(0, STREAM_VT)
        if s['thread']:
            memory[0x44] = 1
            status = 0
            for value in s['exits']:
                trace.append(['exit', s['thread'], value])
                if value is not None:
                    status = value
                trace.append(['sleep', 0])
                if status != 0x103:
                    break
            else:
                raise AssertionError('fixture exhausted exit results')
            trace.append(['close', s['thread']])
        if s['buffer']:
            trace.append(['free', BUFFER])
        trace.append(['destroy', OBJECT+0x10])
        if s['name']:
            trace.append(['freename', NAME, 0x18, 1])
        count = (count-1) & MASK
        if s['handle']:
            trace.append(['close', s['handle']])
            put(8, 0)
        put(0, BASE_VT)
        if kind=='delete':
            result = OBJECT
            if s['flags'] & 1:
                trace.append(['free', OBJECT])
    elif kind=='start':
        start()
    elif kind=='write':
        result = MASK
    else:
        position, available, stop = s['position'], s['available'], s['stop']
        reads = iter(s['reads'])
        for iteration in range(20):
            if stop:
                break
            if signed(s['capacity']-available) < signed(s['block']):
                trace.append(['sleep', 0])
                if s['wake']=='space':
                    available = 0
                    put(0x40, available)
                else:
                    stop = True
                    memory[0x44] = 1
                continue
            n, ok = next(reads)
            dest = (BUFFER+position) & MASK
            trace.append(['read', s['handle'], dest, s['block'], 0, n, ok])
            if 0 < n <= 16 and BUFFER <= dest <= BUFFER+32-n:
                memory[dest-HEAP:dest-HEAP+n] = b'\x7b'*n
            trace.append(['enter', OBJECT+0x10])
            position = (position+n) & MASK
            if signed(position) >= signed(s['capacity']):
                position = 0
            available = (available+n) & MASK
            put(0x38, position)
            put(0x40, available)
            trace.append(['leave', OBJECT+0x10])
            if signed(n) < signed(s['block']):
                break
        else:
            raise AssertionError('unbounded worker fixture')
        if kind=='thread':
            result = 0
    return dict(memory=memory.hex(), trace=trace, count=count, result=result, fault=fault)


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in [(CODE, 0x10000), (HEAP, 0x10000), (STACK, 0x10000), (STOP, 0x2000)]:
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(initial(s)))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    uc.mem_write(COUNT, struct.pack('<I', s['count']))
    symbols = {'?g_win32FileCount@@3IA': COUNT, '??_7EWin32File@@6B@': FILE_VT,
               '??_7DiagnosticFile@@6B@': BASE_VT, '??_7EWin32StreamingFile@@6B@': STREAM_VT}
    for label, (symbol, slot, pop) in CALLEES.items():
        stub = STUBS[label]
        uc.mem_write(stub, b'\xc2'+struct.pack('<H', pop) if pop else b'\xc3')
        if symbol.startswith('__imp_'):
            uc.mem_write(slot, struct.pack('<I', stub))
            symbols[symbol] = slot
        else:
            uc.mem_write(slot, b'\xe9'+struct.pack('<i', stub-slot-5))
            symbols[symbol] = stub
    addresses = REBUILT if rebuilt else TARGETS
    if rebuilt:
        functions = {demangle(f.name): f for f in obj.functions if demangle(f.name) in TARGETS}
        assert functions.keys()==TARGETS.keys()
        symbols.update({f.name: REBUILT[n] for n, f in functions.items()})
        for name, f in functions.items():
            uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
        for slot, name in [(0, '?_GEWin32StreamingFile'), (0x20, 'EWin32StreamingFile::Vf20'),
                            (0x24, 'EWin32StreamingFile::Vf24')]:
            uc.mem_write(STREAM_VT+slot, struct.pack('<I', REBUILT[name]))
    trace, fault, allocations = [], [], []
    handles, exits, reads = iter(s['handles']), iter(s['exits']), iter(s['reads'])
    def string(pointer):
        return bytes(uc.mem_read(pointer, 2048)).split(b'\0', 1)[0]
    def hook(machine, address, length, user):
        labels = [n for n, a in STUBS.items() if a==address]
        if not labels:
            return
        label = labels[0]
        sp = machine.reg_read(UC_X86_REG_ESP)
        def args(n):
            return list(struct.unpack('<'+'I'*n, machine.mem_read(sp+4, n*4)))
        value = s['ok']
        if label=='open':
            p, access, share, security, creation, attributes, template = args(7)
            trace.append([label, p, string(p).hex() if p else None, access, share,
                          security, creation, attributes, template])
            value = next(handles)
        elif label=='error':
            trace.append([label])
            value = s['error']
        elif label=='alloc':
            size, alignment = args(2)
            stage = 'object' if s['kind']=='open' and not allocations else 'buffer'
            value = 0 if s['fail']==stage else OBJECT if stage=='object' else BUFFER
            trace.append([label, size, alignment, value])
            allocations.append(value)
        elif label in ('free', 'close'):
            trace.append([label, *args(1)])
        elif label=='copyname':
            p, category = args(2)
            trace.append([label, p, string(p).hex(), category])
            value = 0 if s['fail']=='name' else NAME
        elif label=='freename':
            trace.append([label, *args(3)])
        elif label=='start':
            security, size, callback, parameter, flags, out = args(6)
            assert callback==addresses['NativeStreamingThread']
            trace.append([label, security, size, 'NativeStreamingThread', parameter, flags, out])
            if s['thread_id'] is not None:
                machine.mem_write(out, struct.pack('<I', s['thread_id']))
            value = s['thread_result']
        elif label=='exit':
            thread, out = args(2)
            status = next(exits)
            trace.append([label, thread, status])
            value = int(status is not None)
            if status is not None:
                machine.mem_write(out, struct.pack('<I', status))
        elif label in ('init', 'destroy', 'enter', 'leave'):
            lock = args(1)[0]
            trace.append([label, lock])
            if label=='init':
                machine.mem_write(lock, b'\x1c'*24)
        elif label=='sleep':
            trace.append([label, *args(1)])
            if s['kind'] in ('worker', 'thread'):
                if s['wake']=='space':
                    machine.mem_write(OBJECT+0x40, struct.pack('<I', 0))
                else:
                    machine.mem_write(OBJECT+0x44, b'\1')
        elif label=='read':
            handle, dest, size, out, overlapped = args(5)
            n, value = next(reads)
            trace.append([label, handle, dest, size, overlapped, n, value])
            machine.mem_write(out, struct.pack('<I', n))
            if 0 < n <= 16 and BUFFER <= dest <= BUFFER+32-n:
                machine.mem_write(dest, b'\x7b'*n)
        elif label=='strrchr':
            p, char = args(2)
            i = string(p).rfind(bytes([char]))
            value = p+i if i >= 0 else 0
        elif label=='mkdir':
            p, security = args(2)
            trace.append([label, string(p).hex(), security])
        machine.reg_write(UC_X86_REG_EAX, value)
    def invalid(machine, access, address, size, value, user):
        fault.append(['read', address, size])
        return False
    uc.hook_add(UC_HOOK_CODE, hook)
    uc.hook_add(UC_HOOK_MEM_READ_UNMAPPED, invalid)
    kind = s['kind']
    args = ([TEXT if s['name'] else 0, s['options']] if kind=='open' else
            [s['handle'], TEXT if s['name'] else 0, s['block'], s['blocks']] if kind=='ctor' else
            [s['flags']] if kind=='delete' else [OBJECT] if kind=='thread' else
            [BUFFER, s['request']] if kind=='write' else [])
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for register, value in preserved.items():
        uc.reg_write(register, value)
    uc.reg_write(UC_X86_REG_ECX, OBJECT)
    uc.reg_write(UC_X86_REG_ESP, sp)
    try:
        uc.emu_start(addresses[s['function']], STOP, count=30000)
    except UcError:
        assert kind=='open' and s['options'] & 0x1000 and s['fail']=='object'
        assert fault==[['read', 0, 4]]
    if not fault:
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        pop = 0 if kind=='open' else len(args)*4
        assert uc.reg_read(UC_X86_REG_ESP)==sp+4+pop
        assert all(uc.reg_read(reg)==value for reg, value in preserved.items())
    result = None if fault or kind in ('dtor', 'start', 'worker') else uc.reg_read(UC_X86_REG_EAX)
    return dict(memory=bytes(uc.mem_read(HEAP, 0x10000)).hex(), trace=trace,
                count=struct.unpack('<I', uc.mem_read(COUNT, 4))[0], result=result,
                fault=fault[0] if fault else None)


def scenarios():
    defaults = dict(options=0x400, handles=[5], error=5, name=True,
        text=b'C:\\one\\two\\file.dat'.hex(), fail='', count=7, handle=5,
        thread=9, thread_id=123, thread_result=77, block=8, blocks=4, capacity=32,
        position=0, available=0, stop=False, buffer=True, flags=0, exits=[0],
        reads=[[0, 1]], wake='stop', ok=1, request=7)
    names = {'open':'OpenNativeFile', 'ctor':'EWin32StreamingFile::EWin32StreamingFile',
        'dtor':'EWin32StreamingFile::~EWin32StreamingFile', 'delete':'?_GEWin32StreamingFile',
        'start':'EWin32StreamingFile::Vf24', 'thread':'NativeStreamingThread',
        'worker':'EWin32StreamingFile::Vf20', 'write':'EWin32StreamingFile::Write'}
    def case(kind, **kw):
        return dict(defaults, kind=kind, function=names[kind], **kw)
    for combination in range(128):
        bits = [0x100, 0x200, 0x400, 0x800, 0x1000, 0x4000, 0x8000]
        options = sum(bit for i, bit in enumerate(bits) if combination & (1 << i))
        yield case('open', options=options)
    for options, error, handles, fail in itertools.product([0x500, 0x700, 0x900, 0x1500],
            [3, 5], [[MASK, 5], [MASK, MASK]], ['', 'object', 'buffer', 'name']):
        yield case('open', options=options, error=error, handles=handles, fail=fail)
    for options, fail, result, thread_id in itertools.product([0x400, 0x1400],
            ['', 'object', 'buffer', 'name'], [0, 77], [0, 123]):
        yield case('open', options=options, fail=fail, thread_result=result, thread_id=thread_id)
    for block, blocks, name, fail in itertools.product([0, 1, 16, 0x80000000, MASK],
            [0, 1, 12], [False, True], ['', 'buffer', 'name']):
        yield case('ctor', block=block, blocks=blocks, name=name, fail=fail, count=MASK)
    for kind, thread, name, buffer, flags, exits in itertools.product(['dtor', 'delete'],
            [0, 9], [False, True], [False, True], [0, 1, 2, 3, MASK],
            [[0], [0x103, 0], [None], [0x103, None, 0]]):
        if kind=='dtor' and flags:
            continue
        yield case(kind, thread=thread, name=name, buffer=buffer, flags=flags, exits=exits, count=0)
    for result, thread_id in itertools.product([0, 77], [0, MASK]):
        yield case('start', thread_result=result, thread_id=thread_id)
    for request in [0, 1, MASK]:
        yield case('write', request=request)
    workers = [dict(stop=True), dict(reads=[[0, 0]]), dict(reads=[[4, 0]]),
        dict(reads=[[8, 1], [4, 1]]), dict(position=28, reads=[[8, 1], [0, 1]]),
        dict(available=32, wake='space', reads=[[4, 1]]), dict(available=32),
        dict(position=0x7fffffff, reads=[[1, 1]]), dict(reads=[[MASK, 0]]),
        dict(available=0x80000000, reads=[[4, 1]]), dict(reads=[[0x80000000, 0]])]
    for kind, kw in itertools.product(['worker', 'thread'], workers):
        yield case(kind, **kw)
    for text in [b'', b'one/two', b'one\\two\\file', b'\\server\\share\\file', b'a'*259]:
        yield case('open', options=0x500, handles=[MASK, 5], error=3, text=text.hex())
    for options in [0, 0x1800, 0x400]:
        yield case('open', options=options, name=False, handles=[MASK])
    yield case('start', thread_result=0, thread_id=None)
    yield case('open', options=0x1400, thread_result=0, thread_id=None)
    yield case('dtor', handle=MASK, ok=0)
    yield case('open', handles=[0], count=MASK)
    yield case('open', options=0x2401)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/native-opener/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ['build', '.local']):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/native_file.obj'
    obj, cases = ObjFile(str(path)), []
    for s in scenarios():
        want = expected(s)
        original, rebuilt = execute(pe, obj, s, False), execute(pe, obj, s, True)
        for field in want:
            assert original[field]==rebuilt[field]==want[field], (
                s, field, original[field] if field!='memory' else 'heap mismatch',
                rebuilt[field] if field!='memory' else 'heap mismatch',
                want[field] if field!='memory' else 'heap mismatch')
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d native opener/streaming differential cases' % len(cases))


if __name__=='__main__':
    main()
