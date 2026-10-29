#!/usr/bin/env python3
"""Hash-gated original PBA reader, name binder and local sampler via Unicorn.

No binary redistribution or modification. Mocks replace allocation/free and the
unused temporary stream destructor only. Original parsing, binding, controller
and interpolation instructions execute; synthetic state isolates their semantics.
This is not original game playback or a renderer/deformation verification.
"""
import hashlib
from pathlib import Path
import struct
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_ESP,UC_X86_REG_EIP,UC_X86_REG_FPCW,UC_X86_REG_FPSW,UC_X86_REG_FPTAG

SHA1='21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07'
FUNCTIONS={0x48c1c0:916,0x48cde0:388,0x48ca30:557,0x48d420:140,0x48d4b0:418}


class OriginalPba:
    def __init__(self,executable):
        raw=Path(executable).read_bytes()
        if hashlib.sha1(raw).hexdigest()!=SHA1:raise ValueError('wrong original executable')
        pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase;image=pe.get_memory_mapped_image()
        self.function_hashes={hex(a):hashlib.sha256(image[a-base:a-base+n]).hexdigest() for a,n in FUNCTIONS.items()}
        self.uc=Uc(UC_ARCH_X86,UC_MODE_32);u=self.uc;u.mem_map(base,(len(image)+4095)&~4095);u.mem_write(base,image)
        u.mem_map(0x2000000,0x1000000);u.mem_map(0x3000000,0x100000);u.mem_map(0x4000000,0x2000)
        self.next=0x2000000;self.mocks={0x4001000:'allocate',0x4001010:'free',0x6ab0e0:'temporary-stream-destructor'}
        u.mem_write(0x700288,struct.pack('<I',0x4001000));u.mem_write(0x700298,struct.pack('<I',0x4001010))
        u.reg_write(UC_X86_REG_FPCW,0x37f);u.reg_write(UC_X86_REG_FPSW,0);u.reg_write(UC_X86_REG_FPTAG,0xffff)
        u.hook_add(UC_HOOK_CODE,self.hook);self.mock_calls={k:0 for k in self.mocks.values()}

    def alloc(self,n):
        if n<0 or n>0x200000:raise ValueError('allocation limit')
        p=self.next;self.next+=(n+15)&~15
        if self.next>=0x3000000:raise ValueError('harness heap exhausted')
        return p

    def hook(self,u,address,size,data):
        if address not in self.mocks:return
        self.mock_calls[self.mocks[address]]+=1;sp=u.reg_read(UC_X86_REG_ESP)
        if self.mocks[address]=='allocate':u.reg_write(UC_X86_REG_EAX,self.alloc(self.dword(sp+4)))
        u.reg_write(UC_X86_REG_EIP,self.dword(sp));u.reg_write(UC_X86_REG_ESP,sp+4)

    def dword(self,p):return struct.unpack('<I',self.uc.mem_read(p,4))[0]

    def call(self,address,this,args=()):
        sp=0x30ff000-4*(len(args)+1);self.uc.mem_write(sp,struct.pack('<'+'I'*(len(args)+1),0x4000000,*args))
        self.uc.reg_write(UC_X86_REG_ESP,sp);self.uc.reg_write(UC_X86_REG_ECX,this)
        self.uc.emu_start(address,0x4000000,count=2000000)
        if self.uc.reg_read(UC_X86_REG_EIP)!=0x4000000:raise RuntimeError('original function did not return within bound')
        return self.uc.reg_read(UC_X86_REG_EAX)

    def load(self,raw):
        if len(raw)<=12:raise ValueError('original wrapper skips headers <=12 bytes')
        self.obj=self.alloc(0x24);p=self.alloc(len(raw)+16);self.uc.mem_write(p,raw+b'probe.pba\0');self.uc.mem_write(self.obj+0x1c,struct.pack('<I',p+len(raw)))
        result=self.call(0x48c1c0,self.obj,(p,len(raw)))&255;count=self.dword(self.obj);table=self.dword(self.obj+4);channels=[]
        if count>4096:raise ValueError('original channel count limit')
        for i in range(count):
            name,n,weights=struct.unpack('<III',self.uc.mem_read(table+12*i,12));encoded=bytes(self.uc.mem_read(name,256)).split(b'\0')[0] if name else b''
            channels.append(dict(name=encoded.decode('latin1'),weights=list(self.uc.mem_read(weights,n)) if n else []))
        return dict(returned_success=bool(result),channels=channels,duration=struct.unpack('<f',self.uc.mem_read(self.obj+8,4))[0])

    def bind(self,names):
        if len(names)>64:raise ValueError('native output limited to64 morph targets')
        self.state=self.alloc(0x124);self.uc.mem_write(self.state,struct.pack('<I',self.obj));descriptor=self.alloc(12);table=self.alloc(4*max(1,len(names)))
        for i,name in enumerate(names):
            b=name.encode('latin1')+b'\0';p=self.alloc(len(b));self.uc.mem_write(p,b);self.uc.mem_write(table+4*i,struct.pack('<I',p))
        self.uc.mem_write(descriptor,struct.pack('<III',len(names)<<5,0,table));self.call(0x48cde0,self.state,(descriptor,))
        self.target_count=len(names);self.map=self.dword(self.state+0x120)
        return list(struct.unpack('<'+'i'*self.dword(self.obj),self.uc.mem_read(self.map,4*self.dword(self.obj))))

    def evaluate(self,seconds,loop=False):
        self.uc.mem_write(self.state+0x104,struct.pack('<ff',seconds,-999.));self.uc.mem_write(self.state+0x10d,bytes([bool(loop)]))
        self.uc.mem_write(self.state+0x118,struct.pack('<f',1.));self.call(0x48ca30,self.state)
        return list(struct.unpack('<'+'f'*self.target_count,self.uc.mem_read(self.state+4,4*self.target_count)))
