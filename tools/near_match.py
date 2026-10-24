#!/usr/bin/env python3
"""Diagnostic near-match classification; never establishes or promotes a match.

Uses the existing byte/relocation comparison, then aligns decoded instructions.
Only observed differences are classified: stack/register correspondences are
hypotheses, not proof of equivalent lifetimes or register allocation. Outputs and
optional source snapshots must remain private. No third-party code is copied.
"""
import argparse
import csv
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'contribute/tools'))

import capstone
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG
from coff import ObjFile
from native_index import ROOT, load_reference, read_va
from native_verify import compare_target, private_path
from objmatch import Exe, demangle


def decode(code, address):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    rows = list(md.disasm(code, address))
    if sum(i.size for i in rows) != len(code):
        raise ValueError('incomplete x86 decode; cannot classify safely')
    return rows


def signature(instruction):
    return instruction.mnemonic, tuple((o.type, o.size) for o in instruction.operands)


def correspondences(pairs):
    pairs = sorted(set(pairs))
    return dict(pairs=pairs, consistent=(len({a for a, _ in pairs}) == len(pairs) and
                                       len({b for _, b in pairs}) == len(pairs)))


def classify(original, rebuilt, original_va, relocations=(), known=None):
    """Align operand-kind shapes, preserving constants and internal branch targets.

    Rebuilt relocation operand fields are compared to the *aligned* original
    instruction, avoiding fixed byte-offset attribution after structural edits.
    Unknown external symbols remain unresolved. ESP slots are diagnostic only;
    this tool does not track changes in the stack pointer.
    """
    left, right = decode(original, original_va), decode(rebuilt, 0x10000000)
    left_targets = {i.address: n for n, i in enumerate(left)}
    right_targets = {i.address: n for n, i in enumerate(right)}
    left_targets[original_va+len(original)] = len(left)
    right_targets[0x10000000+len(rebuilt)] = len(right)
    align = difflib.SequenceMatcher(None, list(map(signature, left)),
                                   list(map(signature, right)), autojunk=False)
    pairs, gaps = [], []
    for tag, a, b, c, d in align.get_opcodes():
        if tag == 'equal':
            pairs.extend(zip(range(a, b), range(c, d)))
        else:
            gaps.append(dict(original=[a, b], rebuilt=[c, d], kind=tag))
    index_mapping = dict(pairs)
    index_mapping[len(left)] = len(right)
    issues, stack, registers, unresolved = [], [], [], []
    known = known or {}
    relocs = {offset: (size, symbol, kind) for offset, size, symbol, kind in relocations}

    def issue(category, a, b, detail):
        issues.append(dict(category=category, original_offset=a.address-original_va,
                           rebuilt_offset=b.address-0x10000000, detail=detail))

    def reg_pair(a, b, x, y):
        if x or y:
            registers.append((a.reg_name(x) or 'none', b.reg_name(y) or 'none'))
        if x != y:
            issue('register_allocation', a, b, [a.reg_name(x) or 'none', b.reg_name(y) or 'none'])

    for li, ri in pairs:
        a, b = left[li], right[ri]
        for x, y in zip(a.operands, b.operands):
            field_offset = b.imm_offset if y.type == X86_OP_IMM else b.disp_offset
            relocation = relocs.get(b.address-0x10000000+field_offset) if field_offset else None
            # Only IMM and memory displacement operands contain COFF relocations.
            if relocation and y.type in (X86_OP_IMM, X86_OP_MEM):
                size, symbol, kind = relocation
                field_size = b.imm_size if y.type == X86_OP_IMM else b.disp_size
                if size != field_size or kind not in (6, 0x14):
                    issue('relocation', a, b, 'unsupported relocation field')
                else:
                    observed = x.imm if x.type == X86_OP_IMM else x.mem.disp
                    # Capstone resolves REL32 immediates to absolute branch targets.
                    addend_bytes = rebuilt[b.address-0x10000000+field_offset:][:size]
                    addend = int.from_bytes(addend_bytes, 'little', signed=True)
                    observed = (observed-addend) & 0xffffffff
                    if symbol in known and observed != known[symbol]:
                        issue('relocation', a, b, dict(symbol=symbol, observed=observed,
                                                      expected=known[symbol]))
                    elif symbol not in known:
                        unresolved.append(dict(symbol=symbol, observed=observed))
                if x.type == X86_OP_IMM:
                    continue
            if x.type == X86_OP_REG:
                reg_pair(a, b, x.reg, y.reg)
            elif x.type == X86_OP_MEM:
                u, v = x.mem, y.mem
                reg_pair(a, b, u.base, v.base)
                reg_pair(a, b, u.index, v.index)
                if u.scale != v.scale or u.segment != v.segment:
                    issue('structural_instruction', a, b, 'memory scale/segment')
                stack_operand = (not relocation and a.reg_name(u.base) in ('ebp', 'esp') and
                                 u.base == v.base and not u.index and not v.index)
                if stack_operand:
                    stack.append((str(a.reg_name(u.base))+':'+str(u.disp),
                                  str(b.reg_name(v.base))+':'+str(v.disp)))
                if not relocation and u.disp != v.disp:
                    if stack_operand:
                        issue('stack_local', a, b, [u.disp, v.disp])
                    else:
                        issue('structural_instruction', a, b, 'nonstack displacement')
            elif x.type == X86_OP_IMM:
                control = a.group(capstone.CS_GRP_JUMP) or a.group(capstone.CS_GRP_CALL)
                if control:
                    ltarget, rtarget = left_targets.get(x.imm), right_targets.get(y.imm)
                    if ltarget is not None and rtarget is not None:
                        equal = index_mapping.get(ltarget) == rtarget
                    else:
                        equal = x.imm == y.imm
                    if not equal:
                        issue('structural_instruction', a, b, 'unrelocated control target')
                elif x.imm != y.imm:
                    issue('structural_instruction', a, b, 'immediate constant')
    counts = {name: sum(x['category'] == name for x in issues) for name in
              ('stack_local', 'register_allocation', 'structural_instruction', 'relocation')}
    counts['structural_instruction'] += sum(max(g['original'][1]-g['original'][0],
                                                 g['rebuilt'][1]-g['rebuilt'][0]) for g in gaps)
    offsets = [x['original_offset'] for x in issues]
    offsets += [left[g['original'][0]].address-original_va if g['original'][0] < len(left) else len(original) for g in gaps]
    return dict(earliest_original_difference=min(offsets) if offsets else None, counts=counts, issues=issues, structural_gaps=gaps,
                original_instructions=len(left), rebuilt_instructions=len(right),
                aligned_instructions=len(pairs), stack_correspondence=correspondences(stack),
                register_correspondence=correspondences(registers), unresolved_relocations=unresolved,
                establishes_match=False,
                limitations=['Heuristic alignment; equal shapes do not prove semantic equivalence.',
                             'No stack-pointer lifetime/dataflow analysis; ESP offsets are provisional.',
                             'Unknown relocation symbols require authoritative global matching.'])


def rank_key(report):
    """Lowest complexity first; useful caller coverage breaks ties before size."""
    counts = report['diagnostic']['counts']
    return (int(not report['comparison']['extent_compatible']),
            counts['structural_instruction'], counts['relocation'],
            len(report['diagnostic']['unresolved_relocations']),
            int(not report['diagnostic']['stack_correspondence']['consistent']),
            int(not report['diagnostic']['register_correspondence']['consistent']),
            counts['register_allocation'], counts['stack_local'],
            -report.get('unmatched_caller_bytes', 0), -report.get('unmatched_callers', 0),
            -report['comparison']['mapped_bytes'])


def analyze(reference, obj, address, symbol, size, known=None):
    _, pe = load_reference(reference)
    functions = [f for f in ObjFile(str(obj)).functions if demangle(f.name) == symbol or f.name == symbol]
    if len(functions) != 1:
        raise ValueError('expected exactly one object function')
    fn = functions[0]
    comparison = compare_target(Exe(str(reference)), fn, address, size, known)
    # Preserve canonical extent; trim only padding accepted by existing comparator.
    code = fn.code[:size] if comparison['extent_compatible'] else fn.code
    diagnostic = classify(read_va(pe, address, size), code, address, fn.relocs(), known)
    diagnostic['counts']['function_extent'] = int(not comparison['extent_compatible'])
    return dict(schema_version=1, comparison=comparison, diagnostic=diagnostic,
                object_sha256=hashlib.sha256(obj.read_bytes()).hexdigest(),
                reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                classifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                establishes_match=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('reference', type=Path)
    ap.add_argument('object', type=Path)
    ap.add_argument('target', help='0xADDRESS=Demangled::Name')
    ap.add_argument('--known', type=Path, help='optional raw symbol -> integer address JSON')
    ap.add_argument('--index', type=Path, help='existing native_index JSON for caller ranking')
    ap.add_argument('--source', type=Path, help='preserve exact source with this attempt')
    ap.add_argument('--hypothesis', default='observation only')
    ap.add_argument('--out', type=Path, required=True, help='new private attempt directory')
    ap.add_argument('--rank', nargs='*', type=Path, default=[], help='other existing report.json files')
    args = ap.parse_args()
    out = private_path(args.out)
    if out.exists():
        ap.error('attempt directory already exists; preserve failed experiments')
    address, symbol = args.target.split('=', 1)
    address = int(address, 0)
    rows = list(csv.DictReader((ROOT/'engine/functions.csv').open()))
    row = next(r for r in rows if int(r['address'], 16) == address)
    known = json.loads(args.known.read_text()) if args.known else {}
    report = analyze(args.reference, args.object, address, symbol, int(row['size']), known)
    report.update(hypothesis=args.hypothesis, created_unix=time.time(), object=str(args.object))
    if args.index:
        index = json.loads(args.index.read_text())
        records = index['functions']
        target = next(r for r in records if r['va'] == address)
        by_va = {r['va']: r for r in records}
        callers = {c['function_va'] for c in target['callers'] if
                   by_va.get(c['function_va'], {}).get('csv_status') != 'matching'}
        report['unmatched_callers'] = len(callers)
        report['unmatched_caller_bytes'] = sum(by_va.get(c, {}).get('mapped_size', 0) for c in callers)
    out.mkdir(parents=True)
    shutil.copyfile(args.object, out/'candidate.obj')
    if args.source:
        source = args.source.read_bytes()
        report['source_sha256'] = hashlib.sha256(source).hexdigest()
        report['source_provenance'] = 'provided snapshot; compilation correspondence requires compiler evidence'
        shutil.copyfile(args.source, out/('source'+args.source.suffix))
    report['priority_key'] = rank_key(report)
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    reports = [report] + [json.loads(p.read_text()) for p in args.rank]
    (out/'ranking.json').write_text(json.dumps([dict(address=r['comparison']['address'],
            priority_key=rank_key(r)) for r in sorted(reports, key=rank_key)], indent=2)+'\n')
    print(json.dumps(dict(address=report['comparison']['address'], counts=report['diagnostic']['counts'],
                         priority_key=report['priority_key'], establishes_match=False)))


if __name__ == '__main__':
    main()
