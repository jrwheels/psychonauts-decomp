"""Guard upstream import-decoration and duplicate-string matching rules."""
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import objmatch


class UpstreamMatcherTests(unittest.TestCase):
    def test_stdcall_import_decoration(self):
        known = objmatch.Known({"__imp__GetLocalTime": 123})
        self.assertIn("__imp__GetLocalTime@4", known)
        self.assertEqual(known["__imp__GetLocalTime@4"], 123)
        self.assertEqual(known.get("__imp__GetLocalTime@4"), 123)
        self.assertNotIn("_GetLocalTime@4", known)

    def test_explicit_decorated_address_takes_precedence(self):
        known = objmatch.Known({"__imp__X": 1, "__imp__X@4": 2})
        self.assertEqual(known["__imp__X@4"], 2)
        self.assertEqual(known.get("__imp__X@4"), 2)

    def test_missing_import_is_not_invented(self):
        known = objmatch.Known()
        self.assertNotIn("__imp__Missing@8", known)
        self.assertIsNone(known.get("__imp__Missing@8"))
        with self.assertRaises(KeyError):
            known["__imp__Missing@8"]

    def string_match(self, target_offset, text):
        base = 0x400000
        image = bytearray(0x200)
        image[0x20:0x25] = b"same\0"
        # Negative pointer fixture deliberately has matching bytes at a Python
        # negative slice's location; that must never count as a valid VA.
        physical = target_offset if target_offset >= 0 else len(image) + target_offset
        image[physical:physical + 5] = text + b"\0"
        code = b"\xb8" + b"\0" * 4 + b"\x90" * 9 + b"\xc3"
        original = bytearray(code)
        struct.pack_into("<I", original, 1, base + target_offset)
        image[0x100:0x100 + len(original)] = original
        exe = SimpleNamespace(base=base, image=bytes(image), text_va=base + 0x100,
                              text=bytes(image[0x100:]), imports={})
        exe.at = lambda va, n: exe.image[va - base:va - base + n]
        fn = SimpleNamespace(name="_literal_user", key="_literal_user", code=code,
            size=len(code), offset=0, section=SimpleNamespace(index=1),
            relocs=lambda: [(1, 4, "STRING", 6)])
        obj = SimpleNamespace(path="fixture.obj", functions=[fn], strings=lambda: {"STRING": b"same"})
        objmatch._find_cache.clear()
        matches, _, _ = objmatch.run(exe, [obj], {"STRING": base + 0x20})
        return matches

    def test_duplicate_identical_string_is_accepted(self):
        self.assertEqual(len(self.string_match(0x40, b"same")), 1)

    def test_different_string_is_rejected(self):
        self.assertEqual(self.string_match(0x40, b"diff"), {})

    def test_string_pointer_below_image_is_rejected(self):
        self.assertEqual(self.string_match(-0x20, b"same"), {})


if __name__ == "__main__":
    unittest.main()
