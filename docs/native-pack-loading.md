# Pack-loading dependencies — 2026-10-21

Reconstruction originated from published `bf6104ac0b481e22ff917d6394f64eabda34f3d6`.
The two bodies and their tests are integrated without changes on contributor-folder
base `f1d0b46a9449e7ea7d6ce49ec057448a1b6e0bfd`.
Reference: Steam Windows PE32 SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
VC++2008 RTM x86 `15.00.21022.08`, `/Od /Oy /Ob1 /Oi /MD /GS-`.

| Attempt | Mapped bytes | Outcome |
| --- | ---: | --- |
| 0x006a5c30, EStream::ReadString2b | 209 | Unique full-object match; 356 differential cases |
| 0x00455200, proposed EMeshManager::ReadPackFile | 279 | Compiling private probes; unmatched local layout; deferred |
| 0x00454f70, EMeshManager::Destroy | 273 | Unique full-object match; 768 differential cases |

Two matches add **482 bytes**: **3,375 /10,930 functions,
300,735 /2,935,679 bytes**, zero regressions. No commit/push or public-main
modification accompanies this local checkpoint. All earlier worktrees remain
separate, including the dirty original checkout and published source.

## Two-byte stream string

The matched four-byte helper at 0x006a5d10 supplies the source pattern. The
new body changes the length to `unsigned short` and transfers a two-byte header;
its integer promotion makes the capacity comparison signed. The first direct
RTM compilation agrees in all 209 mapped bytes; the object's remaining 15
bytes are ordinary int3 alignment, excluded from the mapped-byte count.
There are no relocations. No compiler-output modification was used.

Mode 1 measures strlen, adds one, narrows to 16 bits, and transfers that word.
All modes then transfer payload only when length is nonzero and strictly less
than the signed capacity; otherwise they call the virtual transfer with null.
Only mode 0 clears output[0] on this latter path. Equal capacities do not fit;
negative capacities reject every nonzero 16-bit length. Other flag values do
not trigger the mode-0 clear or mode-1 measurement.

The function allocates no storage, validates no terminator, checks no transfer
result, and does not add a terminator after reading. A writing input with 65,535
characters narrows strlen+1 to zero; 65,536 characters narrow to one. An empty
writing string encodes length one. Null input in writing mode faults during
strlen; null output on a rejected mode-0 read faults when it is cleared. A null
pointer passed to an otherwise fitting transfer is still passed through. No
safeguards were borrowed from external parsers.

`tools/test_stream_string2b.py` independently predicts original/rebuilt callback
traces, all fixture bytes, controlled faults and return ABI. Its 356 cases cover
lengths through 65,535; signed-capacity boundaries; short headers with explicitly
poisoned stack bytes; partial/nonterminated payloads; modes 0/1/2/-1; and strlen
inputs through 131,071 characters. Virtual transfers are mocks. Poisoned partial
headers establish this fixture's observed x86 behavior, not portable semantics
for indeterminate C++ values or actual physical I/O.

## Mesh-pack reader blocker

0x00455200 reads an unchecked four-byte word, then a 16-bit record count. Each
record uses the new string helper with capacity 260, then a 16-bit type and
32-bit payload size. Cache hits call file Seek(size,1) through reader+0x10 and
file vtable+0x10. Misses call dispatcher 0x0041f240 through GameApp+0x81b4, then
cache insertion 0x006a63a0, including null results. Cache lookup is 0x006a6510.
The enclosing reader does not validate MPAK magic; external parsers' validation
must not be copied into it. Allocator/cache ownership is still external.

Fifteen compiling scope/local-name variants were retained privately. Their
267–285-byte bodies do not reproduce the native local placement. The native
header/count/index/result/name/type/size slots are -0x04/-0x08/-0x0c/-0x10/
-0x118/-0x11c/-0x120. A representative loop variant has the right frame and
header/count/index but places type/result/size/name at -0x10/-0x14/-0x18/-0x120.
The ordinary inline GetFile getter does reproduce the seemingly redundant
uninitialized temporary copy; it was not necessary to invent padding or a
wrapper class for that behavior. Different local placements also change branch
displacements and extent. No private body is counted as a reconstruction or
behavioral equivalence result, and no failed body was added to canonical source.

Probe sources, logs and reports remain under `.local/probe/meshpack-*` in the
original private reconstruction worktree; integration does not move or publish them. Recover per-record lexical/type evidence from animation/stub readers
before retrying the same layout experiment. No broad search or altered flags.

## Mesh-unload fallback

The existing provisional spelling EMeshManager::Destroy is kept; Astralathe's
hook identifies this endpoint as UnloadMesh. Offset-based MeshLifetimeView and
MeshOwnerLifetimeView cover only observed fields and virtual slots. They must
not be allocated as complete game objects. Upper 27-bit fields are named for
their position, not assigned reference-count/container ownership semantics.

Immediate deleting virtual slot +0 with argument 1 requires link+0x08 != -1,
zero high bits at +0x3c/+0x48, zero owner+0x80/+0xa0 and zero mesh+0x60.
Otherwise the method calls cdecl helper 0x0040eea0, then virtual slot +0x08,
then rereads link+0x08; only a nonnull/non--1 link permits deleting slot +0.
Cleanup's meaning and virtual slot +0x08's original name remain unresolved.

The first private body matched the pre-cleanup portion but lacked the two
post-cleanup inline Boolean expansions. Using predicates for null and -1, as
already indicated by those instruction sequences, produces the complete
273-byte match on the third bounded probe. Its sole relocation is the cdecl
cleanup endpoint. The full matcher resolves it consistently with the original
0x0040eea0 target. No guessed padding, artificial instructions or output patching.

`tools/test_mesh_unload.py` extends the audit's 768 original-only fixtures to
original/rebuilt/independent-expected comparisons. All 64 combinations of six
predicates are tested with null/non-null initial links, the -1 sentinel,
post-cleanup null/-1/non-null links, low-five-bit metadata and high bit31.
The harness checks all 4,096 fixture heap bytes, exact call order/arguments,
saved registers and ret4. Global cleanup and virtual endpoints are mocks;
physical deletion, invalid mesh/owner pointers and gameplay remain untested.

## Verification and provenance

Both promotions followed fresh strict builds of all 62 sources and full-object
selection with unchanged RTM flags. The final run retains all 3,374 preceding
matches and selects only unload as new. All **74 required tooling tests plus
9 optional Rust tests pass**, with **8,190 fresh differential cases across
26 suites** and **44 separate original-only CYSP cases**. The new suites add
356 +768 =1,124 differential cases to the 7,066 baseline. All tests ran fresh;
the audit's prior original-only count is not added a second time. Neither a
linked/playable engine nor a game test is implied.

Private reports: `build/pack-strings/full-string/`, `full-unload/`,
`string-map-review.json`, `final-map-review.json`; final post-promotion Python
comparison is `post-promotion-python.json`: it independently reproduces the
complete Rust-assisted match set with zero new addresses and zero regressions.
All code, data and decoded relocations in 60 unaffected objects reproduce;
raw COFF files retain different checkout paths in .debug$S metadata. The CSV changes only the two
reviewed rows. See native-verification.json for report hashes and current totals.

The prior audit and its exact source pins stay under ignored local research.
The original signatures come from Astralathe
`0649071db7481ba8814c01c5717bdf6364dcda2b` (GPLv3; reference only).
PsychoPortal, Studio's exact gitlink
`e00c3b529f65b5a9363b0d0cc1f1db9c4a0a7142`, corroborates String2b and pack
record widths; its parser safeguards were not copied. C++ source and independent
fixtures here were reconstructed from this project's original-binary evidence
and existing source conventions, without importing external implementations.

Next prioritize typed cache/dispatcher interfaces and animation-stub reader
0x00495e60 before another mesh-pack layout attempt; alternatively inspect cleanup
0x0040eea0 and mesh virtual slot +0x08 for stronger lifetime evidence. Preserve
existing constructor/allocated-string blockers unless new evidence changes them.


## Contributor-folder integration — 2026-10-21

A separate local integration on published `f1d0b46` carries only the two verified
functions, their map/evidence changes and these tests/docs. The contributor subtree,
relocated commands/imports, requirements and CI remain unchanged. Original source,
research probes and the separate ReSkate project remain untouched.

Fresh `contribute/tools/native_verify.py full` verification compiles all 62 sources
with the same RTM compiler/flags, retains all 3,373 published matches, uniquely
selects the two additions and reproduces 3,375 matches /300,735 bytes. All 26
original/rebuilt suites run, including string2b (356) and mesh unload (768): 8,190
differential cases plus 44 original-only cases pass. Required tooling coverage is
74 tests; the additional nine Rust tests pass separately. Python-only full matching
agrees exactly with Rust-assisted matching, and required Python-only coverage passes.
No contributor-path repairs or game-behavior changes were needed.

Current private reports are `build/integration/full/verification.json`,
`build/integration/full/comparison.json`, `build/integration/python-matching.json`
and `build/integration/python-tooling.json`. Publication checks cover the candidate
worktree, published base and reachable history. Canonical 10,930 addresses/sizes
are unchanged. These are object-level and mocked-behavior results, not a linked
or playable engine. The verified cached Rust library was reused with its recorded
hash and unchanged source because the host Rust compiler is unavailable; its nine
synthetic tests and complete match pass were freshly executed. Hosted CI and a
clean external environment were not exercised by this local integration.
