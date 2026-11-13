#!/usr/bin/env python3
"""Original Boyd action selection, transition lookup and interruption fixtures.

Executes hash-gated original x86, not rebuilt C++. Python stages a runtime table
from retained ActionFile headers/links; the original text parser is NOT tested.
Switch fixtures adapt the interpreter (0x441b00) and virtual notification.
Separate cursor fixtures execute that interpreter with its instruction dispatcher
(0x441240) adapted, establishing advancement and pending-command return behavior.
Animation playback, blend evaluation, Lua execution and gameplay are excluded.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
from native_index import load_reference, read_va

ROOT = Path(__file__).resolve().parents[1]
HEAP, STACK, STOP = 0x2000000, 0x3000000, 0x4000000
ACTOR, TABLE, ROWS, MATRIX, RECORDS, CURSOR = [HEAP+x for x in (0x100, 0x400, 0x800, 0x1000, 0x3000, 0x8000)]
VTABLE, NOTIFY = HEAP+0x9000, STOP+0x100
FUNCTIONS = {'name_lookup': 0x407d70, 'transition_lookup': 0x407e80,
    'switch': 0x440c70, 'named_switch': 0x440c00, 'named_override': 0x440bb0,
    'override': 0x440b30, 'action_name': 0x440ac0,
    'header': 0x407cf0, 'name': 0x407d30, 'entry': 0x407e20,
    'exit': 0x407e50, 'cursor': 0x407b70}
FUNCTIONS['interpret'] = 0x441b00


def source_table(path):
    raw = path.read_bytes()
    text = raw.decode('ascii').replace('\r\n', '\n')
    header, body = text.split('[EndHeaders]', 1)
    lines = header.splitlines()
    assert lines[0] == 'ActionFile' and len(lines[1:]) % 2 == 0
    names, flags = lines[1::2], [int(x) for x in lines[2::2]]
    sections = {}
    for match in re.finditer(r'^\[(\d+),(\d+)\]\n(.*?)(?=^\[\d+,\d+\]|^\[End\])', body, re.M | re.S):
        key = tuple(map(int, match.group(1, 2)))
        assert key not in sections
        sections[key] = match.group(3).strip()
    assert len(names) == 16 and names[4] == 'Init'
    def resolve(key, seen=()):
        assert key not in seen, ('linked cycle', key)
        value = sections.get(key)
        if value is None:return None
        linked = re.fullmatch(r'Linked (\d+),(\d+)', value)
        return resolve(tuple(map(int, linked.groups())), seen+(key,)) if linked else key
    resolved = {key: resolve(key) for key in itertools.product(range(len(names)), repeat=2)}
    assert all(value is not None for key, value in resolved.items() if key in sections)
    return raw, names, flags, sections, resolved


class Runner:
    def __init__(self, pe, names, flags, resolved):
        self.names, self.flags, self.resolved = names, flags, resolved
        self.records = {key: RECORDS+24*i for i, key in enumerate(sorted(set(resolved.values())-{None}))}
        self.reverse = {v:list(k) for k,v in self.records.items()}
        self.uc = u = Uc(UC_ARCH_X86, UC_MODE_32)
        image = pe.get_memory_mapped_image()
        u.mem_map(pe.OPTIONAL_HEADER.ImageBase, (len(image)+4095)&~4095)
        u.mem_write(pe.OPTIONAL_HEADER.ImageBase, image)
        for base, size in ((HEAP, 0x10000), (STACK, 0x10000), (STOP, 0x1000)):u.mem_map(base, size)
        u.hook_add(UC_HOOK_CODE, self.hook)

    def put(self, address, value):self.uc.mem_write(address, struct.pack('<I', value & 0xffffffff))
    def get(self, address):return struct.unpack('<I', self.uc.mem_read(address, 4))[0]
    def text(self, address):
        return bytes(self.uc.mem_read(address, 128)).split(b'\0')[0].decode('ascii') if address else None
    def finish(self, value, clean):
        u = self.uc;sp = u.reg_read(UC_X86_REG_ESP)
        u.reg_write(UC_X86_REG_EAX, value & 0xffffffff)
        u.reg_write(UC_X86_REG_EIP, self.get(sp));u.reg_write(UC_X86_REG_ESP, sp+4+clean)
        u.reg_write(UC_X86_REG_ECX, 0xdeadbeef)

    def hook(self, u, address, size, user):
        if address in FUNCTIONS.values():self.executed.add(address)
        if self.scenario.get('cursor_test'):
            if address == 0x441240:
                sp = u.reg_read(UC_X86_REG_ESP)
                assert self.get(sp+4) == CURSOR and u.reg_read(UC_X86_REG_ECX) == ACTOR
                self.events.append(['dispatch', self.get(CURSOR), self.get(sp+8)])
                if self.scenario.get('clear'):self.put(CURSOR, 0)
                self.finish(self.scenario['complete'], 8)
            return
        if address not in (0x441b00, NOTIFY):return
        sp = u.reg_read(UC_X86_REG_ESP)
        assert u.reg_read(UC_X86_REG_ECX) == ACTOR
        if address == NOTIFY:
            self.events.append(['notify', self.get(ACTOR+0xb0)])
            if self.scenario.get('notify_change'):self.put(ACTOR+0xb0, 3)
            self.finish(0, 0)
        else:
            cursor, flag = self.get(sp+4), self.get(sp+8)
            pointer = self.get(cursor)
            # Constructor writes only nine bytes; its trailing three stack bytes
            # have unspecified values and are not interpreted as semantic state.
            assert self.get(cursor+4) == 0 and self.uc.mem_read(cursor+8, 1) == b'\0'
            self.events.append(['interpret', self.reverse.get(pointer), flag, self.get(ACTOR+0xb0)])
            if self.scenario.get('exit_change') and len(self.events) == 1:self.put(ACTOR+0xb0, 3)
            self.finish(0, 8)

    def reset(self, s):
        self.scenario, self.events, self.executed = s, [], set()
        u = self.uc;u.mem_write(HEAP, b'\xa5'*0x10000);u.mem_write(STACK, b'\xa5'*0x10000)
        self.put(ACTOR, VTABLE);self.put(VTABLE+0x24, NOTIFY)
        for offset, value in ((0xac, 0 if s.get('null_table') else TABLE), (0xb0, s['old']),
                              (0xb4, 0x11111111), (0xb8, 0x22222222), (0xbc, CURSOR)):
            self.put(ACTOR+offset, value)
        self.put(TABLE, len(self.names)<<5 | 7);self.put(TABLE+8, ROWS)
        self.put(TABLE+0xc, MATRIX);self.put(TABLE+0x18, RECORDS)
        self.put(TABLE+0x1c, 0xffffffff)  # absent entry/exit pseudo-actions
        for i, (name, flag) in enumerate(zip(self.names, self.flags)):
            ptr = HEAP+0xa000+128*i;u.mem_write(ptr, name.encode()+b'\0')
            self.put(ROWS+8*i, ptr);self.put(ROWS+8*i+4, flag)
        if s.get('blocked') and 0 <= s['old'] < len(self.names):u.mem_write(ROWS+8*s['old']+4, b'\1')
        for pair, key in self.resolved.items():
            index = 0xffff if key is None else (self.records[key]-RECORDS)//24
            u.mem_write(MATRIX+2*(pair[0]*len(self.names)+pair[1]), struct.pack('<H', index))
        # Original debug instrumentation has an optional name-query branch.
        u.mem_write(0x795810, bytes([int(s.get('debug', False))]))
        for addr, value in ((0x77e9ec, 0xffffffff), (0x77e99c, 0xfffffffe), (0x77e958, 0xfffffffd), (0x77e968, 0xfffffffc)):self.put(addr, value)
        self.initial_actor = bytes(u.mem_read(ACTOR, 0x100))

    def call(self, function, args, this=ACTOR):
        u = self.uc;sp = STACK+0xf000
        u.mem_write(sp, struct.pack('<'+'I'*(len(args)+1), STOP, *(x & 0xffffffff for x in args)))
        saved = {UC_X86_REG_EBP:0x12345678, UC_X86_REG_EBX:0x23456789,
                 UC_X86_REG_ESI:0x3456789a, UC_X86_REG_EDI:0x456789ab}
        for register, value in saved.items():u.reg_write(register, value)
        u.reg_write(UC_X86_REG_ESP, sp);u.reg_write(UC_X86_REG_ECX, this)
        u.emu_start(FUNCTIONS[function], STOP, count=50000)
        assert u.reg_read(UC_X86_REG_EIP) == STOP, 'instruction budget exhausted'
        assert u.reg_read(UC_X86_REG_ESP) == sp+4+4*len(args), ('stack', function)
        assert all(u.reg_read(register) == value for register, value in saved.items()), 'callee saved registers'
        return u.reg_read(UC_X86_REG_EAX)

    def check_switch(self, s):
        self.reset(s)
        new = s['new'];function = s.get('function', 'switch');override = HEAP+0xe000
        self.uc.mem_write(override, b'TransitionFromOpenGate\0')
        if function in ('named_switch', 'named_override'):
            name = self.names[new] if 0 <= new < len(self.names) else 'MissingAction'
            self.uc.mem_write(HEAP+0xe100, name.encode()+b'\0')
            args = (HEAP+0xe100, s.get('immediate', 0)) if function == 'named_switch' else (HEAP+0xe100, 1, s.get('immediate', 0), override)
        elif function == 'override':args = (new, 1, s.get('immediate', 0), override)
        else:args = (new, s.get('immediate', 0), override)
        result = self.call(function, args) & 255
        old = s['old'];want_old, want_prev, want_override = old, 0x11111111, 0x22222222
        want_events = [];want_cursor = None
        # Expectations describe externally visible outcomes, not x86 execution.
        effective = 4 if old == -1 else old
        if function == 'override' and new == old:want = 1
        elif s.get('null_table'):want = 0
        elif new == old or new == effective:want = 1;want_old = effective
        elif new == -1:want = 0;want_old = effective
        elif s.get('blocked'):want = 0;want_old = effective
        elif new == 0xffff or self.resolved.get((effective, new)) is None:want = 0;want_old = effective
        else:
            want = 1;want_cursor = self.records[self.resolved[(effective, new)]]
            want_events = [['interpret', None, 1, effective]]
            if s.get('exit_change'):want_old = 3
            else:
                want_old, want_prev = new, effective
                want_override = override if function != 'named_switch' else 0
                want_events += [['interpret', None, 1, new], ['notify', new]]
                if s.get('notify_change'):want_old = 3
                elif s.get('immediate'):want_events.append(['interpret', list(self.resolved[(effective, new)]), 0, new])
        # Named invalid IDs return before the full switch body; no Init fixup.
        if function == 'named_switch' and new == 0xffff and old != 0xffff:want_old = old
        assert result == want, (s, 'result', result, want)
        assert self.events == want_events, (s, self.events, want_events)
        assert self.get(ACTOR+0xb0) == want_old & 0xffffffff, (s, 'current')
        assert self.get(ACTOR+0xb4) == want_prev and self.get(ACTOR+0xb8) == want_override, (s, 'previous/override')
        before, after = bytearray(self.initial_actor), bytearray(self.uc.mem_read(ACTOR, 0x100))
        before[0xb0:0xbc] = after[0xb0:0xbc]
        assert before == after, (s, 'unrelated actor fields')
        if want_cursor is not None:assert self.get(CURSOR) == want_cursor and self.get(CURSOR+4) == 0 and self.uc.mem_read(CURSOR+8, 1) == b'\0'
        else:assert bytes(self.uc.mem_read(CURSOR, 12)) == b'\xa5'*12
        return dict(s, result=result, events=self.events, executed=[hex(x) for x in sorted(self.executed)], passed=True)

    def check_cursor(self, s):
        self.reset(dict(s, old=4, cursor_test=True))
        pointer = 0 if s['opcode'] == -1 else RECORDS
        self.put(CURSOR, pointer);self.put(CURSOR+4, s['status'])
        self.uc.mem_write(CURSOR+8, b'\x5a')
        for i in range(s['length']):
            self.put(RECORDS+24*i, s['opcode'])
            self.put(RECORDS+24*i+0x10, s['flags'])
        self.put(RECORDS+24*s['length'], 8)
        got = self.call('interpret', (CURSOR,s['immediate'])) & 255
        terminal = s['opcode'] in (-1,8)
        count = 0 if terminal else s['length'] if s['complete'] and not s['clear'] else 1
        want_events = [['dispatch',RECORDS+24*i,s['immediate']] for i in range(count)]
        result = int(not terminal and not s['complete'] and not s['clear'] and s['opcode'] == 1 and s['flags'] & 3 == 3 and s['status'] != 0)
        next_pointer = 0 if terminal or s['complete'] or s['clear'] else RECORDS
        next_status = 0 if s['opcode'] == 8 or (s['complete'] and not terminal and not s['clear']) else s['status']
        assert got == result and self.events == want_events, (s,got,self.events,result,want_events)
        assert self.get(CURSOR) == next_pointer and self.get(CURSOR+4) == next_status, (s,'cursor state')
        assert self.uc.mem_read(CURSOR+8,1) == b'\x5a', (s,'untouched cursor byte')
        assert bytes(self.uc.mem_read(ACTOR,0x100)) == self.initial_actor
        return dict(test='cursor',**s,result=got,events=self.events,passed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path);parser.add_argument('action_file', type=Path)
    parser.add_argument('--report', required=True, type=Path);args = parser.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build', '.local')):parser.error('private report required')
    if args.report.exists():parser.error('report must be new; preserve previous evidence')
    raw, pe = load_reference(args.exe)
    action_raw, names, flags, sections, resolved = source_table(args.action_file)
    runner = Runner(pe, names, flags, resolved);cases = []
    for name, expected in [(name,i) for i,name in enumerate(names)]+[('stand',0xffff),('MissingAction',0xffff),('',0xffff)]:
        runner.reset(dict(old=4));runner.uc.mem_write(HEAP+0xe100, name.encode()+b'\0')
        got = runner.call('name_lookup', (HEAP+0xe100,), TABLE) & 0xffff
        assert got == expected, (name, got, expected)
        cases.append(dict(test='name_lookup', name=name, result=got, passed=True))
    for old,new in itertools.product(range(16), repeat=2):
        runner.reset(dict(old=old));got=runner.call('transition_lookup',(old,new),TABLE)
        assert got == runner.records.get(resolved[(old,new)],0), (old,new,got)
        cases.append(dict(test='transition_lookup', old=old,new=new,record=resolved[(old,new)],passed=True))
    for function,old,new,immediate in itertools.product(('switch','named_switch','named_override','override'),range(16),range(16),(0,1)):
        cases.append(runner.check_switch(dict(function=function,old=old,new=new,immediate=immediate)))
    for function,old,new,option in itertools.product(('switch','named_switch','named_override','override'),(4,11),(2,11),('null_table','blocked','exit_change','notify_change','debug')):
        cases.append(runner.check_switch(dict(function=function,old=old,new=new,immediate=1,**{option:True})))
    for function,old,new in itertools.product(('switch','named_switch','named_override','override'),(-1,4,0xffff),(4,11,0xffff)):
        # A non-sentinel request with invalid current ID dereferences the null
        # header returned by the real accessor; outside valid-runtime fixtures.
        if old == 0xffff and new != 0xffff:continue
        cases.append(runner.check_switch(dict(function=function,old=old,new=new)))
    for new in (-1,):cases.append(runner.check_switch(dict(old=4,new=new)))
    for opcode,flags,status,complete,clear,immediate,length in itertools.product((-1,1,2,3,8),range(4),(0,1),(0,1),(False,True),(0,1),(1,3)):
        cases.append(runner.check_cursor(dict(opcode=opcode,flags=flags,status=status,
            complete=complete,clear=clear,immediate=immediate,length=length)))
    report = dict(binary_sha256=hashlib.sha256(raw).hexdigest(),tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        action_file=str(args.action_file.resolve()),action_file_sha256=hashlib.sha256(action_raw).hexdigest(),
        names=names,header_flags=flags,source_sections=len(sections),resolved_pairs=sum(x is not None for x in resolved.values()),
        functions={k:hex(v) for k,v in FUNCTIONS.items()},scope=__doc__,cases=cases,
        function_body_sha256={hex(va):hashlib.sha256(read_va(pe,va,size)).hexdigest()
            for va,size in ((0x407d70,170),(0x407e80,197),(0x440c70,734),
                (0x440c00,108),(0x440bb0,80),(0x440b30,117),(0x441b00,234))},
        adapters=['switch fixtures: 0x00441b00 interpreter; optional reentrant action mutation',
                  'switch fixtures: virtual slot +0x24 notification; optional reentrant action mutation',
                  'cursor fixtures: 0x00441240 single-instruction dispatcher'],
        exclusions=['original ActionFile text parsing','real action instruction dispatch','blend curves/timing','root motion','real Lua scheduler','gameplay'])
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('Passed %d original Boyd action fixtures; %d source sections; %d resolved pairs' % (len(cases),len(sections),report['resolved_pairs']))


if __name__ == '__main__':main()
