# Complete native publication candidate

This is a reviewable candidate, not a statement that it has already been published.
The base is fork main `815480840e6fb7194b72f1771b1c26edff4a058a`, confirmed by
read-only remote inspection. No root-history merge, history rewrite or remote
change is needed. Existing local files and Git history remain preserved privately.

## Already public and retained

The base contains 3,360 matching functions /298,986 mapped bytes, the complete
existing Lua runtime/script tools, 62 compiling native sources, native file/stream,
mesh/skeleton/resource work, matcher, strict build audit and independent tests.
The latest native snapshot retains all existing project files and all root-checkout
matching addresses. Root source differs in only three older partial interface/file
implementations; newer lifetime-aware versions already published supersede those.
The earlier alternate workflow prototype is also superseded by its hardened version.

## Verified native additions

All 10,930 canonical starts/sizes are identical to the supported checkpoint.
Exactly 13 additional resource-list functions contribute 1,267 bytes. Candidate
matching total: **3,373 /10,930 functions, 300,253 /2,935,679 bytes**.

| Address | Provisional name | Mapped bytes |
| --- | --- | ---: |
| 0x006a4fa0 | AllocateResourceListPool | 62 |
| 0x006a4fe0 | ResourceListPool::Release | 66 |
| 0x006a5100 | ResourceList::RefillNodes | 136 |
| 0x006a5190 | ResourceList::AllocateNode | 204 |
| 0x006a5260 | ResourceList::ReleaseNode | 62 |
| 0x006a52a0 | ResourceList::PushBack | 88 |
| 0x006a5300 | ResourceList::PushFront | 87 |
| 0x006a5360 | ResourceList::AppendList | 68 |
| 0x006a53b0 | ResourceList::PrependList | 67 |
| 0x006a5400 | ResourceList::PopBack | 91 |
| 0x006a54c0 | ResourceList::InsertAfter | 115 |
| 0x006a5540 | ResourceList::InsertBefore | 112 |
| 0x006a55b0 | ResourceList::RemoveNode | 109 |

Source, the individually reviewed CSV rows, native evidence and progress map are
included together. `mesh.cpp` and `resource_context.cpp` also retain accepted
behavior/stack-layout comments. No new engine reconstruction is performed while
preparing publication. Verification is object-level, not linking or gameplay.

## Supporting project content

- All current general native analysis, ranking, build, matching and verification
  tools; differential suites remain at `tools/test_*.py` with their existing imports.
- The reviewed 26-file contributor infrastructure, including its four prior local
  workflow prerequisites, with necessary complete-project/dependency adjustments.
- Current native documentation plus explicitly historical root sound/file/buffered
  and geometry findings; private raw reports are not included or required downloads.
- Original Psychonauts format/mesh/rig/animation/collision inspection source and
  synthetic tests, with complete retained MIT/permissive attribution. These are
  reference research, not runtime-loader proof or a destination-costume workstream.
- Pinned open-source dependencies and public synthetic-only CI on Python3.10/3.13,
  each with optional Rust absent/present. Game/compiler inputs are never CI artifacts.

## Useful provisional work retained

ReadAllocatedString at0x006a5de0 remains compiled/behavior-tested but unmatched;
its four stack-displacement differences are explicit and excluded from totals.
Constructor/association and vector-return ABI blockers are documented, not promoted.
Format decoders/exporters retain fail-closed/partial-format limitations; no complete
resource parsing, faithful shader/lightmap/animation or renderer claim is made.

## Deliberate exclusions

- All destination-costume projects, models, mods, exports, Studio automation,
  SDK helpers, clothing fitting/packaging and installation state.
- Original game/asset data, compiler components, Wine prefixes, raw disassembly,
  databases, generated objects, private caches, personal paths and credentials.
- Raw chat/transcripts/session state and their exporter; mixed root session logs,
  progress/next-step documents and large private recovery archives.
- Superseded per-session JSON/selection inventories and redundant earlier source
  variants; current canonical evidence and historical technical findings are retained.
- Unverified compiler-layout probes/experimental private source outside the actual
  engine build. None becomes matching because of publication preparation.

Exclusion never deletes local originals. The candidate has the public base's
ancestry only; private root/costume history is not brought into the outgoing range.
Full match reconciliation, exact candidate files, file hashes and excluded-source
classifications are preserved in the private review checkpoint.

## Reproduction and remaining boundaries

Use contribute/README.md and the exact owned executable/original RTM compiler. Fresh
public dependencies, synthetic tests, full strict build, all-address regressions
and native differential suites are required before approval. Rust remains optional
and coverage is reported separately. Detailed results are in native-verification.json.

Hosted GitHub execution, fresh distro/SteamOS Wine and compiler acquisition,
Windows/WSL and whitespace-containing checkout paths require external validation.
No original game parsing/export is rerun merely for publication. Numerical format
fixtures and package-reader smoke checks use synthetic inputs only. Public dependency
licenses/notices are retained; no third-party compiler/game package is redistributed.
Publication scans are heuristic and do not replace provenance/license/diff review.

## Final local verification

Both complete native workflows pass: 62 fresh RTM sources, all 3,373 matches /
300,253 bytes, zero regressions, 7,066 fresh differential cases in24suites, and
44 separately counted original-only cases. Python-only full verification takes
240.25s; Rust-enabled takes151.30s. These are same-host runs with different backend
coverage, not statistically controlled performance claims. Python/Rust matching
selects identical address/symbol/object sets.

The clean local-clone rehearsal installs only declared public packages and passes
all four Python3.10.19/3.13.5 x Python/Rust synthetic cells:74required plus9optional
Rust tests. It also performs a fresh strict build, targeted list-copy compilation/
576differential cases, fresh resource ranking and bounded original analysis with
only the privately supplied supported reference/compiler/Wine environment. No
prior game-analysis cache is needed. This is not an independent external contributor
run; hosted CI and fresh platform acquisition/configuration still need validation.
