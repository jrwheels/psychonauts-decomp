#!/usr/bin/env python3
"""Differential volume/attenuation binding tests with mocked helper callees."""
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-04-behavior.json"))
    args = ap.parse_args()
    assert hashlib.sha1(args.exe.read_bytes()).hexdigest() == REFERENCE_SHA1
    root = Path(__file__).resolve().parent.parent
    pe = pefile.PE(str(args.exe))
    rows = {r["name"]: r for r in csv.DictReader((root / "engine/functions.csv").open())}
    funcs = {demangle(f.name): f for f in ObjFile(str(root / "build/game/sound_lua.obj")).functions}
    cases = []
    state = 0x11111111
    for name, slot, nargs in [("MusicVolume_impl", 0x9c, 2), ("FXVolume_impl", 0xa0, 2),
                              ("VoiceVolume_impl", 0xa4, 2),
                              ("SoundSetDistanceFactor_impl", 0xd8, 1),
                              ("SoundSetRolloffFactor_impl", 0xdc, 1)]:
        scenarios = [{"argc": n, "nil": False, "number": 0.0} for n in [0, 2]]
        scenarios += [{"argc": 1, "nil": False, "number": value}
                      for value in [-1.0, -0.0, 0.0, 0.5, 1.0, 2.0,
                                    float("inf"), float("-inf"), float("nan")]]
        for scenario in scenarios:
            original = execute(pe, int(rows[name]["address"], 16), None, state, 0xdeadbeef, scenario)
            rebuilt = execute(pe, COMPILED, relocate(funcs[name]), state, 0xdeadbeef, scenario)
            assert original == rebuilt, (name, scenario, original, rebuilt)
            expected = [["gettop", state], ["check", state, 1, 1]]
            number_bits = struct.unpack("<I", struct.pack("<f", scenario["number"]))[0]
            if scenario["argc"] == 1:
                expected += [["numberarg", state, 1, 0], ["sound", slot, SOUND, number_bits]]
                if nargs == 2:
                    expected[-1].append(0)
            assert rebuilt == {"return": 0, "trace": expected}, (name, scenario, rebuilt, expected)
            cases.append({"function": name, "argc": scenario["argc"],
                          "number_bits": "0x%08x" % number_bits, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"scope": "isolated bindings with mocked helpers/sound",
                                      "cases": cases}, indent=2) + "\n")
    print("Passed %d volume/attenuation original-vs-reconstructed x86 cases" % len(cases))


if __name__ == "__main__":
    main()
