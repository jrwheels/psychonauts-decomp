#!/usr/bin/env python3
"""Read-only reference check and regression report using upstream objmatch.

Never writes engine/functions.csv. Reports contain metadata, not game bytes.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

from coff import ObjFile
from objmatch import Exe, run, demangle

REFERENCE_SHA1 = "21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("functions", type=Path)
    ap.add_argument("objs", nargs="+", type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args()
    protected = [args.exe, args.functions] + args.objs
    if args.report.resolve() in {p.resolve() for p in protected}:
        ap.error("report path must not overwrite the reference, CSV or objects")
    data = args.exe.read_bytes()
    sha1 = hashlib.sha1(data).hexdigest()
    if sha1 != REFERENCE_SHA1:
        sys.exit("Unsupported reference SHA-1: " + sha1)
    csv_bytes = args.functions.read_bytes()
    rows = list(csv.DictReader(csv_bytes.decode().splitlines()))
    results, candidates, known = run(Exe(str(args.exe)), [ObjFile(str(p)) for p in args.objs])
    matched = set(results.values())
    recorded = {int(r["address"], 16) for r in rows if r["status"] == "matching"}
    by_va = {int(r["address"], 16): r for r in rows}
    regressions = sorted(recorded - matched)
    new = sorted((matched & by_va.keys()) - recorded)
    report = {"reference_sha1": sha1, "reference_sha256": hashlib.sha256(data).hexdigest(),
              "functions_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
              "object_functions": len(candidates), "matched_object_functions": len(results),
              "total_engine_functions": len(rows), "matched_engine_functions": len(matched & by_va.keys()),
              "total_engine_bytes": sum(int(r["size"]) for r in rows),
              "matched_engine_bytes": sum(int(by_va[a]["size"]) for a in matched & by_va.keys()),
              "new_addresses": ["0x%08x" % a for a in new],
              "regressions": ["0x%08x" % a for a in regressions],
              "matches": [{"address": "0x%08x" % a, "symbol": demangle(name),
                           "object": str(Path(path).name)} for (path, name), a in sorted(results.items())],
              "unmatched_symbols": [name for key in sorted(candidates) for path, name in [key] if key not in results]}
    if args.functions.read_bytes() != csv_bytes:
        sys.exit("Function database changed during read-only comparison")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("Engine matches:", report["matched_engine_functions"], "/", len(rows))
    print("Code bytes:", report["matched_engine_bytes"], "/", report["total_engine_bytes"])
    print("New:", len(new), "Regressions:", len(regressions))
    return bool(regressions)


if __name__ == "__main__":
    sys.exit(main())
