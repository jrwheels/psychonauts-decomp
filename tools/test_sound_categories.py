#!/usr/bin/env python3
"""Differential tests of sound-category bodies with mocked helper callees."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import pefile

from checkbaseline import REFERENCE_SHA1
from coff import ObjFile
from objmatch import demangle
from test_sound_camera_bindings import COMPILED, SOUND, execute, relocate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-02-behavior.json"))
    args = ap.parse_args()
    assert hashlib.sha1(args.exe.read_bytes()).hexdigest() == REFERENCE_SHA1
    root = Path(__file__).resolve().parent.parent
    pe = pefile.PE(str(args.exe))
    rows = {r["name"]: r for r in csv.DictReader((root / "engine/functions.csv").open())}
    funcs = {demangle(f.name): f for f in ObjFile(str(root / "build/game/sound_lua.obj")).functions}
    scenarios = [{"argc": n, "nil": False, "number": 1.0} for n in [0, 2]]
    scenarios += [{"argc": 1, "nil": True, "number": 0.0}]
    scenarios += [{"argc": 1, "nil": False, "number": n}
                  for n in [-1.0, -0.75, 0.0, 0.75, 11.0, 11.75, 12.0,
                            255.0, 255.75, 256.0, 2147483648.0]]
    cases = []
    state = 0x11111111
    for name, slot, limit in [("SoundPauseCategory_impl", 0x78, 256),
                              ("SoundResumeCategory_impl", 0x80, 12)]:
        for scenario in scenarios:
            original = execute(pe, int(rows[name]["address"], 16), None, state, 0xdeadbeef, scenario)
            rebuilt = execute(pe, COMPILED, relocate(funcs[name]), state, 0xdeadbeef, scenario)
            assert original == rebuilt, (name, scenario, original, rebuilt)
            expected = [["gettop", state], ["check", state, 1, 1]]
            if scenario["argc"] == 1:
                expected += [["numberarg", state, 1, 0], ["type", state, 1]]
                if scenario["nil"]:
                    expected += [["callsite", state]]
                elif 0 <= int(scenario["number"]) < limit:
                    expected += [["sound", slot, SOUND, int(scenario["number"])]]
            assert rebuilt == {"return": 0, "trace": expected}, (name, scenario, rebuilt, expected)
            cases.append({"function": name, "scenario": scenario, "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"scope": "isolated bindings with mocked helpers/sound",
                                      "cases": cases}, indent=2) + "\n")
    print("Passed %d category original-vs-reconstructed x86 cases" % len(cases))


if __name__ == "__main__":
    main()
