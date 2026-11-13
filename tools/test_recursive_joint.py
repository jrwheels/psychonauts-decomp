#!/usr/bin/env python3
"""Recursive joint traversal against independent tree fixtures; stream/name/Euler mocked.

The caller preallocates records. Empty means a joint with no children, not a
zero-root skeleton. Full heap comparison includes untouched records and fields.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
OWNER, STREAM, VTABLE = HEAP+0x100, HEAP+0x300, HEAP+0x400
BONES, INFO, NAMES = HEAP+0x1000, HEAP+0x10000, HEAP+0x20000
ENTRY, STRING, SET_NAME, EULER, READ = 0x492010, 0x6a5d10, 0x491ab0, 0x69f400, CODE+0x2000
IDENTITY_QUAT = struct.pack('<4f', 0, 0, 0, 1)


def fixtures(tree, version, id_mode, rotation_mode, initial_flags, index_base):
    """Build an event stream and independent final graph from a nested tree."""
    nodes = []
    def visit(children, parent):
        ordinal = len(nodes)
        node = dict(children=[], parent=parent)
        nodes.append(node)
        for child in children:
            node['children'].append(visit(child, ordinal))
        return ordinal
    visit(tree, None)
    events = []
    for i, node in enumerate(nodes):
        node['index'] = index_base+i
        node['name'] = ('joint_%d'%i).encode()+b'\0'
        node['translation'] = struct.pack('<3f', i+0.25, -i-0.5, 3.0)
        node['euler'] = struct.pack('<3f', *[(-1.,-1.,-1.), (i+1.,-2.,0.5),
                                            (0.,0.,0.), (-1.,-1.,0.)][rotation_mode])
        node['rotation'] = (IDENTITY_QUAT if rotation_mode == 0 else
                            node['euler']+struct.pack('<f', 0.75))
    def serialize(i):
        node = nodes[i]
        events.extend([('name', i, node['name']), ('set-name', i, node['name']),
                       ('read', INFO+node['index']*0x60+0x40, node['translation']),
                       ('read', None, node['euler'])])
        if rotation_mode: events.append(('euler', i, node['euler']))
        if version > 294: events.append(('read', None, struct.pack('<H', 0xffff if id_mode else i)))
        events.append(('read', None, struct.pack('<I', len(node['children']))))
        for child in node['children']:
            events.append(('read', None, struct.pack('<H', 0xffff if id_mode else child)))
            serialize(child)
    serialize(0)
    return nodes, events


def expected(memory, nodes, flags):
    result = bytearray(memory)
    for i, node in enumerate(nodes):
        bone = BONES-HEAP+i*0xb0
        info = INFO-HEAP+node['index']*0x60
        result[info+0x40:info+0x4c] = node['translation']
        result[info+0x4c:info+0x5c] = node['rotation']
        struct.pack_into('<I', result, info+0x5c, NAMES+i*64)
        result[bone+0x80:bone+0x90] = node['rotation']
        result[bone+0x9c:bone+0xa8] = node['translation']
        struct.pack_into('<I', result, bone+0xa8, OWNER)
        value = flags & ~5
        if node['children']: value |= 4
        if node['euler'] == struct.pack('<3f', -1., -1., -1.): value |= 8
        result[bone+0xaf] = value
        if node['parent'] is not None:
            result[bone+0xad] = nodes[node['parent']]['index']
        for child, sibling in zip(node['children'], node['children'][1:]):
            result[BONES-HEAP+child*0xb0+0xae] = nodes[sibling]['index']
    return bytes(result)


class Runner:
    def __init__(self, pe, function=None):
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base, (len(image)+4095)&~4095)
        uc.mem_write(base, image)
        for address, size in ((CODE,0x4000),(HEAP,0x30000),(STACK,0x20000),(STOP,0x1000)):
            uc.mem_map(address,size)
        self.entry = ENTRY
        if function:
            symbols = {}
            for _, _, symbol, _ in function.relocs():
                name = demangle(symbol)
                if name == 'RuntimeBone::ReadInput': value = ENTRY
                elif name == 'BoneInfo::SetName': value = SET_NAME
                elif 'ReadString' in name: value = STRING
                elif 'SetEuler' in name: value = EULER
                elif 'g_identityQuat' in name: value = 0x795318
                elif symbol == '__real@bf800000': value = 0x7021cc
                else: raise AssertionError(('unknown relocation', symbol, name))
                symbols[symbol] = value
            uc.mem_write(ENTRY, relocate(function, ENTRY, symbols))
        for address, code in ((STRING,b'\xc2\x08\x00'),(SET_NAME,b'\xc2\x04\x00'),
                              (EULER,b'\xc2\x04\x00'),(READ,b'\xc2\x08\x00')):
            uc.mem_write(address,code)
        uc.hook_add(UC_HOOK_CODE,self.callback)

    def callback(self, uc, address, size, user):
        if address not in (STRING, SET_NAME, EULER, READ): return
        assert self.position < len(self.events), ('unexpected call',hex(address))
        kind, target, data = self.events[self.position]
        self.position += 1
        sp = uc.reg_read(UC_X86_REG_ESP)
        arg = lambda i: struct.unpack('<I',uc.mem_read(sp+4+i*4,4))[0]
        this = uc.reg_read(UC_X86_REG_ECX)
        if address == STRING:
            assert kind == 'name' and this == STREAM and arg(1) == 255
            uc.mem_write(arg(0),data)
        elif address == READ:
            assert kind == 'read' and this == STREAM and arg(1) == len(data)
            if target is not None: assert arg(0) == target
            else: assert STACK <= arg(0) < STACK+0x20000
            uc.mem_write(arg(0),data)
        elif address == SET_NAME:
            node = self.nodes[target]
            assert kind == 'set-name' and this == INFO+node['index']*0x60
            assert bytes(uc.mem_read(arg(0),len(data))) == data
            uc.mem_write(this+0x5c,struct.pack('<I',NAMES+target*64))
        else:
            node = self.nodes[target]
            assert kind == 'euler' and this == INFO+node['index']*0x60+0x4c
            assert bytes(uc.mem_read(arg(0),12)) == data
            uc.mem_write(this,node['rotation'])
        uc.reg_write(UC_X86_REG_EAX,0xfeed1234)
        uc.reg_write(UC_X86_REG_ECX,0xdeadbeef)
        uc.reg_write(UC_X86_REG_EDX,0x12345678)

    def run(self, memory, nodes, events, version):
        self.nodes,self.events,self.position = nodes,events,0
        uc = self.uc
        uc.mem_write(HEAP,memory)
        uc.mem_write(STACK,b'\xa5'*0x20000)
        uc.mem_write(0x795318,IDENTITY_QUAT)
        sp = STACK+0x18000
        uc.mem_write(sp,struct.pack('<IIII',STOP,STREAM,version,OWNER))
        saved = {UC_X86_REG_EBX:0x12345678,UC_X86_REG_ESI:0x23456789,
                 UC_X86_REG_EDI:0x3456789a,UC_X86_REG_EBP:0x456789ab}
        for reg,value in saved.items(): uc.reg_write(reg,value)
        uc.reg_write(UC_X86_REG_ECX,BONES)
        uc.reg_write(UC_X86_REG_ESP,sp)
        uc.reg_write(UC_X86_REG_EFLAGS,2)
        uc.emu_start(self.entry,STOP,count=1000000)
        assert uc.reg_read(UC_X86_REG_EIP) == STOP
        assert uc.reg_read(UC_X86_REG_ESP) == sp+16
        assert uc.reg_read(UC_X86_REG_EAX) == BONES+len(nodes)*0xb0
        assert all(uc.reg_read(reg)==value for reg,value in saved.items())
        assert self.position == len(events)
        return bytes(uc.mem_read(HEAP,0x30000))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe',type=Path)
    parser.add_argument('--object',type=Path,default=ROOT/'build/game/skeleton_input.obj')
    parser.add_argument('--original-only',action='store_true')
    parser.add_argument('--report',type=Path,default=ROOT/'build/recursive-joint/behavior.json')
    args = parser.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):
        parser.error('report must stay private')
    raw,pe = load_reference(args.exe)
    runners = [Runner(pe)]
    hashes = {}
    if not args.original_only:
        obj = ObjFile(str(args.object))
        functions = [f for f in obj.functions if demangle(f.name)=='RuntimeBone::ReadInput']
        assert len(functions)==1
        runners.append(Runner(pe,functions[0]))
        hashes[args.object.name] = hashlib.sha256(args.object.read_bytes()).hexdigest()
    rng = random.Random(0x492010)
    trees = {'leaf':[], 'single-child':[[]], 'branching':[[],[],[]],
             'nested':[[[[]]],[],[[],[[]]]]}
    cases = []
    for label,tree in trees.items():
        for version in (0,294,295,0xffffffff):
            for id_mode in (0,1):
                for rotation_mode in (0,1,2,3):
                    for flags in (1,0xff):
                        for index_base in (0,31):
                            nodes,events = fixtures(tree,version,id_mode,rotation_mode,flags,index_base)
                            memory = bytearray(rng.randbytes(0x30000))
                            struct.pack_into('<I',memory,OWNER-HEAP+4,INFO)
                            struct.pack_into('<I',memory,STREAM-HEAP,VTABLE)
                            struct.pack_into('<I',memory,VTABLE-HEAP+8,READ)
                            for i,node in enumerate(nodes):
                                memory[BONES-HEAP+i*0xb0+0xac] = node['index']
                                memory[BONES-HEAP+i*0xb0+0xaf] = flags
                            want = expected(memory,nodes,flags)
                            for runner in runners:
                                got = runner.run(bytes(memory),nodes,events,version)
                                assert got == want,(label,version,id_mode,rotation_mode,flags,index_base,
                                                     next((i for i,(a,b) in enumerate(zip(got,want)) if a!=b),None))
                            cases.append(dict(shape=label,nodes=len(nodes),version=version,
                                              arbitrary_ids=bool(id_mode),rotation_mode=rotation_mode,
                                              initial_flags=flags,index_base=index_base,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256=hashes,scope=__doc__,original_only=args.original_only,
        mocks=['stream Read','stream ReadString','BoneInfo::SetName','quaternion SetEuler'],
        exclusions=['zero-root skeleton','allocation and cleanup (caller/dependencies)',
                    'real string ownership','real Euler conversion','physical I/O',
                    'truncated or malformed streams','invalid pointers/counts','NaN Euler angles',
                    'index overflow/aliasing','gameplay'],cases=cases),indent=2)+'\n')
    print('Passed %d recursive-joint %s cases'%(len(cases),'original-only' if args.original_only else 'differential'))

if __name__ == '__main__': main()
