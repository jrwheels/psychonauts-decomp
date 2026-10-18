"""Exercise failure modes that upstream build.sh can silently swallow."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildAuditTests(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("tools", "src/game", "VC/bin", "VC/include", "bin"):
                (root / name).mkdir(parents=True)
            for name in ("strictbuild.py", "coff.py", "build.sh"):
                shutil.copyfile(ROOT / "tools" / name, root / "tools" / name)
            (root / "VC/bin/cl.exe").touch()
            (root / "src/game/fixture.cpp").write_text("int fixture() { return 1; }\n")
            wine = root / "bin/wine"
            wine.write_text("#!" + sys.executable + "\n" + '''
import os, sys
if len(sys.argv) == 2:
    print("Version " + ("15.00.30729.01" if os.environ["TEST_MODE"] == "sp1" else "15.00.21022.08") + " for 80x86")
    sys.exit(2)
if os.environ["TEST_MODE"] == "failure":
    print("fatal error C9999: synthetic compiler failure")
    sys.exit(7)
sys.exit(0)
''')
            wine.chmod(0o755)
            winepath = root / "bin/winepath"
            winepath.write_text('#!/bin/sh\nprintf "%s\\n" "$2"\n')
            winepath.chmod(0o755)
            env = dict(os.environ, PATH=str(root / "bin") + ":/usr/bin:/bin", TEST_MODE=mode)
            proc = subprocess.run([sys.executable, str(root / "tools/strictbuild.py"), str(root / "VC")],
                                  env=env, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            return proc.stdout + proc.stderr

    def test_hidden_compiler_failure(self):
        self.assertIn("compiler failed", self.exercise("failure"))

    def test_success_exit_without_object(self):
        self.assertIn("fixture.obj", self.exercise("no_object"))

    def test_sp1_rejected(self):
        self.assertIn("Refusing compiler", self.exercise("sp1"))

    def test_wrong_reference_rejected_before_object_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "wrong.exe"
            exe.write_bytes(b"not the reference executable")
            csv = ROOT / "engine/functions.csv"
            before = csv.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / "tools/checkbaseline.py"),
                                     str(exe), str(csv), "nonexistent.obj", "--report",
                                     str(Path(tmp) / "report.json")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unsupported reference SHA-1", result.stderr)
            self.assertEqual(csv.read_bytes(), before)
            self.assertFalse((Path(tmp) / "report.json").exists())

    def test_report_cannot_overwrite_csv(self):
        csv = ROOT / "engine/functions.csv"
        before = csv.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "tools/checkbaseline.py"),
                                 "missing.exe", str(csv), "missing.obj", "--report", str(csv)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not overwrite", result.stderr)
        self.assertEqual(csv.read_bytes(), before)

    def test_report_cannot_overwrite_rust_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Path(tmp) / "decoder.so"
            library.write_bytes(b"preserve")
            result = subprocess.run([sys.executable, str(ROOT / "tools/checkbaseline.py"),
                "missing.exe", str(ROOT / "engine/functions.csv"), "missing.obj",
                "--rust-targets", str(library), "--report", str(library)],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not overwrite", result.stderr)
            self.assertEqual(library.read_bytes(), b"preserve")

    def test_wrong_reference_rejected_before_rust_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "wrong.exe"
            exe.write_bytes(b"wrong reference")
            result = subprocess.run([sys.executable, str(ROOT / "tools/checkbaseline.py"),
                str(exe), str(ROOT / "engine/functions.csv"), "missing.obj",
                "--rust-targets", "missing.so", "--report", str(Path(tmp) / "report.json")],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unsupported reference SHA-1", result.stderr)
            self.assertNotIn("cannot open shared object", result.stderr)


if __name__ == "__main__":
    unittest.main()
