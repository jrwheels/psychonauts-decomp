#!/usr/bin/env python3
"""Compare provider-observed function instructions with a fresh native-index extent.

This is a coverage diagnostic only: it never decides reachability, semantics,
matching, or source correctness. Both detailed input records stay private.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import capstone
from native_index import ROOT, load_reference, load_rows, read_va
from native_verify import private_path


def compare(index, ca):
    """Reject malformed, mixed-target, and unsupported inputs before comparing."""
    if isinstance(ca.get('result'), dict) and 'structuredContent' in ca['result']:
        ca = ca['result']
    if 'structuredContent' in ca:
        ca = ca['structuredContent']
    if 'result' in ca and isinstance(ca['result'], dict) and 'subject' in ca['result']:
        ca = ca['result']
    start = int(index['function']['address'], 16)
    size = int(index['function']['size'])
    indexed = [i['va'] for i in index['instructions']]
    if ca.get('operation') == 'native_function_study':
        if ca['subject']['sha256'] != index['binary_sha256']:
            raise ValueError('binary identity mismatch')
        body = ca['result']
        if body['function'].get('truncated') is not False:
            raise ValueError('provider function is truncated or its coverage is unknown')
        if int(body['function']['entry'], 16) != start:
            raise ValueError('function boundary mismatch')
        observed = [int(i['address'], 16) for i in body['assembly']]
        if body['function'].get('instructions') != len(observed):
            raise ValueError('provider instruction list is incomplete')
        evidence_id, provider = ca['id'], 'craft-anything'
    elif ca.get('operation') == 'analyze_function':
        if ca['subject']['digest']['sha256'] != index['binary_sha256']:
            raise ValueError('binary identity mismatch')
        body = ca['normalized_result']
        proc = body['procedure']
        if int(proc['address'], 16) != start or not proc['body']['available']:
            raise ValueError('function boundary mismatch or unavailable body')
        if body['facet_availability']['assembly']['available'] is not True:
            raise ValueError('provider assembly is unavailable')
        observed = []
        for line in body['assembly']:
            match = re.match(r'^0x([0-9a-fA-F]+): ', line)
            if not match:
                raise ValueError('unsupported provider assembly format')
            observed.append(int(match.group(1), 16))
        ranges = [(int(r['start'], 16), int(r['end'], 16)) for r in proc['body']['ranges']]
        if not ranges or any(not any(lo <= v <= hi for lo, hi in ranges) for v in observed):
            raise ValueError('provider assembly lies outside reported body')
        evidence_id, provider = ca['evidence_id'], ca['provider']['id']
    else:
        raise ValueError('expected complete CA or REA function evidence')
    if size <= 0:
        raise ValueError('invalid mapped extent')
    if not indexed or not observed or len(set(indexed)) != len(indexed) or len(set(observed)) != len(observed):
        raise ValueError('empty or duplicate instruction addresses')
    if any(type(i) is not int or not start <= i < start + size for i in indexed + observed):
        raise ValueError('instruction address outside mapped extent')
    a, b = set(indexed), set(observed)
    return {'schema_version': 1, 'binary_sha256': index['binary_sha256'],
            'function': '0x%08x' % start, 'mapped_size': size,
            'native_index_count': len(a), 'provider_count': len(b),
            'index_only': ['0x%08x' % v for v in sorted(a-b)],
            'provider_only': ['0x%08x' % v for v in sorted(b-a)],
            'provider_evidence_id': evidence_id, 'provider': provider, 'establishes_match': False,
            'limitations': ['Linear disassembly and provider CFG have different boundaries; missing instructions are not proof of reachability.',
                            'Address agreement does not verify instruction semantics, call targets, or binary matching.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference', type=Path)
    p.add_argument('index', type=Path)
    p.add_argument('ca', type=Path, help='complete CA or REA evidence JSON')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    data, pe = load_reference(args.reference)
    index_bytes, ca_bytes = args.index.read_bytes(), args.ca.read_bytes()
    index, ca = json.loads(index_bytes), json.loads(ca_bytes)
    _, rows = load_rows(ROOT/'engine/functions.csv', pe)
    address = int(index['function']['address'], 16)
    row = next((r for r in rows if int(r['address'], 16) == address), None)
    if row is None or index['function'] != row or index['binary_sha256'] != hashlib.sha256(data).hexdigest():
        raise ValueError('stale index identity or function map')
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    expected = [(i.address, i.size, i.mnemonic, i.op_str) for i in md.disasm(read_va(pe, address, int(row['size'])), address)]
    actual = [(i['va'], i['size'], i['mnemonic'], i['operands']) for i in index['instructions']]
    if not expected or sum(i[1] for i in expected) != int(row['size']) or actual != expected:
        raise ValueError('stale or incomplete native index')
    result = compare(index, ca)
    result['input_sha256'] = {'native_index': hashlib.sha256(index_bytes).hexdigest(), 'provider': hashlib.sha256(ca_bytes).hexdigest()}
    result['function_map_sha256'] = hashlib.sha256((ROOT/'engine/functions.csv').read_bytes()).hexdigest()
    out = private_path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps({'function': result['function'], 'index_only': len(result['index_only']), 'provider_only': len(result['provider_only']), 'establishes_match': False}))


if __name__ == '__main__':
    main()
