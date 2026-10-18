#!/usr/bin/env python3
"""Hash-gated native joint and recursive skeleton lookup tests.

Real lookup/recursion/sibling chains execute. Only ASCII _stricmp is mocked;
no asset, animation playback, renderer or filesystem is exercised.
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
BONES, INFO, STRINGS = HEAP+0x1000, HEAP+0xd000, HEAP+0x14000
JOINTS, SKELETON, QUERY = HEAP+0x16000, HEAP+0x17000, HEAP+0x18000
ORIGINAL = {'ETriggerA8::FindBone': 0x438b70, 'ETriggerA8::FindJoint': 0x438be0,
            'EBone::GetNext': 0x4378b0, 'EBone::Find': 0x492c10}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}
NAMES = {0: 'Root', 1: 'Spine', 2: 'Head', 3: 'Arm', 4: 'Hand', 255: 'Last'}
CHILDREN = {0: [1, 3], 1: [2], 3: [4]}
COMPARE = STOP+0x100


def fixture(s):
    memory = bytearray(b'\xcc'*0x20000)
    def put(address, value):
        struct.pack_into('<I', memory, address-HEAP, value)
    def string(address, text):
        data = text.encode('ascii')+b'\0'
        memory[address-HEAP:address-HEAP+len(data)] = data
    put(SKELETON+4, INFO)
    for i, name in NAMES.items():
        put(BONES+i*0xb0+0xa8, SKELETON)
        memory[BONES-HEAP+i*0xb0+0xac:BONES-HEAP+i*0xb0+0xb0] = bytes([
            i, 0xa5, 3 if i==1 else 255,
            s['noise'] | (4 if i in CHILDREN else 0)])
        put(INFO+i*0x60+0x5c, STRINGS+i*32)
        string(STRINGS+i*32, name)
    for j, (index, name) in enumerate(s['roots']):
        joint, record = JOINTS+j*32, JOINTS+0x800+j*32
        put(JOINTS+0x400+j*4, joint)
        put(joint, record)
        put(joint+8, BONES+index*0xb0)
        put(record, STRINGS+0x2200+j*64)
        string(STRINGS+0x2200+j*64, name)
    put(HEAP+0x54, (len(s['roots']) << 5) | s['category'])
    put(HEAP+0x58, 0xffffffff)
    put(HEAP+0x5c, JOINTS+0x400 if s['roots'] else 0)
    if s['function']=='EBone::GetNext':
        memory[BONES-HEAP+s['index']*0xb0+0xac] = s['index']
        memory[BONES-HEAP+s['index']*0xb0+0xae] = s['next']
    string(QUERY, s['query'])
    return memory


def expected(s):
    trace = []
    def search(index):
        trace.append([s['query'], NAMES[index]])
        if s['query'].lower()==NAMES[index].lower():
            return BONES+index*0xb0
        for child in CHILDREN.get(index, []):
            found = search(child)
            if found:
                return found
        return 0
    name = s['function']
    if name=='EBone::GetNext':
        result = 0 if s['next']==255 else BONES+s['next']*0xb0
    elif name=='EBone::Find':
        result = search(s['index'])
    elif name=='ETriggerA8::FindJoint':
        result = next((JOINTS+j*32 for j, (_, n) in enumerate(s['roots'])
                       if n==s['query']), 0)
    else:
        result = 0
        for index, _ in s['roots']:
            result = search(index)
            if result:
                break
    return result, trace


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, size in [(CODE, 0x4000), (HEAP, 0x20000),
                           (STACK, 0x10000), (STOP, 0x1000)]:
        uc.mem_map(address, size)
    initial = bytes(fixture(s))
    uc.mem_write(HEAP, initial)
    uc.mem_write(STACK, b'\xa5'*0x10000)
    uc.mem_write(0x7002ac, struct.pack('<I', COMPARE))
    uc.mem_write(COMPARE, b'\xc3')
    addresses = REBUILT if rebuilt else ORIGINAL
    if rebuilt:
        functions = {demangle(f.name): f for f in obj.functions
                     if demangle(f.name) in REBUILT}
        assert functions.keys()==REBUILT.keys()
        symbols = {f.name: REBUILT[n] for n, f in functions.items()}
        symbols['__imp___stricmp'] = 0x7002ac
        for name, f in functions.items():
            uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
    trace = []
    def hook(machine, address, size, user):
        if address==COMPARE:
            sp = machine.reg_read(UC_X86_REG_ESP)
            pointers = struct.unpack('<2I', machine.mem_read(sp+4, 8))
            values = [bytes(machine.mem_read(p, 256)).split(b'\0', 1)[0] for p in pointers]
            trace.append([v.decode('ascii') for v in values])
            a, b = [v.lower() for v in values]
            machine.reg_write(UC_X86_REG_EAX, ((a>b)-(a<b)) & 0xffffffff)
    uc.hook_add(UC_HOOK_CODE, hook)
    args = [] if s['function']=='EBone::GetNext' else [QUERY]
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for reg, value in preserved.items():
        uc.reg_write(reg, value)
    uc.reg_write(UC_X86_REG_ECX, BONES+s['index']*0xb0
                 if s['function'].startswith('EBone::') else HEAP)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(addresses[s['function']], STOP, count=30000)
    assert uc.reg_read(UC_X86_REG_EIP)==STOP
    assert uc.reg_read(UC_X86_REG_ESP)==sp+4+len(args)*4
    assert all(uc.reg_read(reg)==value for reg, value in preserved.items())
    assert bytes(uc.mem_read(HEAP, 0x20000))==initial, 'lookup mutated fixture'
    return uc.reg_read(UC_X86_REG_EAX), trace


def scenarios():
    defaults = dict(roots=[], query='', index=0, next=255, noise=0, category=0)
    roots = [[], [(0, 'pack')], [(3, 'hat')], [(255, 'last')],
             [(0, 'pack'), (3, 'hat')], [(3, 'same'), (0, 'same')]]
    queries = ['', 'Root', 'root', 'Head', 'head', 'Hand', 'Arm', 'Last',
               'missing', 'pack', 'PACK', 'hat', 'same']
    for function, entries, query, noise, category in itertools.product(
            ['ETriggerA8::FindBone', 'ETriggerA8::FindJoint'], roots, queries,
            [0, 0xfb], [0, 31]):
        yield dict(defaults, function=function, roots=entries, query=query,
                   noise=noise, category=category)
    for index, query, noise in itertools.product([0, 1, 2, 3, 255], queries, [0, 0xfb]):
        yield dict(defaults, function='EBone::Find', index=index, query=query, noise=noise)
    for index, next_index in itertools.product([0, 1, 127, 255], [0, 1, 127, 254, 255]):
        yield dict(defaults, function='EBone::GetNext', index=index, next=next_index)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/mesh/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ['build', '.local']):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/mesh.obj'
    obj, cases = ObjFile(str(path)), []
    for s in scenarios():
        want = expected(s)
        assert execute(pe, obj, s, False)==execute(pe, obj, s, True)==want, s
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d native mesh/skeleton differential cases' % len(cases))


if __name__=='__main__':
    main()
