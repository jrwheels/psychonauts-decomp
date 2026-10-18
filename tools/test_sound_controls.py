#!/usr/bin/env python3
"""Original/rebuilt category-volume and release ducking binding tests."""
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
    ap.add_argument("--report", type=Path, default=Path("build/batch-05-behavior.json"))
    args = ap.parse_args()
    assert hashlib.sha1(args.exe.read_bytes()).hexdigest() == REFERENCE_SHA1
    root = Path(__file__).resolve().parent.parent
    pe = pefile.PE(str(args.exe))
    rows = {r["name"]: r for r in csv.DictReader((root / "engine/functions.csv").open())}
    funcs = {demangle(f.name): f for f in ObjFile(str(root / "build/game/sound_lua.obj")).functions}
    cases = []
    state = 0x11111111
    for name in ["SoundSetDucking_impl", "SoundVolumeCategory_impl"]:
        ducking = name == "SoundSetDucking_impl"
        minimum, maximum = (1, 1) if ducking else (2, 3)
        scenarios = [{"argc": n, "nil": False, "number": 0.0} for n in [0, maximum + 1]]
        if ducking:
            scenarios += [{"argc": 1, "nil": False, "number": n}
                          for n in [-1.0, -0.0, 0.0, 1.0, float("nan"), float("inf")]]
        else:
            scenarios += [{"argc": 2, "nil": True, "number": 0.0}]
            scenarios += [{"argc": argc, "nil": False, "number": category,
                           "second": volume, "third": time}
                          for argc in [2, 3] for category in [-1.0, -0.75, 0.0, 255.75, 256.0, 2147483648.0]
                          for volume in [-0.0, 0.5] for time in [0.0, 3.5]]
        for scenario in scenarios:
            scenario.update({"min": minimum, "max": maximum})
            original = execute(pe, int(rows[name]["address"], 16), None, state, 0xdeadbeef, scenario)
            rebuilt = execute(pe, COMPILED, relocate(funcs[name]), state, 0xdeadbeef, scenario)
            assert original == rebuilt, (name, scenario, original, rebuilt)
            expected = [["gettop", state], ["check", state, minimum, maximum]]
            if minimum <= scenario["argc"] <= maximum:
                expected += [["numberarg", state, 1, 0]]
                if not ducking:
                    expected += [["type", state, 1]]
                    if scenario["nil"]:
                        expected += [["callsite", state]]
                    else:
                        expected += [["numberarg", state, 2, 0]]
                        if scenario["argc"] == 3:
                            expected += [["numberarg", state, 3, 1]]
                        category = int(scenario["number"])
                        if 0 <= category < 256:
                            expected += [["sound", 0x94, SOUND, category, bits(scenario["second"]),
                                          bits(scenario["third"] if scenario["argc"] == 3 else 0.0)]]
            assert rebuilt == {"return": 0, "trace": expected}, (name, scenario, rebuilt, expected)
            cases.append({"function": name, "argc": scenario["argc"],
                          "number_bits": "0x%08x" % bits(scenario["number"]), "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"scope": "isolated bindings with mocked callees", "cases": cases}, indent=2) + "\n")
    print("Passed %d ducking/category-volume differential cases" % len(cases))


if __name__ == "__main__":
    main()
