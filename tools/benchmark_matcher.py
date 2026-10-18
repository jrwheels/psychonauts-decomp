#!/usr/bin/env python3
"""Compare matching backends on identical inputs without writing the map.

Timings cover run(), with a cold byte-search cache for each backend. A cached
Python control separates relocation-table reuse from native decoding speed.
Every candidate's decoded targets are also checked outside the timed runs.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from coff import ObjFile
from native_index import load_reference
import objmatch
from rust_targets import RustTargets

ROOT = Path(__file__).resolve().parents[1]


def cached_python(exe, fn, hits):
    relocs, code = fn.relocs(), fn.code
    proxy = SimpleNamespace(code=code, relocs=lambda: relocs)
    return [(va, objmatch.targets(exe, proxy, va)) for va in hits]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("exe", type=Path)
    ap.add_argument("objs", nargs="+", type=Path)
    ap.add_argument("--rust-targets", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args()
    if not any(args.report.resolve().is_relative_to(ROOT / d) for d in ["build", ".local"]):
        ap.error("report must stay under ignored build/ or .local/")
    if args.report.resolve() in {p.resolve() for p in [args.exe, args.rust_targets] + args.objs}:
        ap.error("report must not overwrite an input")
    data, _ = load_reference(args.exe)
    exe = objmatch.Exe(str(args.exe))
    objects = [ObjFile(str(p)) for p in args.objs]
    rust = RustTargets(exe, args.rust_targets)
    runs, expected = {}, None
    for name, backend in [("python", None), ("cached_python", cached_python), ("rust", rust)]:
        objmatch._find_cache.clear()
        gc.collect()
        start = time.perf_counter()
        result, candidates, known = objmatch.run(exe, objects, target_batch=backend)
        elapsed = time.perf_counter() - start
        if expected is None:
            expected = (result, candidates, known)
        else:
            if (result, candidates, known) != expected:
                raise ValueError("Backend changed matching, candidate hits or known symbols: " + name)
        runs[name] = {"seconds": elapsed, "matched_records": len(result)}
        print("%s: %.3f seconds, %d matching records" % (name, elapsed, len(result)), flush=True)
    pairs, words = 0, 0
    for obj in objects:
        for fn in obj.functions:
            hits = objmatch.find(exe, fn)
            actual, want = rust(exe, fn, hits), cached_python(exe, fn, hits)
            if actual != want:
                raise ValueError("Relocation target difference: " + obj.path + ":" + fn.name)
            pairs += len(hits)
            words += sum(len(targets) for _, targets in want)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {"reference_sha256": hashlib.sha256(data).hexdigest(),
        "object_sha256": {str(p): sha(p) for p in args.objs},
        "rust_library_sha256": sha(args.rust_targets),
        "rust_source_sha256": sha(ROOT / "tools/reloc_targets.rs"),
        "python_matcher_sha256": sha(ROOT / "tools/objmatch.py"),
        "python_adapter_sha256": sha(ROOT / "tools/rust_targets.py"),
        "runs": runs, "matching_speedup": runs["python"]["seconds"] / runs["rust"]["seconds"],
        "speedup_over_cached_python": runs["cached_python"]["seconds"] / runs["rust"]["seconds"],
        "candidate_function_address_pairs_checked": pairs, "decoded_symbol_targets_checked": words,
        "all_matches_candidates_known_symbols_equal": True, "all_decoded_targets_equal": True,
        "scope": __doc__}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("Verified %d candidate pairs; matching speedup %.2fx" % (pairs, report["matching_speedup"]))


if __name__ == "__main__":
    main()
