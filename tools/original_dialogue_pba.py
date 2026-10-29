#!/usr/bin/env python3
"""Isolated original dialogue/actor/face-manager execution with explicit services.

Lua argument access, byte-exact ready file I/O, CRT copies/formatting and sound
start are harness adapters. Actor forwarding, facial creation/read/bind/list,
clock/fade/update/composition and stop/destruction execute original instructions.
This is a controlled ready-resource, normal-mode software path, not game capture.
"""
import struct
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP
from original_reader_pba import OriginalPba


def bits(x):return struct.unpack('<I',struct.pack('<f',x))[0]


class DialoguePba(OriginalPba):
    def __init__(self,executable,raw,targets,path):
        self.events=[];self.executed={};super().__init__(executable)
        self.raw=raw;self.path=path;self.target_count=len(targets);self.elapsed=0.
        self.manager=self.alloc(0x224);self.backend=self.alloc(0x80);self.actor=self.alloc(0xb0);self.mesh=self.alloc(0x1d8);self.player=self.alloc(0xb0)
        self.write(self.actor+0xa8,self.mesh);self.write(self.mesh+0x1d4,self.manager);self.write(self.manager+0x18,self.backend)
        pool=self.alloc(4*16);nodes=self.alloc(8*16);self.write(self.manager+4,nodes)
        for i in range(16):self.write(pool+4*i,nodes+8*i)
        for offset,value in ((8,pool),(0x10,16),(0x14,16)):self.write(self.manager+offset,value)
        descriptor=self.alloc(12);table=self.alloc(4*len(targets));self.write(descriptor,len(targets)<<5);self.write(descriptor+8,table)
        for i,name in enumerate(targets):self.write(table+4*i,self.string(name))
        self.write(self.manager+0x20,descriptor)
        self.game=self.alloc(0x9b00);self.write(0x78bc20,self.game);self.write(self.game+0x818c,self.player)
        sound=self.alloc(16);vt=self.alloc(0x110);self.write(sound,vt);self.write(vt+0x2c,0x4001200);self.write(self.game+0x198,sound)
        self.write(vt+0xec,0x4001210)
        self.stream=self.alloc(len(raw));self.uc.mem_write(self.stream,raw);self.file_node=self.alloc(0x58);self.write(self.file_node+0x24,len(raw))
        self.adapters={0x6aef20:('lua-count',0),0x5af750:('lua-arity',0),0x5b01b0:('lua-actor',0),0x5b02b0:('lua-string',0),0x5b0230:('lua-number',0),0x597d60:('lua-sound',0),0x6af600:('lua-result-number',0),0x6af700:('lua-result-handle',0),0x6a7130:('profiling-time',0),0x6a8ca0:('resource-path',16),0x48f760:('ready-file-entry',0),0x40b4c0:('open-ready-file',20),0x40b9f0:('file-ready',0),0x40b980:('file-buffer',0),0x48f7a0:('file-release',4),0x6ed156:('memcpy',0),0x4001100:('strncpy',0),0x4001110:('snprintf',0),0x4001120:('compare-nocase',0),0x4001200:('audio-start',12),0x5022c0:('normal-mode',0),0x48f1e0:('uncached-name-lookup',4)}
        for slot,callback in ((0x7002b4,0x4001100),(0x70028c,0x4001110),(0x7002ac,0x4001120)):self.write(slot,callback)
        self.uc.mem_write(0x4001300,b'\xd9\x05'+struct.pack('<I',0x4000100)+b'\xc3')
        self.namespace=self.string('Milla/MITU');self.line=self.string('MITU066MI');self.sound_id=1234;self.result_numbers=[];self.result_handles=[]
        self.adapters[0x4001210]=('audio-actor-notification',8)
        self.adapters[0x48f550]=('cache-miss',4)
        self.adapters[0x48f7e0]=('cache-eviction',4)
        self.mode=0;self.lua_count=8;self.lua_numbers={5:0.,6:1.,7:0.,8:.1};self.lua_strings={}

    def write(self,p,v):self.uc.mem_write(p,struct.pack('<I',v))
    def f(self,p):return struct.unpack('<f',self.uc.mem_read(p,4))[0]
    def string(self,text):
        b=text.encode('latin1')+b'\0';p=self.alloc(len(b));self.uc.mem_write(p,b);return p
    def text(self,p):
        if not p:return ''
        return bytes(self.uc.mem_read(p,1024)).split(b'\0')[0].decode('latin1')
    def finish(self,value=0,clean=0):
        sp=self.uc.reg_read(UC_X86_REG_ESP);self.uc.reg_write(UC_X86_REG_EAX,value&0xffffffff);self.uc.reg_write(UC_X86_REG_EIP,self.dword(sp));self.uc.reg_write(UC_X86_REG_ESP,sp+4+clean)

    def hook(self,u,address,size,data):
        if address in (0x5980d0,0x5bfbb0,0x43a060,0x48da80,0x48c1c0,0x48cde0,0x48e4a0,0x48e910,0x48c850,0x48c8a0,0x48cf70,0x48e010,0x43a110,0x48f660,0x48bc10,0x48e870,0x48eec0):
            key=hex(address);self.executed[key]=self.executed.get(key,0)+1
        if address in (0x43a060,0x48da80,0x48c850,0x48f660):
            sp=u.reg_read(UC_X86_REG_ESP)
            if address in (0x43a060,0x48da80):
                self.events.append(dict(event=hex(address),path=self.text(self.dword(sp+4)),this=u.reg_read(UC_X86_REG_ECX),args=[self.dword(sp+4+4*i) for i in range(7)]))
            elif address==0x48f660:self.events.append(dict(event='original-controller-release',controller=self.dword(sp+4)))
        if address==0x43a110:
            sp=u.reg_read(UC_X86_REG_ESP);self.events.append(dict(event='actor-stop',path=self.text(self.dword(sp+4)),fade=self.f(sp+8)))
        if address not in getattr(self,'adapters',{}):return super().hook(u,address,size,data)
        kind,clean=self.adapters[address];sp=u.reg_read(UC_X86_REG_ESP);a=lambda i:self.dword(sp+4+4*i);result=0
        if kind=='lua-count':result=self.lua_count
        elif kind=='lua-arity':result=1
        elif kind=='lua-actor':result=self.actor
        elif kind=='lua-string':result=self.lua_strings.get(a(1),self.namespace if a(1)==1 else self.line)
        elif kind=='lua-sound':result=self.sound_id
        elif kind in ('lua-number','profiling-time'):
            number=self.lua_numbers.get(a(1),0.) if kind=='lua-number' else 0.
            self.uc.mem_write(0x4000100,struct.pack('<f',number));u.reg_write(UC_X86_REG_EIP,0x4001300);return
        elif kind=='lua-result-number':self.result_numbers.append(self.f(sp+8))
        elif kind=='lua-result-handle':self.result_handles.append(a(1))
        elif kind=='resource-path':result=a(0)
        elif kind=='ready-file-entry':result=self.file_node
        elif kind=='open-ready-file':
            actual=self.text(a(0));self.events.append(dict(event='file-open',path=actual,ready=True))
            result=int(actual.lower()==self.path.lower())
        elif kind=='file-ready':result=1
        elif kind=='file-buffer':result=self.stream
        elif kind=='normal-mode':result=self.mode
        elif kind=='uncached-name-lookup':result=getattr(self,'lookup_result',0)
        elif kind in ('file-release','cache-miss','cache-eviction'):result=0
        elif kind=='memcpy':
            if a(2)>0x200000:raise ValueError('copy limit')
            self.uc.mem_write(a(0),bytes(self.uc.mem_read(a(1),a(2))));result=a(0)
        elif kind=='strncpy':
            if a(2)>0x200000:raise ValueError('string copy limit')
            value=self.text(a(1)).encode('latin1')[:a(2)];self.uc.mem_write(a(0),value+b'\0'*(a(2)-len(value)));result=a(0)
        elif kind=='snprintf':
            fmt=self.text(a(2));values=[];index=3;at=0
            while at<len(fmt):
                if fmt[at]=='%':
                    spec=fmt[at+1];value=a(index);index+=1;values.append(self.text(value) if spec=='s' else chr(value&255));at+=2
                else:at+=1
            text=fmt%tuple(values);self.uc.mem_write(a(0),text.encode('latin1')[:a(1)-1]+b'\0');result=len(text)
        elif kind=='compare-nocase':
            x,y=self.text(a(0)).lower(),self.text(a(1)).lower();result=(x>y)-(x<y)
        elif kind=='audio-start':
            self.events.append(dict(event='audio-start',sound_id=a(0),attachment=a(1),options=a(2),facial_count=self.dword(self.manager+0xc)));result=77
        elif kind=='audio-actor-notification':
            self.events.append(dict(event=kind,actor=a(0),sound_handle=a(1)))
        else:raise ValueError('unknown adapter '+kind)
        self.finish(result,clean)

    def babble(self):
        self.lua_count=8;self.lua_strings={};self.lua_numbers={5:0.,6:1.,7:0.,8:.1}
        self.call(0x5980d0,0,(0x12345678,));return self.capture()

    def capture(self):
        head=self.dword(self.manager)
        if not head:return None
        self.state=self.dword(head+4);self.obj=self.dword(self.state)
        if bytes(self.uc.mem_read(self.dword(self.obj+0x14),len(self.raw)))!=self.raw:
            raise ValueError('original runtime object is not bound to the supplied PBA bytes')
        return self.snapshot()

    def manual(self,path,loop=False,replace=False,fade=0.):
        self.lua_count=5;self.lua_strings={2:self.string(path)};self.lua_numbers={3:float(loop),4:float(replace),5:fade}
        self.call(0x5bfbb0,0,(0x12345678,));return self.capture()

    def snapshot(self):
        if not self.dword(self.manager+0xc):return dict(controllers=0,released=True)
        return dict(seconds=self.f(self.state+0x104),last_evaluated=self.f(self.state+0x108),weight=self.f(self.state+0x118),fade_rate=self.f(self.state+0x114),active=int(self.uc.mem_read(self.state+0x10c,1)[0]),loop=int(self.uc.mem_read(self.state+0x10d,1)[0]),complete=int(self.uc.mem_read(self.state+0x10e,1)[0]),fading=int(self.uc.mem_read(self.state+0x10f,1)[0]),bound=int(self.uc.mem_read(self.state+0x112,1)[0]),skeletal_owner=self.dword(self.state+0x11c),controllers=self.dword(self.manager+0xc))

    def output(self):
        self.call(0x48e910,self.manager);return list(struct.unpack('<'+'f'*self.target_count,self.uc.mem_read(self.manager+0x24,4*self.target_count)))

    def step(self,delta):
        self.call(0x48e4a0,self.manager,(bits(delta),));return dict(state=self.snapshot(),weights=self.output())

    def stop(self,fade):
        self.call(0x43a110,self.mesh,(self.string(self.path),bits(fade)));return self.snapshot()
