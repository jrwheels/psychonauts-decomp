#!/usr/bin/env python3
"""Experimental PBA layout and local weight predictions, not a playback decoder.

Production psymorph.pba still rejects version101. Use original_reader_pba.py to
compare supported local behavior against the hash-gated original executable.
Actor association, clocks/fades and skeletal synchronization are separate evidence.
"""
import math
import struct
import numpy as np


def decode(raw):
    if len(raw)<8 or len(raw)>16*1024*1024:raise ValueError('PBA size')
    magic,version=struct.unpack_from('<4sI',raw)
    if magic!=b'ABPE' or version not in (100,101):raise ValueError('PBA magic/version')
    if len(raw)==8:return dict(version=version,declared_channels=0,channels=[],missing_declared_channels=0,header_only=True)
    if len(raw)<12:raise ValueError('short channel count')
    declared=struct.unpack_from('<I',raw,8)[0]
    if declared>4096:raise ValueError('channel count limit')
    at=12;channels=[]
    for _ in range(declared):
        if at==len(raw):break
        start=at;length=raw[at];at+=1
        if at+length+4>len(raw):raise ValueError('truncated channel name/count')
        encoded=raw[at:at+length];at+=length;n=struct.unpack_from('<I',raw,at)[0];at+=4
        if n>len(raw)-at:raise ValueError('truncated weights')
        channels.append(dict(name=encoded.split(b'\0')[0].decode('latin1'),name_bytes=list(encoded),offset=start,
                             weights_offset=at,weights=list(raw[at:at+n])));at+=n
    if at!=len(raw):raise ValueError('unconsumed PBA bytes')
    return dict(version=version,declared_channels=declared,channels=channels,missing_declared_channels=declared-len(channels),header_only=len(raw)<=12)


def local_weights(decoded,seconds,targets,loop=False):
    """Candidate for active full-weight 0x48ca30, nonnegative local seconds only.

    Mirrors observed float32 time staging; n==1 returns an unnormalized byte in
    original0x48d4b0. Duplicate target channels overwrite, matching original order.
    Controller lifecycle, fades, external clocks and global synchronization omitted.
    """
    if not math.isfinite(seconds) or seconds<0:raise ValueError('nonnegative finite local seconds required')
    if len(targets)>64 or len(set(targets))!=len(targets):raise ValueError('unambiguous <=64 target table required')
    t=float(np.float32(seconds));result=[0.]*len(targets)
    duration=max((len(c['weights'])/30 for c in decoded['channels']),default=0)
    if not loop and t>=float(np.float32(duration)):return result
    for channel in decoded['channels']:
        if channel['name'] not in targets:continue
        w=channel['weights'];n=len(w)
        if not n:continue
        if n==1:value=float(w[0])
        else:
            adjusted=float(np.float32((n-1)*t/n))
            frame=float(np.float32(n/(n-1)*adjusted*30))
            i=int(frame);a=i%n if loop else min(i,n-1);b=(a+1)%n if loop else min(a+1,n-1)
            delta=float(np.float32((w[b]-w[a])*(frame-int(frame))))
            value=float(np.float32((w[a]+delta)/255))
        result[targets.index(channel['name'])]=value
    return result
