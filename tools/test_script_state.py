#!/usr/bin/env python3
"""Script-state transitions and thread helpers against independent heap expectations.

GetThread, Reset and ReleaseThread execute with the transition body. Lua API
endpoints are mocks (including returning errors); real tables, error longjmp,
coroutines, scheduling, animation blending, navigation and gameplay are excluded.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_INVALID, UcError
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EDI, UC_X86_REG_EIP,
    UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EFLAGS)

from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate, read_string

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
SIZE = 0x20000
GAME, GAME2 = HEAP+0x100, HEAP+0xa000
MANAGER, MANAGER2 = GAME+0x9a34, GAME2+0x9a34
OBJECT, LUA, THREAD, THREAD_LUA = HEAP+0x1000, HEAP+0x2000, HEAP+0x4000, HEAP+0x5000
GLOBAL = 0x78bc20
ORIGINAL = {'EScriptObject::SetState': 0x5cb1e0,
    'EScriptManager::GetThread': 0x5cdef0, 'EScriptThread::Reset': 0x5ca870,
    'EScriptManager::ReleaseThread': 0x5ce220}
REBUILT = {name: CODE+i*0x1000 for i, name in enumerate(ORIGINAL)}
API = {'lua_gettop': 0x6aef20, 'lua_type': 0x6af080,
    'lua_pushstring': 0x6af7b0, 'lua_pushvalue': 0x6af030,
    'lua_settable': 0x6afc90, 'lua_error': 0x6b0cf0}
STRINGS = {0x711e08: b'ScriptVM: Wrong call to SetState. Usage: object:SetState(object.NewState);',
    0x711db0: b'ScriptVM: Wrong args passed to SetState. Usage: object:SetState(object.NewState);',
    0x711da0: b'CurrentState'}


def put(memory, address, value):
    struct.pack_into('<I', memory, address-HEAP, value & 0xffffffff)


def get(memory, address):
    return struct.unpack_from('<I', memory, address-HEAP)[0]


def byte(memory, address, value):
    memory[address-HEAP] = value & 255


def expected(s):
    """Explicit expected affected fields; no engine routines compute expectations."""
    memory = bytearray(b'\xa5'*SIZE)
    for pool in (MANAGER, MANAGER2):
        for i in range(255):
            put(memory, pool+0x138+4*i, HEAP+0x6000+4*i)
        put(memory, pool+0x238, s['mask'] & 0xffffffff)
        put(memory, pool+0x23c, s['mask'] >> 32)
    put(memory, THREAD+0x40, GLOBAL if s['redirect'] else THREAD_LUA)
    put(memory, THREAD+0x4c, s['status'])
    put(memory, THREAD+0x58, 0xabcdef01)
    put(memory, THREAD_LUA, HEAP+0x7000)
    put(memory, THREAD_LUA+4, HEAP+0x7100)
    put(memory, THREAD_LUA+16, HEAP+0x7200)  # Cbase must not be used by Reset.
    byte(memory, OBJECT+0x1c, s['flags'])
    byte(memory, OBJECT+0x1f, s['token'])
    if s['token']:
        put(memory, MANAGER+0x138+4*(s['token']-1), 0 if s['null_thread'] else THREAD)
    for i in s['duplicates']:
        put(memory, MANAGER+0x138+4*i, s['release_pointer'])
    put(memory, MANAGER2+0x138+4*7, THREAD)
    initial = bytes(memory)
    trace, result, fault, global_after = [], None, None, GAME
    kind = s['function']
    if kind == 'EScriptManager::GetThread':
        token = s['argument'] & 255
        result = get(memory, MANAGER+0x138+4*(token-1)) if token else 0
    elif kind == 'EScriptManager::Reset':
        raise AssertionError('invalid fixture symbol')
    elif kind == 'EScriptThread::Reset':
        if s['redirect']:
            global_after = GAME2
        else:
            put(memory, THREAD_LUA, HEAP+0x7100)
        put(memory, THREAD+0x58, 0)
        put(memory, THREAD+0x4c, 0)
    elif kind == 'EScriptManager::ReleaseThread':
        matches = [i for i in range(64) if (s['mask'] >> i) & 1 and
                   get(initial, MANAGER+0x138+4*i) == s['release_pointer']]
        if matches:
            i = min(matches)
            put(memory, MANAGER+0x238+4*(i//32), get(memory, MANAGER+0x238+4*(i//32)) & ~(1 << (i%32)))
    else:
        trace = [['gettop', LUA]]
        if s['top'] < 1:
            trace.append(['error', LUA, STRINGS[0x711e08].decode()])
        else:
            trace.append(['type', LUA, 1])
            valid = s['first_type'] == 4
            if valid:
                trace.append(['type', LUA, 2])
                if s['second_type'] != 5:
                    trace.append(['type', LUA, 2])
                valid = s['second_type'] in (1, 5)
            if not valid:
                trace.append(['error', LUA, STRINGS[0x711db0].decode()])
            else:
                trace += [['pushstring', LUA, 'CurrentState'], ['pushvalue', LUA, 2],
                          ['settable', LUA, 1], ['type', LUA, 2]]
                # settable mock may mutate the aliasing object's flags.
                flags = s['post_flags']
                byte(memory, OBJECT+0x1c, (flags | 4) if s['after_type'] == 1 else (flags & ~4))
                if s['token']:
                    trace.append(['getthread', MANAGER, s['token']])
                    if s['null_thread']:
                        fault = 0x4c
                    elif s['status'] == 4:
                        byte(memory, OBJECT+0x1f, 0)
                        trace.append(['reset', THREAD])
                        if s['redirect']:
                            global_after = GAME2
                        else:
                            put(memory, THREAD_LUA, HEAP+0x7100)
                        put(memory, THREAD+0x58, 0)
                        put(memory, THREAD+0x4c, 0)
                        pool = MANAGER2 if s['redirect'] else MANAGER
                        trace.append(['release', pool, THREAD])
                        matches = [i for i in range(64) if get(memory, pool+0x238+4*(i//32)) & (1 << (i%32)) and
                                   get(memory, pool+0x138+4*i) == THREAD]
                        if matches:
                            i = min(matches)
                            put(memory, pool+0x238+4*(i//32), get(memory, pool+0x238+4*(i//32)) & ~(1 << (i%32)))
    return initial, bytes(memory), trace, result, fault, global_after


class Runner:
    def __init__(self, pe, obj, rebuilt):
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
        uc.mem_map(base, (len(image)+4095)&~4095)
        uc.mem_write(base, image)
        for address, size in [(CODE, 0x5000), (HEAP, SIZE), (STACK, 0x10000), (STOP, 0x1000)]:
            uc.mem_map(address, size)
        self.entries = REBUILT if rebuilt else ORIGINAL
        functions = {demangle(f.name): f for f in obj.functions}
        symbols = {'_'+name: va for name, va in API.items()}
        symbols['?g_game@@3PAVGameApp@@A'] = GLOBAL
        for f in obj.functions:
            for _, _, name, _ in f.relocs():
                if demangle(name) in self.entries:
                    symbols[name] = self.entries[demangle(name)]
        for name, text in obj.strings().items():
            address = next(a for a, value in STRINGS.items() if value == text)
            assert pe.get_string_at_rva(address-base) == text
            symbols[name] = address
        if rebuilt:
            for name, va in self.entries.items():uc.mem_write(va, relocate(functions[name], va, symbols))
        for address in API.values():uc.mem_write(address, b'\xc3')
        uc.hook_add(UC_HOOK_CODE, self.callback)
        uc.hook_add(UC_HOOK_MEM_INVALID, self.invalid)

    def invalid(self, uc, access, address, size, value, user):
        self.fault = address
        return False

    def callback(self, uc, address, size, user):
        sp = uc.reg_read(UC_X86_REG_ESP)
        arg = lambda n: struct.unpack('<I', uc.mem_read(sp+4*n, 4))[0]
        if self.s['function'] == 'EScriptObject::SetState':
            for symbol, short in [('EScriptManager::GetThread', 'getthread'), ('EScriptThread::Reset', 'reset'), ('EScriptManager::ReleaseThread', 'release')]:
                if address == self.entries[symbol]:
                    event = [short, uc.reg_read(UC_X86_REG_ECX)]
                    if short != 'reset':event.append(arg(1))
                    if short in ('reset', 'release'):
                        assert bytes(uc.mem_read(OBJECT+0x1f, 1)) == b'\0'
                    if short == 'release':
                        assert struct.unpack('<I', uc.mem_read(THREAD+0x4c, 4))[0] == 0
                        assert struct.unpack('<I', uc.mem_read(THREAD+0x58, 4))[0] == 0
                    self.trace.append(event)
        if address not in API.values():return
        name = next(name for name, va in API.items() if va == address)
        assert arg(1) == LUA
        result = 0xdeadbeef
        if name == 'lua_gettop':self.trace.append(['gettop', LUA]);result = self.s['top']
        elif name == 'lua_type':
            index = arg(2);self.trace.append(['type', LUA, index])
            result = self.s['first_type'] if index == 1 else self.s['after_type'] if self.wrote_table else self.s['second_type']
        elif name in ('lua_pushstring', 'lua_error'):
            self.trace.append(['pushstring' if name == 'lua_pushstring' else 'error', LUA, read_string(uc, arg(2)).decode()])
        else:
            self.trace.append(['pushvalue' if name == 'lua_pushvalue' else 'settable', LUA, arg(2)])
            if name == 'lua_settable':
                self.wrote_table = True
                uc.mem_write(OBJECT+0x1c, bytes([self.s['post_flags']]))
        uc.reg_write(UC_X86_REG_EAX, result & 0xffffffff)
        uc.reg_write(UC_X86_REG_ECX, 0x11223344)
        uc.reg_write(UC_X86_REG_EDX, 0x55667788)

    def run(self, s, initial):
        self.s, self.trace, self.fault, self.wrote_table = s, [], None, False
        uc = self.uc
        uc.mem_write(HEAP, initial)
        uc.mem_write(GLOBAL, struct.pack('<II', GAME, GAME2))
        uc.mem_write(STACK, b'\xa5'*0x10000)
        kind = s['function']
        argument = LUA if kind == 'EScriptObject::SetState' else s['argument'] if kind == 'EScriptManager::GetThread' else s['release_pointer']
        sp = STACK+0x8000
        uc.mem_write(sp, struct.pack('<II', STOP, argument))
        saved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
        for reg, value in saved.items():uc.reg_write(reg, value)
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_ECX, OBJECT if kind == 'EScriptObject::SetState' else THREAD if kind == 'EScriptThread::Reset' else MANAGER)
        uc.reg_write(UC_X86_REG_EFLAGS, 2)
        try:uc.emu_start(self.entries[kind], STOP, count=20000)
        except UcError:
            if self.fault is None:raise
        if self.fault is None:
            assert uc.reg_read(UC_X86_REG_EIP) == STOP
            assert uc.reg_read(UC_X86_REG_ESP) == sp+(4 if kind == 'EScriptThread::Reset' else 8)
            assert all(uc.reg_read(reg) == value for reg, value in saved.items())
        if kind == 'EScriptManager::GetThread':
            want = ((argument & ~255) | (((argument & 255)-1) & 255)) if argument & 255 else argument
            assert struct.unpack('<I', uc.mem_read(sp+4, 4))[0] == want
        return bytes(uc.mem_read(HEAP, SIZE)), self.trace, uc.reg_read(UC_X86_REG_EAX), self.fault, struct.unpack('<I', uc.mem_read(GLOBAL, 4))[0]


def scenarios():
    base = dict(function='EScriptObject::SetState', top=2, first_type=4, second_type=5,
        after_type=5, flags=0xa5, post_flags=0x5a, token=1, status=4,
        mask=(1 << 64)-1, argument=1, release_pointer=THREAD, duplicates=[], redirect=False, null_thread=False)
    for top, first, second in itertools.product((-1, 0, 1, 2, 5), (-1, 0, 1, 2, 3, 4, 5), (-1, 0, 1, 2, 3, 4, 5)):
        yield dict(base, top=top, first_type=first, second_type=second)
    for token, status, second, after, flags in itertools.product((0, 1, 32, 33, 64, 65, 255), (-1, 0, 3, 4, 5), (1, 5), (1, 5, 2), (0, 255)):
        yield dict(base, token=token, status=status, second_type=second, after_type=after, flags=flags, post_flags=flags)
    for token, second in itertools.product((1, 64, 255), (1, 5)):
        yield dict(base, token=token, second_type=second, null_thread=True)
        yield dict(base, token=token, second_type=second, redirect=True)
    for token, upper in itertools.product(range(256), (0, 0xffffff00)):
        yield dict(base, function='EScriptManager::GetThread', token=0, argument=upper | token)
    for status, redirect in itertools.product((-1, 0, 4, 0x7fffffff), (False, True)):
        yield dict(base, function='EScriptThread::Reset', status=status, redirect=redirect)
    rng = random.Random(0x5ce220)
    for i, mode, pointer in itertools.product(range(64), ('empty', 'one', 'all', 'random'), (0, THREAD)):
        mask = 0 if mode == 'empty' else 1 << i if mode == 'one' else (1 << 64)-1 if mode == 'all' else rng.getrandbits(64)
        yield dict(base, function='EScriptManager::ReleaseThread', token=0, mask=mask,
                   release_pointer=pointer, duplicates=sorted({i, 63-i}))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    ap.add_argument('--object', type=Path, default=ROOT/'build/game/script_state.obj')
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):ap.error('private output required')
    raw, pe = load_reference(args.exe)
    obj = ObjFile(str(args.object))
    names = {demangle(f.name) for f in obj.functions}
    assert names >= ORIGINAL.keys()
    runners = [Runner(pe, obj, rebuilt) for rebuilt in (False, True)]
    cases = []
    for s in scenarios():
        initial, want, trace, result, fault, global_after = expected(s)
        for runner in runners:
            memory, calls, value, actual_fault, actual_global = runner.run(s, initial)
            assert memory == want, (s, 'heap')
            assert calls == trace, (s, calls, trace)
            assert fault == actual_fault, (s, actual_fault, fault)
            assert actual_global == global_after, (s, 'global')
            if result is not None:assert value == result, (s, value, result)
        cases.append(dict(s, passed=True))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(raw).hexdigest(),
        object_sha256={args.object.name: hashlib.sha256(args.object.read_bytes()).hexdigest()},
        scope=__doc__, cases=cases, mocks=list(API), exclusions=['real Lua tables/error longjmp',
        'real coroutine execution/scheduling', 'animation blending', 'navigation', 'gameplay']), indent=2)+'\n')
    print('Passed %d script-state differential cases' % len(cases))


if __name__ == '__main__':main()
