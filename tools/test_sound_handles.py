#!/usr/bin/env python3
"""Original/rebuilt x86 dispatch tests for three sound-handle consumers."""
import argparse
from pathlib import Path

from test_sound_camera_bindings import SOUND
from test_sound_triggers import STATE, bits, verify_cases

TARGETS = {"LoadSound_impl": 0x597e90, "IsSoundPlaying_impl": 0x598f90, "GetCueLength_impl": 0x59b320}


def scenarios():
    for name in TARGETS:
        for count in (0, 2):
            yield name, {"argc": count}, {"return": 0, "trace": [["gettop", STATE], ["check", STATE, 1, 1]]}
    for string in (0, 0x34567000):
        for available in (0, 1, 0x100, 0xffffffff):
            for handle in (0, 0x45678000, 0xffffffff):
                trace = [["gettop", STATE], ["check", STATE, 1, 1], ["stringarg", STATE, 1, 0]]
                if string:
                    trace.append(["sound", 0x48, SOUND])
                    if available & 0xff:
                        trace += [["sound", 0x20, SOUND, string], ["rawnumber", STATE, handle]]
                    else:
                        trace.append(["rawnumber", STATE, 0xffffffff])
                yield "LoadSound_impl", {"argc": 1, "string": string, "available": available,
                                         "find_result": handle}, {"return": int(bool(string)), "trace": trace}
    for present in (False, True):
        for playing in (0, 1, 0x100, 0xffffffff):
            for handle in (0, 0x12345000, 0xffffffff):
                trace = [["gettop", STATE], ["check", STATE, 1, 1], ["soundarg", STATE, 1]]
                if present:
                    trace.append(["sound", 0x34, SOUND, handle])
                trace.append(["number", STATE, bits(float(present and bool(playing & 0xff)))])
                yield "IsSoundPlaying_impl", {"argc": 1, "sound_present": present, "playing": playing,
                                               "sound_handle": handle}, {"return": 1, "trace": trace}
    for handle in (0, 0x12345000, 0xffffffff):
        for result in (0, 1, 0xffffffff):
            yield "GetCueLength_impl", {"argc": 1, "sound_handle": handle, "cue_result": result}, {
                "return": 0, "trace": [["gettop", STATE], ["check", STATE, 1, 1],
                                        ["soundarg", STATE, 1], ["sound", 0x40, SOUND, handle]]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-08-behavior.json"))
    args = ap.parse_args()
    verify_cases(args.exe, args.report, TARGETS, scenarios())


if __name__ == "__main__":
    main()
