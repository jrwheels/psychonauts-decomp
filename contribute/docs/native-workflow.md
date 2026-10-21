# Native reconstruction workflow

This workflow selects and verifies candidates for the existing VC++ 2008 RTM
reconstruction. It does not generate source, change compiler flags, edit the
canonical map, commit, or publish anything.

## What already existed

`native_index.py` provides version-bound cached direct-call observations,
callers, source/evidence links and independent milestones. `strictbuild.py`
audits the upstream build. `checkbaseline.py` checks the complete object set
against every previously matching address. Existing differential harnesses
execute original and rebuilt x86 with mocked dependencies. The optional Rust
relocation decoder and cached Python path already accelerate matching; this
workflow does not claim their historical gains as a new optimization.

The additions connect those pieces: deterministic ranking, resumable batch
plans, optional attempt/blocker records, isolated development compilation and
a complete verification command with timings and a guarded review proposal.

## Select a focused batch

Use the existing Python environment, exact owned reference and toolchain.
Put working Wine and winepath on PATH. All generated outputs below are ignored.

```sh
python3 -B contribute/tools/native_workflow.py rank "$REFERENCE" \
  --subsystem mesh --out build/workflow/ranking.json
python3 -B contribute/tools/native_workflow.py plan "$REFERENCE" \
  --subsystem mesh --out build/workflow/plan.json
```

Ranking uses mapped size, observed known and unresolved direct callees,
indirect calls, partial source/class associations, unmatched callers, previous
attempts and blockers. Each score component is visible. Exact matching rows and
named import thunks are excluded. A focus follows at most two observed call
edges from recorded subsystem/source seeds; it is a relevance heuristic, not
proof of class membership or complete dependencies. Tail jumps and unresolved
virtual targets are not recovered by this ranking.

Plans reserve small, medium and complex lanes, with maximum batch sizes of
10, 3 and 1. Small batches can contain fewer than five targets when evidence is
limited. Targets sharing an observed direct dependency are not grouped together.
This does not prove independence through unknown calls or shared global state.
Only one worker should edit a shared source/layout or canonical metadata.

A generated plan starts `review_required`. Before using it, fill each target's
`symbol`, `source` and `suites` from actual evidence, then mark its batch
`reviewed`. Symbols are demangled names from your compiled source; they are not
claims about recovered original names. Source, CSV, evidence and reference hashes
bind the plan. Refresh it when those inputs change.

## Use the verification ladder

Development mode compiles explicit affected sources with the unchanged upstream
flags and validates the RTM banner. Objects go into a fresh output directory.
Target byte compatibility, decoded relocations, unresolved/conflicting symbols
and byte differences are reported. It does not establish unique global matches.

```sh
python3 -B contribute/tools/native_verify.py dev "$REFERENCE" "$VC" \
  --source src/game/mesh.cpp \
  --target '0x00455900=EModel::SetName' \
  --suite test_model_input --out build/workflow/dev-001
```

Affected suites run in an isolated view containing the newly compiled objects,
unchanged supporting objects, Python harnesses and required map metadata. The
canonical build is not replaced. Omitted suites are not assumed to pass, and
this development result always remains ineligible for promotion.

The reviewed plan can supply the same arguments:

```sh
python3 -B contribute/tools/native_verify.py dev "$REFERENCE" "$VC" \
  --plan build/workflow/plan.json --batch 0 --out build/workflow/dev-002
```

At a batch boundary, run full verification:

```sh
python3 -B contribute/tools/native_verify.py full "$REFERENCE" "$VC" \
  --rust-targets build/rust/reloc_targets.so \
  --target '0x00455900=EModel::SetName' --out build/workflow/full-001
```

Full mode invokes unchanged `strictbuild.py` and the full-object matcher, then
all tooling tests and all differential suites. The optional Rust library must
be locally built if testing that backend; see [matching acceleration](matching-acceleration.md).
The Python matcher remains authoritative without acceleration. Full verification always runs required Python tooling tests and all differential
suites. Rust is optional: without --rust-targets, tooling-summary.json reports
Rust as not_requested. With --rust-targets, all Rust tests must pass too. Required
skips/failures and explicitly requested Rust skips/failures reject verification.
The manual Python build/comparison also remain available without Rust.

Input and object hashes are checked again before success. Six legacy sound
reports omit a SHA-256 field; their known schemas are explicitly bound by the
wrapper's dual-hash reference gate and post-suite reference hash check. A
present wrong hash is always rejected. Original-only parser cases are counted
separately from differential equivalence.

A proposal is ready only if the full matcher selects every requested
address/symbol and its exact set of new addresses equals the requested set.
`promotion-proposal.json` is a review artifact, not a CSV update. Inspect it,
save the original CSV, review the actual row diff, and promote separately.
Milestones remain independent; a byte match alone is not behavioral coverage.

## Preserve failed investigations

The optional `workflow` object in `engine/native-evidence.json` adds subsystem,
blockers, next action, deferred state and attempts without changing schema
version 1 or existing milestone meanings. Attempts store method, input
fingerprint, outcome and elapsed seconds only when measured.

```sh
python3 -B contribute/tools/native_workflow.py record-attempt "$REFERENCE" \
  --address 0x006a5de0 --method inline-layout-probe --outcome blocked \
  --blocker 'Four temporary displacements still differ' \
  --next-action 'Wait for neighboring inline-layout evidence' \
  --out build/workflow/attempt-001.json
```

Recording backs up the original evidence under ignored output, validates the
schema and rejects recording the same method on unchanged inputs unless
`--retry` is explicit. Plans suppress unchanged blocked/failed/mismatched
attempts. `plan --method another-method` permits a different approach;
`plan --retry` explicitly overrides retry suppression. Curated `deferred`
blockers still require a deliberate evidence edit to re-enable scheduling.

Use a bounded investigation budget: roughly 25 minutes or a small documented
probe series, then record the blocker. These are operator stop rules, not a
background agent scheduler or a claim that time was automatically measured.
Fingerprints conservatively include all source hashes and observed caller
context. Even comment changes may invalidate them; they avoid stale evidence
at the cost of sometimes allowing another review.

## Measure useful work

`verification.json` records compilation, matching/target checks, testing and total
elapsed seconds, fresh cases, original-only cases and verified new bytes/functions.
Per-hour rates are null when a run verifies no new matches. Do not convert a
maintenance check into a reconstruction-productivity claim.

The initial two-object development smoke took 12.44 seconds, including 0.604
seconds of compiler subprocess work, 0.00020 seconds for target checks and 7.70
seconds for 434 affected cases. Compiler identity/path setup is included only
in total time. A cold rank/index refresh took 17.67 seconds and a warm cached
plan took 1.92 seconds. These runs do different work; they are not an equal-work
speedup benchmark. Full-run measurements and limitations are in
[native reconstruction status](../../docs/native-reconstruction.md).

The complete new verification command took 138.96 seconds: 14.46 seconds for
the strict build, 12.01 seconds for matching and 111.98 seconds for testing. It
passed 46 tooling tests, all 6,490 differential cases and 44 separate
original-only cases. The reviewed-plan legacy sound smoke passed in 5.47 seconds
with 28 cases. No engine functions were added by this tooling task, so
reconstruction productivity rates remain null rather than fabricated.
