#!/usr/bin/env python3
"""Native mesh replacement, lazy animation state and bone-ID differential tests.

The original SetMesh helper executes in both chains; it is not reconstructed.
Resource lookup, destruction, constructors, allocation and physics/rendering
endpoints are mocked. No original assets or runtime animation are exercised.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_WRITE_UNMAPPED
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
ENTITY, OLD, LOADED, EMPTY, STATE, EXISTING = (HEAP+i*0x1000 for i in range(6))
MODEL, EMPTY_MODEL = HEAP+0x6000, HEAP+0x6200
MANAGER, VT, PHYSICS, CONTEXT, GAME, BLENDS, TEXT = (HEAP+i*0x1000 for i in range(8, 15))
VT = STOP+0xe00
BONES, SKELETON, GROUP, ARRAY = HEAP+0x10000, HEAP+0x20000, HEAP+0x21000, HEAP+0x22000
ORIGINAL = {'EMeshEntity::LoadMesh': 0x43c980, 'ESkeleton::GetBoneId': 0x49a920,
    'EBone::GetId': 0x492cc0, 'EMeshManager::Create': 0x454eb0,
    'ETriggerA8::EnsureAnimState': 0x43ae60, 'EMeshAnimState::SetBlendShapes': 0x48e480}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}
CALLEES = {'manager': (0x454b10, 0), 'load': (0x454bc0, 8),
    'mesh_ctor': (0x435480, 0), 'state_ctor': (0x48d990, 0),
    'destroy': (0x454f70, 4), 'physics': (0x46f650, 0),
    'head': (0x43cc00, 4), 'context': (0x4370f0, 8),
    'alloc': (0x700288, 0), 'v14': (0, 4)}
STUBS = {name: STOP+(i+1)*0x100 for i, name in enumerate(CALLEES)}

EXTERNALS = {
    '?CreateMeshManager@@YAXXZ': 'manager',
    '?Load@EMeshManager@@QAEPAVETriggerA8@@PBDH@Z': 'load',
    '??0ETriggerA8@@QAE@XZ': 'mesh_ctor',
    '??0EMeshAnimState@@QAE@XZ': 'state_ctor',
    '?SetHeadBone@EMeshEntity@@QAEXPBD@Z': 'head',
    '?SetContext@ETriggerA8@@QAEXHPAX@Z': 'context'}


def fixture(s):
    memory = bytearray(b'\xcc'*0x30000)
    def put(address, value):
        struct.pack_into('<I', memory, address-HEAP, value & 0xffffffff)
    put(ENTITY, VT)
    put(ENTITY+0x10, PHYSICS)
    put(ENTITY+0x34, CONTEXT)
    put(ENTITY+0xa8, OLD if s['old'] else 0)
    put(LOADED+8, s['link'])
    put(LOADED+0x18, MODEL)
    put(LOADED+0x1d4, EXISTING if s['existing'] else 0)
    put(OLD+0x18, EMPTY_MODEL)
    memory[MODEL-HEAP+0x78] = int(s['animated'])
    put(MODEL+0xa4, s['association'])
    put(EMPTY_MODEL+0xa4, s['association'])
    put(GAME+0x10, BLENDS)
    text = (b'' if s['name']=='empty' else b'model.plb')+b'\0'
    memory[TEXT-HEAP:TEXT-HEAP+len(text)] = text
    put(SKELETON+0xc, GROUP)
    put(SKELETON+0x10, BONES)
    put(GROUP+0x54, (s['count'] << 5) | 31)
    put(GROUP+0x5c, ARRAY)
    for i in range(s['count']):
        put(ARRAY+i*4, SKELETON if i in s['members'] else GROUP+0x100+i*32)
    if s['function']=='EBone::GetId':
        put(BONES+s['offset']*0xb0+0xa8, SKELETON)
        memory[BONES-HEAP+s['offset']*0xb0+0xac] = 0xee
    return memory


def expected(s):
    memory, trace, fault = fixture(s), [], None
    def put(address, value):
        struct.pack_into('<I', memory, address-HEAP, value & 0xffffffff)
    manager_ready = s['manager']
    def manager():
        nonlocal manager_ready
        if not manager_ready:
            trace.append(['manager'])
            manager_ready = True
    def create():
        nonlocal fault
        trace.append(['alloc', 0x210, 16])
        if s['fail']=='mesh':
            fault = [0x14, 4]
            return 0
        trace.append(['mesh_ctor', EMPTY])
        memory[EMPTY-HEAP:EMPTY-HEAP+0x210] = b'\xa1'*0x210
        put(EMPTY+8, 0)
        put(EMPTY+0x18, EMPTY_MODEL)
        put(EMPTY+0x1d4, 0)
        put(EMPTY+0x14, ENTITY)
        return EMPTY
    def ensure():
        nonlocal fault
        if s['existing']:
            return EXISTING
        trace.append(['alloc', 0x224, 16])
        if s['fail']=='state':
            put(LOADED+0x1d4, 0)
            fault = [0x18, 4]
            return 0
        trace.append(['state_ctor', STATE])
        memory[STATE-HEAP:STATE-HEAP+0x224] = b'\xa3'*0x224
        put(LOADED+0x1d4, STATE)
        put(STATE+0x18, BLENDS)
        return STATE
    name = s['function']
    result = None
    if name in ('EBone::GetId', 'ESkeleton::GetBoneId'):
        index = next((i for i in range(s['count']) if i in s['members']), 0)
        result = ((index << 12) | (s['offset'] & 0xffff)) & 0xffff
    elif name=='EMeshAnimState::SetBlendShapes':
        put(STATE+0x18, BLENDS)
    elif name=='ETriggerA8::EnsureAnimState':
        ensure()
    elif name=='EMeshManager::Create':
        create()
        result = EMPTY if not fault else None
    else:
        success, replacement = False, 1
        if s['name']!='null':
            manager()
            trace.append(['load', '' if s['name']=='empty' else 'model.plb', s['flags']])
            if s['loaded']:
                success, replacement = True, LOADED
                if s['animated']:
                    state = ensure()
                    if fault:
                        return dict(memory=memory.hex(), trace=trace, result=None, fault=fault)
                    put(state+0x20, MODEL+0x6c)
        if not s['old']:
            manager()
            installed = create()
        else:
            manager()
            trace.append(['destroy', OLD])
            put(ENTITY+0xa8, 0)
            if replacement==1:
                installed = create()
            else:
                installed = replacement
                put(installed+0x14, ENTITY)
            if not fault:
                trace.append(['physics', PHYSICS])
                trace.append(['context', installed, 0, CONTEXT])
        if fault:
            return dict(memory=memory.hex(), trace=trace, result=None, fault=fault)
        put(ENTITY+0xa8, installed)
        if s['association']:
            trace.append(['v14', ENTITY, s['association']])
        trace.append(['head', ENTITY, 'headJA_1'])
        trace.append(['context', installed, 0, CONTEXT])
        result = int(success)
    return dict(memory=memory.hex(), trace=trace, result=result, fault=fault)


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, size in [(CODE, 0x10000), (HEAP, 0x30000),
                           (STACK, 0x10000), (STOP, 0x1000)]:
        uc.mem_map(address, size)
    uc.mem_write(HEAP, bytes(fixture(s)))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    uc.mem_write(0x783a30, struct.pack('<I', MANAGER if s['manager'] else 0))
    uc.mem_write(0x78bc20, struct.pack('<I', GAME))
    symbols = {'?g_meshManager@@3PAVEMeshManager@@A': 0x783a30,
               '?g_game@@3PAVGameApp@@A': 0x78bc20,
               '?SetMesh@EMeshEntity@@QAEXPAVETriggerA8@@_N@Z': 0x43cad0}
    for name, (address, pop) in CALLEES.items():
        uc.mem_write(STUBS[name], b'\xc2'+struct.pack('<H', pop) if pop else b'\xc3')
        if name=='alloc':
            uc.mem_write(address, struct.pack('<I', STUBS[name]))
        elif address:
            uc.mem_write(address, b'\xe9'+struct.pack('<i', STUBS[name]-address-5))
    addresses = REBUILT if rebuilt else ORIGINAL
    if rebuilt:
        functions = {demangle(f.name): f for f in obj.functions if demangle(f.name) in REBUILT}
        assert functions.keys()==REBUILT.keys()
        symbols.update({f.name: REBUILT[n] for n, f in functions.items()})
        for f in functions.values():
            for offset, size, symbol, kind in f.relocs():
                if symbol in symbols:
                    continue
                if symbol.startswith('$SG') or ':$SG' in symbol:
                    symbols[symbol] = 0x703f94
                elif symbol=='__imp___aligned_malloc':
                    symbols[symbol] = 0x700288
                else:
                    assert symbol in EXTERNALS, symbol
                    symbols[symbol] = STUBS[EXTERNALS[symbol]]
        for name, f in functions.items():
            uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
            uc.mem_write(ORIGINAL[name], b'\xe9'+struct.pack('<i', REBUILT[name]-ORIGINAL[name]-5))
    uc.mem_write(VT+0x14, struct.pack('<I', STUBS['v14']))
    uc.mem_write(VT+0x6c, struct.pack('<I', addresses['EMeshEntity::LoadMesh']))
    trace, fault = [], []
    def hook(machine, address, size, user):
        label = next((n for n in STUBS if STUBS[n]==address), None)
        if label is None:
            return
        sp, this = machine.reg_read(UC_X86_REG_ESP), machine.reg_read(UC_X86_REG_ECX)
        def args(n):
            return list(struct.unpack('<'+'I'*n, machine.mem_read(sp+4, n*4)))
        def text(pointer):
            return bytes(machine.mem_read(pointer, 128)).split(b'\0', 1)[0].decode('ascii')
        value = 0
        if label=='manager':
            trace.append([label])
            machine.mem_write(0x783a30, struct.pack('<I', MANAGER))
        elif label=='load':
            pointer, flags = args(2)
            assert this==MANAGER
            trace.append([label, text(pointer), flags])
            value = LOADED if s['loaded'] else 0
        elif label=='alloc':
            requested, alignment = args(2)
            trace.append([label, requested, alignment])
            assert alignment==16 and requested in (0x210, 0x224)
            value = (EMPTY if requested==0x210 else STATE)
            if s['fail']==('mesh' if requested==0x210 else 'state'):
                value = 0
        elif label in ('mesh_ctor', 'state_ctor'):
            trace.append([label, this])
            length, pattern = (0x210, b'\xa1') if label=='mesh_ctor' else (0x224, b'\xa3')
            machine.mem_write(this, pattern*length)
            if label=='mesh_ctor':
                for off, data in [(8, 0), (0x18, EMPTY_MODEL), (0x1d4, 0)]:
                    machine.mem_write(this+off, struct.pack('<I', data))
            value = this
        elif label=='destroy':
            assert this==MANAGER
            trace.append([label, *args(1)])
        elif label=='physics':
            trace.append([label, this])
        elif label=='head':
            trace.append([label, this, text(args(1)[0])])
        else:
            trace.append([label, this, *args(1 if label=='v14' else 2)])
        machine.reg_write(UC_X86_REG_EAX, value)
    def invalid(machine, access, address, size, value, user):
        fault.append([address, size])
        return False
    uc.hook_add(UC_HOOK_CODE, hook)
    uc.hook_add(UC_HOOK_MEM_WRITE_UNMAPPED, invalid)
    name = s['function']
    this = {'EMeshEntity::LoadMesh': ENTITY, 'EMeshManager::Create': MANAGER,
            'ETriggerA8::EnsureAnimState': LOADED, 'EMeshAnimState::SetBlendShapes': STATE,
            'ESkeleton::GetBoneId': SKELETON, 'EBone::GetId': BONES+s['offset']*0xb0}[name]
    args = ([0 if s['name']=='null' else TEXT, s['flags']] if name=='EMeshEntity::LoadMesh' else
            [ENTITY] if name=='EMeshManager::Create' else
            [BLENDS] if name=='EMeshAnimState::SetBlendShapes' else
            [BONES+s['offset']*0xb0] if name=='ESkeleton::GetBoneId' else [])
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
    saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
             UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    uc.reg_write(UC_X86_REG_ECX, this)
    uc.reg_write(UC_X86_REG_ESP, sp)
    entry = addresses[name]
    if name=='EMeshEntity::LoadMesh' and s['virtual']:
        entry = CODE+0xf000
        uc.mem_write(entry, b'\x8b\x01\xff\x60\x6c')
    try:
        uc.emu_start(entry, STOP, count=40000)
    except UcError:
        assert fault and fault[0] in ([0x14, 4], [0x18, 4]), (s, fault)
    if not fault:
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+4+len(args)*4
        assert all(uc.reg_read(reg)==value for reg, value in saved.items())
    result = None
    if not fault and name in ('EMeshEntity::LoadMesh', 'EMeshManager::Create', 'EBone::GetId', 'ESkeleton::GetBoneId'):
        mask = 0xff if name=='EMeshEntity::LoadMesh' else 0xffff if 'Id' in name else 0xffffffff
        result = uc.reg_read(UC_X86_REG_EAX) & mask
    return dict(memory=bytes(uc.mem_read(HEAP, 0x30000)).hex(), trace=trace,
                result=result, fault=fault[0] if fault else None)


def scenarios():
    base = dict(manager=True, name='model', old=True, loaded=True, animated=False,
        existing=False, association=0, link=0, flags=3, fail='', virtual=False,
        count=0, members=[], offset=0)
    for manager, name, old, loaded, animated, existing, association in itertools.product(
            [False, True], ['null', 'empty', 'model'], [False, True], [False, True],
            [False, True], [False, True], [0, 0x12345678]):
        yield dict(base, function='EMeshEntity::LoadMesh', manager=manager, name=name,
            old=old, loaded=loaded, animated=animated, existing=existing,
            association=association, virtual=not manager)
    for flags in [0, 1, 0xffffffff]:
        yield dict(base, function='EMeshEntity::LoadMesh', flags=flags)
    for link in [0xffffffff, LOADED]:
        yield dict(base, function='EMeshEntity::LoadMesh', link=link, association=0x12345678)
    for fail, old, name in itertools.product(['mesh', 'state'], [False, True], ['null', 'model']):
        yield dict(base, function='EMeshEntity::LoadMesh', fail=fail, old=old, name=name, animated=True)
    for fail in ['', 'mesh']:
        yield dict(base, function='EMeshManager::Create', fail=fail)
    for existing, fail in itertools.product([False, True], ['', 'state']):
        yield dict(base, function='ETriggerA8::EnsureAnimState', existing=existing, fail=fail)
    yield dict(base, function='EMeshAnimState::SetBlendShapes')
    for count, members, offset in itertools.product([0, 1, 3, 17],
            [[], [0], [1], [1, 2], [16]], [0, 1, 255, 4095, 4096, 65535, -1]):
        yield dict(base, function='ESkeleton::GetBoneId', count=count, members=members, offset=offset)
    for count, members, offset in itertools.product([0, 1, 3, 17], [[], [1], [16]], [0, 1, 255]):
        yield dict(base, function='EBone::GetId', count=count, members=members, offset=offset)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/mesh-replacement/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ['build', '.local']):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/mesh.obj'
    obj, cases = ObjFile(str(path)), []
    for i, s in enumerate(scenarios()):
        want = expected(s)
        original, rebuilt = execute(pe, obj, s, False), execute(pe, obj, s, True)
        for field in want:
            assert original[field]==rebuilt[field]==want[field], (i, s, field,
                original[field] if field!='memory' else 'original heap',
                rebuilt[field] if field!='memory' else 'rebuilt heap',
                want[field] if field!='memory' else 'expected heap')
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d mesh replacement/ID differential cases' % len(cases))


if __name__=='__main__':
    main()
