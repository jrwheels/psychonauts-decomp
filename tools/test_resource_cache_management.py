#!/usr/bin/env python3
"""Integrated hash/cache-chain differential checks against independent heap expectations.

Original/rebuilt Hash, Find, TryGet, Remove, Unlink and Release execute together.
FreeFileName and aligned_free are mocked; allocation, insertion, invalid pointers,
concurrent access and gameplay are excluded. Boolean results compare AL only.
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
    UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EFLAGS)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
CACHE, ENTRIES, BUCKETS, QUERY, OUTPUT = [HEAP+x for x in (0x100, 0x400, 0x800, 0x1000, 0x1200)]
SIZE = 0x4000
FREE_NAME, FREE_IMPORT, FREE_STUB = 0x6a6e30, 0x700298, STOP+0x100
ORIGINAL = {'ResourceCacheHash': 0x6a6780, 'ResourceCache::Find': 0x6a66a0,
    'ResourceCache::TryGet': 0x6a65d0, 'ResourceCache::Remove': 0x6a6560,
    'ResourceCache::Unlink': 0x6a6630, 'ResourceCache::Release': 0x6a6850}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}


def hash_expected(name):
    # Independent positional polynomial, rather than the engine's recurrence.
    return sum(byte * pow(31, len(name)-1-i, 1 << 32)
               for i, byte in enumerate(name)) & 0xffffffff


def put(memory, address, value):
    struct.pack_into('<I', memory, address-HEAP, value & 0xffffffff)


def get(memory, address):
    return struct.unpack_from('<I', memory, address-HEAP)[0]


def fixture(s):
    memory = bytearray(b'\xa5' * SIZE)
    for offset, value in ((0, 4*32+26), (4, 8*2+1), (8, ENTRIES),
            (12, s['live']), (16, s['free_head']), (24, BUCKETS), (28, s['buckets'])):
        put(memory, CACHE+offset, value)
    memory[CACHE+20-HEAP:CACHE+22-HEAP] = b'\xfe\xff'
    for index in range(s['buckets']):
        put(memory, BUCKETS+4*index, 0xffffffff)
    names = (b'Aa', b'BB', b'AaX', b'\x80\xff')
    for i, name in enumerate(names):
        address = HEAP+0x1400+i*0x100
        memory[address-HEAP:address-HEAP+len(name)+1] = name+b'\0'
        put(memory, ENTRIES+i*12, address)
        put(memory, ENTRIES+i*12+4, (0, 1, 0xffffffff, HEAP+0x3000)[i])
        put(memory, ENTRIES+i*12+8, 0xffffffff)
    # Aa and BB share their complete hash, providing a nontrivial collision.
    # Fixtures deliberately use one bucket to exercise deeper unrelated chains.
    chain = s['chain']
    if chain:
        bucket = hash_expected(names[chain[0]]) % s['buckets']
        put(memory, BUCKETS+4*bucket, chain[0] | s['flag'])
        for first, second in zip(chain, chain[1:]):
            put(memory, ENTRIES+first*12+8, second | s['flag'])
    memory[QUERY-HEAP:QUERY-HEAP+len(s['name'])+1] = s['name']+b'\0'
    return memory


def expected(s):
    memory = fixture(s)
    kind, trace = s['function'], []
    if kind == 'ResourceCacheHash':
        return memory, trace, hash_expected(s['name'])
    bucket = hash_expected(s['name']) % s['buckets']
    link = BUCKETS+4*bucket
    # Independent fixture model searches the declared chain, without interpreting
    # raw handles or following the engine's pointer traversal.
    hit = None
    names = (b'Aa', b'BB', b'AaX', b'\x80\xff')
    for position, index in enumerate(s['chain']):
        if names[index] == s['name']:
            hit = index
            link = BUCKETS+4*bucket if position == 0 else ENTRIES+s['chain'][position-1]*12+8
            break
    if kind == 'ResourceCache::Find':
        if s['output']:
            put(memory, OUTPUT, bucket)
        return memory, trace, link if hit is not None else 0
    if kind == 'ResourceCache::TryGet':
        if hit is not None and s['output']:
            put(memory, OUTPUT, get(memory, ENTRIES+hit*12+4))
        return memory, trace, int(hit is not None)
    if kind == 'ResourceCache::Release':
        hit = s['index']
        result = None
    elif kind == 'ResourceCache::Unlink':
        hit = s['index']
        position = s['chain'].index(hit)
        link = BUCKETS+4*bucket if position == 0 else ENTRIES+s['chain'][position-1]*12+8
        put(memory, link, get(memory, ENTRIES+hit*12+8))
        result = None
    else:
        if hit is None:
            return memory, trace, s['fallback']
        result = get(memory, ENTRIES+hit*12+4)
        put(memory, link, get(memory, ENTRIES+hit*12+8))
    entry = ENTRIES+hit*12
    trace.append(['FreeFileName', get(memory, entry), 26, 0])
    put(memory, entry, ((s['free_head'] & 0x7fffffff)*2+1) & 0xffffffff)
    put(memory, CACHE+16, hit)
    put(memory, CACHE+12, s['live']-1)
    return memory, trace, result


class Runner:
    def __init__(self, pe, functions, rebuilt):
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base, (len(image)+4095) & ~4095)
        uc.mem_write(base, image)
        for address, size in ((CODE, 0x10000), (HEAP, SIZE), (STACK, 0x10000), (STOP, 0x1000)):
            uc.mem_map(address, size)
        self.addresses = REBUILT if rebuilt else ORIGINAL
        if rebuilt:
            symbols = {f.name: REBUILT[name] for name, f in functions.items()}
            symbols.update({'?FreeFileName@@YAXPADHH@Z': FREE_NAME,
                            '__imp___aligned_free': FREE_IMPORT})
            for name, f in functions.items():
                uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
        uc.mem_write(FREE_NAME, b'\xc3')
        uc.mem_write(FREE_STUB, b'\xc3')
        uc.mem_write(FREE_IMPORT, struct.pack('<I', FREE_STUB))
        uc.hook_add(UC_HOOK_CODE, self.hook)

    def hook(self, uc, address, size, user):
        if address == FREE_NAME:
            sp = uc.reg_read(UC_X86_REG_ESP)
            arguments = struct.unpack('<III', uc.mem_read(sp+4, 12))
            self.trace.append(['FreeFileName', *arguments])
            uc.reg_write(UC_X86_REG_EAX, 0xdeadbeef)
            uc.reg_write(UC_X86_REG_ECX, 0x87654321)
            uc.reg_write(UC_X86_REG_EDX, 0xfedcba98)
        elif address == FREE_STUB:
            raise AssertionError('Entry explicit destruction must not delete storage')
        elif address in self.addresses.values():
            self.calls.append(next(name for name, va in self.addresses.items() if va == address))
            if address != self.entry:
                assert uc.reg_read(UC_X86_REG_ECX) == CACHE or address == self.addresses['ResourceCacheHash']

    def run(self, s):
        uc = self.uc
        self.trace, self.calls = [], []
        self.entry = self.addresses[s['function']]
        memory = fixture(s)
        uc.mem_write(HEAP, bytes(memory))
        uc.mem_write(STACK, b'\xa5'*0x10000)
        kind = s['function']
        if kind == 'ResourceCacheHash':
            args = [QUERY]
        elif kind in ('ResourceCache::Find', 'ResourceCache::TryGet'):
            args = [QUERY, OUTPUT if s['output'] else 0]
        elif kind == 'ResourceCache::Remove':
            args = [QUERY, s['fallback']]
        elif kind == 'ResourceCache::Unlink':
            args = [s['index'] | s['flag'], hash_expected(s['name']) % s['buckets']]
        else:
            args = [s['index'] | s['flag']]
        sp = STACK+0x8000
        uc.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *args))
        saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
        for reg, value in saved.items():
            uc.reg_write(reg, value)
        uc.reg_write(UC_X86_REG_ECX, CACHE)
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_EFLAGS, 2)
        uc.emu_start(self.entry, STOP, count=20000)
        assert uc.reg_read(UC_X86_REG_EIP) == STOP
        assert uc.reg_read(UC_X86_REG_ESP) == sp+4+(0 if kind == 'ResourceCacheHash' else 4*len(args))
        assert all(uc.reg_read(reg) == value for reg, value in saved.items())
        result = uc.reg_read(UC_X86_REG_EAX)
        if kind == 'ResourceCache::TryGet':
            result &= 255
        return bytes(uc.mem_read(HEAP, SIZE)), self.trace, result, self.calls


def scenarios():
    base = dict(function='ResourceCacheHash', buckets=1, chain=[0, 1, 2, 3],
                name=b'Aa', flag=0, live=4, free_head=0x7fffffff,
                output=True, fallback=0x12345678, index=0)
    for name in (b'', b'Aa', b'BB', b'AaX', b'\x80\xff', b'\xff'*64, b'abc'*200):
        yield dict(base, name=name)
    for kind, chain, name, flag, output in itertools.product(
            ('ResourceCache::Find', 'ResourceCache::TryGet', 'ResourceCache::Remove'),
            ([], [0], [0, 1], [0, 1, 2, 3]),
            (b'', b'Aa', b'BB', b'AaX', b'\x80\xff', b'AaY'),
            (0, 0x80000000), (False, True)):
        yield dict(base, function=kind, chain=chain, name=name, flag=flag, output=output)
    for buckets, name, flag in itertools.product((3, 17), (b'Aa', b'BB', b'absent'), (0, 0x80000000)):
        for kind in ('ResourceCache::Find', 'ResourceCache::TryGet', 'ResourceCache::Remove'):
            yield dict(base, function=kind, buckets=buckets, chain=[0, 1], name=name, flag=flag)
    for kind, index, flag, free_head, live in itertools.product(
            ('ResourceCache::Release', 'ResourceCache::Unlink'), range(4),
            (0, 0x80000000), (0x7fffffff, 0, 3, 0xffffffff), (0, 4)):
        yield dict(base, function=kind, index=index, flag=flag, free_head=free_head, live=live)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--object', type=Path, default=ROOT/'build/game/resource_cache.obj')
    ap.add_argument('--report', type=Path, default=ROOT/'build/cache-management/behavior.json')
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):
        ap.error('report must stay under ignored build/ or .local/')
    raw, pe = load_reference(args.exe)
    functions = {demangle(f.name): f for f in ObjFile(str(args.object)).functions if demangle(f.name) in ORIGINAL}
    assert functions.keys() == ORIGINAL.keys()
    runners = [Runner(pe, functions, rebuilt) for rebuilt in (False, True)]
    cases = []
    for s in scenarios():
        want_memory, want_trace, want_result = expected(s)
        results = [r.run(s) for r in runners]
        for memory, trace, result, calls in results:
            assert memory == want_memory, (s, 'heap')
            assert trace == want_trace, (s, trace, want_trace)
            if want_result is not None:
                assert result == want_result, (s, result, want_result)
        want_calls = [s['function']]
        if s['function'] in ('ResourceCache::Find', 'ResourceCache::TryGet', 'ResourceCache::Remove'):
            if s['function'] != 'ResourceCache::Find':
                want_calls.append('ResourceCache::Find')
            want_calls.append('ResourceCacheHash')
        if s['function'] in ('ResourceCache::Remove', 'ResourceCache::Unlink') and want_trace:
            want_calls.append('ResourceCache::Release')
        assert all(result[3] == want_calls for result in results), (s, 'call graph', want_calls)
        cases.append(dict(function=s['function'], name_hex=s['name'].hex(),
                          chain=s['chain'], flag=s['flag'], output=s['output'],
                          index=s['index'], live=s['live'], free_head=s['free_head'],
                          bucket_count=s['buckets'], passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={args.object.name: hashlib.sha256(args.object.read_bytes()).hexdigest()},
        scope=__doc__, cases=cases), indent=2)+'\n')
    print('Passed %d resource-cache management differential cases' % len(cases))


if __name__ == '__main__':
    main()
