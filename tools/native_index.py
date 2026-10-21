#!/usr/bin/env python3
"""Generate version-bound metadata without changing upstream's function CSV.

Outputs contain addresses/observations only, except an explicitly requested
targeted disassembly, which must stay in ignored build/ or .local/.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct

import capstone
from capstone.x86 import X86_OP_IMM, X86_OP_MEM
import pefile

from checkbaseline import REFERENCE_SHA1

REFERENCE_SHA256 = "cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3"
ROOT = Path(__file__).resolve().parent.parent
CONSTRUCTOR = 0x005af520
OBSERVATION_VERSION = 1  # Bump if disassembly/xref interpretation changes.


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_reference(path):
    data = path.read_bytes()
    if hashlib.sha1(data).hexdigest() != REFERENCE_SHA1 or digest(data) != REFERENCE_SHA256:
        raise ValueError("unsupported reference: both recorded hashes must match")
    pe = pefile.PE(data=data)
    if pe.FILE_HEADER.Machine != 0x14c or pe.OPTIONAL_HEADER.Magic != 0x10b:
        raise ValueError("expected i386 PE32")
    return data, pe


def section_at(pe, va, size=1):
    rva = va - pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        if s.VirtualAddress <= rva and rva + size <= s.VirtualAddress + s.Misc_VirtualSize:
            return s
    raise ValueError("range outside sections: 0x%x + %d" % (va, size))


def read_va(pe, va, size):
    s = section_at(pe, va, size)
    offset = va - pe.OPTIONAL_HEADER.ImageBase - s.VirtualAddress
    if offset + size > s.SizeOfRawData:
        raise ValueError("range has no complete file backing")
    data = pe.get_data(va - pe.OPTIONAL_HEADER.ImageBase, size)
    if len(data) != size:
        raise ValueError("short binary read")
    return data


def read_name(pe, va):
    s = section_at(pe, va)
    limit = min(256, s.Misc_VirtualSize - (va - pe.OPTIONAL_HEADER.ImageBase - s.VirtualAddress))
    data = read_va(pe, va, limit)
    end = data.find(b"\0")
    if end <= 0:
        raise ValueError("unterminated or empty Lua name")
    name = data[:end].decode("ascii")
    if not all(c.isalnum() or c == "_" for c in name):
        raise ValueError("unexpected Lua name")
    return name


def decode_initializer(code, va):
    """Exact observed 25-byte constructor call; no name-based inference."""
    if (len(code) != 25 or code[:4] != b"\x55\x8b\xec\x68" or
            code[8] != 0x68 or code[13] != 0xb9 or code[18] != 0xe8 or
            code[23:] != b"\x5d\xc3"):
        return None
    target = (va + 23 + struct.unpack_from("<i", code, 19)[0]) & 0xffffffff
    if target != CONSTRUCTOR:
        return None
    return tuple(struct.unpack_from("<I", code, i)[0] for i in (4, 9, 14))


def load_rows(path, pe):
    data = path.read_bytes()
    rows = list(csv.DictReader(data.decode().splitlines()))
    seen = set()
    for row in rows:
        va, size = int(row["address"], 16), int(row["size"])
        if va in seen or size <= 0 or not section_at(pe, va, size).Characteristics & 0x20000000:
            raise ValueError("duplicate or invalid executable function range")
        seen.add(va)
    return data, rows


def extract_registrations(pe, rows):
    by_va = {int(r["address"], 16): r for r in rows}
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    result = []
    for row in rows:
        va = int(row["address"], 16)
        if int(row["size"]) != 25:
            continue
        decoded = decode_initializer(read_va(pe, va, 25), va)
        if decoded is None:
            continue
        string, wrapper, obj = decoded
        name = read_name(pe, string)
        if section_at(pe, obj, 12).Name.rstrip(b"\0") != b".dflua":
            raise ValueError("registration object outside .dflua")
        if wrapper not in by_va or by_va[wrapper]["name"] != name:
            raise ValueError("CSV/registration name or address disagreement: " + name)
        if row["name"] != "dynamic initializer for " + name + "_reg":
            raise ValueError("initializer name disagreement: " + name)
        # Wrapped functions contain one direct call. NOSTACK functions register
        # their implementation itself; no fictitious _impl address is added.
        body_row = by_va[wrapper]
        calls = [i.operands[0].imm & 0xffffffff
                 for i in md.disasm(read_va(pe, wrapper, int(body_row["size"])), wrapper)
                 if i.mnemonic == "call" and i.operands[0].type == X86_OP_IMM]
        impls = [a for a in calls if a in by_va and by_va[a]["name"] == name + "_impl"]
        has_impl = any(r["name"] == name + "_impl" for r in rows)
        if has_impl and (len(calls) != 1 or len(impls) != 1):
            raise ValueError("unexpected wrapper call graph: " + name)
        result.append({"name": name, "initializer_va": va, "name_va": string,
                       "object_va": obj, "registered_va": wrapper,
                       "implementation_va": impls[0] if impls else wrapper,
                       "stack_wrapper": bool(impls), "constructor_va": CONSTRUCTOR})
    if len(result) != 1134 or len({r["name"] for r in result}) != 1134:
        raise ValueError("expected 1134 unique hash-specific registrations")
    if len({r["object_va"] for r in result}) != len(result):
        raise ValueError("duplicate registration objects")
    return result


def binary_metadata(data, pe):
    opt = pe.OPTIONAL_HEADER
    return {"sha1": hashlib.sha1(data).hexdigest(), "sha256": digest(data),
            "size": len(data), "machine": pe.FILE_HEADER.Machine,
            "format": "PE32", "architecture": "i386", "image_base": opt.ImageBase,
            "entry_va": opt.ImageBase + opt.AddressOfEntryPoint,
            "timestamp_untrusted": pe.FILE_HEADER.TimeDateStamp,
            "linker": [opt.MajorLinkerVersion, opt.MinorLinkerVersion],
            "sections": [{"name": s.Name.rstrip(b"\0").decode("ascii"),
                          "rva": s.VirtualAddress, "virtual_size": s.Misc_VirtualSize,
                          "raw_offset": s.PointerToRawData, "raw_size": s.SizeOfRawData,
                          "characteristics": s.Characteristics} for s in pe.sections],
            "imports": [{"dll": d.dll.decode("ascii"), "symbols": [
                {"name": i.name.decode("ascii") if i.name else None,
                 "ordinal": i.ordinal, "iat_va": i.address} for i in d.imports]}
                for d in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])],
            "exports": [{"name": s.name.decode("ascii") if s.name else None,
                         "rva": s.address, "ordinal": s.ordinal}
                        for s in getattr(getattr(pe, "DIRECTORY_ENTRY_EXPORT", None), "symbols", [])],
            "exception_directory": {"rva": opt.DATA_DIRECTORY[3].VirtualAddress,
                                    "size": opt.DATA_DIRECTORY[3].Size}}


def function_records(pe, rows, registrations, evidence, cached_observations=None):
    validate_evidence(evidence, {int(r["address"], 16) for r in rows})
    if evidence.get("binary_sha256") != REFERENCE_SHA256:
        raise ValueError("evidence belongs to another executable")
    notes = evidence.get("functions", {})
    by_va = {int(r["address"], 16): r for r in rows}
    if any(int(a, 16) not in by_va for a in notes):
        raise ValueError("evidence address absent from canonical map")
    linked = {}
    for reg in registrations:
        for field in ("initializer_va", "registered_va", "implementation_va"):
            linked.setdefault(reg[field], []).append(reg)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    records = []
    for row in rows:
        va, size = int(row["address"], 16), int(row["size"])
        cached = (cached_observations or {}).get(va)
        calls, refs = (cached["callees"], cached["xrefs"]) if cached else ([], [])
        for ins in (() if cached else md.disasm(read_va(pe, va, size), va)):
            if ins.mnemonic == "call":
                if ins.operands[0].type == X86_OP_IMM:
                    calls.append({"site_va": ins.address, "target_va": ins.operands[0].imm & 0xffffffff})
                else:
                    calls.append({"site_va": ins.address, "target_va": None,
                                  "operand": ins.op_str})
            for op in ins.operands:
                if op.type == X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                    refs.append({"site_va": ins.address, "target_va": op.mem.disp & 0xffffffff,
                                 "kind": "absolute_memory_operand"})
        note = notes.get("0x%08x" % va, {})
        milestones = {k: None for k in ("analyzed", "reconstructed", "compiled", "behaviorally_verified", "binary_matched")}
        milestones["identified"] = True
        milestones.update(note.get("milestones", {}))
        records.append({"id": REFERENCE_SHA256 + ":%08x" % (va - pe.OPTIONAL_HEADER.ImageBase),
                        "binary_sha256": REFERENCE_SHA256, "va": va,
                        "rva": va - pe.OPTIONAL_HEADER.ImageBase,
                        "end_va_exclusive": va + size, "mapped_size": size,
                        "boundary_method": "upstream CSV discovery; not revalidated CFG",
                        "name": row["name"] or None, "signature": note.get("signature"),
                        "calling_convention": note.get("calling_convention"),
                        "parent": note.get("parent"), "callers": [], "callees": calls,
                        "xrefs": refs, "relevant_strings": sorted({r["name"] for r in linked.get(va, [])}),
                        "lua_registrations": sorted({r["initializer_va"] for r in linked.get(va, [])}),
                        "vtable_relationships": note.get("vtable_relationships", []),
                        "source": note.get("source"), "legacy_object": row["object"] or None,
                        "csv_status": row["status"] or None,
                        "milestones": milestones, "confidence": note.get("confidence", "mapped_boundary_only"),
                        "evidence": ["engine/functions.csv"] + note.get("evidence", []),
                        "verification_method": note.get("verification_method", []),
                        "unresolved": note.get("unresolved", []),
                        "workflow": note.get("workflow", {}),
                        "last_analysis_date": note.get("last_analysis_date")})
    by_start = {r["va"]: r for r in records}
    for row in records:
        for call in row["callees"]:
            if call["target_va"] in by_start:
                by_start[call["target_va"]]["callers"].append({"function_va": row["va"], "site_va": call["site_va"]})
    return records


def validate_evidence(evidence, starts):
    if evidence.get("schema_version") != 1 or evidence.get("binary_sha256") != REFERENCE_SHA256:
        raise ValueError("unsupported evidence version or binary identity")
    allowed = {"identified", "analyzed", "reconstructed", "compiled", "behaviorally_verified", "binary_matched"}
    for address, note in evidence.get("functions", {}).items():
        if address != "0x%08x" % int(address, 16) or int(address, 16) not in starts:
            raise ValueError("evidence address not canonical")
        states = note.get("milestones", {})
        if set(states) - allowed or any(type(v) is not bool and v is not None for v in states.values()):
            raise ValueError("invalid independent milestone flags")
        if any(v is True for v in states.values()) and not note.get("evidence"):
            raise ValueError("verified properties require evidence")
        if states.get("binary_matched") and not note.get("verification_method"):
            raise ValueError("binary match requires an explicit comparison method")
        workflow = note.get("workflow", {})
        if not isinstance(workflow, dict):
            raise ValueError("workflow must be an object")
        for field in ("subsystem", "next_action"):
            if field in workflow and (not isinstance(workflow[field], str) or not workflow[field].strip()):
                raise ValueError("workflow text must be nonempty")
        if "deferred" in workflow and type(workflow["deferred"]) is not bool:
            raise ValueError("workflow deferred must be boolean")
        blockers = workflow.get("blockers", [])
        if not isinstance(blockers, list) or any(not isinstance(x, str) or not x.strip() for x in blockers):
            raise ValueError("workflow blockers must be nonempty strings")
        attempts = workflow.get("attempts", [])
        if not isinstance(attempts, list):
            raise ValueError("workflow attempts must be a list")
        for attempt in attempts:
            if not isinstance(attempt, dict) or any(not isinstance(attempt.get(k), str) or not attempt[k].strip() for k in ("method", "fingerprint", "outcome")):
                raise ValueError("invalid workflow attempt")
            if len(attempt["fingerprint"]) != 64 or any(c not in "0123456789abcdef" for c in attempt["fingerprint"]):
                raise ValueError("invalid workflow fingerprint")
            elapsed = attempt.get("elapsed_seconds")
            if elapsed is not None and (type(elapsed) not in (int, float) or not __import__("math").isfinite(elapsed) or elapsed < 0):
                raise ValueError("invalid workflow elapsed seconds")
        source = note.get("source")
        if source and (Path(source).is_absolute() or ".." in Path(source).parts or not (ROOT / source).is_file()):
            raise ValueError("source must identify an existing repository file")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "build/native-index")
    ap.add_argument("--target", type=lambda s: int(s, 0), action="append", default=[])
    ap.add_argument("--target-only", action="store_true", help="export bounded disassembly without rebuilding the index")
    args = ap.parse_args()
    out = args.out.resolve()
    if not any(out.is_relative_to(ROOT / d) for d in ("build", ".local")):
        ap.error("outputs must stay under ignored build/ or .local/")
    if len(args.target) > 32 or (args.target_only and not args.target):
        ap.error("request 1 to 32 mapped functions for target-only mode")
    data, pe = load_reference(args.exe)
    if args.exe.resolve() in {out / n for n in ("binary.json", "lua-native.json", "functions.json", "manifest.json")}:
        ap.error("output would overwrite the reference")
    csv_data, rows = load_rows(ROOT / "engine/functions.csv", pe)
    evidence_data = (ROOT / "engine/native-evidence.json").read_bytes()
    inputs = {"binary_sha256": digest(data), "csv_sha256": digest(csv_data),
              "range_sha256": digest(json.dumps([(r["address"], r["size"]) for r in rows]).encode()),
              "evidence_sha256": digest(evidence_data), "tool_sha256": digest(Path(__file__).read_bytes()),
              "observation_version": OBSERVATION_VERSION,
              "capstone_version": capstone.__version__, "pefile_version": pefile.__version__}
    manifest_path = out / "manifest.json"
    cached = False
    cached_observations = None
    if manifest_path.is_file() and not args.target_only:
        previous = json.loads(manifest_path.read_text())
        cached = previous.get("inputs") == inputs and all(
            (out / name).is_file() and digest((out / name).read_bytes()) == h
            for name, h in previous.get("outputs", {}).items()) and len(previous.get("outputs", {})) == 3
        previous_inputs = previous.get("inputs", {})
        prior_functions = out / "functions.json"
        if (all(previous_inputs.get(k) == inputs[k] for k in
                ("binary_sha256", "range_sha256", "observation_version", "capstone_version")) and
                prior_functions.is_file() and
                digest(prior_functions.read_bytes()) == previous.get("outputs", {}).get("functions.json")):
            cached_observations = {r["va"]: r for r in json.loads(prior_functions.read_text())}
    if args.target_only:
        out.mkdir(parents=True, exist_ok=True)
    elif cached:
        print("Reused hash-validated native index")
    else:
        regs = extract_registrations(pe, rows)
        functions = function_records(pe, rows, regs, json.loads(evidence_data), cached_observations)
        outputs = {"binary.json": binary_metadata(data, pe), "lua-native.json": regs, "functions.json": functions}
        out.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for name, obj in outputs.items():
            if (out / name).is_symlink():
                ap.error("refusing symlink output")
            payload = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
            (out / name).write_bytes(payload)
            hashes[name] = digest(payload)
        manifest_path.write_text(json.dumps({"schema_version": 1, "inputs": inputs, "outputs": hashes,
                                           "function_count": len(functions), "registration_count": len(regs)}, indent=2) + "\n")
        print("Indexed %d functions and %d Lua registrations" % (len(functions), len(regs)))
    # Bounded request: reuse CSV and binary; never rerun function discovery.
    by_va = {int(r["address"], 16): r for r in rows}
    for va in args.target:
        if va not in by_va or int(by_va[va]["size"]) > 65536:
            ap.error("target must be a mapped start of at most 64 KiB")
        row = by_va[va]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        instructions = [{"va": i.address, "size": i.size, "mnemonic": i.mnemonic, "operands": i.op_str}
                        for i in md.disasm(read_va(pe, va, int(row["size"])), va)]
        target_path = out / ("target-%08x.json" % va)
        if target_path.is_symlink() or target_path.resolve() == args.exe.resolve():
            ap.error("refusing unsafe target output")
        target_path.write_text(json.dumps(
            {"binary_sha256": REFERENCE_SHA256, "function": row, "instructions": instructions}, indent=2) + "\n")


if __name__ == "__main__":
    main()
