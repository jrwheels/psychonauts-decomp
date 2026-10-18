#!/usr/bin/env python3
"""Hash-gated buffered-file differential tests, with bounded mock file/CRT I/O.

Normal fixtures execute memcpy semantics in the mock; exceptional arithmetic
fixtures record large/invalid copy requests without dereferencing them. They
verify native integer/call behavior, not real CRT handling of invalid memory.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_diagnostics import relocate

ROOT = Path(__file__).resolve().parent.parent
CODE, HEAP, STACK, STOP = 0x1000000, 0x2000000, 0x3000000, 0x2100000
OBJECT, FILE, VT, BUFFER, DEST, INPUT = (HEAP + n * 0x100 for n in range(6))
READ, COPY, WRITE, SIZE, SEEK = STOP + 0x100, 0x6ed156, STOP + 0x200, STOP + 0x300, STOP + 0x400
ORIGINAL = {"EReadBufferedFile::Read": 0x6a9ee0, "EReadBufferedFile::Refill": 0x6aa080,
            "EReadBufferedFile::Size": 0x6aa020, "EWriteBufferedFile::Flush": 0x6a9d50,
            "EWriteBufferedFile::Write": 0x6a9ca0, "EWriteBufferedFile::Seek": 0x6a9c00}
REBUILT = {name: CODE + n * 0x1000 for n, name in enumerate(ORIGINAL)}
MASK = 0xffffffff


def initial_memory(s):
    memory = bytearray(b"\xcc" * 0x1000)
    if s["function"].startswith("EWriteBufferedFile::"):
        struct.pack_into("<7I", memory, 0, 0x71d934, 0xaabbccdd, FILE,
                         s["capacity"], s["pending"], s["start"], BUFFER)
    else:
        struct.pack_into("<7I", memory, 0, 0x71d958, 0xaabbccdd, FILE, BUFFER,
                         s["capacity"], s["valid"], s["position"])
    struct.pack_into("<I", memory, FILE - HEAP, VT)
    struct.pack_into("<I", memory, VT + 8 - HEAP, READ)
    struct.pack_into("<I", memory, VT + 0xc - HEAP, WRITE)
    struct.pack_into("<I", memory, VT + 0x14 - HEAP, SIZE)
    struct.pack_into("<I", memory, VT + 0x10 - HEAP, SEEK)
    memory[BUFFER - HEAP:BUFFER - HEAP + 32] = bytes(range(32))
    memory[INPUT - HEAP:INPUT - HEAP + 32] = b"W" * 32
    return memory


def expected(s):
    memory, trace = initial_memory(s), []
    if s["function"] in ("EWriteBufferedFile::Write", "EWriteBufferedFile::Seek"):
        pending, start = s["pending"], s["start"]
        if s["flush"]:
            trace.append(["write", FILE, BUFFER, pending, bytes(range(pending)).hex()])
            pending, start = 0, 0
        if s["function"].endswith("::Seek"):
            trace.append(["seek", FILE, s["offset"], s["origin"] & MASK])
            result = s["seek_returned"]
        elif s["branch"] == "direct":
            text = "not-dereferenced" if s["request"] > 32 else (b"W" * s["request"]).hex()
            trace.append(["write", FILE, INPUT, s["request"], text])
            result = s["returned"]
        else:
            if s["seek"]:
                trace.append(["seek", FILE, 0, 1])
                start = s["seek_returned"]
            dest = (BUFFER + pending) & MASK
            trace.append(["copy", dest, INPUT, s["request"]])
            memory[dest - HEAP:dest - HEAP + s["request"]] = b"W" * s["request"]
            pending = (pending + s["request"]) & MASK
            result = s["request"]
        struct.pack_into("<2I", memory, 0x10, pending, start)
        return {"trace": trace, "return": result, "memory": memory.hex()}
    if s["function"] == "EReadBufferedFile::Size":
        return {"trace": [["size", FILE]], "return": s["returned"], "memory": memory.hex()}
    if s["function"] == "EWriteBufferedFile::Flush":
        if s["pending"]:
            trace = [["write", FILE, BUFFER, s["pending"], bytes(range(s["pending"])).hex()]]
            struct.pack_into("<2I", memory, 0x10, 0, 0)
        return {"trace": trace, "return": None, "memory": memory.hex()}
    position, valid = s["position"], s["valid"]

    def copy(dest, source, size):
        if size:
            trace.append(["copy", dest & MASK, source & MASK, size])
            if not s.get("trace_only"):
                assert 0 <= dest - HEAP <= 0x1000 - size and 0 <= source - HEAP <= 0x1000 - size
                memory[dest - HEAP:dest - HEAP + size] = memory[source - HEAP:source - HEAP + size]

    def read(dest, count):
        trace.append(["read", FILE, dest & MASK, count])
        if not s.get("trace_only"):
            n = min(count, s["returned"], 32)
            memory[dest - HEAP:dest - HEAP + n] = b"R" * n

    if s["function"].endswith("::Refill"):
        read(BUFFER, s["capacity"])
        valid, position, result = s["returned"], 0, None
    else:
        first = s["first_copy"]
        copy(DEST, (BUFFER + position) & MASK, first)
        position = (position + first) & MASK
        if s["branch"] == "none":
            result = first
        elif s["branch"] == "direct":
            read((DEST + first) & MASK, s["remainder"])
            result = (first + s["returned"]) & MASK
        else:
            read(BUFFER, s["capacity"])
            valid, position = s["returned"], s["second_copy"]
            copy((DEST + first) & MASK, BUFFER, s["second_copy"])
            result = (first + s["second_copy"]) & MASK
    struct.pack_into("<2I", memory, 0x14, valid, position)
    return {"trace": trace, "return": result, "memory": memory.hex()}


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image) + 4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in ((CODE, 0x6000), (HEAP, 0x1000), (STACK, 0x10000), (STOP, 0x1000)):
        uc.mem_map(address, length)
    uc.mem_write(STACK, b"\xa5" * 0x10000)
    uc.mem_write(HEAP, bytes(initial_memory(s)))
    uc.mem_write(READ, b"\xb8" + struct.pack("<I", s["returned"]) + b"\xc2\x08\x00")
    uc.mem_write(WRITE, b"\xb8" + struct.pack("<I", s["returned"]) + b"\xc2\x08\x00")
    uc.mem_write(SIZE, b"\xb8" + struct.pack("<I", s["returned"]) + b"\xc3")
    uc.mem_write(SEEK, b"\xb8" + struct.pack("<I", s.get("seek_returned", 0)) + b"\xc2\x08\x00")
    uc.mem_write(COPY, b"\xc3")
    if rebuilt:
        symbols = {"_memcpy": COPY,
                   "?Refill@EReadBufferedFile@@QAEXXZ": REBUILT["EReadBufferedFile::Refill"],
                   "?Flush@EWriteBufferedFile@@QAEXXZ": REBUILT["EWriteBufferedFile::Flush"]}
        for f in obj.functions:
            name = demangle(f.name)
            if name in REBUILT:
                uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
    trace = []

    def hook(machine, address, size, context):
        sp = machine.reg_read(UC_X86_REG_ESP)
        if address == COPY:
            dest, source, count = struct.unpack("<3I", machine.mem_read(sp + 4, 12))
            trace.append(["copy", dest, source, count])
            if not s.get("trace_only") and count:
                assert count <= 32
                machine.mem_write(dest, bytes(machine.mem_read(source, count)))
            machine.reg_write(UC_X86_REG_EAX, dest)
        elif address == READ:
            dest, count = struct.unpack("<2I", machine.mem_read(sp + 4, 8))
            trace.append(["read", machine.reg_read(UC_X86_REG_ECX), dest, count])
            if not s.get("trace_only"):
                machine.mem_write(dest, b"R" * min(s["returned"], count, 32))
        elif address == WRITE:
            source, count = struct.unpack("<2I", machine.mem_read(sp + 4, 8))
            trace.append(["write", machine.reg_read(UC_X86_REG_ECX), source, count,
                          bytes(machine.mem_read(source, count)).hex() if count <= 32 else "not-dereferenced"])
        elif address == SIZE:
            trace.append(["size", machine.reg_read(UC_X86_REG_ECX)])
        elif address == SEEK:
            trace.append(["seek", machine.reg_read(UC_X86_REG_ECX),
                          *struct.unpack("<2I", machine.mem_read(sp + 4, 8))])

    uc.hook_add(UC_HOOK_CODE, hook)
    is_read = s["function"].endswith("::Read")
    args, pop = ([DEST, s["request"]], 8) if is_read else ([], 0)
    if s["function"] == "EWriteBufferedFile::Write":
        args, pop = [INPUT, s["request"]], 8
    elif s["function"] == "EWriteBufferedFile::Seek":
        args, pop = [s["offset"], s["origin"] & MASK], 8
    sp = STACK + 0x8000
    uc.mem_write(sp, struct.pack("<" + "I" * (len(args) + 1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for r, value in preserved.items():
        uc.reg_write(r, value)
    uc.reg_write(UC_X86_REG_ECX, OBJECT)
    uc.reg_write(UC_X86_REG_EAX, s.get("eax", 0xdeadbeef))
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start((REBUILT if rebuilt else ORIGINAL)[s["function"]], STOP, count=3000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP
    assert uc.reg_read(UC_X86_REG_ESP) == sp + 4 + pop
    assert all(uc.reg_read(r) == value for r, value in preserved.items())
    has_return = is_read or s["function"].endswith(("::Size", "::Write", "::Seek"))
    return {"trace": trace, "return": uc.reg_read(UC_X86_REG_EAX) if has_return else None,
            "memory": bytes(uc.mem_read(HEAP, 0x1000)).hex()}


def scenarios():
    # valid, position, capacity, request, initial copy, branch, remaining.
    fixtures = [(8, 2, 8, 0, 0, "none", 0), (8, 2, 8, 3, 3, "none", 0),
        (8, 2, 8, 6, 6, "none", 0), (8, 2, 8, 7, 6, "refill", 1),
        (8, 2, 8, 14, 6, "refill", 8), (8, 2, 8, 15, 6, "direct", 9),
        (0, 0, 8, 0, 0, "none", 0), (0, 0, 8, 1, 0, "refill", 1),
        (0, 0, 8, 8, 0, "refill", 8), (0, 0, 8, 9, 0, "direct", 9),
        (0, 0, 0, 1, 0, "direct", 1), (4, 4, 4, 4, 0, "refill", 4),
        (4, 4, 4, 5, 0, "direct", 5), (4, 0, 4, 32, 4, "direct", 28)]
    for fixture, returned, eax in itertools.product(fixtures, [0, 1, 4, 8], [0, MASK]):
        valid, position, capacity, request, first, branch, remainder = fixture
        yield dict(function="EReadBufferedFile::Read", valid=valid, position=position,
            capacity=capacity, request=request, first_copy=first, branch=branch,
            remainder=remainder, returned=returned, second_copy=min(remainder, returned), eax=eax)
    for capacity, returned, position in itertools.product([0, 4, 16], [0, 1, 4, 16, MASK], [0, 7]):
        yield dict(function="EReadBufferedFile::Refill", capacity=capacity, valid=11,
                   position=position, returned=returned)
    # Explicit arithmetic fixtures; large copy requests are traced only.
    special = [
        dict(valid=0, position=0, capacity=8, request=MASK, first_copy=MASK,
             branch="none", remainder=0, returned=0, second_copy=0),
        dict(valid=0, position=1, capacity=8, request=0, first_copy=MASK,
             branch="refill", remainder=1, returned=0, second_copy=0),
        dict(valid=0, position=0, capacity=8, request=1, first_copy=0,
             branch="refill", remainder=1, returned=MASK, second_copy=MASK),
        dict(valid=0, position=0, capacity=0x80000000, request=8, first_copy=0,
             branch="refill", remainder=8, returned=0, second_copy=0),
        dict(valid=8, position=0, capacity=8, request=0x80000000, first_copy=0x80000000,
             branch="none", remainder=0, returned=0, second_copy=0),
        dict(valid=4, position=0, capacity=8, request=32, first_copy=4,
             branch="direct", remainder=28, returned=MASK, second_copy=0)]
    for s in special:
        yield dict(s, function="EReadBufferedFile::Read", trace_only=True)
    for pending, returned, start in itertools.product([0, 1, 4, 16], [0, 1, 4, MASK], [0, 42, MASK]):
        yield dict(function="EWriteBufferedFile::Flush", capacity=16, pending=pending,
                   start=start, returned=returned)
    for returned in [0, 1, 42, 0x80000000, MASK]:
        yield dict(function="EReadBufferedFile::Size", capacity=16, valid=11,
                   position=7, returned=returned)
    # capacity, pending, request, branch, should flush, should query position.
    writes = [(8, 0, 0, "buffer", False, True), (8, 0, 1, "buffer", False, True),
        (8, 2, 0, "buffer", False, False), (8, 2, 3, "buffer", False, False),
        (8, 2, 6, "buffer", True, True), (8, 7, 1, "buffer", True, True),
        (8, 2, 7, "buffer", True, True), (8, 0, 8, "direct", False, False),
        (8, 4, 8, "direct", True, False), (8, 4, 9, "direct", True, False),
        (0, 0, 0, "direct", False, False), (8, 0, MASK, "direct", False, False),
        (8, MASK, 1, "buffer", False, False)]
    for fixture, returned, seek_returned in itertools.product(writes, [0, 1, 8, MASK], [0, 31, MASK]):
        capacity, pending, request, branch, flush, seek = fixture
        yield dict(function="EWriteBufferedFile::Write", capacity=capacity, pending=pending,
                   start=42, request=request, branch=branch, flush=flush, seek=seek,
                   returned=returned, seek_returned=seek_returned)
    for pending, offset, origin, returned in itertools.product([0, 4], [0, 7, 0x80000000, MASK],
            [0, 1, 2, -1], [0, 31, MASK]):
        yield dict(function="EWriteBufferedFile::Seek", capacity=8, pending=pending,
                   start=42, offset=offset, origin=origin, flush=bool(pending),
                   returned=MASK, seek_returned=returned)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-14-behavior.json"))
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT / d) for d in ("build", ".local")):
        ap.error("report must stay in ignored build/ or .local/")
    data, pe = load_reference(args.exe)
    objpath = ROOT / "build/game/buffered_file.obj"
    obj, cases = ObjFile(str(objpath)), []
    for s in scenarios():
        want = expected(s)
        assert execute(pe, obj, s, False) == execute(pe, obj, s, True) == want, s
        cases.append({**s, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"binary_sha256": hashlib.sha256(data).hexdigest(),
        "object_sha256": hashlib.sha256(objpath.read_bytes()).hexdigest(),
        "scope": __doc__, "cases": cases}, indent=2) + "\n")
    print("Passed %d buffered-file differential cases" % len(cases))


if __name__ == "__main__":
    main()
