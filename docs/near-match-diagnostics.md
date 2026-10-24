# Near-match diagnostics

`tools/near_match.py` classifies an existing compiled candidate without changing
matching, compiler settings, source, or canonical metadata. It reuses the COFF
reader and `native_verify.compare_target`, then aligns Capstone instruction
mnemonics and operand kinds. It does not invoke a compiler or run full matching.

```sh
python -B tools/near_match.py "$REFERENCE" build/game/resource_cache.obj \
  '0x006a66a0=ResourceCache::Find' \
  --source src/game/resource_cache.cpp \
  --hypothesis 'Inspect typed index lifetime before another compiler probe' \
  --out build/near-match/cache-find-001
```

The output directory must be new and private (`build/` or `.local/`). It preserves
the candidate object, optional exact source, hashes, hypothesis, classifications,
first differing original offset and a ranking report. Keep compiler logs and
failed builds in the existing native-verifier/probe directories. Those historical
attempts remain valuable even if no usable object was produced. Do not overwrite
a failed attempt with its successor.

Classifications are independent and may coexist:

- `stack_local`: an aligned EBP/ESP memory operand has a different displacement.
  Correspondences include unchanged slots to expose collisions. ESP offsets are
  provisional because this diagnostic does not analyze stack-pointer lifetimes.
- `register_allocation`: aligned register or memory base/index operands differ.
  This is an observed register difference, not proof of an allocator cause.
- `structural_instruction`: inserted/deleted instruction shapes, different
  constants, nonstack displacements or different unrelocated branch destinations.
- `relocation`: an aligned COFF relocation conflicts with explicitly known symbol
  addresses, or has unsupported kind/field width. Unresolved symbols remain
  separate; zero relocation conflicts never means that all targets are verified.
- `function_extent`: the existing comparator rejects the canonical extent,
  allowing only its established trailing INT3 padding rule.

`--known private-symbol-addresses.json` accepts raw COFF symbols mapped to integer
addresses from independently established evidence. Do not populate it from the
candidate's own inferred targets. `--index private-native-index.json` reuses the
existing `native_index.py` output for unmatched caller counts and caller byte
opportunities. `--rank other/report.json ...` compares preserved attempts.
Ranking puts extent/structural/relocation complexity first, then unresolved
symbols, stack-correspondence conflicts, register and slot differences. Useful
unmatched caller coverage precedes candidate size as the final tie-breakers.
The index must be current; caller bytes are opportunities, never recovered bytes.

The authoritative byte comparison is included separately. Heuristic instruction
alignment can pair the wrong repeated instructions, and does not prove behavior,
unique matching, register lifetimes, or original source declarations. Consult
original assembly at the earliest difference before choosing a bounded source
experiment. Full verification and individual promotion review remain mandatory.

Synthetic validation covers constants, insertions, internal control flow, stack
slot collisions including unchanged slots, register differences, REL32/DIR32
relocations, unknown/unsupported symbols, incomplete decoding and ranking.
Retrospective private validation on October 23 artifacts reproduced cache Find's
8 stack-only differences, Remove's 5, and resource-array swap's 4. Matched Release
and Skeleton::ReadInput had zero stack/register/structural differences. The
animation stub retained structural, register and extent discrepancies; the mesh
pack candidate retained stack and extent discrepancies. These results explain
why repeating local-slot experiments on the animation stub is insufficient.

This is an original implementation building on the repository's existing private
stack-correspondence diagnostic. No reccmp, objdiff or other third-party
implementation code was copied.
