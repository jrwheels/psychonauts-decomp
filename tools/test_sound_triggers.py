#!/usr/bin/env python3
"""Differential x86 verification for trigger/parameter/handle bindings.

All Lua and sound callees are mocked. Tests establish isolated ABI and dispatch
behavior only. Expected traces follow original assembly, not API names.
"""
import argparse
import json
import math
from pathlib import Path
import struct

from coff import ObjFile
from native_index import load_reference
from objmatch import demangle
from test_sound_camera_bindings import COMPILED, SOUND, SYMBOLS, execute, relocate

TARGETS = {"StopAllSounds_impl": 0x599390, "SoundSetTriggerVariable_impl": 0x59a310,
           "SoundGetTriggerVariable_impl": 0x59a430, "SoundSetParameterControl_impl": 0x59a550,
           "GetSoundArg": 0x597d60}
STATE = 0x11111111


def bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def truncated_dword(value):
    # Original x87 FISTP qword, then low DWORD. Nonfinite/overflow inputs
    # produce integer-indefinite under the default masked x87 control word.
    value = struct.unpack("<f", struct.pack("<f", value))[0]
    if not (-2**63 <= value < 2**63):
        return 0
    return int(value) & 0xffffffff


def scenarios():
    for present in (False, True):
        yield "StopAllSounds_impl", {"argc": 0, "sound_present": present}, (
            {"return": 0, "trace": [["sound", 0x58, SOUND]] if present else []})
    for setter in (False, True):
        name = "SoundSetTriggerVariable_impl" if setter else "SoundGetTriggerVariable_impl"
        argc = 2 if setter else 1
        for count in (0, argc + 1):
            yield name, {"argc": count, "min": argc, "max": argc}, {
                "return": 0, "trace": [["gettop", STATE], ["check", STATE, argc, argc]]}
        for value in (-1.0, -0.75, -0.0, 0.75, 1.0, 31.0, 31.75, 32.0,
                      255.0, 2**31, 2**32, -(2**32), 2**40,
                      float("inf"), -float("inf"), float("nan")):
            # Nil is intentionally not checked here (unlike category bindings).
            for nil in (False, True):
                scenario = {"argc": argc, "min": argc, "max": argc,
                            "number": value, "nil": nil, "second": -0.0, "getter_result": -3.25}
                trace = [["gettop", STATE], ["check", STATE, argc, argc], ["numberarg", STATE, 1, 0]]
                index = truncated_dword(value)
                if setter:
                    trace.append(["numberarg", STATE, 2, 0])
                if index < 32:
                    trace.append(["sound", 0xc0 if setter else 0xc4, SOUND, index] + ([bits(-0.0), 0] if setter else []))
                    if not setter:
                        trace.append(["number", STATE, bits(-3.25)])
                yield name, scenario, {"return": int(not setter and index < 32), "trace": trace}
        if not setter:
            for result in (-0.0, 0.0, float("inf"), -float("inf"), float("nan")):
                yield name, {"argc": 1, "number": 2.0, "getter_result": result}, {
                    "return": 1, "trace": [["gettop", STATE], ["check", STATE, 1, 1],
                    ["numberarg", STATE, 1, 0], ["sound", 0xc4, SOUND, 2], ["number", STATE, bits(result)]]}
        else:
            for value in (-2.0, 0.0, float("inf"), float("nan")):
                yield name, {"argc": 2, "min": 2, "max": 2, "number": 1.0, "second": value}, {
                    "return": 0, "trace": [["gettop", STATE], ["check", STATE, 2, 2],
                    ["numberarg", STATE, 1, 0], ["numberarg", STATE, 2, 0], ["sound", 0xc0, SOUND, 1, bits(value), 0]]}
    for count in (0, 3, 5):
        yield "SoundSetParameterControl_impl", {"argc": count, "min": 4, "max": 4}, {
            "return": 0, "trace": [["gettop", STATE], ["check", STATE, 4, 4]]}
    for handle in (0, 0x12345000):
        for instance in (0, 0xffffffff):
            for string in (0, 0x34567000):
                for value in (-0.0, 3.5, float("nan")):
                    trace = [["gettop", STATE], ["check", STATE, 4, 4], ["soundarg", STATE, 1],
                             ["rawvalue", STATE, 2], ["stringarg", STATE, 3, 0], ["numberarg", STATE, 4, 0]]
                    if string:
                        trace.append(["sound", 0xc8, SOUND, string, bits(value), instance, handle])
                    yield "SoundSetParameterControl_impl", {
                        "argc": 4, "min": 4, "max": 4, "sound_handle": handle,
                        "rawvalue": instance, "string": string, "fourth": value}, {"return": 0, "trace": trace}
    for index in (-21, -20, -19, -1, 0, 1, 19, 20, 21):
        for numeric, string in ((True, False), (True, True), (False, True), (False, False)):
            for handle in (0, 0xffffffff):
                trace, result = [], 0
                if abs(index) < 20:
                    trace.append(["isrealnumber", STATE, index & 0xffffffff])
                    if numeric:
                        trace.append(["rawvalue", STATE, index & 0xffffffff]); result = handle
                    else:
                        trace.append(["isstring", STATE, index & 0xffffffff])
                        if string:
                            trace += [["string", STATE, index & 0xffffffff], ["callsite", STATE],
                                      ["sound", 0x20, SOUND, 0x34567000]]
                            result = handle
                yield "GetSoundArg", {"argc": 1, "real_soundarg": True, "arg_index": index, "isrealnumber": int(numeric),
                                       "isstring": int(string), "rawvalue": handle,
                                       "find_result": handle}, {"return": result, "trace": trace}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-07-behavior.json"))
    args = ap.parse_args()
    verify_cases(args.exe, args.report, TARGETS, scenarios())


def verify_cases(exe, report_path, targets, scenario_iterator):
    root = Path(__file__).resolve().parent.parent
    report = report_path.resolve()
    if not any(report.is_relative_to(root / d) for d in ("build", ".local")) or report == exe.resolve():
        raise ValueError("report must stay in ignored build/ or .local/, separate from the reference")
    data, pe = load_reference(exe)
    objpath = Path(__file__).resolve().parent.parent / "build/game/sound_lua.obj"
    obj = ObjFile(str(objpath))
    functions = {demangle(f.name): f for f in obj.functions}
    SYMBOLS[functions["GetSoundArg"].key] = TARGETS["GetSoundArg"]
    strings = {b"Unknown": 0x703680, b"ScriptVM: Invalid sound handle ": 0x7113f8}
    for symbol, value in obj.strings().items():
        if value in strings:
            address = strings[value]
            assert pe.get_string_at_rva(address - pe.OPTIONAL_HEADER.ImageBase) == value
            SYMBOLS[symbol] = address
    cases = []
    for name, scenario, expected in scenario_iterator:
        scenario = {"nil": False, "number": 0.0, **scenario}
        for initial_eax in (0, 0xdeadbeef):
            original = execute(pe, targets[name], None, STATE, initial_eax, scenario)
            rebuilt = execute(pe, COMPILED, relocate(functions[name]), STATE, initial_eax, scenario)
            assert original == rebuilt, (name, scenario, original, rebuilt)
            assert all(rebuilt[k] == value for k, value in expected.items()), (name, scenario, rebuilt, expected)
            stored = {k: v if not isinstance(v, float) or math.isfinite(v) else str(v) for k, v in scenario.items()}
            cases.append({"name": name, "scenario": stored, "initial_eax": initial_eax, "passed": True})
    report_path.parent.mkdir(parents=True, exist_ok=True)
    import hashlib
    report_path.write_text(json.dumps({"binary_sha256": hashlib.sha256(data).hexdigest(),
                                      "object_sha256": hashlib.sha256(objpath.read_bytes()).hexdigest(),
                                      "scope": "isolated x86 bindings with mocked Lua and sound callees",
                                      "cases": cases}, indent=2, allow_nan=False) + "\n")
    print("Passed %d new differential x86 cases" % len(cases))


if __name__ == "__main__":
    main()
