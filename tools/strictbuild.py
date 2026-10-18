#!/usr/bin/env python3
"""Audit the unchanged upstream build, including errors hidden by its pipeline.

Run with Python 3, Wine and winepath on PATH. Reports stay under ignored build/.
The original build.sh replaces generated build/<source-directory>/ outputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from coff import ObjFile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("vc", type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    vc = args.vc.resolve()
    wine = shutil.which("wine")
    if not wine or not shutil.which("winepath"):
        ap.error("wine and winepath must be on PATH")
    if shutil.which("wslpath"):
        ap.error("this Wine audit wrapper does not support WSL")
    if not (vc / "bin/cl.exe").is_file() or not (vc / "include").is_dir():
        ap.error("VC must contain bin/cl.exe and include/")
    banner = subprocess.run([wine, str(vc / "bin/cl.exe")],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace").stdout
    if "Version 15.00.21022.08 for 80x86" not in banner:
        sys.exit("Refusing compiler: expected VC++ 2008 RTM x86\n" + banner)
    expected = sorted(root.glob("src/*/*.c")) + sorted(root.glob("src/*/*.cpp"))
    outputs = [root / "build" / p.parent.name / (p.stem + ".obj") for p in expected]
    if len(set(outputs)) != len(outputs):
        sys.exit("Duplicate source basenames would overwrite objects")
    report_dir = root / "build/audit" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    report_dir.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, AUDIT_WINE=wine, AUDIT_DIR=str(report_dir), WINEDEBUG="-all")
    # Intercept compiler calls only; keep Wine's unfiltered output and exit code.
    # build.sh's pipeline can return success despite this nonzero exit code.
    with tempfile.TemporaryDirectory(prefix="psy-build-audit-") as tmp:
        proxy = Path(tmp) / "wine"
        proxy.write_text("#!" + sys.executable + "\n" + '''
import json, os, pathlib, subprocess, sys, time
p = subprocess.run([os.environ["AUDIT_WINE"]] + sys.argv[1:],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
d = pathlib.Path(os.environ["AUDIT_DIR"])
key = str(time.time_ns())
(d / (key + ".log")).write_bytes(p.stdout)
(d / (key + ".json")).write_text(json.dumps({"args": sys.argv[1:], "returncode": p.returncode}))
sys.stdout.buffer.write(p.stdout)
sys.exit(p.returncode)
''')
        proxy.chmod(0o755)
        env["PATH"] = tmp + os.pathsep + env["PATH"]
        started = time.time_ns()
        result = subprocess.run(["sh", str(root / "tools/build.sh"), str(vc)],
                                cwd=root, env=env)
    calls = [json.loads(p.read_text()) for p in report_dir.glob("*.json")]
    failures = []
    groups = {p.parent.name for p in expected}
    if result.returncode:
        failures.append("build.sh exit %d" % result.returncode)
    if len(calls) != len(groups):
        failures.append("expected %d compiler calls; saw %d" % (len(groups), len(calls)))
    if any(c["returncode"] != 0 for c in calls):
        failures.append("compiler failed; inspect unfiltered logs")
    objects = []
    for path in outputs:
        try:
            if path.stat().st_mtime_ns < started:
                raise ValueError("stale object")
            obj = ObjFile(str(path))
            if not obj.functions:
                raise ValueError("object contains no functions")
            objects.append({"path": str(path.relative_to(root)),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "functions": len(obj.functions)})
        except (OSError, ValueError, IndexError) as exc:
            failures.append("%s: %s" % (path.relative_to(root), exc))
    report = {"compiler": "15.00.21022.08 x86", "compiler_banner": banner,
              "compiler_sha256": hashlib.sha256((vc / "bin/cl.exe").read_bytes()).hexdigest(),
              "build_script_sha256": hashlib.sha256((root / "tools/build.sh").read_bytes()).hexdigest(),
              "expected_objects": len(outputs),
              "objects": objects, "failures": failures, "success": not failures}
    (report_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Audit:", report_dir / "summary.json")
    for failure in failures:
        print(failure, file=sys.stderr)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
