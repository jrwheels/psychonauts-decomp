#!/usr/bin/env python3
"""Original/rebuilt resource-file adapters and result-transfer tests.

The bridge executes native reader callbacks and destructor chains. File I/O,
resource parsing, close/free and node recycling are bounded mocks; no files or
assets are read. Ambiguous short COMDAT helpers are tested, not promoted.
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
STREAM, FILE, FACTORY, DEST, NAME, LIST, FIRST, NEXT = (HEAP+i*0x1000 for i in range(8))
BASE_VT, FILE_VT, READER_VT = 0x703650, 0x703640, 0x703630
ORIGINAL = {'EFileStream::GetName': 0x40ae40, 'EFileStream::~EFileStream': 0x40adf0,
    'EFileReader::Read': 0x40ae90, 'EFileReader::ReadBytes': 0x40aeb0,
    'MeshResourceReader::LoadFile': 0x41f1b0, 'ResourceList::PopFront': 0x6a5460,
    'EStream::GetName': 0x40ab00, '?_GEStream': 0x40ab10,
    '?_GEFileStream': 0x40ae60, '?_GEFileReader': 0x40af10}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}
STUBS = {n: STOP+(i+1)*0x100 for i, n in enumerate(['open', 'close', 'read', 'seek', 'free', 'recycle'])}
DISPATCH, FILE_TABLE, FACTORY_TABLE = STOP+0x800, STOP+0xe00, STOP+0xf00


def fixture(s):
    memory = bytearray(b'\xcc'*0x10000)
    def put(address, value):
        struct.pack_into('<I', memory, address-HEAP, value)
    put(STREAM, READER_VT)
    put(STREAM+0x10, FILE if s['file'] else 0)
    memory[0xc] = int(s['error'])
    memory[0x14] = int(s['owned'])
    put(FILE, FILE_TABLE)
    put(FILE+4, NAME if s['named'] else 0)
    put(FACTORY, FACTORY_TABLE)
    memory[NAME-HEAP:NAME-HEAP+10] = b'model.plb\0'
    put(LIST+0x10, NEXT if s['count']==2 else FIRST)
    put(LIST+0x14, FIRST)
    put(FIRST+4, NEXT if s['count']==2 else 0)
    put(FIRST+8, s['payload'])
    put(NEXT, FIRST)
    return memory


def expected(s):
    memory, trace, result = fixture(s), [], None
    def put(address, value):
        struct.pack_into('<I', memory, address-HEAP, value)
    def read(dest, size, returned):
        trace.append(['read', dest, size, returned])
        if 0 < size <= 8 and returned <= 8:
            n = min(size, returned)
            memory[DEST-HEAP:DEST-HEAP+n] = b'\x7b'*n
    def destroy(base=False):
        put(STREAM, BASE_VT)
        if not base and s['owned']:
            if s['file']:
                trace.append(['close', FILE])
            put(STREAM+0x10, 0)
    name = s['function']
    if name in ('EFileReader::Read', 'EFileReader::ReadBytes'):
        if s['data']:
            read(DEST, s['size'], s['returned'])
            if s['returned']!=s['size']:
                memory[0xc] = 1
        else:
            trace.append(['seek', s['size'], 1])
    elif name=='EFileStream::GetName':
        result = NAME if s['named'] else 0
    elif name=='EStream::GetName':
        result = 0
    elif name=='EFileStream::~EFileStream':
        destroy()
    elif name.startswith('?_G'):
        destroy(name=='?_GEStream')
        if s['flags'] & 1:
            trace.append(['free', STREAM])
        result = STREAM
    elif name=='ResourceList::PopFront':
        put(LIST+0x14, NEXT if s['count']==2 else 0)
        put(NEXT if s['count']==2 else LIST+0x10, 0)
        trace.append(['recycle', LIST, FIRST])
        result = s['payload']
    else:
        trace.append(['open', NAME, 0x400, 0])
        result = 0
        if s['opened']:
            trace.append(['dispatch', s['flags'], 0, 0, 1, FILE])
            error = False
            if s['data']:
                read(DEST, 8, s['returned'])
                error = s['returned']!=8
            else:
                trace.append(['seek', 8, 1])
            read(DEST, 8, 8)
            trace.append(['parsed', int(error)])
            trace.append(['close', FILE])
            result = s['resource']
    return dict(memory=memory.hex(), trace=trace, result=result)


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in [(CODE, 0x10000), (HEAP, 0x10000), (STACK, 0x10000), (STOP, 0x2000)]:
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(fixture(s)))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    uc.mem_write(0x781d90, struct.pack('<I', FACTORY))
    for name, pop in [('open', 12), ('close', 0), ('read', 8), ('seek', 8), ('free', 0), ('recycle', 4)]:
        uc.mem_write(STUBS[name], b'\xc2'+struct.pack('<H', pop) if pop else b'\xc3')
    for offset, name in [(4, 'close'), (8, 'read'), (0x10, 'seek')]:
        uc.mem_write(FILE_TABLE+offset, struct.pack('<I', STUBS[name]))
    uc.mem_write(FACTORY_TABLE, struct.pack('<I', STUBS['open']))
    uc.mem_write(0x700298, struct.pack('<I', STUBS['free']))
    # A bounded parser mock invokes the actual virtual reader twice, then returns.
    body = bytearray(b'\x55\x8b\xec')
    for dest in [DEST if s['data'] else 0, DEST]:
        body += b'\x6a\x08\x68'+struct.pack('<I', dest)+b'\x8b\x4d\x08\x8b\x01\xff\x50\x08'
    parsed = DISPATCH+len(body)
    body += b'\xb8'+struct.pack('<I', s['resource'])+b'\x8b\xe5\x5d\xc2\x08\x00'
    uc.mem_write(DISPATCH, bytes(body))
    for address, target in [(0x41f240, DISPATCH), (0x6a5260, STUBS['recycle'])]:
        uc.mem_write(address, b'\xe9'+struct.pack('<i', target-address-5))
    symbols = {'?g_diagnosticFileFactory@@3PAVEFileManager@@A': 0x781d90,
        '??_7EStream@@6B@': BASE_VT, '??_7EFileStream@@6B@': FILE_VT,
        '??_7EFileReader@@6B@': READER_VT, '__imp___aligned_free': 0x700298,
        '?ReadResource@MeshResourceReader@@QAEPAXPAVEFileReader@@H@Z': DISPATCH,
        '?ReleaseNode@ResourceList@@QAEXPAUResourceListNode@@@Z': STUBS['recycle']}
    addresses = REBUILT if rebuilt else ORIGINAL
    if rebuilt:
        functions = {demangle(f.name): f for f in obj.functions if demangle(f.name) in REBUILT}
        assert functions.keys()==REBUILT.keys()
        symbols.update({f.name: REBUILT[n] for n, f in functions.items()})
        for n, f in functions.items():
            uc.mem_write(REBUILT[n], relocate(f, REBUILT[n], symbols))
        for vt, entries in [(BASE_VT, ['?_GEStream', 'EStream::GetName']),
                (FILE_VT, ['?_GEFileStream', 'EFileStream::GetName']),
                (READER_VT, ['?_GEFileReader', 'EFileStream::GetName', 'EFileReader::Read'])]:
            for i, n in enumerate(entries):
                uc.mem_write(vt+i*4, struct.pack('<I', REBUILT[n]))
    trace, operations = [], []
    def hook(machine, address, length, user):
        sp = machine.reg_read(UC_X86_REG_ESP)
        def args(n):
            return list(struct.unpack('<'+'I'*n, machine.mem_read(sp+4, n*4)))
        if address==DISPATCH:
            reader, flags = args(2)
            assert struct.unpack('<I', machine.mem_read(reader, 4))[0]==READER_VT
            values = [struct.unpack('<I', machine.mem_read(reader+4, 4))[0],
                machine.mem_read(reader+0xc, 1)[0], machine.mem_read(reader+0x14, 1)[0],
                struct.unpack('<I', machine.mem_read(reader+0x10, 4))[0]]
            trace.append(['dispatch', flags, *values])
        elif address==parsed:
            reader = struct.unpack('<I', machine.mem_read(machine.reg_read(UC_X86_REG_EBP)+8, 4))[0]
            trace.append(['parsed', machine.mem_read(reader+0xc, 1)[0]])
        else:
            label = next((n for n in STUBS if STUBS[n]==address), None)
            value = 0
            if label=='open':
                trace.append([label, *args(3)])
                value = FILE if s['opened'] else 0
            elif label=='close':
                trace.append([label, machine.reg_read(UC_X86_REG_ECX)])
            elif label=='read':
                dest, size = args(2)
                value = s['returned'] if not operations else 8
                operations.append(value)
                trace.append([label, dest, size, value])
                if 0 < size <= 8 and value <= 8:
                    machine.mem_write(dest, b'\x7b'*min(size, value))
            elif label=='seek':
                operations.append(None)
                trace.append([label, *args(2)])
            elif label=='free':
                trace.append([label, *args(1)])
            elif label=='recycle':
                trace.append([label, machine.reg_read(UC_X86_REG_ECX), *args(1)])
            else:
                return
            machine.reg_write(UC_X86_REG_EAX, value)
    uc.hook_add(UC_HOOK_CODE, hook)
    name = s['function']
    args = ([DEST if s['data'] else 0, s['size']] if name in ('EFileReader::Read', 'EFileReader::ReadBytes') else
        [NAME, s['flags']] if name=='MeshResourceReader::LoadFile' else
        [s['flags']] if name.startswith('?_G') else [])
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
    saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
        UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    uc.reg_write(UC_X86_REG_ECX, LIST if name=='ResourceList::PopFront' else STREAM)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(addresses[name], STOP, count=30000)
    assert uc.reg_read(UC_X86_REG_EIP)==STOP
    assert uc.reg_read(UC_X86_REG_ESP)==sp+4+len(args)*4
    assert all(uc.reg_read(reg)==value for reg, value in saved.items())
    result = None if name in ('EFileReader::Read', 'EFileReader::ReadBytes', 'EFileStream::~EFileStream') else uc.reg_read(UC_X86_REG_EAX)
    return dict(memory=bytes(uc.mem_read(HEAP, 0x10000)).hex(), trace=trace, result=result)


def scenarios():
    base = dict(file=True, owned=True, named=True, error=False, data=True,
        size=8, returned=8, flags=0, opened=True, resource=0x12345678, count=1, payload=0)
    for name, data, size, returned, error in itertools.product(
            ['EFileReader::Read', 'EFileReader::ReadBytes'], [False, True],
            [0, 1, 8, 0xffffffff], [0, 1, 8, 0xffffffff], [False, True]):
        yield dict(base, function=name, data=data, size=size, returned=returned, error=error)
    for name, owned, file, flags in itertools.product(['EFileStream::~EFileStream',
            '?_GEStream', '?_GEFileStream', '?_GEFileReader'], [False, True], [False, True], [0, 1, 2, 3, 0xffffffff]):
        yield dict(base, function=name, owned=owned, file=file, flags=flags)
    for name, named in itertools.product(['EFileStream::GetName', 'EStream::GetName'], [False, True]):
        yield dict(base, function=name, named=named)
    for opened, resource, flags, data, returned in itertools.product([False, True],
            [0, 0x12345678], [0, 1, 0xffffffff], [False, True], [0, 8]):
        yield dict(base, function='MeshResourceReader::LoadFile', opened=opened,
            resource=resource, flags=flags, data=data, returned=returned)
    for count, payload in itertools.product([1, 2], [0, 0x12345678, 0xffffffff]):
        yield dict(base, function='ResourceList::PopFront', count=count, payload=payload)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/resource-stream/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ['build', '.local']):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/resource_stream.obj'
    obj, cases = ObjFile(str(path)), []
    for i, s in enumerate(scenarios()):
        want = expected(s)
        original, rebuilt = execute(pe, obj, s, False), execute(pe, obj, s, True)
        for key in want:
            assert original[key]==rebuilt[key]==want[key], (i, s, key,
                original[key] if key!='memory' else 'original heap',
                rebuilt[key] if key!='memory' else 'rebuilt heap',
                want[key] if key!='memory' else 'expected heap')
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d resource-stream differential cases' % len(cases))


if __name__=='__main__':
    main()
