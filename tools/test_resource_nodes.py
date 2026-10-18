#!/usr/bin/env python3
"""Original/rebuilt recursive resource-owner propagation on synthetic graphs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import (UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX,
    UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
ORIGINAL = 0x464150


def fixture(shape):
    memory = bytearray(b'\xcc'*0x20000)
    node_cursor, link_cursor = 0x4000, 0x14000
    def build(offset, item):
        nonlocal node_cursor, link_cursor
        links, children = item
        child_base, link_base = node_cursor, link_cursor
        node_cursor += len(children)*0x80
        link_cursor += links*0x2c
        assert node_cursor <= 0x14000 and link_cursor <= len(memory)
        for member, count, data in ((0x4c, len(children), child_base), (0x58, links, link_base)):
            struct.pack_into('<III', memory, offset+member,
                count*32+13, count*2+1, HEAP+data if count else 0)
        return dict(offset=offset, links=[link_base+i*0x2c for i in range(links)],
            children=[build(child_base+i*0x80, child) for i, child in enumerate(children)])
    tree = build(0, shape)
    return memory, tree


def expected(shape, owner):
    memory, tree = fixture(shape)
    def visit(node):
        struct.pack_into('<I', memory, node['offset']+0x64, owner)
        for index, child in enumerate(node['children']):
            visit(child)
            for link in child['links']:
                struct.pack_into('<I', memory, link+8, owner)
                memory[link+12] = index & 0xff
    visit(tree)
    return bytes(memory)


def execute(pe, function, shape, owner, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image)+4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in ((CODE, 0x10000), (HEAP, 0x20000),
            (STACK, 0x10000), (STOP, 0x1000)):
        uc.mem_map(address, length)
    uc.mem_write(HEAP, bytes(fixture(shape)[0]))
    uc.mem_write(STACK, b'\xa5'*0x10000)
    if rebuilt:
        uc.mem_write(CODE, relocate(function, CODE, {function.name: CODE}))
    sp = STACK+0x8000
    uc.mem_write(sp, struct.pack('<III', STOP, owner, 0xaabbccdd))
    saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
        UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    uc.reg_write(UC_X86_REG_ECX, HEAP)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start(CODE if rebuilt else ORIGINAL, STOP, count=200000)
    assert uc.reg_read(UC_X86_REG_EIP)==STOP
    assert uc.reg_read(UC_X86_REG_ESP)==sp+8
    assert all(uc.reg_read(reg)==value for reg, value in saved.items())
    return bytes(uc.mem_read(HEAP, 0x20000))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'build/resource-parser/node-behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    data, pe = load_reference(args.exe)
    path = ROOT/'build/game/resource_node.obj'
    function = next(f for f in ObjFile(str(path)).functions if demangle(f.name)=='ResourceNode::SetOwner')
    shapes = {'empty': (2, []), 'single': (2, [(1, [])]),
        'chain': (1, [(2, [(1, [])])]),
        'branch': (1, [(2, []), (1, [(3, [])])]),
        'wide': (1, [(1, [])]*257)}
    cases = []
    for name, shape in shapes.items():
        for owner in (0, 0x12345678):
            want = expected(shape, owner)
            original, rebuilt = execute(pe, function, shape, owner, False), execute(pe, function, shape, owner, True)
            assert original==rebuilt==want, (name, owner, 'heap mismatch')
            cases.append(dict(shape=name, owner=owner, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'binary_sha256': hashlib.sha256(data).hexdigest(),
        'object_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        'scope': __doc__, 'cases': cases}, indent=2)+'\n')
    print('Passed %d recursive resource-node differential cases' % len(cases))


if __name__=='__main__':
    main()
