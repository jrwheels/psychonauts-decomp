"""Fail-closed guards for the native verification ladder."""
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'contribute/tools'))
from native_verify import (compare_target, compiler_flags, dev_test_view, digest,
                           parse_target, private_path, reviewed_plan, source_path,
                           validate_suites, validate_case_report, input_hashes, REFERENCE_SHA256)


def function(code, relocations=()):
    return SimpleNamespace(code=code, name='example', relocs=lambda: relocations)


def executable(code, imports=None):
    return SimpleNamespace(at=lambda address, size: code[:size], imports=imports or {})


class VerifyTests(unittest.TestCase):
    def test_compatible_bytes_never_prove_unique_match(self):
        result = compare_target(executable(b'\xc3\xcc'), function(b'\xc3\xcc'), 0x401000, 1)
        self.assertTrue(result['candidate_compatible'])
        self.assertFalse(result['establishes_unique_match'])
        changed = compare_target(executable(b'\x90\xcc'), function(b'\xc3\xcc'), 0x401000, 1)
        self.assertFalse(changed['candidate_compatible'])
        extent = compare_target(executable(b'\xc3\x90'), function(b'\xc3\x90'), 0x401000, 1)
        self.assertFalse(extent['candidate_compatible'])

    def test_relocation_conflicts_and_unsupported_kinds_reject_candidate(self):
        code = struct.pack('<I', 0x12345678)
        fn = function(b'\0'*4, [(0, 4, 'callee', 6)])
        result = compare_target(executable(code, {'callee':0x87654321}), fn, 0x401000, 4)
        self.assertFalse(result['candidate_compatible'])
        self.assertIn('callee', result['conflicting_symbols'])
        unknown = compare_target(executable(code), fn, 0x401000, 4)
        self.assertEqual(unknown['unresolved_symbols'], ['callee'])
        bad = function(b'\0'*4, [(0,4,'callee',7)])
        self.assertFalse(compare_target(executable(code),bad,0x401000,4)['candidate_compatible'])
        short = function(b'\0'*4, [(3,4,'callee',6)])
        with self.assertRaises(ValueError):compare_target(executable(code),short,0x401000,4)

    def test_output_and_source_paths_reject_escape_and_symlink_aliases(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'build').mkdir();(root/'docs').mkdir();(root/'src/game').mkdir(parents=True)
            (root/'src/game/a.cpp').write_text('')
            self.assertEqual(source_path('src/game/a.cpp',root),root/'src/game/a.cpp')
            with self.assertRaises(ValueError):source_path('../../a.cpp',root)
            with self.assertRaises(ValueError):private_path(root/'docs/result.json',root)
            (root/'build/alias').symlink_to(root/'build',target_is_directory=True)
            with self.assertRaises(ValueError):private_path(root/'build/alias/result.json',root)
            with self.assertRaises(ValueError):private_path(root/'build/../docs/result.json',root)

    def test_flags_must_equal_pinned_upstream_flags(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tools').mkdir()
            p=root/'tools/build.sh';p.write_text('CFLAGS="/nologo /c /Od /Oy /Ob1 /Oi /MD /GS-"\n')
            self.assertIn('/Oy',compiler_flags(root))
            p.write_text('CFLAGS="/nologo /c /O2 /Oy /Ob1 /Oi /MD /GS-"\n')
            with self.assertRaisesRegex(ValueError,'flags changed'):compiler_flags(root)

    def test_development_suites_use_overrides_without_mutating_canonical_objects(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'build/game').mkdir(parents=True);(root/'tools').mkdir()
            (root/'tools/test_example.py').write_text('# fixture')
            (root/'engine').mkdir()
            (root/'engine/functions.csv').write_text('address,name')
            original=root/'build/game/a.obj';original.write_bytes(b'old')
            (root/'build/game/b.obj').write_bytes(b'unchanged')
            out=root/'build/dev';(out/'objects/game').mkdir(parents=True)
            candidate=out/'objects/game/a.obj';candidate.write_bytes(b'new')
            view=dev_test_view(out,[candidate],root)
            self.assertEqual((view/'build/game/a.obj').read_bytes(),b'new')
            self.assertEqual((view/'build/game/b.obj').read_bytes(),b'unchanged')
            self.assertEqual(original.read_bytes(),b'old')
            self.assertEqual((view/'engine/functions.csv').read_text(),'address,name')

    def test_batch_needs_review_and_rejects_changed_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for sub in ('build','engine','src/game'):(root/sub).mkdir(parents=True,exist_ok=True)
            for name in ('functions.csv','native-evidence.json'):(root/'engine'/name).write_text('{}')
            src=root/'src/game/a.cpp';src.write_text('before')
            plan=dict(binary_sha256=REFERENCE_SHA256,csv_sha256=digest(root/'engine/functions.csv'),
                evidence_sha256=digest(root/'engine/native-evidence.json'),source_sha256={'src/game/a.cpp':digest(src)},
                batches=[dict(status='review_required',targets=[dict(address='0x00401000',symbol='Example',source='src/game/a.cpp',suites=['test_example'])])])
            path=root/'build/plan.json';path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'reviewed'):reviewed_plan(path,0,root)
            plan['batches'][0]['status']='reviewed';path.write_text(json.dumps(plan))
            self.assertEqual(reviewed_plan(path,0,root)[0],['0x00401000=Example'])
            src.write_text('after')
            with self.assertRaisesRegex(ValueError,'sources changed'):reviewed_plan(path,0,root)

    def test_targets_and_suite_names_do_not_accept_shell_commands(self):
        self.assertEqual(parse_target('0x00401000=Example::Method'),(0x401000,'Example::Method'))
        with self.assertRaises(ValueError):parse_target('0x00401000')
        with self.assertRaises(ValueError):parse_target('-1=Example')
        with self.assertRaises(ValueError):validate_suites(['test_x;echo_secret'])

    def test_legacy_reports_still_require_wrapper_hash_gate(self):
        report={'cases':[{'passed':True}]}
        self.assertTrue(validate_case_report(report,'test_sound_mute',REFERENCE_SHA256))
        with self.assertRaises(ValueError):validate_case_report(report,'test_new',REFERENCE_SHA256)
        with self.assertRaises(ValueError):validate_case_report(report,'test_sound_mute','0'*64)
        with self.assertRaises(ValueError):validate_case_report(dict(report,binary_sha256='0'*64),'test_sound_mute',REFERENCE_SHA256)
        with self.assertRaises(ValueError):validate_case_report({'cases':[]},'test_sound_mute',REFERENCE_SHA256)

    def test_verification_fingerprint_covers_vendor_code_and_dependency_manifests(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'engine').mkdir();(root/'third_party').mkdir()
            for name in ('functions.csv','native-evidence.json'):(root/'engine'/name).write_text('{}')
            vendor=root/'third_party/reader.py';vendor.write_text('original')
            requirements=root/'requirements-reference.txt';requirements.write_text('package==1')
            (root/'contribute/tools').mkdir(parents=True)
            helper=root/'contribute/tools/helper.py';helper.write_text('original')
            contributor_requirements=root/'contribute/requirements-dev.txt'
            contributor_requirements.write_text('package==1')
            before=input_hashes(root)
            vendor.write_text('changed');requirements.write_text('package==2')
            helper.write_text('changed');contributor_requirements.write_text('package==2')
            after=input_hashes(root)
            self.assertNotEqual(before['third_party/reader.py'],after['third_party/reader.py'])
            self.assertNotEqual(before['requirements-reference.txt'],after['requirements-reference.txt'])
            self.assertNotEqual(before['contribute/tools/helper.py'],after['contribute/tools/helper.py'])
            self.assertNotEqual(before['contribute/requirements-dev.txt'],after['contribute/requirements-dev.txt'])
