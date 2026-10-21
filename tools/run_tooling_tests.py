#!/usr/bin/env python3
"""Run synthetic tooling tests; report required Python and optional Rust separately."""
import argparse
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def partition(suite):
    required, rust = [], []
    for test in flatten(suite):
        # Only this explicit optional class may be omitted. New skips elsewhere fail.
        optional = (type(test).__module__ == 'test_rust_targets' and
                    type(test).__name__ == 'RustTargetTests')
        (rust if optional else required).append(test)
    return required, rust


def run_group(tests, stream):
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite(tests))
    skipped = [test.id() for test, _ in result.skipped]
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(skipped) - len(result.expectedFailures) - len(result.unexpectedSuccesses)
    success = (bool(tests) and result.wasSuccessful() and not skipped and
               not result.expectedFailures and not result.unexpectedSuccesses)
    return dict(run=result.testsRun, passed=passed, skipped=skipped,
                failures=[test.id() for test, _ in result.failures],
                errors=[test.id() for test, _ in result.errors],
                expected_failures=[test.id() for test, _ in result.expectedFailures],
                unexpected_successes=[test.id() for test in result.unexpectedSuccesses],
                success=success)


def run_groups(required, rust, rust_requested, stream):
    primary = run_group(required, stream)
    optional = (dict(run_group(rust, stream), requested=True, status='executed') if rust_requested else
                dict(requested=False, status='not_requested', run=0, passed=0,
                     omitted=[test.id() for test in rust]))
    return dict(schema_version=1, success=primary['success'] and
                (optional.get('success', False) if rust_requested else True),
                required=primary, rust=optional)


def report_path(path, root=ROOT):
    path = Path(path).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)) or
            not any(path.resolve().is_relative_to(root/d) for d in ('build', '.local'))):
        raise ValueError('report must stay under ignored build/ or .local/')
    if path.exists():
        raise ValueError('report must be new; preserve previous results')
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rust-targets', type=Path, help='trusted locally built library; all Rust tests required')
    ap.add_argument('--report', type=Path, help='new JSON under build/ or .local/')
    args = ap.parse_args()
    output = report_path(args.report) if args.report else None
    if args.rust_targets:
        library = args.rust_targets.resolve()
        if not library.is_file():
            ap.error('explicit Rust library does not exist')
        os.environ['PSY_RUST_TARGETS'] = str(library)
    else:
        # Ambient configuration or an existing library never enables optional coverage.
        os.environ.pop('PSY_RUST_TARGETS', None)
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    required, rust = partition(suite)
    result = run_groups(required, rust, bool(args.rust_targets), sys.stderr)
    if args.rust_targets:
        import hashlib
        result['rust']['library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
