#!/usr/bin/env python3
"""Hash-gated x86 differential tests; resolver and native opener are mocked.

Open and AcquirePackedFile execute as a real two-body chain. Tests establish
dispatch, pool mutations and ABI, not path resolution or actual resource I/O.
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
POOL, RESOLVE, NATIVE, ACQUIRE = 0x795c80, 0x6a8ca0, 0x6a8180, 0x6aac10
ORIGINAL = {"EFileManager::Open": 0x6a9140, "AcquirePackedFile": ACQUIRE}
REBUILT = {name: CODE + i * 0x1000 for i, name in enumerate(ORIGINAL)}
NAME, PATH, FILE, FIRST, SECOND = (HEAP + n * 0x100 for n in range(1, 6))


def pool_bytes(states):
    return b"".join(struct.pack("<5I", 0x71d990, 0xaaaa0000 + i,
        FIRST if state & 1 else 0, SECOND if state & 2 else 0, 0xfeed0000 + i)
        for i, state in enumerate(states))


def expected(s):
    memory, trace = bytearray(pool_bytes(s["pool"])), []
    first, second = s["first"], s["second"]
    if s["function"] == "EFileManager::Open":
        if not s["name"] or s["options"] & 0xffff80ff:
            return {"return": 0, "pool": memory.hex(), "trace": trace}
        mode = s["mode"] or (9 if not s["count"] else (4 if s["options"] & 0xb00 else 1))
        trace.append(["resolve", HEAP, s["name"], mode & 0xffffffff])
        if not (first and second):
            if s["path"]:
                trace.append(["native", s["path"], s["options"]])
            return {"return": s["native"] if s["path"] else 0,
                    "pool": memory.hex(), "trace": trace}
    result = 0
    for i, state in enumerate(s["pool"]):
        if state == 0:
            struct.pack_into("<3I", memory, i * 20 + 8, first, second, 0)
            result = POOL + i * 20
            break
    return {"return": result, "pool": memory.hex(), "trace": trace}


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image) + 4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in ((CODE, 0x2000), (HEAP, 0x1000), (STACK, 0x10000), (STOP, 0x1000)):
        uc.mem_map(address, length)
    uc.mem_write(STACK, b"\xa5" * 0x10000)
    uc.mem_write(POOL, pool_bytes(s["pool"]))
    uc.mem_write(HEAP + 0x20, struct.pack("<I", (s["count"] << 5) | 0x1f))
    uc.mem_write(RESOLVE, b"\xb8" + struct.pack("<I", s["path"]) + b"\xc2\x10\x00")
    uc.mem_write(NATIVE, b"\xb8" + struct.pack("<I", s["native"]) + b"\xc3")
    if rebuilt:
        symbols = {"?g_packedFileSlots@@3PAUPackedFileSlot@@A": POOL,
            "?ResolvePath@EFileManager@@QAEPBDPBDHPAPAX1@Z": RESOLVE,
            "?OpenNativeFile@@YAPAVDiagnosticFile@@PBDI@Z": NATIVE,
            "?AcquirePackedFile@@YAPAVDiagnosticFile@@PAX0@Z": REBUILT["AcquirePackedFile"]}
        for f in obj.functions:
            name = demangle(f.name)
            if name in REBUILT:
                uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
    trace = []

    def hook(machine, address, size, context):
        sp = machine.reg_read(UC_X86_REG_ESP)
        if address == RESOLVE:
            name, mode, out1, out2 = struct.unpack("<4I", machine.mem_read(sp + 4, 16))
            trace.append(["resolve", machine.reg_read(UC_X86_REG_ECX), name, mode])
            assert out1 != out2 and all(STACK <= p < STACK + 0x10000 for p in (out1, out2))
            assert machine.mem_read(out1, 4) == machine.mem_read(out2, 4) == b"\0" * 4
            machine.mem_write(out1, struct.pack("<I", s["first"]))
            machine.mem_write(out2, struct.pack("<I", s["second"]))
        elif address == NATIVE:
            trace.append(["native", *struct.unpack("<2I", machine.mem_read(sp + 4, 8))])

    uc.hook_add(UC_HOOK_CODE, hook)
    is_open = s["function"] == "EFileManager::Open"
    args = [s["name"], s["options"], s["mode"] & 0xffffffff] if is_open else [s["first"], s["second"]]
    sp = STACK + 0x8000
    uc.mem_write(sp, struct.pack("<" + "I" * (len(args) + 1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for r, value in preserved.items():
        uc.reg_write(r, value)
    uc.reg_write(UC_X86_REG_ECX, HEAP)
    uc.reg_write(UC_X86_REG_EAX, s["eax"])
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.emu_start((REBUILT if rebuilt else ORIGINAL)[s["function"]], STOP, count=3000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP
    assert uc.reg_read(UC_X86_REG_ESP) == sp + 4 + (12 if is_open else 0)
    assert all(uc.reg_read(r) == value for r, value in preserved.items())
    return {"return": uc.reg_read(UC_X86_REG_EAX),
            "pool": bytes(uc.mem_read(POOL, 80)).hex(), "trace": trace}


def scenarios():
    base = dict(function="EFileManager::Open", pool=[0, 0, 0, 0], first=FIRST,
                second=SECOND, path=PATH, native=FILE, name=NAME, options=0,
                mode=0, count=0, eax=0xdeadbeef)
    for options, mode, count in itertools.product(
            [0, 0x100, 0x200, 0x400, 0x800, 0x1000, 0x4000, 0x7f00, 1, 0x8000, 0xffffffff],
            [0, 1, 4, 9, -1], [0, 1, 0x7ffffff]):
        yield {**base, "options": options, "mode": mode, "count": count}
    for first, second, path, native, name in itertools.product(
            [0, FIRST], [0, SECOND], [0, PATH], [0, FILE], [0, NAME]):
        yield {**base, "first": first, "second": second, "path": path, "native": native, "name": name}
    # Exhaust all 256 combinations of occupied, half-initialized and free slots.
    for pool in itertools.product(range(4), repeat=4):
        for function in ORIGINAL:
            yield {**base, "pool": list(pool), "function": function}
    for first, second, eax in itertools.product([0, FIRST], [0, SECOND], [0, 0xffffffff]):
        yield {**base, "function": "AcquirePackedFile", "first": first, "second": second, "eax": eax}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-12-behavior.json"))
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT / d) for d in ("build", ".local")):
        ap.error("report must stay in ignored build/ or .local/")
    data, pe = load_reference(args.exe)
    def dword(va):
        return struct.unpack("<I", pe.get_data(va - pe.OPTIONAL_HEADER.ImageBase, 4))[0]
    # Confirm original identities separately from our provisional method names.
    assert dword(0x71d91c) == 0x77b85c
    assert dword(0x77b85c + 12) == 0x781de8
    assert pe.get_string_at_rva(0x781df0 - pe.OPTIONAL_HEADER.ImageBase) == b".?AVEFileManager@@"
    assert [dword(0x71d920 + i * 4) for i in range(3)] == [0x6a9140, 0x6a9a00, 0x6a9a10]
    assert dword(0x71d98c) == 0x77b93c
    descriptor = dword(0x77b93c + 12)
    assert pe.get_string_at_rva(descriptor + 8 - pe.OPTIONAL_HEADER.ImageBase) == b".?AVEPackageFileAccessor@EPackageFile@@"
    objpath = ROOT / "build/game/file_manager.obj"
    obj, cases = ObjFile(str(objpath)), []
    for s in scenarios():
        want = expected(s)
        assert execute(pe, obj, s, False) == execute(pe, obj, s, True) == want, s
        cases.append({**s, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"binary_sha256": hashlib.sha256(data).hexdigest(),
        "object_sha256": hashlib.sha256(objpath.read_bytes()).hexdigest(),
        "scope": __doc__, "rtti_identity_checks_passed": True, "cases": cases}, indent=2) + "\n")
    print("Passed %d native file-manager differential cases" % len(cases))


if __name__ == "__main__":
    main()
