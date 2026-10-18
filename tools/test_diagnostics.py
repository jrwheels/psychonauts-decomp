#!/usr/bin/env python3
"""Differential native diagnostic tests; CRT formatting and stream I/O mocked.

Tests isolated bodies and the complete reconstructed four-body call chain.
This verifies varargs forwarding, byte bounds, newline/enable policy and ABI;
it does not establish CRT formatting equivalence or real file output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
    UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)

from coff import ObjFile
from native_index import load_reference
from objmatch import demangle

ROOT = Path(__file__).resolve().parent.parent
CODE, HEAP, STUBS, STACK = 0x1000000, 0x2000000, 0x2100000, 0x3000000
SINK, TEXT, FORMAT, ARGS = HEAP, HEAP + 0x1000, HEAP + 0x2000, HEAP + 0x3000
ENTRY_SP, STOP, FORMATTER = STACK + 0x8000, STUBS, STUBS + 0x100
STREAM = SINK + 0x1c
FACTORY, FACTORY_VT, FILE, FILE_VT, FILE_NAME = (HEAP + n * 0x1000 for n in range(4, 9))
OPEN, CLOSE, WRITE, SEEK = (STUBS + n for n in (0x200, 0x240, 0x260, 0x280))
ORIGINAL = {"NativeDiagnostic": 0x402300, "DiagnosticSink::Write": 0x4024d0,
            "DiagnosticSink::VPrintf": 0x402560, "DiagnosticStream::Write": 0x6a4ee0}
REBUILT = {name: CODE + i * 0x1000 for i, name in enumerate(ORIGINAL)}
SYMBOLS = {"?g_diagnosticSink@@3PAVDiagnosticSink@@A": 0x781fd8,
           "?VPrintf@DiagnosticSink@@QAEXPBDPAD@Z": 0x402560,
           "?Write@DiagnosticSink@@QAEXPBD@Z": 0x4024d0,
           "?Write@DiagnosticStream@@QAE_NPBD@Z": 0x6a4ee0,
           "?g_diagnosticFileFactory@@3PAVEFileManager@@A": 0x781d90,
           "__imp___vsnprintf": 0x70029c}
VARIADIC = (0x12345678, 0x87654321)


def relocate(fn, address, symbols):
    code = bytearray(fn.code)
    for offset, size, symbol, kind in fn.relocs():
        assert size == 4 and symbol in symbols, (symbol, kind)
        value = symbols[symbol] + struct.unpack_from("<I", code, offset)[0]
        if kind == 0x14:
            value -= address + offset + 4
        else:
            assert kind == 6, kind
        struct.pack_into("<I", code, offset, value & 0xffffffff)
    return bytes(code)


def read_string(uc, pointer):
    data = bytes(uc.mem_read(pointer, 1024))
    assert b"\0" in data, "unterminated diagnostic output"
    return data.split(b"\0", 1)[0]


def execute(pe, obj, name, scenario, rebuilt):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    uc.mem_map(base, (len(image) + 0xfff) & ~0xfff)
    uc.mem_write(base, image)
    for address, size in [(CODE, 0x4000), (HEAP, 0x10000), (STUBS, 0x1000), (STACK, 0x10000)]:
        uc.mem_map(address, size)
    uc.mem_write(STACK, b"\xa5" * 0x10000)
    functions = {demangle(f.name): f for f in obj.functions}
    symbols = dict(SYMBOLS)
    for symbol, text in obj.strings().items():
        assert text == b"\n", (symbol, text)
        assert pe.get_string_at_rva(0x702240 - base) == text
        symbols[symbol] = 0x702240
    if rebuilt and scenario["chain"]:
        symbols["?VPrintf@DiagnosticSink@@QAEXPBDPAD@Z"] = REBUILT["DiagnosticSink::VPrintf"]
        symbols["?Write@DiagnosticSink@@QAEXPBD@Z"] = REBUILT["DiagnosticSink::Write"]
        if scenario.get("real_stream"):
            symbols["?Write@DiagnosticStream@@QAE_NPBD@Z"] = REBUILT["DiagnosticStream::Write"]
    if rebuilt:
        for function, address in REBUILT.items():
            uc.mem_write(address, relocate(functions[function], address, symbols))
    uc.mem_write(SYMBOLS["?g_diagnosticSink@@3PAVDiagnosticSink@@A"],
                 struct.pack("<I", SINK if scenario["sink"] else 0))
    uc.mem_write(SINK + 0x20, bytes([scenario["enabled"]]))
    uc.mem_write(STREAM + 0x10, struct.pack("<I", FILE_NAME))
    uc.mem_write(FILE_NAME, b"unit.log\0")
    uc.mem_write(0x781d90, struct.pack("<I", FACTORY))
    uc.mem_write(FACTORY, struct.pack("<I", FACTORY_VT))
    uc.mem_write(FACTORY_VT, struct.pack("<I", OPEN))
    uc.mem_write(FILE, struct.pack("<I", FILE_VT))
    for slot, address, pop, result in [(4, CLOSE, 0, scenario.get("close_result", 0)),
                                     (0xc, WRITE, 8, scenario.get("write_result", 0)),
                                     (0x10, SEEK, 8, scenario.get("seek_result", 0))]:
        uc.mem_write(FILE_VT + slot, struct.pack("<I", address))
        uc.mem_write(address, b"\xb8" + struct.pack("<I", result) +
                     (b"\xc2" + struct.pack("<H", pop) if pop else b"\xc3"))
    uc.mem_write(OPEN, b"\xb8" + struct.pack("<I", FILE if scenario.get("open", True) else 0) + b"\xc2\x0c\x00")
    uc.mem_write(TEXT, scenario["text"] + b"\0")
    uc.mem_write(FORMAT, b"mock:%x\0")
    uc.mem_write(ARGS, struct.pack("<II", *VARIADIC))
    uc.mem_write(0x70029c, struct.pack("<I", FORMATTER))
    uc.mem_write(FORMATTER, b"\xb8" + struct.pack("<I", scenario["format_result"]) + b"\xc3")
    if name != "DiagnosticStream::Write" and not scenario.get("real_stream"):
        uc.mem_write(0x6a4ee0, b"\xc2\x04\x00")
    mocked = {}
    if not scenario["chain"]:
        if name == "NativeDiagnostic":
            uc.mem_write(0x402560, b"\xc2\x08\x00")
            mocked[0x402560] = "vprintf"
        if name == "DiagnosticSink::VPrintf":
            uc.mem_write(0x4024d0, b"\xc2\x04\x00")
            mocked[0x4024d0] = "write"
    trace = []

    def hook(machine, address, size, context):
        esp = machine.reg_read(UC_X86_REG_ESP)
        this = machine.reg_read(UC_X86_REG_ECX)
        if address == FORMATTER:
            dest, maximum, fmt, args = struct.unpack("<4I", machine.mem_read(esp + 4, 16))
            assert maximum == 1023
            assert dest == ENTRY_SP - (0x404 if not scenario["chain"] else 0x418)
            trace.append(["format", maximum, fmt,
                          list(struct.unpack("<II", machine.mem_read(args, 8)))])
            machine.mem_write(dest, scenario["formatted"])
        elif address == 0x6a4ee0 and name != "DiagnosticStream::Write" and not scenario.get("real_stream"):
            pointer = struct.unpack("<I", machine.mem_read(esp + 4, 4))[0]
            trace.append(["stream", this, read_string(machine, pointer).hex()])
        elif address == OPEN:
            values = struct.unpack("<III", machine.mem_read(esp + 4, 12))
            trace.append(["open", this, *values])
        elif address == SEEK:
            values = struct.unpack("<II", machine.mem_read(esp + 4, 8))
            trace.append(["seek", this, *values])
        elif address == WRITE:
            pointer, count = struct.unpack("<II", machine.mem_read(esp + 4, 8))
            trace.append(["file_write", this, count, bytes(machine.mem_read(pointer, count)).hex()])
        elif address == CLOSE:
            trace.append(["close", this])
        elif address in mocked:
            if mocked[address] == "vprintf":
                fmt, args = struct.unpack("<II", machine.mem_read(esp + 4, 8))
                assert args == ENTRY_SP + 8
                trace.append(["vprintf", this, fmt,
                              list(struct.unpack("<II", machine.mem_read(args, 8)))])
            else:
                pointer = struct.unpack("<I", machine.mem_read(esp + 4, 4))[0]
                assert machine.mem_read(pointer + 1023, 1) == b"\0"
                trace.append(["write", this, read_string(machine, pointer).hex()])

    uc.hook_add(UC_HOOK_CODE, hook)
    if name == "NativeDiagnostic":
        args, pop = [FORMAT, *VARIADIC], 0
    elif name in ("DiagnosticSink::Write", "DiagnosticStream::Write"):
        args, pop = [TEXT if scenario["text_present"] else 0], 4
    else:
        args, pop = [FORMAT, ARGS], 8
    uc.mem_write(ENTRY_SP, struct.pack("<" + "I" * (len(args) + 1), STOP, *args))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for register, value in preserved.items():
        uc.reg_write(register, value)
    uc.reg_write(UC_X86_REG_ECX, STREAM if name == "DiagnosticStream::Write" else SINK)
    uc.reg_write(UC_X86_REG_EAX, scenario["initial_eax"])
    uc.reg_write(UC_X86_REG_ESP, ENTRY_SP)
    uc.emu_start(REBUILT[name] if rebuilt else ORIGINAL[name], STOP, count=20000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP
    assert uc.reg_read(UC_X86_REG_ESP) == ENTRY_SP + 4 + pop, "ABI stack imbalance"
    for register, value in preserved.items():
        assert uc.reg_read(register) == value, "nonvolatile register modified"
    return {"trace": trace, "return": uc.reg_read(UC_X86_REG_EAX) & 0xff} if name == "DiagnosticStream::Write" else trace


def scenarios():
    base = {"chain": False, "sink": True, "enabled": 1, "text_present": True,
            "text": b"abc", "formatted": b"hello\0", "format_result": 5}
    for sink in (False, True):
        yield "NativeDiagnostic", {**base, "sink": sink}, (
            [["vprintf", SINK, FORMAT, list(VARIADIC)]] if sink else [])
    for enabled in (0, 1, 2, 255):
        for text in (None, b"", b"abc", b"already\n", b"\xff"):
            trace = [["stream", SINK + 0x1c, text.hex()], ["stream", SINK + 0x1c, "0a"]] if enabled and text else []
            yield "DiagnosticSink::Write", {**base, "enabled": enabled,
                "text_present": text is not None, "text": text or b""}, trace
    for formatted, result in [(b"\0", 0), (b"hello\0", 5), (b"x" * 1022 + b"\0", 1022),
                              (b"y" * 1023, 0xffffffff), (b"", 0xffffffff)]:
        expected = formatted.split(b"\0", 1)[0] if formatted else b"\xa5" * 1023
        trace = [["format", 1023, FORMAT, list(VARIADIC)], ["write", SINK, expected.hex()]]
        yield "DiagnosticSink::VPrintf", {**base, "formatted": formatted, "format_result": result}, trace
        for enabled in (0, 1):
            trace = [["format", 1023, FORMAT, list(VARIADIC)]]
            if enabled and expected:
                trace += [["stream", SINK + 0x1c, expected.hex()], ["stream", SINK + 0x1c, "0a"]]
            yield "NativeDiagnostic", {**base, "chain": True, "formatted": formatted,
                "format_result": result, "enabled": enabled}, trace
    yield "NativeDiagnostic", {**base, "chain": True, "sink": False}, []
    for enabled in (0, 1, 2, 255):
        for opened in (False, True):
            for text in (b"", b"abc", b"\xff\n"):
                for failed_write in (False, True):
                    trace = stream_trace(text, enabled, opened)
                    yield "DiagnosticStream::Write", {**base, "enabled": enabled,
                        "open": opened, "text": text, "write_result": 0 if failed_write else len(text),
                        "close_result": 0xdeadbeef if failed_write else 0}, {
                            "return": int(bool(enabled and opened)), "trace": trace}
    for enabled, opened in ((0, True), (1, False)):
        yield "DiagnosticStream::Write", {**base, "enabled": enabled, "open": opened,
            "text_present": False}, {"return": 0, "trace": stream_trace(b"", enabled, opened)}
    for enabled in (0, 1):
        for opened in (False, True):
            for text in (b"hello", b"x" * 1023):
                trace = [["format", 1023, FORMAT, list(VARIADIC)]]
                # Sink enable also guards its stream calls; failed open is
                # attempted separately for text and appended newline.
                if enabled:
                    trace += stream_trace(text, enabled, opened) + stream_trace(b"\n", enabled, opened)
                yield "NativeDiagnostic", {**base, "chain": True, "real_stream": True,
                    "enabled": enabled, "open": opened,
                    "formatted": text if len(text) == 1023 else text + b"\0"}, trace


def stream_trace(text, enabled, opened):
    if not enabled:
        return []
    trace = [["open", FACTORY, FILE_NAME, 0x800, 4]]
    if opened:
        trace += [["seek", FILE, 0, 2], ["file_write", FILE, len(text), text.hex()], ["close", FILE]]
    return trace


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-10-behavior.json"))
    args = ap.parse_args()
    report = args.report.resolve()
    if not any(report.is_relative_to(ROOT / d) for d in ("build", ".local")) or report == args.exe.resolve():
        ap.error("report must stay in ignored build/ or .local/, separate from the reference")
    data, pe = load_reference(args.exe)
    objpath = ROOT / "build/game/diagnostic.obj"
    obj = ObjFile(str(objpath))
    cases = []
    for name, scenario, expected in scenarios():
        for eax in (0, 0xdeadbeef):
            scenario["initial_eax"] = eax
            original = execute(pe, obj, name, scenario, False)
            rebuilt = execute(pe, obj, name, scenario, True)
            assert original == rebuilt == expected, (name,
                {k: len(v) if isinstance(v, bytes) else v for k, v in scenario.items()},
                "original/rebuilt/expected trace mismatch")
            cases.append({"function": name, "scenario": {k: v.hex() if isinstance(v, bytes) else v
                          for k, v in scenario.items()}, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"binary_sha256": hashlib.sha256(data).hexdigest(),
        "object_sha256": hashlib.sha256(objpath.read_bytes()).hexdigest(),
        "scope": "native bodies and four-body chain; CRT formatter and file factory/file methods mocked",
        "cases": cases}, indent=2) + "\n")
    print("Passed %d native diagnostic differential cases" % len(cases))


if __name__ == "__main__":
    main()
