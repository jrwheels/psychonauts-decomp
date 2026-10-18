#!/usr/bin/env python3
"""Differential stop/mute/unmute/Dolby binding tests with mocked callees."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct

import pefile

from checkbaseline import REFERENCE_SHA1
from coff import ObjFile
from objmatch import demangle
from test_sound_camera_bindings import COMPILED, SOUND, execute, relocate


def bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-03-behavior.json"))
    args = ap.parse_args()
    assert hashlib.sha1(args.exe.read_bytes()).hexdigest() == REFERENCE_SHA1
    root = Path(__file__).resolve().parent.parent
    pe = pefile.PE(str(args.exe))
    rows = {r["name"]: r for r in csv.DictReader((root / "engine/functions.csv").open())}
    funcs = {demangle(f.name): f for f in ObjFile(str(root / "build/game/sound_lua.obj")).functions}
    cases = []
    state = 0x11111111
    for name, slot, maxargs in [("SoundStopCategory_impl", 0x5c, 1),
                                ("SoundMuteCategory_impl", 0x64, 2),
                                ("SoundUnmuteCategory_impl", 0x6c, 2)]:
        scenarios = [{"argc": n, "nil": False, "number": 0.0} for n in [0, maxargs + 1]]
        scenarios += [{"argc": n, "nil": True, "number": 0.0} for n in range(1, maxargs + 1)]
        scenarios += [{"argc": n, "nil": False, "number": value, "second": time}
                      for n in range(1, maxargs + 1)
                      for value in [-1.0, -0.75, 0.0, 11.75, 12.0, 255.75, 256.0, 2147483648.0]
                      for time in ([0.0, 3.5] if n == 2 else [0.0])]
        for scenario in scenarios:
            scenario.update({"min": 1, "max": maxargs})
            original = execute(pe, int(rows[name]["address"], 16), None, state, 0xdeadbeef, scenario)
            rebuilt = execute(pe, COMPILED, relocate(funcs[name]), state, 0xdeadbeef, scenario)
            assert original == rebuilt, (name, scenario, original, rebuilt)
            expected = [["gettop", state], ["check", state, 1, maxargs]]
            if 1 <= scenario["argc"] <= maxargs:
                expected += [["numberarg", state, 1, 0], ["type", state, 1]]
                if scenario["nil"]:
                    expected += [["callsite", state]]
                else:
                    if scenario["argc"] == 2:
                        expected += [["numberarg", state, 2, 1]]
                    if 0 <= int(scenario["number"]) < 256:
                        expected += [["sound", slot, SOUND, int(scenario["number"])]]
                        if slot == 0x64:
                            expected[-1].append(bits(scenario.get("second", 0.0)))
            assert rebuilt == {"return": 0, "trace": expected}, (name, scenario, rebuilt, expected)
            cases.append({"function": name, "scenario": scenario, "passed": True})
    name = "SoundIsDolbyDigital_impl"
    for argc in [0, 1]:
        for supported in [0, 1]:
            scenario = {"argc": argc, "nil": False, "number": 0.0, "min": 0, "max": 0, "dolby": supported}
            original = execute(pe, int(rows[name]["address"], 16), None, state, 0xdeadbeef, scenario)
            rebuilt = execute(pe, COMPILED, relocate(funcs[name]), state, 0xdeadbeef, scenario)
            expected = [["gettop", state], ["check", state, 0, 0]]
            if argc == 0:
                expected += [["sound", 0x54, SOUND], ["number", state, bits(float(supported))]]
            assert original == rebuilt == {"return": int(argc == 0), "trace": expected}
            cases.append({"function": name, "scenario": scenario, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"scope": "isolated binding behavior with mocked callees",
                                      "cases": cases}, indent=2) + "\n")
    print("Passed %d stop/mute/Dolby original-vs-reconstructed x86 cases" % len(cases))


if __name__ == "__main__":
    main()
