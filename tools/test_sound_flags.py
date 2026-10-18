#!/usr/bin/env python3
"""Differential tests of sound flag writes, with mocked entity/Lua helpers."""
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
from test_sound_camera_bindings import COMPILED, HEAP, SOUND, execute, relocate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-06-behavior.json"))
    args = ap.parse_args()
    assert hashlib.sha1(args.exe.read_bytes()).hexdigest() == REFERENCE_SHA1
    root = Path(__file__).resolve().parent.parent
    pe = pefile.PE(str(args.exe))
    rows = {r["name"]: r for r in csv.DictReader((root / "engine/functions.csv").open())}
    funcs = {demangle(f.name): f for f in ObjFile(str(root / "build/game/sound_lua.obj")).functions}
    state, cases = 0x11111111, []
    for name in ["SoundSetCameraRelative_impl", "SoundSetEcho_impl"]:
        camera = name == "SoundSetCameraRelative_impl"
        scenarios = []
        if camera:
            for argc in [0, 1, 2, 3]:
                for flags in [0, 0xff, 0x15, 0xa5]:
                    for value in [0.0, -0.0, 1.0, -1.0, float("nan")]:
                        for second in [0.0, 1.0]:
                            scenarios.append({"argc": argc, "flags": flags, "number": value, "second": second,
                                              "entity_flags": 0xa5a5a5a5, "min": 1, "max": 2})
        else:
            for argc in [1, 2, 3]:
                for entity in [False, True]:
                    for instance in [0, HEAP + 0x5000]:
                        for flags in [0, 0xffffffff, 0xa5a5a5a5]:
                            for enable in [0.0, -0.0, 1.0, -1.0, float("nan")]:
                                scenarios.append({"argc": argc, "entity": entity, "instance": instance,
                                                  "entity_flags": flags, "number": 0.0, "second": enable,
                                                  "flags": 0x15, "min": 2, "max": 2})
        for scenario in scenarios:
            scenario.update({"nil": False, "observe": True})
            original = execute(pe, int(rows[name]["address"], 16), None, state, 0xdeadbeef, scenario)
            rebuilt = execute(pe, COMPILED, relocate(funcs[name]), state, 0xdeadbeef, scenario)
            assert original == rebuilt, (name, scenario, original, rebuilt)
            trace = [["gettop", state], ["check", state, scenario["min"], scenario["max"]]]
            camera_flags, entity_flags = scenario["flags"], scenario["entity_flags"]
            valid = scenario["min"] <= scenario["argc"] <= scenario["max"]
            if valid:
                if camera:
                    trace += [["numberarg", state, 1, 0]]
                    if scenario["argc"] == 2:
                        trace += [["numberarg", state, 2, 1]]
                    first = int(scenario["number"] != 0)
                    second = int(scenario["second"] != 0) if scenario["argc"] == 2 else 1
                    camera_flags = (camera_flags & 0x3f) | (first << 6) | (second << 7)
                else:
                    trace += [["entityarg", state, 1, 0, 0]]
                    if scenario["entity"]:
                        trace += [["numberarg", state, 2, 0]]
                        enable = int(scenario["second"] != 0)
                        entity_flags = (entity_flags & ~4) | (enable << 2)
                        if scenario["instance"]:
                            trace += [["sound", 0xe0, SOUND, scenario["instance"], enable]]
            assert rebuilt == {"return": 0, "trace": trace, "camera_flags": camera_flags,
                               "entity_flags": entity_flags}, (name, scenario, rebuilt)
            value = scenario["number"] if camera else scenario["second"]
            cases.append({"function": name, "argc": scenario["argc"],
                          "number_bits": "%08x" % struct.unpack("<I", struct.pack("<f", value))[0],
                          "passed": True})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"scope": "isolated flag writes with mocked callees", "cases": cases}, indent=2) + "\n")
    print("Passed %d sound flag differential cases" % len(cases))


if __name__ == "__main__":
    main()
