#!/usr/bin/env python3
"""Differential x86 tests of batch-01 bodies with mocked engine/Lua callees.

Does not launch or modify the game. Requires pefile and unicorn. This tests
binding dispatch and ABI behavior, not the implementations of sound or Lua.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP
from unicorn.x86_const import UC_X86_REG_ESI, UC_X86_REG_ESP
from unicorn.x86_const import UC_X86_REG_FPCW

from checkbaseline import REFERENCE_SHA1
from coff import ObjFile
from objmatch import demangle

TARGETS = {"SoundPauseAll_impl": ("sound", 0x74),
           "SoundResumeAll_impl": ("sound", 0x7c),
           "SoundPauseNonMenu_impl": ("sound", 0x84),
           "SoundResumeNonMenu_impl": ("sound", 0x88),
           "GetCameraDefaultFOV_impl": ("number", 104.0)}
COMPILED, HEAP, STUBS, STACK = 0x1000000, 0x2000000, 0x2100000, 0x3000000
GAME, SOUND, VTABLE, STOP = HEAP, HEAP + 0x1000, HEAP + 0x2000, STUBS + 0x1000
ENTITY = HEAP + 0x4000
SYMBOLS = {"?g_game@@3PAVGameApp@@A": 0x78bc20,
           "_lua_pushnumber": 0x6af600, "__real@42d00000": 0x70f764,
           "_lua_gettop": 0x6aef20, "_lua_type": 0x6af080,
           "?CheckArgs@@YA_NPAUlua_State@@HH@Z": 0x5af750,
           "?GetNumberArg@@YAMPAUlua_State@@H_N@Z": 0x5b0230,
           "?LuaCallSite@@YAPBDPAUlua_State@@@Z": 0x5af570,
           "__real@0000000000000000": 0x7021d8,
           "?GetEntityArg@@YAPAVEEntity@@PAUlua_State@@H_NPAVEClassInfo@@@Z": 0x5afff0}
SYMBOLS.update({"?GetSoundArg@@YAPAXPAUlua_State@@H@Z": 0x597d60,
                "?NativeDiagnostic@@YAXPBDZZ": 0x402300,
                "?StopSounds@EEntity@@QAEXXZ": 0x421520,
                "_lua_pushstring": 0x6af7b0,
                "_lua_pushrawnumber": 0x6af700,
                "_lua_torawvalue": 0x6af3d0, "_lua_tostring": 0x6af410,
                "_lua_isrealnumber": 0x6af200, "_lua_isstring": 0x6af240,
                "?GetStringArg@@YAPBDPAUlua_State@@H_N@Z": 0x5b02b0})
# Explicit argument counts for the observed x86 thiscall virtual slots.
SOUND_ARGUMENTS = {0x20: 1, 0x28: 1, 0x30: 3, 0x34: 1, 0x38: 1, 0x40: 1, 0x48: 0, 0x58: 0, 0x5c: 1, 0x64: 2, 0x6c: 1,
                   0x78: 1, 0x80: 1, 0x94: 3, 0x9c: 2, 0xa0: 2,
                   0xa4: 2, 0xc0: 3, 0xc4: 1, 0xc8: 4, 0xd8: 1,
                   0xdc: 1, 0xe0: 2}


def relocate(fn):
    code = bytearray(fn.code)
    for off, size, name, typ in fn.relocs():
        assert size == 4 and name in SYMBOLS, (name, typ)
        addend = struct.unpack_from("<I", code, off)[0]
        value = SYMBOLS[name] + addend
        if typ == 0x14:
            value -= COMPILED + off + 4
        else:
            assert typ == 0x06, typ
        struct.pack_into("<I", code, off, value & 0xffffffff)
    return code


def execute(pe, start, compiled, lua_state, initial_eax, scenario=None):
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    image = pe.get_memory_mapped_image()
    uc.mem_map(pe.OPTIONAL_HEADER.ImageBase, (len(image) + 0xfff) & ~0xfff)
    uc.mem_write(pe.OPTIONAL_HEADER.ImageBase, image)
    for address, size in [(COMPILED, 0x1000), (HEAP, 0x10000), (STUBS, 0x2000), (STACK, 0x10000)]:
        uc.mem_map(address, size)
    if compiled is not None:
        uc.mem_write(COMPILED, bytes(compiled))
    uc.mem_write(SYMBOLS["?g_game@@3PAVGameApp@@A"], struct.pack("<I", GAME))
    uc.mem_write(GAME + 0x198, struct.pack("<I", SOUND if scenario is None or scenario.get("sound_present", True) else 0))
    uc.mem_write(SOUND, struct.pack("<I", VTABLE))
    callbacks = {}
    for offset in range(0, 0xe4, 4):
        address = STUBS + offset * 4
        uc.mem_write(VTABLE + offset, struct.pack("<I", address))
        pop = 4 * SOUND_ARGUMENTS.get(offset, 0)
        uc.mem_write(address, b"\xc2" + struct.pack("<H", pop) if pop else b"\xc3")
        callbacks[address] = offset
    uc.mem_write(SYMBOLS["_lua_pushnumber"], b"\xc3")
    uc.mem_write(SYMBOLS["_lua_pushrawnumber"], b"\xc3")
    uc.mem_write(SYMBOLS["_lua_pushstring"], b"\xc3")
    helper_args = {}
    if scenario is not None:
        uc.mem_write(GAME + 0x9035, bytes([scenario.get("flags", 0)]))
        uc.mem_write(ENTITY + 0x64, struct.pack("<I", scenario.get("entity_flags", 0)))
        uc.mem_write(ENTITY + 0x38, struct.pack("<I", scenario.get("instance", 0)))
        for name, value in [("_lua_gettop", scenario["argc"]),
                            ("_lua_type", 1 if scenario["nil"] else 2),
                            ("?CheckArgs@@YA_NPAUlua_State@@HH@Z",
                             int(scenario.get("min", 1) <= scenario["argc"] <= scenario.get("max", 1))),
                            ("?LuaCallSite@@YAPBDPAUlua_State@@@Z", 0)]:
            uc.mem_write(SYMBOLS[name], b"\xb8" + struct.pack("<I", value) + b"\xc3")
        uc.mem_write(HEAP + 0x3000, struct.pack("<f", scenario["number"]))
        uc.mem_write(SYMBOLS["?GetNumberArg@@YAMPAUlua_State@@H_N@Z"],
                     b"\xd9\x05" + struct.pack("<I", HEAP + 0x3000) + b"\xc3")
        uc.mem_write(STUBS + 0x54 * 4, b"\xb8" + struct.pack("<I", scenario.get("dolby", 0)) + b"\xc3")
        helper_args = {SYMBOLS["_lua_gettop"]: ("gettop", 1),
                       SYMBOLS["_lua_type"]: ("type", 2),
                       SYMBOLS["?CheckArgs@@YA_NPAUlua_State@@HH@Z"]: ("check", 3),
                       SYMBOLS["?GetNumberArg@@YAMPAUlua_State@@H_N@Z"]: ("numberarg", 3),
                       SYMBOLS["?LuaCallSite@@YAPBDPAUlua_State@@@Z"]: ("callsite", 1)}
        entity_helper = SYMBOLS["?GetEntityArg@@YAPAVEEntity@@PAUlua_State@@H_NPAVEClassInfo@@@Z"]
        uc.mem_write(entity_helper, b"\xb8" + struct.pack("<I", ENTITY if scenario.get("entity", True) else 0) + b"\xc3")
        helper_args[entity_helper] = ("entityarg", 4)
        uc.mem_write(SYMBOLS["?NativeDiagnostic@@YAXPBDZZ"], b"\xc3")
        helper_args[SYMBOLS["?NativeDiagnostic@@YAXPBDZZ"]] = ("diagnostic", 2)
        if not scenario.get("real_entity_stop"):
            uc.mem_write(SYMBOLS["?StopSounds@EEntity@@QAEXXZ"], b"\xc3")
            helper_args[SYMBOLS["?StopSounds@EEntity@@QAEXXZ"]] = ("entitystop", 0)
        for name, label, count, value in [
                ("?GetSoundArg@@YAPAXPAUlua_State@@H@Z", "soundarg", 2, scenario.get("sound_handle", 0x12345000)),
                ("_lua_torawvalue", "rawvalue", 2, scenario.get("rawvalue", 0x23456000)),
                ("_lua_tostring", "string", 2, scenario.get("string", 0x34567000)),
                ("_lua_isrealnumber", "isrealnumber", 2, scenario.get("isrealnumber", 0)),
                ("_lua_isstring", "isstring", 2, scenario.get("isstring", 0)),
                ("?GetStringArg@@YAPBDPAUlua_State@@H_N@Z", "stringarg", 3, scenario.get("string", 0x34567000))]:
            if label == "soundarg" and scenario.get("real_soundarg"):
                continue
            uc.mem_write(SYMBOLS[name], b"\xb8" + struct.pack("<I", value) + b"\xc3")
            helper_args[SYMBOLS[name]] = (label, count)
        uc.mem_write(HEAP + 0x3010, struct.pack("<f", scenario.get("getter_result", 0.0)))
        uc.mem_write(STUBS + 0xc4 * 4, b"\xd9\x05" + struct.pack("<I", HEAP + 0x3010) + b"\xc2\x04\x00")
        uc.mem_write(STUBS + 0x20 * 4, b"\xb8" + struct.pack("<I", scenario.get("find_result", 0x45678000)) + b"\xc2\x04\x00")
        for slot, key, default in [(0x28, "sound_name", HEAP + 0x3100), (0x34, "playing", 1), (0x40, "cue_result", 123), (0x48, "available", 1)]:
            pop = 4 * SOUND_ARGUMENTS[slot]
            uc.mem_write(STUBS + slot * 4, b"\xb8" + struct.pack("<I", scenario.get(key, default)) +
                         (b"\xc2" + struct.pack("<H", pop) if pop else b"\xc3"))
    trace = []

    def hook(machine, address, size, context):
        if address in callbacks:
            entry = ["sound", callbacks[address], machine.reg_read(UC_X86_REG_ECX)]
            count = SOUND_ARGUMENTS.get(callbacks[address], 0)
            if count:
                entry.extend(struct.unpack("<" + "I" * count,
                             machine.mem_read(machine.reg_read(UC_X86_REG_ESP) + 4, count * 4)))
            trace.append(entry)
        elif address in helper_args:
            name, count = helper_args[address]
            values = struct.unpack("<" + "I" * count,
                                   machine.mem_read(machine.reg_read(UC_X86_REG_ESP) + 4, count * 4))
            trace.append([name] + list(values))
            if name == "entitystop":
                trace[-1].append(machine.reg_read(UC_X86_REG_ECX))
            if name == "numberarg":
                number = scenario["number"] if values[1] == 1 else scenario.get({2: "second", 3: "third", 4: "fourth"}[values[1]], 0.0)
                machine.mem_write(HEAP + 0x3000, struct.pack("<f", number))
        elif address == SYMBOLS["_lua_pushnumber"]:
            esp = machine.reg_read(UC_X86_REG_ESP)
            state, bits = struct.unpack("<II", machine.mem_read(esp + 4, 8))
            trace.append(["number", state, bits])
        elif address == SYMBOLS["_lua_pushrawnumber"]:
            state, bits = struct.unpack("<II", machine.mem_read(machine.reg_read(UC_X86_REG_ESP) + 4, 8))
            trace.append(["rawnumber", state, bits])
        elif address == SYMBOLS["_lua_pushstring"]:
            state, pointer = struct.unpack("<II", machine.mem_read(machine.reg_read(UC_X86_REG_ESP) + 4, 8))
            trace.append(["pushstring", state, pointer])

    uc.hook_add(UC_HOOK_CODE, hook)
    esp = STACK + 0x8000
    uc.mem_write(esp, struct.pack("<III", STOP, lua_state,
                                  (scenario or {}).get("arg_index", 1) & 0xffffffff))
    preserved = {UC_X86_REG_EBP: 0x12345678, UC_X86_REG_EBX: 0x23456789,
                 UC_X86_REG_ESI: 0x3456789a, UC_X86_REG_EDI: 0x456789ab}
    for register, value in preserved.items():
        uc.reg_write(register, value)
    uc.reg_write(UC_X86_REG_ESP, esp)
    uc.reg_write(UC_X86_REG_EAX, initial_eax)
    if scenario is not None and "entry_this" in scenario:
        uc.reg_write(UC_X86_REG_ECX, scenario["entry_this"])
    uc.reg_write(UC_X86_REG_FPCW, 0x37f)
    uc.emu_start(start, STOP, count=500)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP, "function did not return"
    assert uc.reg_read(UC_X86_REG_ESP) == esp + 4, "cdecl stack imbalance"
    assert uc.reg_read(UC_X86_REG_FPCW) == 0x37f, "x87 control word modified"
    for register, value in preserved.items():
        assert uc.reg_read(register) == value, "nonvolatile register modified"
    result = {"return": uc.reg_read(UC_X86_REG_EAX), "trace": trace}
    if scenario is not None and scenario.get("observe"):
        result["camera_flags"] = bytes(uc.mem_read(GAME + 0x9035, 1))[0]
        result["entity_flags"] = struct.unpack("<I", uc.mem_read(ENTITY + 0x64, 4))[0]
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-01-behavior.json"))
    args = ap.parse_args()
    assert hashlib.sha1(args.exe.read_bytes()).hexdigest() == REFERENCE_SHA1
    pe = pefile.PE(str(args.exe))
    root = Path(__file__).resolve().parent.parent
    rows = {r["name"]: r for r in csv.DictReader((root / "engine/functions.csv").open())}
    funcs = {demangle(f.name): f for path in ["sound_lua.obj", "camera_lua.obj"]
             for f in ObjFile(str(root / "build/game" / path)).functions}
    cases = []
    for name, (kind, expected) in TARGETS.items():
        for state in [0, 0x11111111, 0xffffffff]:
            for initial_eax in [0, 0xdeadbeef]:
                original = execute(pe, int(rows[name]["address"], 16), None, state, initial_eax)
                rebuilt = execute(pe, COMPILED, relocate(funcs[name]), state, initial_eax)
                assert original == rebuilt, (name, original, rebuilt)
                if kind == "sound":
                    assert rebuilt == {"return": 0, "trace": [["sound", expected, SOUND]]}
                else:
                    bits = struct.unpack("<I", struct.pack("<f", expected))[0]
                    assert rebuilt == {"return": 1, "trace": [["number", state, bits]]}
                cases.append({"name": name, "lua_state": state, "initial_eax": initial_eax, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"scope": "isolated binding dispatch with mocked callees",
                                      "cases": cases}, indent=2) + "\n")
    print("Passed %d original-vs-reconstructed x86 cases" % len(cases))


if __name__ == "__main__":
    main()
