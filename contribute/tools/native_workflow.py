#!/usr/bin/env python3
"""Heuristic native target selection; never promotes matches or edits the CSV."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

from native_index import ROOT, REFERENCE_SHA256, load_reference, validate_evidence


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_output(path, root=ROOT):
    path = Path(path)
    if not path.is_absolute():
        path = root/path
    if any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)) or not any(path.resolve().is_relative_to(root / d) for d in ('build', '.local')):
        raise ValueError('output must be an ignored, nonsymlink path')
    return path


def fingerprint(record, code_hash, evidence, sources=None):
    # Include observed caller context, declared source and all tracked source bytes:
    # neighboring layout changes can alter the usefulness of a previous attempt.
    if sources is None:
        sources = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted((ROOT/'src').rglob('*')) if p.is_file()}
    payload = [REFERENCE_SHA256, record['va'], code_hash, record.get('callers', []),
               record.get('source'), sources, evidence.get('signature'), evidence.get('parent')]
    return sha(json.dumps(payload, sort_keys=True).encode())


def rank(records, subsystem=None):
    by_va = {r['va']: r for r in records}
    distances = {}
    if subsystem:
        seeds = {r['va'] for r in records if subsystem in str(r.get('source') or '') or
                 subsystem in str(r.get('workflow', {}).get('subsystem') or '')}
        neighbors = {va: set() for va in by_va}
        for r in records:
            for c in r['callees']:
                target = c['target_va']
                if target in neighbors:
                    neighbors[r['va']].add(target)
                    neighbors[target].add(r['va'])
        frontier = seeds
        for distance in range(3):
            for va in frontier: distances.setdefault(va, distance)
            frontier = {target for va in frontier for target in neighbors[va] if target not in distances}
    result = []
    for r in records:
        if r.get('csv_status') == 'matching' or '.dll!' in str(r.get('name') or '').lower():
            continue
        workflow = r.get('workflow', {})
        group = workflow.get('subsystem') or r.get('source') or r.get('parent') or 'unclassified'
        direct = sorted({c['target_va'] for c in r['callees'] if c['target_va'] is not None})
        known = [a for a in direct if a in by_va and by_va[a].get('csv_status') == 'matching']
        unknown = [a for a in direct if a not in known]
        indirect = sum(c['target_va'] is None for c in r['callees'])
        size = r['mapped_size']
        lane = 'small' if size <= 160 else 'medium' if size <= 800 else 'complex'
        callers = len({c['function_va'] for c in r['callers'] if by_va.get(c['function_va'], {}).get('csv_status') != 'matching'})
        related = bool(r.get('source') or r.get('parent'))
        components = dict(size=max(-100, 80-size//8), known=8*len(known), unresolved=-12*len(unknown),
                          indirect=-20*indirect, relevant=(45-15*distances[r['va']] if r['va'] in distances else -80) if subsystem else 0,
                          partial_class=15 if related else 0, unlocks=min(40, callers*4),
                          attempts=-10*len(workflow.get('attempts', [])), blockers=-15*len(workflow.get('blockers', [])))
        result.append(dict(address='0x%08x'%r['va'], va=r['va'], size=size, lane=lane, group=group,
                           score=sum(components.values()), components=components, focus_distance=distances.get(r['va']),
                           source=r.get('source'), deferred=workflow.get('deferred', False), direct_dependencies=direct,
                           unknown_dependencies=unknown, indirect_calls=indirect, workflow=workflow))
    return sorted(result, key=lambda r: (-r['score'], r['va']))


def plan(ranked):
    batches = []
    for lane, limit in [('small', 10), ('medium', 3), ('complex', 1)]:
        candidates = [r for r in ranked if r['lane'] == lane and not r.get('deferred') and not r.get('retry_suppressed')]
        if not candidates:
            continue
        chosen = []
        group = candidates[0]['group']
        for r in candidates:
            if r['group'] != group or len(chosen) == limit:
                continue
            if any(r['va'] in x['direct_dependencies'] or x['va'] in r['direct_dependencies'] for x in chosen):
                continue
            chosen.append(r)
        batches.append(dict(lane=lane, group=group, targets=[dict(address=r['address'], symbol=None, source=None, suites=[]) for r in chosen],
                            declarations=[], symbols={}, suites=[],
                            status='review_required', stopping_condition='Record blockers after bounded failed probes; full verification required before promotion'))
    return batches


def validate_cache(directory, inputs):
    manifest = json.loads((directory/'manifest.json').read_text())
    if any(manifest['inputs'].get(k) != v for k,v in inputs.items()):
        raise ValueError('stale native index inputs')
    if set(manifest.get('outputs', {})) != {'binary.json','functions.json','lua-native.json'}:
        raise ValueError('incomplete native index')
    for name, digest in manifest['outputs'].items():
        if sha((directory/name).read_bytes()) != digest:
            raise ValueError('stale native index output')
    return json.loads((directory/'functions.json').read_text())


def record_attempt(evidence, address, method, context, outcome, elapsed=None, retry=False):
    note = evidence.setdefault('functions', {}).setdefault(address, {})
    workflow = note.setdefault('workflow', {})
    attempts = workflow.setdefault('attempts', [])
    if not retry and any(a['method']==method and a['fingerprint']==context for a in attempts):
        raise ValueError('same method and unchanged inputs; explicit --retry required')
    entry = dict(method=method, fingerprint=context, outcome=outcome)
    if elapsed is not None:
        if elapsed < 0 or not __import__('math').isfinite(elapsed):
            raise ValueError('elapsed seconds must be finite and nonnegative')
        entry['elapsed_seconds'] = elapsed
    attempts.append(entry)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=['rank','plan','record-attempt'])
    ap.add_argument('exe', type=Path)
    ap.add_argument('--index', type=Path, default=ROOT/'build/native-index')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--subsystem')
    ap.add_argument('--address')
    ap.add_argument('--method')
    ap.add_argument('--outcome')
    ap.add_argument('--blocker', action='append', default=[])
    ap.add_argument('--next-action')
    ap.add_argument('--elapsed-seconds', type=float)
    ap.add_argument('--retry', action='store_true')
    args = ap.parse_args()
    try:
        out = safe_output(args.out)
        if out.resolve() == args.exe.resolve():
            raise ValueError('output would overwrite reference')
        safe_output(args.index)
        data, pe = load_reference(args.exe)
        ep = ROOT/'engine/native-evidence.json'
        original_evidence = ep.read_bytes()
        evidence = json.loads(original_evidence)
        # Existing index owns observation caching and identity validation.
        subprocess.run([sys.executable, '-B', str(ROOT/'tools/native_index.py'), str(args.exe), '--out', str(args.index)], check=True)
        records = validate_cache(args.index, {'binary_sha256':sha(data), 'csv_sha256':sha((ROOT/'engine/functions.csv').read_bytes()), 'evidence_sha256':sha(ep.read_bytes())})
        by_va = {r['va']: r for r in records}
        validate_evidence(evidence, set(by_va))
        sources = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted((ROOT/'src').rglob('*')) if p.is_file()}
        contexts = {}
        for r in records:
            offset = pe.get_offset_from_rva(r['rva'])
            contexts[r['va']] = fingerprint(r, sha(data[offset:offset+r['mapped_size']]), evidence.get('functions', {}).get('0x%08x'%r['va'], {}), sources)
        ranking = rank(records, args.subsystem)
        for candidate in ranking:
            candidate['retry_suppressed'] = not args.retry and any(a['fingerprint'] == contexts[candidate['va']] and
                (not args.method or a['method'] == args.method) and a['outcome'] in ('blocked', 'failed', 'mismatch')
                for a in candidate['workflow'].get('attempts', []))
        payload = dict(schema_version=1, binary_sha256=sha(data), csv_sha256=sha((ROOT/'engine/functions.csv').read_bytes()),
                       evidence_sha256=sha(ep.read_bytes()), source_sha256=sources, heuristic=True)
        if args.mode == 'record-attempt':
            if not args.address or not args.method or not args.outcome:
                raise ValueError('record-attempt requires --address, --method, --outcome')
            va = int(args.address, 0)
            if va not in by_va or by_va[va].get('csv_status') == 'matching':
                raise ValueError('attempt must target an unmatched canonical start')
            address = '0x%08x'%va
            record_attempt(evidence, address, args.method, contexts[va], args.outcome, args.elapsed_seconds, args.retry)
            workflow = evidence['functions'][address]['workflow']
            if args.blocker: workflow['blockers'] = args.blocker
            if args.next_action: workflow['next_action'] = args.next_action
            validate_evidence(evidence, set(by_va))
            backup = safe_output(out.parent/(out.name+'.evidence-before.json'))
            backup.parent.mkdir(parents=True, exist_ok=True)
            if backup.exists(): raise ValueError('backup exists; select a fresh output path')
            if ep.read_bytes() != original_evidence:
                raise ValueError('evidence changed during recording; retry with fresh inputs')
            backup.write_bytes(original_evidence)
            ep.write_text(json.dumps(evidence, indent=2)+'\n')
            payload.update(address=address, attempt=workflow['attempts'][-1])
        elif args.mode == 'rank':
            payload['ranking'] = [dict(r, fingerprint=contexts[r['va']]) for r in ranking]
        else:
            focused = [r for r in ranking if not args.subsystem or r['focus_distance'] is not None]
            payload['batches'] = plan(focused)
            payload['fingerprints'] = {r['address']:contexts[r['va']] for r in ranking if any(any(t['address']==r['address'] for t in b['targets']) for b in payload['batches'])}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2)+'\n')
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        ap.error(str(exc))

if __name__ == '__main__':
    main()
