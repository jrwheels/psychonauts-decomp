#!/usr/bin/env python3
"""Original/rebuilt package accessor and helper tests with mocked file I/O.

The actual Read -> ReadPackedData chain executes; seek/read virtual endpoints
are mocked. Boundary counts are explicit fixtures, including native overflow.
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
SLOT, SOURCE, ENTRY, FILE, VT, DEST = (HEAP + n * 0x100 for n in range(6))
READ, SEEK = STOP + 0x100, STOP + 0x200
ORIGINAL = {"ReadPackedData": 0x6aabb0, "PackedFileSlot::Read": 0x6aad60,
    "PackedFileSlot::Seek": 0x6aadc0, "PackedFileSlot::Close": 0x6aad40,
    "PackedFileSlot::Size": 0x6aae10}
REBUILT = {name: CODE + i * 0x1000 for i, name in enumerate(ORIGINAL)}
MASK = 0xffffffff


def execute(pe, obj, s, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image, base = pe.get_memory_mapped_image(), pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image) + 4095) & ~4095)
    uc.mem_write(base, image)
    for address, length in ((CODE, 0x5000), (HEAP, 0x1000), (STACK, 0x10000), (STOP, 0x1000)):
        uc.mem_map(address, length)
    uc.mem_write(STACK, b"\xa5" * 0x10000)
    uc.mem_write(HEAP, b"\xcc" * 0x1000)
    uc.mem_write(SLOT, struct.pack("<5I", 0x71d990, 0xaabbccdd,
                                  s["first"], s["second"], s["position"]))
    uc.mem_write(SOURCE + 0x20, struct.pack("<I", FILE))
    uc.mem_write(ENTRY + 8, struct.pack("<2I", s["offset"], s["length"]))
    uc.mem_write(FILE, struct.pack("<I", VT))
    uc.mem_write(VT + 8, struct.pack("<I", READ))
    uc.mem_write(VT + 0x10, struct.pack("<I", SEEK))
    for address, value in ((READ, s["result"]), (SEEK, s["seek_result"])):
        uc.mem_write(address, b"\xb8" + struct.pack("<I", value) + b"\xc2\x08\x00")
    if rebuilt:
        symbols = {"?ReadPackedData@@YAIPAUPackageReadSource@@PAUPackageReadEntry@@IPAXI@Z": REBUILT["ReadPackedData"]}
        for f in obj.functions:
            name = demangle(f.name)
            if name in REBUILT:
                uc.mem_write(REBUILT[name], relocate(f, REBUILT[name], symbols))
    trace = []

    def hook(machine, address, size, context):
        if address in (SEEK, READ):
            sp = machine.reg_read(UC_X86_REG_ESP)
            values = struct.unpack("<2I", machine.mem_read(sp + 4, 8))
            trace.append(["seek" if address == SEEK else "read",
                          machine.reg_read(UC_X86_REG_ECX), *values])
            # Bounded mocked output, independent of deliberately huge return values.
            if address == READ and values[1]:
                assert values[0] == DEST
                machine.mem_write(DEST, b"R")

    uc.hook_add(UC_HOOK_CODE, hook)
    name = s["function"]
    args, pop = [], 0
    if name == "ReadPackedData":
        args = [SOURCE, ENTRY, s["position"], DEST, s["count"]]
    elif name == "PackedFileSlot::Read":
        args, pop = [DEST, s["count"]], 8
    elif name == "PackedFileSlot::Seek":
        args, pop = [s["offset"], s["origin"] & MASK], 8
    sp = STACK + 0x8000
    uc.mem_write(sp, struct.pack("<" + "I" * (len(args) + 1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for r, value in preserved.items():
        uc.reg_write(r, value)
    uc.reg_write(UC_X86_REG_ECX, SLOT)
    uc.reg_write(UC_X86_REG_EAX, 0xdeadbeef)
    uc.reg_write(UC_X86_REG_ESP, sp)
    initial = bytes(uc.mem_read(HEAP, 0x1000))
    uc.emu_start((REBUILT if rebuilt else ORIGINAL)[name], STOP, count=3000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP
    assert uc.reg_read(UC_X86_REG_ESP) == sp + 4 + pop
    assert all(uc.reg_read(r) == value for r, value in preserved.items())
    expected_memory = bytearray(initial)
    if name == "PackedFileSlot::Close":
        expected_memory[8:16] = b"\0" * 8
    elif name == "PackedFileSlot::Read":
        struct.pack_into("<I", expected_memory, 16, (s["position"] + s["result"]) & MASK)
    elif name == "PackedFileSlot::Seek":
        struct.pack_into("<I", expected_memory, 16, s["final_position"])
    if name in ("ReadPackedData", "PackedFileSlot::Read") and s["expected_count"]:
        expected_memory[DEST - HEAP] = ord("R")
    assert bytes(uc.mem_read(HEAP, 0x1000)) == bytes(expected_memory), (name, "unexpected memory mutation", s)
    return {"trace": trace, "return": None if name == "PackedFileSlot::Close" else uc.reg_read(UC_X86_REG_EAX)}


def scenarios():
    base = dict(position=0, offset=0, count=0, length=0, result=0, seek_result=0,
                first=SOURCE, second=ENTRY, origin=0)
    # position, requested count, length, expected forwarded count.
    boundaries = [(0, 0, 0, 0), (0, 4, 8, 4), (4, 4, 8, 4), (4, 5, 8, 4),
        (8, 1, 8, 0), (9, 0, 8, MASK), (9, 1, 8, MASK),
        (MASK, 1, 8, 1), (MASK, 0, 8, 9), (0x80000000, 0x80000000, 8, 0x80000000),
        (0, MASK, 8, 8), (1, MASK, 8, MASK)]
    for name, boundary, offset, result in itertools.product(
            ["ReadPackedData", "PackedFileSlot::Read"], boundaries, [0, 32, MASK], [0, 1, 7, MASK]):
        position, count, length, expected_count = boundary
        s = dict(base, function=name, position=position, count=count, length=length,
                 expected_count=expected_count, offset=offset, result=result, seek_result=result)
        trace = [["seek", FILE, (offset + position) & MASK, 0], ["read", FILE, DEST, expected_count]]
        yield s, {"return": result, "trace": trace}
    for position, offset, origin in itertools.product([0, 7, 0x7fffffff, 0x80000000, MASK],
            [0, 1, 0x80000000, MASK], [0, 1, 2, -1]):
        final = offset if origin == 0 else (position + offset) & MASK if origin == 1 else position
        yield dict(base, function="PackedFileSlot::Seek", position=position, offset=offset,
                   origin=origin, final_position=final), {"trace": [], "return": final if origin in (0, 1) else MASK}
    for first, second, position in itertools.product([0, SOURCE], [0, ENTRY], [0, 42, MASK]):
        yield dict(base, function="PackedFileSlot::Close", first=first, second=second,
                   position=position), {"trace": [], "return": None}
    for length in [0, 1, 42, 0x80000000, MASK]:
        yield dict(base, function="PackedFileSlot::Size", length=length), {"trace": [], "return": length}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-13-behavior.json"))
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT / d) for d in ("build", ".local")):
        ap.error("report must stay in ignored build/ or .local/")
    data, pe = load_reference(args.exe)
    objpath = ROOT / "build/game/file_manager.obj"
    obj, cases = ObjFile(str(objpath)), []
    for s, expected in scenarios():
        assert execute(pe, obj, s, False) == execute(pe, obj, s, True) == expected, s
        cases.append({**s, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"binary_sha256": hashlib.sha256(data).hexdigest(),
        "object_sha256": hashlib.sha256(objpath.read_bytes()).hexdigest(),
        "scope": __doc__, "cases": cases}, indent=2) + "\n")
    print("Passed %d native package-accessor differential cases" % len(cases))


if __name__ == "__main__":
    main()
