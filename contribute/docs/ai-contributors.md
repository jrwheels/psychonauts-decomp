# AI-assisted native reconstruction

Use this guide with Codex or another coding agent after reading
[CONTRIBUTING](../README.md). The contributor owns the result and must review
it. AI output is a hypothesis until supported by original assembly and verification.
Codex recognizes repository `AGENTS.md` guidance; see the
[official workflow documentation](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex).
Other agents should be explicitly directed to read that file. No particular paid
service or model is required. Keep binaries, compiler files, credentials, transcripts
and raw analysis private; check your service's data policy before sharing inputs.

## Reconstruction prompt

```text
Continue this existing reconstruction from base commit [COMMIT].
Claim/issue: [ID]. Reference SHA-1: 21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07;
SHA-256: cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3.
Targets: [canonical addresses, sizes]. Subsystem purpose: [reason].
Read AGENTS.md, contribute/README.md, relevant source, function map and evidence.
Inspect worktree status and preserve all pre-existing work before edits.
Use privately configured REFERENCE and VC; never print their personal paths.
Inspect bounded original assembly, callers and dependencies before naming behavior.
Recover real C++ using VC++ 2008 RTM x86 15.00.21022.08 with unchanged flags.
Preserve layouts, ABI, allocation/copy ordering, overflow and other original edges.
Do not invent full class layouts or ownership. Record uncertainty explicitly.
Work on one function or 2-5 related small functions, with one shared-file writer.
After 25 minutes or a small documented probe series without progress, record the
blocker and choose another authorized related target; do not repeat unchanged probes.
Run targeted compilation, affected differential cases, then full strict verification.
Do not patch objects, relax the matcher, change flags or bulk-promote the CSV.
Report compiled, behaviorally verified and uniquely matching statuses separately.
Preserve each previous matching address and review each proposed map change.
Do not touch game installations/assets/saves or unrelated work.
Do not commit, push, open issues/PRs or publish without explicit authorization.
Finish with the result report below and an exact proposed public file list.
```

## Independent review prompt

```text
Review this reconstruction diff without modifying it. Check its base/reference,
original assembly evidence, ABI/layout assumptions, ownership/copy ordering and edge
cases. Inspect full matching/regression reports, tests and mocked/excluded behavior.
Look for artificial compiler-layout tricks, output manipulation, stale objects,
missing tests, unexpected CSV promotions and private/proprietary material.
Return concrete findings with file locations and distinguish evidence from inference.
Do not treat source readability, a development byte check or an AI explanation as
proof of unique matching. Do not commit, publish or change installations.
```

## Acceptance criteria

- Correct canonical starts and privately hash-gated supported executable.
- Original RTM compiler/flags, actual C++ reconstruction, attributed dependencies.
- Bounded batch related to a real subsystem; no unrelated count padding.
- Fresh full-object unique matches, all prior matching addresses retained.
- Independent behavioral checks where feasible; explicit mocks and exclusions.
- Every required tooling test passes without skips; Rust coverage separately stated.
- All differential suites pass after relevant verifier/harness changes.
- Reviewed individual CSV changes; no promotion from dev compatibility alone.
- Unresolved semantics remain documented; object matching is not gameplay proof.
- Explicit publication list passes safety checks and human review.

## Result report

```text
Base commit / local changes:
Claim / subsystem / files touched:
Reference SHA-1 and SHA-256 (no file upload):
Compiler version / flags / host Python and dependency versions:
Address | provisional name | mapped bytes | compiled | behavior tested | matched
Original evidence: branches, offsets, calls, copy/allocation/lifetime order
Before -> after: matching functions / bytes; lost addresses: [must be zero]
Commands and private report hashes:
Required Python tooling: passed / failed / skipped
Optional Rust: not requested OR passed / failed / skipped; backend/library hash
Differential: fresh / reused cases, suites, mocks and excluded inputs
Original-only cases (separate from differential):
Known limitations / blockers / measured experiment budget:
Publication checker scope and findings; proposed public files:
Next related targets:
Commit/push/install actions (state explicitly):
```

Keep context short and factual. A resume note should point to saved evidence,
failed attempts and the current dirty worktree, not invent missing chat history.
