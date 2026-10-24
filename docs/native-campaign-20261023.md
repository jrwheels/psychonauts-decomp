# Native reconstruction campaign — 2026-10-22/23

Two coherent batches advance resource-cache dependencies, animation containers,
and skeleton construction/input. All results target the supported Steam PE32
executable (SHA-1 `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`).
Compiler: VC++ 2008 RTM x86 `15.00.21022.08`, unchanged
`/Od /Oy /Ob1 /Oi /MD /GS-`. Names remain provisional.

## Starting state and provenance

The active detached worktree remains based on `bf6104a`; all older worktrees,
untracked files and ignored recovery material are preserved. Before edits, the
14 recorded checkpoint source hashes, all 63 object hashes, canonical row totals
and successful reports were checked. A fresh read-only full-object comparison
reproduced **3,376 functions /300,804 bytes**, with zero regressions. Its previous
full verification had 8,702 differential cases, 44 separate original-only cases
and 74 required tooling tests. These are measured baseline results, not copied
assumptions.

Fetched parent main remains `6959341` (3,252 functions /286,485 bytes), with no
new work to merge. Fetched fork main remains `ab20a04` (3,375 /300,735), including
the published contributor reorganization and earlier stream/unload work. The
69-byte cache lookup was verified locally and uncommitted at campaign start.
This campaign has no inherited upstream gain and creates no commits or pushes.
The older dirty root is recovery material; no sources/maps were taken from it.
Published `contribute/` and the separate ReSkate project were not modified.

## Ranked opportunities before reconstruction

These were estimates, not accepted matches. Original instructions, canonical
ranges, callers/callees, existing layouts and behavioral suites informed ranking.
Read-only parallel investigations were isolated; one writer integrated engine
sources, shared metadata and promotions. Test writers owned separate new files.

| Rank | Cluster | Estimated opportunity | First dependencies and difficulty |
| --- | --- | ---: | --- |
| 1 | Sparse resource hash cache | 2,129 bytes | Hash/search/release before insertion, allocation and rehash; shared first 12 bytes agree with EArrayBase. Medium local/inline-layout difficulty. |
| 2 | Animation header/accounting/stub | 966 bytes, plus container specializations | Matched ReadBytes/String2b neighbors; two version layouts and typed arrays. Medium serialization and caller-layout difficulty. |
| 3 | Association transfer/dispatch | 945 bytes; mesh-pack adds 279 | Array swap327 and association constructor99 before dispatch519; context constructor remains blocked. Medium/high RAII layout difficulty. |
| 4 | Skeleton construction/input | 1,187 bytes | Bone419, info117 and data43 constructors before reader608; exact ownership/index and array-cookie evidence needed. |

The 5,802-byte context loader remains a later integration target: its TLS arena
scopes, recursive ownership, mesh reader and many unresolved dependencies make
its apparent byte size a poor immediate throughput estimate.

## Newly selected matches

Sizes below are canonical mapped bytes, excluding object alignment padding.
Every row is selected uniquely by full-object matching and covered behaviorally
within the stated bounds. Semantic confidence is high for observed field effects,
ordering and ABI; original names and broader engine ownership remain provisional.

| Address | Reconstructed operation | Size = newly matched bytes | Source | Confidence |
| --- | --- | ---: | --- | --- |
| 0x006a6780 | ResourceCacheHash | 69 | src/game/resource_cache.cpp | High: unsigned-byte polynomial and wrapping arithmetic |
| 0x006a65d0 | ResourceCache::TryGet | 81 | src/game/resource_cache.cpp | High: link lookup/output and AL return |
| 0x006a6630 | ResourceCache::Unlink | 108 | src/game/resource_cache.cpp | High: raw-handle chain unlink and release ordering |
| 0x006a6850 | ResourceCache::Release | 133 | src/game/resource_cache.cpp | High: name destruction/free-slot packing/live count |
| 0x004962c0 | AnimationStub::ReadHeader | 366 | src/game/animation_stub.cpp | High: exact version200/201 field mappings |
| 0x00496430 | AnimationStub::RecalculateBytes | 118 | src/game/animation_stub.cpp | High: capacities and unsigned arithmetic |
| 0x00498f50 | AnimationArray&lt;AnimationTrackSet&gt;::Resize | 410 | src/game/animation_stub.cpp | High: class growth/shrink algorithm; Reserve mocked |
| 0x00491a10 | BoneInfo::BoneInfo | 117 | src/game/skeleton_input.cpp | High: matrix/translation/quaternion/name initialization |
| 0x00491b00 | RuntimeBone::RuntimeBone | 419 | src/game/skeleton_input.cpp | High: two matrices, component defaults and eight flags |
| 0x00499ac0 | SkeletonData::SkeletonData | 43 | src/game/skeleton_input.cpp | High: three observed fields zeroed |
| 0x0049a040 | Skeleton::ReadInput | 608 | src/game/skeleton_input.cpp | High: allocation/cookies/aliases/indexing and dispatch; recursive semantics mocked |

**11 reconstructed functions /2,472 bytes.** The current demangler spells the
track-set symbol `UAnimationTrackSet::?$AnimationArray::Resize`; the report uses
its readable C++ spelling without changing matching or demangling infrastructure.

Two additional exact matches are emitted by the RTM compiler's array-new support:

| Address | Compiler-generated operation | Bytes | Emission source |
| --- | --- | ---: | --- |
| 0x00401820 | Forward constructor iterator (`??_H...`) | 35 | src/game/skeleton_input.cpp array construction |
| 0x004011f0 | Reverse destructor iterator (`??_I...`) | 48 | src/game/skeleton_input.cpp array construction |

These **2 helpers /83 bytes** have their own 140-case behavioral suite. They are
counted separately from manual engine reconstruction. No new inherited upstream
matches are claimed.

| Measurement | Before | After |
| --- | ---: | ---: |
| Matching functions | 3,376 | 3,389 /10,930 |
| Matching mapped bytes | 300,804 | 303,359 /2,935,679 |
| Net matched-byte gain | — | 2,555 (2,472 reconstructed +83 generated) |
| Engine byte coverage | 10.25% | 10.3335% |
| Fresh source objects | 63 | 66 |
| Previous matching addresses/bytes lost | — | 0 /0 |

## Verification and exact limits

`build/campaign/full-02/` strictly verifies batch1: 65 fresh sources, 7 new
functions /1,285 bytes, all previous matches, 74 required Python tests and 9
requested Rust tests, 11,524 differential cases and 44 original-only cases.
`full-03/` strictly verifies batch2 against that promoted map: 66 fresh sources,
4 engine functions /1,187 bytes plus the 2 generated helpers /83 bytes, with
zero regressions. All **74 required +9 optional Rust tests**, **12,124 fresh
differential cases across 34 suites**, and **44 separate original-only CYSP
cases** pass. Required tests have no skips. Input and object hashes are rechecked
by the verifier after tests. Rust acceleration never changes matching rules.

The first full selection (`full-01/`) intentionally failed requested-target
selection: two byte-compatible Resize specializations were ambiguous. Nothing
was promoted from that failed run. The selected seven-function batch was then
fully verified with all tests. Their removal from requested promotions did not
remove the source or its independent behavioral tests.

The final full run includes every pre-existing differential suite and these new
suites (all also run during development):

| New suite | Cases | Scope/mocks |
| --- | ---: | --- |
| test_resource_cache_management | 459 | Real Hash/Find/TryGet/Remove/Unlink/Release integrated; FreeFileName mocked, deletion of entry storage forbidden |
| test_resource_array_swap | 1,280 | Full packed descriptor swap and self alias; no mocks; compiled, tested, still nonmatching |
| test_animation_header | 625 | Versions, poisoned short reads, field mapping and capacity budgets; virtual Seek/ReadBytes mocked |
| test_animation_resize | 458 | All three specializations, exact/nonexact growth/shrink/equal, wrapping arithmetic; Reserve/allocation mocked |
| test_skeleton_construction | 352 | Three real constructors, varied identity globals and poisoned objects; 64 destructor cases mock SetName only |
| test_skeleton_input | 108 | Three real constructors integrated, 16-byte cookies, aliases, runtime indices through257; allocation/name/read/recursive load/transform mocked |
| test_vector_iterators | 140 | Generated helpers' forward/reverse calls, bounded signed counts, strides and ABI; element callbacks mocked |

All fixtures check independent expected results as well as original/rebuilt
agreement. Suites check complete fixture memory and relevant call order,
arguments, preserved registers, stack cleanup and AL/return-this conventions.
The 3,422 new cases add to the 8,702 baseline without recounting original-only
cases as differential cases.

No physical I/O, gameplay or linked engine is established. Skeleton zero-count,
allocation failure/overflow and actual recursive topology/transform behavior are
excluded. Large invalid cache pointers/indices and zero-bucket faults are not
covered. Huge class-resize loops are excluded; bounded byte-array fixtures test
request overflow without allocating an enormous buffer. General overlapping or
self matrix assignment is not established by distinct-object constructor tests.
String ownership/destruction is mocked where identified. No game launch,
installation, asset, save or configuration changes occurred.

## Recovered structure and compiler behavior

The cache's first words carry category5/count27 and flag1/capacity31, followed by
12-byte name/value/next entries. Observed sparse fields are live count+0xc,
free head+0x10, generation word+0x14, buckets+0x18 and bucket count+0x1c. Free
slots replace the name word with a free-bit/next-index encoding. Release frees
only the name, leaves value/next storage unchanged, and links the slot onto the
free list. A high handle bit is masked where observed; its general meaning is
not asserted. Providing the real inline release body also recovers the callers'
previously unexplained retained stack space.

Animation versions200 and201 have different serialized layouts. Magic is not
validated here. Old words narrow to bytes; new flags combine a ushort and byte
with OR **without shifting**. Byte accounting uses array capacities, not counts.
The recovered generic Resize algorithm has meaningful class-versus-byte and
exact-versus-spare-capacity behavior; equal class counts do nothing, whereas an
exact byte resize still reserves. This is shared source understanding across
three emitted functions, not three unrelated count-padding wrappers.

The runtime bone is0xb0 bytes, bone info0x60, and retained skeleton data12. Runtime
byte indices are assigned from the allocation order before deserialization;
serialized ushort root IDs are read but do not select runtime allocation slots.
Index narrowing through255/256/257 is verified without claiming that arbitrary
large real hierarchies are valid. The recursive reader result is checked only for
null; a controlled nonnull sentinel return is accepted as success without a new
pointer-validity check.

Three source-level explanations resolved the larger constructor/reader bodies:

- A real 64-byte matrix assignment operator explains the inline `this` temporary,
  preserving duplicated identity initialization and subsequent matrix copy.
- Observed user-declared destructors (including an empty runtime-bone destructor)
  make destruction nontrivial and restore the compiler's16-byte array cookies.
- A scalar typed stream-read helper materializes the complex count pointer and
  emits a constant four-byte read. A count-taking overload instead emits a shift
  under /Od and does not match. No fabricated local, padding or output patch is
  used to supply the missing spill.

Local names affect VC2008 hash-bucket allocation; declaration-only reordering
was measured and did not fix slot order. Bounded descriptive naming/scope probes
were retained, then deferred when they supplied no new evidence. No compiler
flags, matcher, toolchain or shared engine header was modified.

## Deferred work and next campaign

- Animation track Resize0x004991c0(409) and byte Resize0x00499920(412): all mapped
  bytes compatible and behavior tested, but full matching cannot select unique
  addresses. They remain unpromoted. A matching stub caller0x00495e60(482) could
  unlock **1,301 estimated bytes** including that caller. Its retained locals and
  payload-access assignment still disagree; existing failed probes are private.
  Recover neighboring accessor declarations before further slot experiments.
- Recursive joint reader0x00492010(955): newly verified constructor/input layouts
  make this the strongest next substantive parser. Preserve byte runtime indices,
  discarded serialized IDs, version fields, quaternion and recursive ownership
  behavior. Actual Transform0x004923d0 remains external.
- Cache Find0x006a66a0(218), Remove0x006a6560(108), and array swap0x0041f450(327):
  integrated expected/original/rebuilt behavior passes, but named-local placement
  still prevents matching. Canonical source retains these tested bodies without
  matching status. Private Rehash0x006a61c0(414) and Insert0x006a63a0(354) now have
  complete observed algorithms and only18/11 byte differences; they are compiling
  hypotheses, not integrated or behaviorally verified results. These four cache
  targets offer1,094 estimated bytes before sparse allocation260 and cleanup.
- Mesh-pack0x00455200(279): new mixed-scope probe remains nonmatching; no unsafe
  source-padding workaround was adopted. Dispatch0x0041f240(519), swap327 and
  association constructor99 remain a945-byte opportunity after typed context
  ownership and constructor evidence improve. Context load5802 remains later.
- The21/11-byte bone destructors are compiled and behavior tested but ambiguous;
  their bytes are not included in the newly matching totals.

## Research, recovery and publication scope

This campaign reused pinned findings instead of repeating broad searches. The
private stack diagnostic applies reccmp's correspondence **idea** with original
Capstone/COFF code. Reference: reccmp
`4708baffc6bc271ff19dbd2e53b15cb67294ba53`, AGPLv3 ([COPYING](https://github.com/isledecomp/reccmp/blob/4708baffc6bc271ff19dbd2e53b15cb67294ba53/COPYING)); x86/MSVC stack analysis transfers, its linked/PDB matcher is not substituted.
Astralathe `0649071db7481ba8814c01c5717bdf6364dcda2b` (GPLv3) and prior
PsychoPortal/Studio serialization findings remain reference only. The local
PsychoPortal archive is `2a16f990ad843f84dafe10a2244f4246454c27a9` (GPLv3 plus its
stated exception); Studio's older recorded gitlink is `e00c3b529f65b5a9363b0d0cc1f1db9c4a0a7142`.
No incompatible implementation code was copied; new C++/fixtures derive from this
project's reference evidence and existing original source conventions.

Private plans, analyses, compilation probes, reports, pre-change copies, raw
objects and per-batch checkpoints stay ignored. `build/campaign/` contains the
baseline, failed selections, successful full runs, map reviews and final read-only
comparison; `.local/campaign-20261022/` contains the machine-readable state and
bounded failed attempts. Detailed hashes and resume pointers are private.

Exact campaign public-file scope: README.md; this report; native-reconstruction.md
and native-verification.json; engine/functions.csv, native-evidence.json and
progress.svg; src/game/resource_cache.cpp, resource_array.cpp, animation_stub.cpp
and skeleton_input.cpp; the seven new test suites listed above. Earlier dirty
mesh/stream files and their suites are preserved. No contributor infrastructure
is relocated, no files are staged, and there are no commits, pushes or publication.


## Reproduction and final evidence

Use the private REFERENCE/VC setup from CONTRIBUTING.md and this worktree's
existing tools. Target arguments for both batches are preserved privately; for
all currently promoted sources, the normal full run checks the complete map:

```sh
python -B contribute/tools/native_verify.py full "$REFERENCE" "$VC" \
  --rust-targets build/rust/reloc_targets.so --out build/reproduction-campaign
python -B contribute/tools/publication_check.py --worktree
```

The post-promotion Python-only comparison independently reproduces all3,389
matches /303,359bytes with zero new addresses and zero regressions. All66object
hashes and every captured source/test/tooling input remain unchanged from the
final full run. Metadata/map promotions are reviewed separately from those
frozen inputs. Full reports and per-row map review hashes follow.

- `build/campaign/baseline.json`: `25afae23f78e5adb054fe223e3306909577773662720089c3fb87ea05b9de92d`
- `build/campaign/full-02/verification.json`: `b2a2454842f66b03caa7fce77647bd678e5d5a9b744a0b68fd76a02324b9694c`
- `build/campaign/full-02/comparison.json`: `ff62dba9f4311db3fb41a982d9fb73e94462a7002ece6028994c3163861c0184`
- `build/campaign/full-03/verification.json`: `2ce73c568892dcde6c3fd82a92a52aac8e8aa37b2a13430cb933cd0e045ce12d`
- `build/campaign/full-03/comparison.json`: `9b91385ac9ad43709dee5ec44d9393093e4ebc78d8b6850c9d510478f222432b`
- `build/campaign/batch-01-map-review.json`: `5a2d4d28913b556705e77c137f5f1954e47e0ba18ef72a578ce3f9ca9a8cc739`
- `build/campaign/batch-02-map-review.json`: `a3126161a8b6001582b0b2bd51c49514417933db123a828851e42d5421d5f44c`
- `build/campaign/post-promotion-python.json`: `6ac8d2c3a3eba4023f7e1657bdf7e8532acc03b343cd18b28fbf953981c3753b`


Recorded native-verifier runtime totals 433.193seconds across25 development/full reports (347.797seconds in full runs), or0.1752seconds per reconstructed byte **for that verification scope only**. Private compile probes, standalone read-only comparisons and investigation are excluded. The snapshot-to-final wall interval spans approval/idle gaps and is not an active-engineering stopwatch; no total active-time rate is claimed.

Final consistency review confirms exactly18 campaign public files and13 individually reviewed CSV row changes, with all10,930 canonical addresses/sizes/origins preserved. All earlier mesh/stream sources and suites retain their starting hashes. Publication-content review checks283files with zero findings; no staging or publication is performed.
