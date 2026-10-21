"""Synthetic-only smoke checks for the attributed package index reader."""
import importlib.util
import io
from pathlib import Path
import struct
import unittest

SPEC = importlib.util.spec_from_file_location('reference_psypkg', Path(__file__).resolve().parents[1]/'third_party/psypkg.py')
pkg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pkg)


class PackageIndexTests(unittest.TestCase):
    def test_empty_synthetic_index(self):
        header=struct.pack('<4s7I',b'ZPKG',1,512,0,512,0,512,512)
        self.assertEqual(list(pkg.read_index(io.BytesIO(header+bytes(480)))),[])

    def test_wrong_identity_or_version_is_rejected(self):
        for magic,version in ((b'NOPE',1),(b'ZPKG',99)):
            header=struct.pack('<4s7I',magic,version,512,0,512,0,512,512)
            with self.assertRaises(ValueError):list(pkg.read_index(io.BytesIO(header+bytes(480))))
