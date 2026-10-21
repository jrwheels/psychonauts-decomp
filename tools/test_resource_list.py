#!/usr/bin/env python3
"""Original/rebuilt resource-list and pool chains with independent heap models.

Only aligned allocation/free are mocked. New list/pool methods, existing
PopFront and the already matched context-list Clear body execute as real x86.
The Clear alias is an observed same-layout code entry, not a class identity claim.
All fixtures are synthetic; no real allocator, game file or asset is exercised.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parents[1]
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
POOL0, POOL1, NODES, FREE_NODES = HEAP+0x1000, HEAP+0x1800, HEAP+0x1008, HEAP+0x1100
MALLOC, FREE = STOP+0x100, STOP+0x200
ORIGINAL = {'AllocateResourceListPool':0x6a4fa0,'ResourceListPool::Release':0x6a4fe0,
    'ResourceList::AllocateNode':0x6a5190,'ResourceList::ReleaseNode':0x6a5260,
    'ResourceList::PushBack':0x6a52a0,'ResourceList::PushFront':0x6a5300,
    'ResourceList::PopBack':0x6a5400,'ResourceList::InsertAfter':0x6a54c0,
    'ResourceList::InsertBefore':0x6a5540,'ResourceList::RemoveNode':0x6a55b0,
    'ResourceList::AppendList':0x6a5360,'ResourceList::PrependList':0x6a53b0,
    'ResourceList::RefillNodes':0x6a5100,'ResourceList::PopFront':0x6a5460,'ContextListBase::Clear':0x6a5090}
REBUILT = {name:CODE+i*0x1000 for i,name in enumerate(ORIGINAL)}
OPERATIONS = {'pushback':'ResourceList::PushBack','pushfront':'ResourceList::PushFront',
    'popback':'ResourceList::PopBack','popfront':'ResourceList::PopFront',
    'insert':'ResourceList::InsertAfter','allocate':'ResourceList::AllocateNode',
    'release':'ResourceList::ReleaseNode','pool_alloc':'AllocateResourceListPool',
    'pool_release':'ResourceListPool::Release','clear':'ContextListBase::Clear'}
OPERATIONS.update(before='ResourceList::InsertBefore',remove='ResourceList::RemoveNode',append='ResourceList::AppendList',prepend='ResourceList::PrependList',refill='ResourceList::RefillNodes')
VOID = {'release','pool_release','clear','append','prepend','refill','remove'}
MASK = 0xffffffff


def fixture(s):
    memory=bytearray(b'\xcc'*0x8000)
    def put(address,value):struct.pack_into('<I',memory,address-HEAP,value&MASK)
    count=s['count'];depth=s['pools'];free=s['free']
    for i,pool in enumerate((POOL0,POOL1)[:depth]):put(pool,POOL0 if i else 0)
    for i in range(count):
        node=NODES+i*12
        put(node,NODES+(i-1)*12 if i else 0)
        put(node+4,NODES+(i+1)*12 if i+1<count else 0)
        put(node+8,(0,0xabcdef01,0xffffffff)[i%3])
    for i in range(free):
        put(FREE_NODES+i*12,FREE_NODES+(i+1)*12 if i+1<free else 0)
    for offset,value in [(0,s.get('count_override',count)),(4,(POOL0,POOL1)[depth-1] if depth else 0),
            (8,s['growth']),(12,FREE_NODES if free else 0),
            (16,NODES+(count-1)*12 if count else 0),(20,NODES if count else 0)]:put(HEAP+offset,value)
    if 'source_count' in s:
        source=HEAP+0x100;start=HEAP+0x2000;length=s['source_count']
        for offset,value in [(0,length),(4,0),(8,0),(12,0),(16,start+(length-1)*12 if length else 0),(20,start if length else 0)]:put(source+offset,value)
        for i in range(length):
            put(start+i*12,start+(i-1)*12 if i else 0)
            put(start+i*12+4,start+(i+1)*12 if i+1<length else 0)
            put(start+i*12+8,(0,0xffffffff,0x12345678)[i%3])
    return memory


class Model:
    def __init__(self,s):self.s=s;self.memory=fixture(s);self.trace=[];self.allocations=0
    def read(self,address):return struct.unpack_from('<I',self.memory,address-HEAP)[0]
    def write(self,address,value):struct.pack_into('<I',self.memory,address-HEAP,value&MASK)
    def allocate_pool(self,count,stride):
        block=HEAP+0x4000+self.allocations*0x200;self.allocations+=1
        self.trace.append(['alloc',(count*stride+8)&MASK,16,block])
        self.write(block,self.read(HEAP+4));self.write(HEAP+4,block)
        return block
    def release_pool(self,pool):
        while pool:
            following=self.read(pool);self.trace.append(['free',pool])
            if self.s['poison']:self.memory[pool-HEAP:pool-HEAP+8]=b'\xdd'*8
            pool=following
    def clear(self):
        for offset in (0,20,16,12):self.write(HEAP+offset,0)
        self.release_pool(self.read(HEAP+4));self.write(HEAP+4,0)
    def refill(self):
        if not self.read(HEAP+12):
            growth=self.read(HEAP+8);pool=self.allocate_pool(growth,12)
            signed=(growth-1)&MASK
            signed=signed if signed<0x80000000 else signed-0x100000000
            for i in range(signed,-1,-1):
                node=pool+8+i*12;self.write(node,self.read(HEAP+12));self.write(HEAP+12,node)
    def allocate_node(self,following,previous):
        self.refill()
        node=self.read(HEAP+12);self.write(HEAP+12,self.read(node))
        self.write(node+4,following);self.write(node,previous)
        self.write(HEAP,self.read(HEAP)+1);self.write(node+8,0)
        return node
    def release_node(self,node):
        self.write(node,self.read(HEAP+12));self.write(HEAP+12,node)
        self.write(HEAP,self.read(HEAP)-1)
        if not self.read(HEAP):self.clear()
    def position(self,index):
        if index is None:return 0
        node=self.read(HEAP+20)
        for i in range(index):node=self.read(node+4)
        return node
    def apply(self,op):
        name=op[0]
        if name=='refill':self.refill();return None
        if name in ('append','prepend'):
            source=HEAP if self.s.get('self_copy') else HEAP+0x100
            if self.s.get('bounded_self_copy'):
                cursor=self.read(source+(20 if name=='append' else 16))
                for _ in range(12):
                    value=self.read(cursor+8)
                    cursor=self.read(cursor+(4 if name=='append' else 0))
                    self.apply(['pushback' if name=='append' else 'pushfront',value])
                return None
            # Independent sequence oracle: snapshot payloads before destination edits.
            values=[];cursor=self.read(source+20)
            while cursor:
                values.append(self.read(cursor+8));cursor=self.read(cursor+4)
            for value in values if name=='append' else reversed(values):
                self.apply(['pushback' if name=='append' else 'pushfront',value])
            return None
        if name=='before':
            if op[1] is None:return self.apply(['pushfront',op[2]])
            following=self.position(op[1]);previous=self.read(following)
            node=self.allocate_node(following,previous);self.write(node+8,op[2])
            if previous:self.write(previous+4,node)
            else:self.write(HEAP+20,node)
            self.write(following,node);return node
        if name=='remove':
            node=self.position(op[1]);previous=self.read(node);following=self.read(node+4)
            if previous:self.write(previous+4,following)
            else:self.write(HEAP+20,following)
            if following:self.write(following,previous)
            else:self.write(HEAP+16,previous)
            self.release_node(node);return None
        if name=='pool_alloc':return self.allocate_pool(op[1],op[2])
        if name=='pool_release':self.release_pool(self.read(HEAP+4));return None
        if name=='clear':self.clear();return None
        if name=='allocate':return self.allocate_node(op[1],op[2])
        if name=='release':self.release_node(NODES);return None
        if name=='insert' and op[1] is None:return self.apply(['pushback',op[2]])
        if name in ('pushback','pushfront','insert'):
            previous=self.position(op[1]) if name=='insert' else self.read(HEAP+16) if name=='pushback' else 0
            following=self.read(previous+4) if name=='insert' else self.read(HEAP+20) if name=='pushfront' else 0
            node=self.allocate_node(following,previous)
            self.write(node+8,op[2] if name=='insert' else op[1])
            if name=='pushfront':
                if following:self.write(following,node)
                else:self.write(HEAP+16,node)
                self.write(HEAP+20,node)
            elif name=='pushback':
                if previous:self.write(previous+4,node)
                else:self.write(HEAP+20,node)
                self.write(HEAP+16,node)
            else:
                if following:self.write(following,node)
                else:self.write(HEAP+16,node)
                self.write(previous+4,node)
            return node
        front=name=='popfront';node=self.read(HEAP+(20 if front else 16));data=self.read(node+8)
        neighbor=self.read(node+(4 if front else 0));self.write(HEAP+(20 if front else 16),neighbor)
        if neighbor:self.write(neighbor+(0 if front else 4),0)
        else:self.write(HEAP+(16 if front else 20),0)
        self.release_node(node);return data
    def expected(self):
        states=[]
        for op in self.s['ops']:
            result=self.apply(op);states.append((bytes(self.memory),list(self.trace),result))
        return states


def execute(pe,functions,s,rebuilt):
    uc=Uc(UC_ARCH_X86,UC_MODE_32);image=pe.get_memory_mapped_image();base=pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base,(len(image)+4095)&~4095);uc.mem_write(base,image)
    for address,size in ((CODE,0x10000),(HEAP,0x8000),(STACK,0x10000),(STOP,0x1000)):uc.mem_map(address,size)
    uc.mem_write(HEAP,bytes(fixture(s)));uc.mem_write(STACK,b'\xa5'*0x10000)
    uc.mem_write(MALLOC,b'\xc3');uc.mem_write(FREE,b'\xc3')
    uc.mem_write(0x700288,struct.pack('<I',MALLOC));uc.mem_write(0x700298,struct.pack('<I',FREE))
    if rebuilt:
        symbols={f.name:REBUILT[name] for name,f in functions.items()}
        symbols.update({'__imp___aligned_malloc':0x700288,'__imp___aligned_free':0x700298,
            '?Clear@ResourceList@@QAEXXZ':REBUILT['ContextListBase::Clear'],
            '?Release@ContextPool@@QAEXXZ':REBUILT['ResourceListPool::Release']})
        for name,f in functions.items():uc.mem_write(REBUILT[name],relocate(f,REBUILT[name],symbols))
    trace=[];allocations=0;insertions=0;bounded_stop=False
    def read(address):return struct.unpack('<I',uc.mem_read(address,4))[0]
    def hook(machine,address,length,user):
        nonlocal allocations,insertions,bounded_stop
        if s.get('bounded_self_copy'):
            entry=(REBUILT if rebuilt else ORIGINAL)['ResourceList::PushBack' if s['ops'][0][0]=='append' else 'ResourceList::PushFront']
            if address==entry:
                insertions+=1
                if insertions>12:
                    bounded_stop=True;machine.emu_stop();return
        sp=machine.reg_read(UC_X86_REG_ESP)
        if address==MALLOC:
            size,alignment=struct.unpack('<II',machine.mem_read(sp+4,8));block=HEAP+0x4000+allocations*0x200;allocations+=1
            assert allocations<32;trace.append(['alloc',size,alignment,block]);machine.reg_write(UC_X86_REG_EAX,block)
        elif address==FREE:
            block=read(sp+4);trace.append(['free',block])
            if s['poison']:machine.mem_write(block,b'\xdd'*8)
            machine.reg_write(UC_X86_REG_EAX,0xdeadbeef)
        else:return
        machine.reg_write(UC_X86_REG_ECX,0x11223344);machine.reg_write(UC_X86_REG_EDX,0x55667788)
    uc.hook_add(UC_HOOK_CODE,hook);states=[]
    for op in s['ops']:
        name=op[0];args=op[1:];receiver=HEAP
        if name in ('insert','before','remove'):
            position=0 if op[1] is None else read(HEAP+20)
            if op[1] is not None:
                for i in range(op[1]):position=read(position+4)
            args=[position] if name=='remove' else [position,op[2]]
        if name in ('append','prepend'):args=[HEAP if s.get('self_copy') else HEAP+0x100]
        if name=='release':args=[NODES]
        if name=='pool_alloc':args=[HEAP+4,*args]
        if name=='pool_release':receiver=read(HEAP+4)
        sp=STACK+0x8000;uc.mem_write(sp,struct.pack('<'+'I'*(len(args)+1),STOP,*args))
        saved={UC_X86_REG_EBP:0x12345678,UC_X86_REG_EBX:0x23456789,UC_X86_REG_ESI:0x3456789a,UC_X86_REG_EDI:0x456789ab}
        for reg,value in saved.items():uc.reg_write(reg,value)
        uc.reg_write(UC_X86_REG_ESP,sp);uc.reg_write(UC_X86_REG_ECX,receiver)
        uc.emu_start((REBUILT if rebuilt else ORIGINAL)[OPERATIONS[name]],STOP,count=30000)
        if s.get('bounded_self_copy'):
            assert bounded_stop and insertions==13
            states.append((bytes(uc.mem_read(HEAP,0x8000)),list(trace),None))
            continue
        assert uc.reg_read(UC_X86_REG_EIP)==STOP
        assert uc.reg_read(UC_X86_REG_ESP)==sp+4+(0 if name=='pool_alloc' else len(args)*4)
        assert all(uc.reg_read(reg)==value for reg,value in saved.items())
        result=None if name in VOID else uc.reg_read(UC_X86_REG_EAX)
        states.append((bytes(uc.mem_read(HEAP,0x8000)),list(trace),result))
    return states


def scenarios():
    base=dict(count=0,free=0,growth=2,pools=0,poison=False,ops=[])
    for count,source_count,free,growth,name in itertools.product((0,1,3),(0,1,3),(0,2),(1,4),('append','prepend')):
        yield dict(base,count=count,source_count=source_count,free=free,growth=growth,pools=1,ops=[[name]])
    for count,free,growth,name in itertools.product((0,1,3),(0,2),(1,4),('append','prepend')):
        yield dict(base,count=count,free=free,growth=growth,pools=1,self_copy=True,bounded_self_copy=count>1,ops=[[name]])
    for free,growth,count in itertools.product((0,2),(0,1,4,0xffffffff),(0,3)):
        yield dict(base,count=count,free=free,growth=growth,pools=1,ops=[['refill'],['refill']])
    for count,free,growth,poison,value in itertools.product((0,1,3),(0,2),(1,4),(False,True),(0,0xffffffff)):
        state=dict(base,count=count,free=free,growth=growth,pools=1,poison=poison)
        for name in ('pushback','pushfront'):yield dict(state,ops=[[name,value]])
        for position in [None,*range(count)]:
            for method in ('insert','before'):yield dict(state,ops=[[method,position,value]])
    for count,free,poison in itertools.product((1,2,3),(0,2),(False,True)):
        for position in range(count):yield dict(base,count=count,free=free,pools=2,poison=poison,ops=[['remove',position]])
        for name in ('popfront','popback'):yield dict(base,count=count,free=free,pools=2,poison=poison,ops=[[name]])
    for count,free,poison in itertools.product((0,1,3,0xffffffff),(0,2),(False,True)):
        yield dict(base,count=1,count_override=count,free=free,pools=2,poison=poison,ops=[['release']])
    for count,stride,depth in itertools.product((0,1,0x80000000,0xffffffff),(0,1,12,0xffffffff),(0,2)):
        yield dict(base,pools=depth,ops=[['pool_alloc',count,stride]])
    for depth,poison in itertools.product((0,1,2),(False,True)):
        yield dict(base,pools=depth,poison=poison,ops=[['pool_release']])
    for count,free,poison in itertools.product((0,1,3),(0,2),(False,True)):
        yield dict(base,count=count,free=free,pools=2,poison=poison,ops=[['clear']])
    for free,growth,links,count in itertools.product((0,2),(1,4),((0,0),(0xfedcba98,0x76543210)),(0,0xffffffff)):
        yield dict(base,free=free,growth=growth,pools=1,count_override=count,ops=[['allocate',*links]])
    for name in ('pushback','pushfront'):
        yield dict(base,free=2,pools=1,count_override=0xffffffff,ops=[[name,0xffffffff]])
    for growth,depth,poison in itertools.product((1,2,4),(0,1),(False,True)):
        yield dict(base,growth=growth,pools=depth,poison=poison,ops=[['pushback',11],['pushback',22],
            ['pushfront',0],['insert',1,0xffffffff],['popback'],['popfront'],['popback'],['popfront'],
            ['pushback',33],['popfront']])


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('exe',type=Path);ap.add_argument('--report',type=Path,required=True);args=ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT/d) for d in ('build','.local')):ap.error('report must stay private')
    data,pe=load_reference(args.exe);paths=[ROOT/'build/game/resource_stream.obj',ROOT/'build/game/resource_context.obj']
    functions={demangle(f.name):f for path in paths for f in ObjFile(str(path)).functions if demangle(f.name) in ORIGINAL}
    assert functions.keys()==ORIGINAL.keys();cases=[]
    for i,s in enumerate(scenarios()):
        expected=Model(s).expected();original=execute(pe,functions,s,False);rebuilt=execute(pe,functions,s,True)
        assert original==rebuilt==expected,(i,s,'heap/call/return mismatch')
        cases.append(dict(s,passed=True))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(binary_sha256=hashlib.sha256(data).hexdigest(),
        object_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},scope=__doc__,cases=cases),indent=2)+'\n')
    print('Passed %d resource-list/pool differential cases'%len(cases))
if __name__=='__main__':main()
