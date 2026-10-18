import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_index import (CONSTRUCTOR, REFERENCE_SHA256, decode_initializer,
                          load_reference, load_rows, read_name, validate_evidence)


class NativeIndexTests(unittest.TestCase):
    def test_initializer_uses_signed_rel32_and_actual_addresses(self):
        va = 0x6f58a0
        code = (b"\x55\x8b\xec\x68" + struct.pack("<I", 0x79b760) +
                b"\x68" + struct.pack("<I", 0x59a2b0) + b"\xb9" +
                struct.pack("<I", 0x79b9f8) + b"\xe8" +
                struct.pack("<i", CONSTRUCTOR - va - 23) + b"\x5d\xc3")
        self.assertEqual(decode_initializer(code, va), (0x79b760, 0x59a2b0, 0x79b9f8))
        wrong_callee = code[:19] + struct.pack("<i", CONSTRUCTOR - va - 22) + code[23:]
        self.assertIsNone(decode_initializer(wrong_callee, va))
        self.assertIsNone(decode_initializer(code[:-1], va))
        self.assertIsNone(decode_initializer(code.replace(b"\xb9", b"\xba"), va))

    def test_wrong_binary_rejected_before_pe_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.exe"
            path.write_bytes(b"MZ" + b"\0" * 100)
            with self.assertRaisesRegex(ValueError, "unsupported reference"):
                load_reference(path)

    def test_duplicate_function_address_rejected(self):
        section = SimpleNamespace(VirtualAddress=0x1000, Misc_VirtualSize=100,
                                  Characteristics=0x20000000)
        pe = SimpleNamespace(OPTIONAL_HEADER=SimpleNamespace(ImageBase=0x400000), sections=[section])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "functions.csv"
            path.write_text("address,size\n0x00401000,16\n0x00401000,16\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_rows(path, pe)
            path.write_text("address,size\n0x00401060,16\n")
            with self.assertRaisesRegex(ValueError, "outside sections"):
                load_rows(path, pe)

    def test_unterminated_name_rejected(self):
        section = SimpleNamespace(VirtualAddress=0, Misc_VirtualSize=256, SizeOfRawData=256)
        pe = SimpleNamespace(OPTIONAL_HEADER=SimpleNamespace(ImageBase=0x400000), sections=[section],
                             get_data=lambda rva, size: b"a" * size)
        with self.assertRaisesRegex(ValueError, "unterminated"):
            read_name(pe, 0x400000)

    def test_evidence_is_bound_to_binary_and_canonical_address(self):
        evidence = {"schema_version": 1, "binary_sha256": REFERENCE_SHA256,
                    "functions": {"0x00599390": {"milestones": {"analyzed": True}, "evidence": ["assembly"]}}}
        validate_evidence(evidence, {0x599390})
        other = json.loads(json.dumps(evidence)); other["binary_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_evidence(other, {0x599390})
        with self.assertRaisesRegex(ValueError, "canonical"):
            validate_evidence(evidence, {0x599391})

    def test_verification_milestones_require_evidence_and_boolean_types(self):
        for note in ({"milestones": {"compiled": True}},
                     {"milestones": {"binary_matched": True}, "evidence": ["assembly"]},
                     {"milestones": {"compiled": "yes"}, "evidence": ["test"]},
                     {"milestones": {"complete": True}, "evidence": ["test"]}):
            with self.assertRaises(ValueError):
                validate_evidence({"schema_version": 1, "binary_sha256": REFERENCE_SHA256,
                                   "functions": {"0x00599390": note}}, {0x599390})

    def test_unknown_properties_stay_independent(self):
        validate_evidence({"schema_version": 1, "binary_sha256": REFERENCE_SHA256,
                           "functions": {"0x00599390": {"milestones": {
                               "compiled": True, "binary_matched": None,
                               "behaviorally_verified": False}, "evidence": ["build"]}}}, {0x599390})


if __name__ == "__main__":
    unittest.main()
