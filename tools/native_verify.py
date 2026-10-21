#!/usr/bin/env python3
"""Native verification ladder. Development results never promote the CSV.

Full mode reuses strictbuild/checkbaseline and every committed differential
suite. It emits a review proposal, never edits matching metadata or Git refs.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

from coff import ObjFile
from native_index import ROOT, REFERENCE_SHA256, load_reference
from objmatch import Exe, demangle, targets

FLAGS = ('/Od', '/Oy', '/Ob1', '/Oi', '/MD', '/GS-')
LEGACY_REPORTS = frozenset(('test_sound_categories', 'test_sound_controls', 'test_sound_flags',
    'test_sound_levels', 'test_sound_mute', 'test_sound_camera_bindings'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_path(path, root=ROOT):
    path = Path(path)
    if not path.is_absolute():
        path = root/path
    if (any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root) and p != root) or
            not any(path.resolve().is_relative_to(root/d) for d in ('build', '.local'))):
        raise ValueError('output must stay under ignored build/ or .local/')
    return path.resolve()


def save(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def source_path(value, root=ROOT):
    path = (root/value).resolve()
    if (not path.is_relative_to(root/'src') or path.suffix not in ('.c', '.cpp') or
            not path.is_file() or len(path.relative_to(root).parts) != 3):
        raise ValueError('source must be an existing src/<group> C/C++ file')
    return path


def compiler_flags(root=ROOT):
    text = (root/'tools/build.sh').read_text()
    match = re.search(r'^CFLAGS="([^"]+)"$', text, re.M)
    if not match or tuple(shlex.split(match[1])) != ('/nologo', '/c', *FLAGS):
        raise ValueError('build flags changed; review before using this workflow')
    return ('/nologo', '/c', *FLAGS)


def input_hashes(root=ROOT):
    paths = [root/'engine/functions.csv', root/'engine/native-evidence.json']
    paths += [p for directory in ('src', 'tools', 'tests', 'third_party') for p in (root/directory).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py', '.rs', '.sh', '.h', '.cpp', '.c')]
    paths += list(root.glob('requirements*.txt'))
    return {str(p.relative_to(root)): digest(p) for p in sorted(set(paths))}


def parse_target(value):
    address, sep, symbol = value.partition('=')
    va = int(address, 0)
    if not sep or not symbol or not 0 <= va <= 0xffffffff:
        raise ValueError('target must be 0xADDRESS=Demangled::Name')
    return va, symbol


def compare_target(exe, function, va, mapped_size, known=None):
    # Raw-byte compatibility is not a globally unique relocation-aware match.
    # All original relocation fields are decoded and surfaced for review.
    code = function.code
    original = exe.at(va, len(code))
    if len(original) != len(code):
        raise ValueError('target extends outside the reference image')
    mask = set()
    unsupported = []
    for offset, size, symbol, kind in function.relocs():
        if offset < 0 or offset+size > len(code):
            raise ValueError('relocation extends outside function')
        mask.update(range(offset, offset+size))
        if kind not in (6, 0x14):
            unsupported.append(dict(offset=offset, kind=kind, symbol=symbol))
    differences = [i for i, (a, b) in enumerate(zip(code, original)) if i not in mask and a != b]
    relocations = targets(exe, function, va)
    knowledge = dict(exe.imports)
    knowledge.update(known or {})
    conflicts = {name: dict(expected=knowledge[name], observed=value)
                 for name, value in relocations.items() if name in knowledge and knowledge[name] != value}
    unresolved = sorted(name for name in relocations if name not in knowledge)
    # COFF may include int3 alignment after the canonical function extent.
    extent_ok = len(code) >= mapped_size and all(x == 0xcc for x in code[mapped_size:])
    return dict(address='0x%08x'%va, symbol=demangle(function.name),
                mapped_bytes=mapped_size, object_bytes=len(code), extent_compatible=extent_ok,
                differing_byte_offsets=differences, relocations=relocations,
                unresolved_symbols=unresolved, relocations_fully_resolved=not unresolved, conflicting_symbols=conflicts,
                unsupported_relocations=unsupported,
                candidate_compatible=extent_ok and not differences and not conflicts and not unsupported,
                establishes_unique_match=False)


def run_command(args, log, cwd, metrics, phase, env=None):
    started = time.monotonic()
    with log.open('w') as stream:
        result = subprocess.run([str(x) for x in args], cwd=cwd, env=env,
                                stdout=stream, stderr=subprocess.STDOUT)
    metrics[phase] = metrics.get(phase, 0) + time.monotonic()-started
    if result.returncode:
        raise RuntimeError('%s failed (%d); see %s' % (phase, result.returncode, log.name))
    return log.read_text(errors='replace')


def compile_sources(vc, sources, out, metrics):
    wine, winepath = shutil.which('wine'), shutil.which('winepath')
    if not wine or not winepath:
        raise ValueError('wine and winepath must be on PATH')
    compiler = vc/'bin/cl.exe'
    banner = subprocess.run([wine, str(compiler)], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True).stdout
    if 'Version 15.00.21022.08 for 80x86' not in banner:
        raise ValueError('expected VC++2008 RTM x86 compiler')
    include = subprocess.check_output([winepath, '-w', str(vc/'include')],
                                     stderr=subprocess.DEVNULL, text=True).strip()
    flags = compiler_flags()
    objects = []
    for source in sources:
        directory = out/'objects'/source.parent.name
        directory.mkdir(parents=True, exist_ok=True)
        obj = directory/(source.stem+'.obj')
        if obj.exists():
            raise ValueError('development output already exists; use a fresh --out directory')
        started = time.time_ns()
        run_command([wine, compiler, *flags, '/I'+include, '/Fo'+obj.name,
                     os.path.relpath(source, directory)], out/(source.stem+'-compile.log'),
                    directory, metrics, 'compile_seconds')
        if obj.stat().st_mtime_ns < started or not ObjFile(str(obj)).functions:
            raise ValueError('missing, stale or invalid development object')
        objects.append(obj)
    return objects, dict(version='15.00.21022.08 x86', sha256=digest(compiler), flags=list(FLAGS))


def validate_suites(names, root=ROOT):
    suites = []
    for name in names:
        if not re.fullmatch(r'test_[a-z0-9_]+', name) or not (root/'tools'/(name+'.py')).is_file():
            raise ValueError('suite must name a committed tools/test_*.py script')
        suites.append(name)
    return sorted(set(suites))


def dev_test_view(out, objects, root=ROOT):
    # Existing harnesses resolve objects relative to their own tools directory.
    # Copy scripts into an ignored view so they execute the just-built objects,
    # without replacing the canonical build or modifying any existing harness.
    view = out/'test-view'
    (view/'tools').mkdir(parents=True)
    for script in (root/'tools').glob('*.py'):
        shutil.copy2(script, view/'tools'/script.name)
    overridden = {str(p.relative_to(out/'objects')): p for p in objects}
    existing = {str(p.relative_to(root/'build')): p for p in (root/'build').glob('*/*.obj')}
    existing.update(overridden)
    for name, source in existing.items():
        dest = view/'build'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    (view/'engine').mkdir()
    for metadata in (root/'engine').glob('*'):
        if metadata.is_file() and metadata.suffix in ('.csv', '.json'):
            shutil.copy2(metadata, view/'engine'/metadata.name)
    (view/'build/results').mkdir(parents=True)
    return view


def validate_case_report(result, name, reference_hash):
    if reference_hash != REFERENCE_SHA256:
        raise ValueError('reference changed during suite')
    bound = result.get('binary_sha256')
    if bound != REFERENCE_SHA256 and not (bound is None and name in LEGACY_REPORTS):
        raise ValueError('suite report binary identity missing or wrong: '+name)
    cases = result.get('cases')
    if not isinstance(cases, list) or not cases or any(x.get('passed') is not True for x in cases):
        raise ValueError('suite cases missing or failed: '+name)
    return bound is None


def reviewed_plan(path, batch_index, root=ROOT):
    plan = json.loads(private_path(path, root).read_text())
    if (plan.get('binary_sha256') != REFERENCE_SHA256 or
            plan.get('csv_sha256') != digest(root/'engine/functions.csv') or
            plan.get('evidence_sha256') != digest(root/'engine/native-evidence.json')):
        raise ValueError('stale or unsupported batch plan inputs')
    current = {str(p.relative_to(root)): digest(p) for p in sorted((root/'src').rglob('*')) if p.is_file()}
    if plan.get('source_sha256') != current:
        raise ValueError('batch plan sources changed')
    batch = plan['batches'][batch_index]
    if batch.get('status') != 'reviewed':
        raise ValueError('batch plan needs reviewed status and explicit symbols/sources/suites')
    targets, sources, suites = [], [], []
    for target in batch['targets']:
        if not target.get('symbol') or not target.get('source') or not target.get('suites'):
            raise ValueError('each reviewed target needs symbol, source and affected suites')
        targets.append(str(target['address'])+'='+target['symbol'])
        sources.append(target['source'])
        suites.extend(target['suites'])
    if not 1 <= len(targets) <= 15:
        raise ValueError('reviewed batch must contain1to15targets')
    return targets, sorted(set(sources)), sorted(set(suites))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('dev', 'full'))
    ap.add_argument('exe', type=Path)
    ap.add_argument('vc', type=Path)
    ap.add_argument('--source', action='append', default=[])
    ap.add_argument('--target', action='append', default=[])
    ap.add_argument('--suite', action='append', default=[])
    ap.add_argument('--rust-targets', type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--plan', type=Path)
    ap.add_argument('--batch', type=int, default=0)
    args = ap.parse_args()
    started = time.monotonic()
    out = private_path(args.out)
    if out.exists():
        ap.error('--out must be a new ignored directory, preserving earlier reports')
    load_reference(args.exe)  # Both reference hashes, before compiler execution.
    compiler_flags()
    if args.plan:
        if args.source or args.target or args.suite:
            ap.error('use a reviewed plan or explicit target/source/suite arguments, not both')
        args.target, args.source, args.suite = reviewed_plan(args.plan, args.batch)
        if args.mode == 'full':
            args.suite = []  # Full mode runs all suites, including plan requirements.
    selected = [parse_target(x) for x in args.target]
    if len(selected) != len({a for a, _ in selected}) or len(selected) > 15:
        ap.error('select at most15distinct targets')
    sources = [source_path(x) for x in args.source]
    if len(sources) != len(set(sources)):
        ap.error('duplicate source path')
    if args.mode == 'dev' and (not sources or not selected):
        ap.error('dev needs explicit sources and address=symbol targets')
    suites = validate_suites(args.suite)
    if args.mode == 'full' and suites:
        ap.error('full mode always runs every suite; use dev for selected tests')
    before = input_hashes()
    rows = {int(r['address'], 16): r for r in csv.DictReader((ROOT/'engine/functions.csv').open())}
    if any(a not in rows for a, _ in selected):
        ap.error('target must be a canonical mapped function start')
    out.mkdir(parents=True)
    metrics, report = {}, dict(schema_version=1, mode=args.mode, binary_sha256=REFERENCE_SHA256,
                              inputs=before, tests_reused=False, promotion_ready=False)
    try:
        if args.mode == 'dev':
            objects, compiler = compile_sources(args.vc.resolve(), sources, out, metrics)
            report['compiler'] = compiler
            functions = {}
            for path in objects:
                for function in ObjFile(str(path)).functions:
                    functions.setdefault(demangle(function.name), []).append(function)
            exe = Exe(str(args.exe))
            checks = []
            begin = time.monotonic()
            for address, name in selected:
                matches = functions.get(name, [])
                if len(matches) != 1:
                    raise ValueError('expected exactly one affected-object symbol: '+name)
                checks.append(compare_target(exe, matches[0], address, int(rows[address]['size'])))
            metrics['target_check_seconds'] = time.monotonic()-begin
            report['targets'] = checks
            report['candidate_compatible'] = all(x['candidate_compatible'] for x in checks)
            report['object_sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in objects}
        else:
            run_command([sys.executable, '-B', ROOT/'tools/strictbuild.py', args.vc.resolve()],
                        out/'strictbuild.log', ROOT, metrics, 'compile_seconds')
            audits = sorted((ROOT/'build/audit').glob('*/summary.json'), key=lambda p: p.stat().st_mtime_ns)
            audit = json.loads(audits[-1].read_text())
            if not audit['success']:
                raise ValueError('strict build audit did not pass')
            report['strict_audit'] = str(audits[-1].relative_to(ROOT))
            report['object_sha256'] = {x['path']: x['sha256'] for x in audit['objects']}
            objects = [ROOT/x['path'] for x in audit['objects']]
            cmd = [sys.executable, '-B', ROOT/'tools/checkbaseline.py', args.exe,
                   ROOT/'engine/functions.csv', *objects, '--report', out/'comparison.json']
            if args.rust_targets:
                cmd += ['--rust-targets', args.rust_targets.resolve()]
            run_command(cmd, out/'matching.log', ROOT, metrics, 'matching_seconds')
            comparison = json.loads((out/'comparison.json').read_text())
            report['comparison'] = {k: comparison[k] for k in ('matched_engine_functions',
                'matched_engine_bytes', 'regressions', 'new_addresses')}
            suites = [p.stem for p in sorted((ROOT/'tools').glob('test_*.py'))]
            # Symbol/address selection is checked against the FULL matching result.
            for address, symbol in selected:
                if not any(int(x['address'], 16) == address and x['symbol'] == symbol
                           for x in comparison['matches']):
                    raise ValueError('requested target is not selected by full matcher: '+symbol)
            test_command = [sys.executable, '-B', ROOT/'tools/run_tooling_tests.py',
                            '--report', out/'tooling-summary.json']
            if args.rust_targets:
                test_command += ['--rust-targets', args.rust_targets.resolve()]
            run_command(test_command, out/'tooling-tests.log', ROOT, metrics, 'testing_seconds')
            coverage = json.loads((out/'tooling-summary.json').read_text())
            if not coverage['success']:
                raise ValueError('required tooling coverage failed')
            report['tooling_coverage'] = coverage
            report['tooling_tests_passed'] = coverage['required']['passed'] + coverage['rust']['passed']
        counts, original_only = {}, {}
        test_root = dev_test_view(out, objects) if args.mode == 'dev' and suites else ROOT
        for name in suites:
            result_path = (test_root/'build/results'/(name+'.json')) if test_root != ROOT else out/(name+'.json')
            run_command([sys.executable, '-B', test_root/'tools'/(name+'.py'), args.exe.resolve(), '--report', result_path],
                        out/(name+'.log'), ROOT, metrics, 'testing_seconds')
            result = json.loads(result_path.read_text())
            if test_root != ROOT:
                shutil.copy2(result_path, out/(name+'.json'))
            legacy = validate_case_report(result, name, digest(args.exe))
            if legacy:
                report.setdefault('legacy_reports_bound_by_wrapper', []).append(name)
            (original_only if result.get('original_only') else counts)[name] = len(result['cases'])
        report['differential_suites'], report['original_only_suites'] = counts, original_only
        report['fresh_differential_cases'] = sum(counts.values())
        report['fresh_original_only_cases'] = sum(original_only.values())
        if input_hashes() != before:
            raise ValueError('tracked verification inputs changed during run')
        if any(digest(ROOT/p) != h for p, h in report['object_sha256'].items()):
            raise ValueError('verified objects changed during run')
        if args.mode == 'full':
            new = set(report['comparison']['new_addresses'])
            requested = {'0x%08x'%a for a, _ in selected}
            report['promotion_ready'] = bool(new) and new == requested
            proposal = [dict(rows[int(a, 16)], proposed_symbol=dict(selected)[int(a, 16)]) for a in sorted(new & requested)]
            save(out/'promotion-proposal.json', dict(ready=report['promotion_ready'],
                rows=proposal, csv_sha256=before['engine/functions.csv'],
                requirement='Review row diff and preserve original CSV before any separate promotion.'))
            report['newly_verified_functions'] = len(new)
            report['newly_verified_bytes'] = sum(int(rows[int(a, 16)]['size']) for a in new)
        report['success'] = args.mode == 'full' or report['candidate_compatible']
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        report.update(success=False, error=str(error), promotion_ready=False)
    finally:
        metrics['total_seconds'] = time.monotonic()-started
        report['metrics'] = metrics
        new = report.get('newly_verified_functions', 0)
        report['new_functions_per_hour'] = new*3600/metrics['total_seconds'] if new and report.get('success') else None
        report['new_bytes_per_hour'] = report.get('newly_verified_bytes', 0)*3600/metrics['total_seconds'] if new and report.get('success') else None
        save(out/'verification.json', report)
    print(json.dumps(dict(success=report['success'], promotion_ready=report['promotion_ready'],
                          report=str((out/'verification.json').relative_to(ROOT)), metrics=metrics)))
    return 0 if report['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
