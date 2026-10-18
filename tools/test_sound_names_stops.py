#!/usr/bin/env python3
"""Differential x86 name lookup, instance stop and native entity-stop tests.

String/audio/Lua helpers are mocked. Native entity stop is tested separately;
the optional composition cases execute the original native entity callee in
both sides, not a fully linked reconstructed engine.
"""
import argparse
from pathlib import Path

from test_sound_camera_bindings import ENTITY, HEAP, SOUND
from test_sound_triggers import STATE, verify_cases

TARGETS = {"GetSoundName_impl": 0x597fc0, "StopSoundsOnEntity_impl": 0x5991d0,
           "StopSoundInstance_impl": 0x5992a0, "EEntity::StopSounds": 0x421520}


def scenarios():
    for name, minimum, maximum in [("GetSoundName_impl", 1, 1),
                                    ("StopSoundsOnEntity_impl", 1, 1),
                                    ("StopSoundInstance_impl", 2, 2)]:
        for count in (0, maximum + 1):
            yield name, {"argc": count, "min": minimum, "max": maximum}, {
                "return": 0, "trace": [["gettop", STATE], ["check", STATE, minimum, maximum]]}
    for handle in (0, 1, 0x80000000, 0xffffffff):
        for present in (False, True):
            for available in (0, 1, 0x100, 0xffffffff):
                for result in (0, HEAP + 0x3100, 0xffffffff):
                    trace = [["gettop", STATE], ["check", STATE, 1, 1], ["soundarg", STATE, 1]]
                    if not handle:
                        trace.append(["diagnostic", 0x7113f8, 0])
                    else:
                        if present:
                            trace.append(["sound", 0x48, SOUND])
                        if present and available & 0xff:
                            trace += [["sound", 0x28, SOUND, handle], ["pushstring", STATE, result or 0x703680]]
                        else:
                            trace.append(["pushstring", STATE, 0x703680])
                    yield "GetSoundName_impl", {"argc": 1, "sound_handle": handle,
                        "sound_present": present, "available": available,
                        "sound_name": result}, {"return": int(bool(handle)), "trace": trace}
    for present in (False, True):
        for entity in (False, True):
            trace = [["gettop", STATE], ["check", STATE, 1, 1], ["entityarg", STATE, 1, 0, 0]]
            if present and entity:
                trace.append(["entitystop", ENTITY])
            yield "StopSoundsOnEntity_impl", {"argc": 1, "sound_present": present,
                                               "entity": entity}, {"return": 0, "trace": trace}
    for present in (False, True):
        for handle in (0, 1, 0xffffffff):
            for instance in (0, 0x80000000, 0xffffffff):
                trace = [["gettop", STATE], ["check", STATE, 2, 2],
                         ["soundarg", STATE, 1], ["rawvalue", STATE, 2]]
                if present:
                    trace.append(["sound", 0x30, SOUND, handle, 0, instance])
                yield "StopSoundInstance_impl", {"argc": 2, "min": 2, "max": 2,
                    "sound_present": present, "sound_handle": handle,
                    "rawvalue": instance}, {"return": 0, "trace": trace}
    for instance in (0, 1, 0x12345000, 0xffffffff):
        trace = [["sound", 0x38, SOUND, instance]] if instance else []
        # No high-level return assertion for a void native method.
        yield "EEntity::StopSounds", {"argc": 0, "instance": instance,
            "real_entity_stop": True, "entry_this": ENTITY}, {"trace": trace}
        yield "StopSoundsOnEntity_impl", {"argc": 1, "instance": instance,
            "real_entity_stop": True}, {"return": 0, "trace": [
                ["gettop", STATE], ["check", STATE, 1, 1], ["entityarg", STATE, 1, 0, 0]] + trace}
    yield "EEntity::StopSounds", {"argc": 0, "instance": 0, "sound_present": False,
        "real_entity_stop": True, "entry_this": ENTITY}, {"trace": []}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--report", type=Path, default=Path("build/batch-09-behavior.json"))
    args = ap.parse_args()
    verify_cases(args.exe, args.report, TARGETS, scenarios())


if __name__ == "__main__":
    main()
