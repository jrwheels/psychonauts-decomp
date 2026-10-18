"""Optional Rust decoder must agree with the unchanged Python target oracle."""
import ctypes
import os
from pathlib import Path
import random
import struct
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import objmatch
from rust_targets import RustTargets

LIBRARY = Path(os.environ.get("PSY_RUST_TARGETS", ROOT / "build/rust/reloc_targets.so"))


@unittest.skipUnless(LIBRARY.is_file(), "optional Rust relocation library not built")
class RustTargetTests(unittest.TestCase):
    def fixture(self, text, code, relocs, base=0x400000):
        exe = SimpleNamespace(text=text, text_va=base)
        exe.at = lambda va, size: text[va-base:va-base+size]
        fn = SimpleNamespace(code=code, relocs=lambda: relocs)
        return exe, fn, RustTargets(exe, LIBRARY)

    def compare(self, text, code, relocs, hits, base=0x400000):
        exe, fn, batch = self.fixture(text, code, relocs, base)
        self.assertEqual(batch(exe, fn, hits),
                         [(va, objmatch.targets(exe, fn, va)) for va in hits])

    def test_signed_addends_and_address_wrap(self):
        for kind in [6, 0x14]:
            for addend in [0, 1, 0x7fffffff, 0x80000000, 0xffffffff]:
                for value in [0, 1, 0x80000000, 0xffffffff]:
                    self.compare(struct.pack("<I", value), struct.pack("<I", addend),
                        [(0, 4, "target", kind)], [0xfffffff0], 0xfffffff0)

    def test_repeated_symbols_keep_last_valid_value(self):
        self.compare(struct.pack("<3I", 1, 2, 3), b"\0"*12,
            [(0, 4, "same", 6), (4, 4, "same", 0x14), (8, 4, "other", 6),
             (11, 4, "same", 6)], [0x400000])

    def test_truncated_raw_words_and_short_addends(self):
        for text_length in range(9):
            for code_length in range(9):
                self.compare(bytes(range(text_length)), b"\xff"*code_length,
                    [(off, 4, "r%d" % off, 6) for off in range(8)],
                    [0x400000, 0x400002, 0x400010])

    def test_unknown_kinds_and_static_symbol_keys(self):
        self.compare(b"\xff"*16, b"\0"*16,
            [(0, 2, "unknown", 7), (4, 4, ("fixture.obj", "static"), 6),
             (8, 4, "relative", 0x14)], [0x400000, 0x400004])

    def test_empty_batches_and_tables(self):
        self.compare(b"", b"", [], [])
        self.compare(b"1234", b"", [], [0x400000])
        self.compare(b"1234", b"1234", [(0, 4, "x", 6)], [])

    def test_below_text_address_preserves_python_oracle(self):
        self.compare(b"abcdefgh12345678", b"\0"*4, [(0, 4, "x", 6)],
                     [0x3ffff8, 0x400000])

    def test_rejects_another_executable(self):
        exe, fn, batch = self.fixture(b"1234", b"\0"*4, [(0, 4, "x", 6)])
        with self.assertRaises(ValueError):
            batch(SimpleNamespace(text=exe.text, text_va=exe.text_va), fn, [exe.text_va])

    def test_ffi_rejects_invalid_buffers_and_overflow(self):
        exe, fn, batch = self.fixture(b"", b"", [])
        self.assertEqual(batch.decode(None, 0, 0, None, 0, None, None, None, 0,
                                      None, None, 0), 0)
        self.assertEqual(batch.decode(None, 4, 0, None, 1, None, None, None, 1,
                                      None, None, 1), 1)
        maximum = ctypes.c_size_t(-1).value
        self.assertEqual(batch.decode(None, 0, 0, None, maximum, None, None, None, 2,
                                      None, None, 0), 1)

    def test_fixed_seed_differential_batches(self):
        rng = random.Random(0x6a8180)
        for _ in range(250):
            text = rng.randbytes(rng.randrange(0, 128))
            code = rng.randbytes(rng.randrange(0, 64))
            relocs = [(rng.randrange(0, 64), 4, "s%d" % rng.randrange(8),
                       rng.choice([6, 0x14, 7, 10])) for _ in range(rng.randrange(20))]
            hits = [0x400000+rng.randrange(160) for _ in range(rng.randrange(30))]
            self.compare(text, code, relocs, hits)


if __name__ == "__main__":
    unittest.main()
