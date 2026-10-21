"""Optional coverage never permits skipped or failing required checks."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'contribute/tools'))
from run_tooling_tests import partition, report_path, run_groups


def cases(outcome, module='example', name='ExampleTests'):
    def body(self):
        if outcome == 'skip':self.skipTest('synthetic skip')
        if outcome == 'fail':self.fail('synthetic failure')
    cls = type(name, (unittest.TestCase,), {'test_case':body, '__module__':module})
    return [cls('test_case')]


class ToolingRunnerTests(unittest.TestCase):
    def test_python_only_omits_only_explicit_rust_class(self):
        required = cases('pass');optional = cases('skip', 'test_rust_targets', 'RustTargetTests')
        a,b=partition(unittest.TestSuite([unittest.TestSuite(required),*optional]))
        result=run_groups(a,b,False,io.StringIO())
        self.assertTrue(result['success']);self.assertEqual(result['required']['passed'],1)
        self.assertEqual(result['rust']['status'],'not_requested');self.assertEqual(len(result['rust']['omitted']),1)

    def test_required_skip_and_failure_always_fail(self):
        for outcome in ('skip','fail'):
            self.assertFalse(run_groups(cases(outcome),cases('pass'),False,io.StringIO())['success'])

    def test_requested_rust_skip_or_failure_fails(self):
        for outcome in ('skip','fail'):
            self.assertFalse(run_groups(cases('pass'),cases(outcome),True,io.StringIO())['success'])
        self.assertTrue(run_groups(cases('pass'),cases('pass'),True,io.StringIO())['success'])

    def test_no_required_tests_fails_and_unknown_optional_class_stays_required(self):
        self.assertFalse(run_groups([],cases('pass'),False,io.StringIO())['success'])
        a,b=partition(unittest.TestSuite(cases('skip','test_other_optional','OtherTests')))
        self.assertEqual(len(a),1);self.assertFalse(b)

    def test_report_cannot_overwrite_or_escape_private_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'build').mkdir()
            path=root/'build/report.json';self.assertEqual(report_path(path,root),path)
            path.touch()
            with self.assertRaises(ValueError):report_path(path,root)
            with self.assertRaises(ValueError):report_path(root/'docs/report.json',root)
            (root/'build/alias').symlink_to(root/'build',target_is_directory=True)
            with self.assertRaises(ValueError):report_path(root/'build/alias/report.json',root)
