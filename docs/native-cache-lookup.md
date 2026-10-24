# Resource cache lookup and external research — 2026-10-22

Continuation of local base `bf6104ac0b481e22ff917d6394f64eabda34f3d6` and the
verified pack-string/unload checkpoint. The parent was fetched and its complete
published ref list checked: HEAD/main remain
`6959341ed94edeb17d77ad39c3b59ae5dd8f5011`; no additional branches or tags were
advertised. There was nothing new to integrate. Existing dirty work is preserved.

## Cache dependency

`src/game/resource_cache.cpp` reconstructs 0x006a6510 (69 mapped bytes), using
provisional names `ResourceCache::Lookup` and `ResourceCache::Find`. The latter
is the external 0x006a66a0 helper, called with the name and null bucket output.
A null handle returns the caller's fallback. Otherwise the low 31 handle bits
index 12-byte entries through cache+0x08 and the method returns entry+0x04,
including null values. It performs no index, pointer or string validation.
The view is incomplete and must not be allocated as a full engine object.

The insertion neighbor 0x006a63a0 independently corroborates the stride and
value offset: its hit path reads the previous value and replaces entry+0x04.
Its miss path links a new name/value/next record through bucket storage. This
supports a hash-cache interpretation, but does not establish complete allocation
or ownership semantics. Astralathe's existing EHashTable<uint>::Find signature
also corroborates this endpoint's instruction pattern; no GPL implementation
was imported. Existing provisional source names are retained rather than
asserting an original class identity or pointer-versus-integer template type.

The first RTM compile reproduces all 69 bytes outside the ordinary call relocation.
`tools/test_resource_cache.py` adds 512 original/rebuilt/independent-expectation
cases: hit/miss, 16 indices, both high-bit flags, four fallback values, and null
or nonnull name pointers forwarded to the mocked helper. Fixtures include null,
1, -1 and ordinary pointer values. Tests check unchanged fixture memory, exactly
one helper call, this/name/null-output arguments, callee-saved registers and ret8.
Hash lookup, hashing, invalid handles/indices, allocation, physical I/O and gameplay
are excluded. Null-name forwarding does not establish actual helper acceptance.

Private development/behavior/full reports are under `build/cache-lookup/`.
Full verification passes: 63 fresh RTM objects; 3,376 matching functions /
300,804 bytes, up from 3,375 /300,735, with zero lost addresses. All 74 required
Python tooling tests pass without skips. Optional Rust was not requested. All
8,702 differential cases across 27 suites and 44 separate original-only cases
ran fresh and pass. Only the reviewed 0x006a6510 CSV row is promoted. No linked
engine or game test is claimed; no commit, push, publication or installation.
Host Python 3.13.5; capstone 5.0.9, pefile 2024.8.26, Unicorn 2.1.4,
numpy 2.5.4 and Pillow 12.3.0. Reference hashes and unchanged RTM compiler/flags
are recorded in native-verification.json.

## Reusable work from other projects

The practical comparison axis is PE32 x86, MSVC C++, COFF/PDB and original-compiler
matching. Matching engine ancestry is stronger evidence for source reuse than
release date, genre or a similar archive extension. No foreign game body was
substituted for Psychonauts behavior.

| Project | Observed compatibility and usable result |
| --- | --- |
| [LEGO Island / reccmp](https://github.com/isledecomp/reccmp/blob/4708baffc6bc271ff19dbd2e53b15cb67294ba53/reccmp/tools/stackcmp.py) | Old MSVC x86 comparison tooling; its stack correspondence/ambiguity diagnostic is directly useful for our local-layout blockers. PDB/linked-image setup is not a drop-in replacement for our object matcher. |
| [Touhou 6](https://github.com/GensokyoClub/th06/blob/79db08a71f492d86a763639bc61037c74cd80232/README.md) | VS2002, DirectX8, Wine-hosted build and reccmp. Useful toolchain/workflow comparison; distinct compiler and engine. Compiler var_order patch not adopted. |
| [Touhou 7](https://github.com/some100/th07/blob/4878bf0e42a9280ef44735eb0517d4fda7cb6e04/README.md) | MSVC2002 Win32; explicitly credits th06 types/organization and th08 memory/LZSS/math reuse. Demonstrates strong reuse within shared engine lineage, not evidence for Psychonauts container layouts. |
| [Meteor / FFXIV 1.x](https://github.com/swstegall/meteor-decomp/blob/424c1bfc4d737920f8c564dc1202de343c11ad7d/src/ffxivgame/_rosetta/FUN_00411fa0.cpp) | Search inspection found naked-assembly reproduction; those bodies cannot advance this project's real-C++ matching requirements. No import. |
| [VC8 compiler decomp](https://github.com/lemiur/vc8-decomp/blob/master/README.md) | Adjacent MSVC generation; bounded evidence, referent checks and explicit unadmitted candidates are useful review ideas. Compiler-driver reconstruction supplies no engine bodies and is not a replacement RTM compiler. |
| Astralathe / Open-Li-Po | Existing private source pins remain 0649071db7481ba8814c01c5717bdf6364dcda2b / 1f37d5dfb72eb1b94f8e6ffa7a998fdef003fbd9. Astralathe signature cross-check above is useful; Open-Li-Po's searched hash implementations are third-party Lua/mojoshader, not evidence for this cache. |

An original private Capstone/COFF diagnostic adapts the **idea** of stack-slot
correspondence from reccmp; no external implementation text is copied. It stays
under ignored local research and does not affect verification or matcher behavior.
Four synthetic controls cover identity, swapped slots, merged slots and structural
gaps. The cache control aligns all 25 instruction shapes with identical slots.
The existing blocked mesh-pack probe aligns 77/78 instruction shapes and maps
slots one-to-one, with a structural gap explicitly flagged. This is a diagnostic,
not semantic equivalence, a match, or evidence to invent source padding.

Inspection of the next animation reader 0x00495e60 confirms two 4-byte fields,
a capacity-260 String2b, and a conditional pair of 16-bit fields followed by a
count-times-14 payload read. This is not a mesh-pack per-record struct and does
not justify replacing the blocked reader's independent locals with one. No new
compiler-layout probes were attempted without that missing source evidence.

Next related work: reconstruct the bounded cache-search helper 0x006a66a0 and
inspect insertion 0x006a63a0 with its allocator/growth dependencies. Mesh-pack
0x00455200 remains deferred; compiler flags and output are unchanged.

## Reproduce and review

With the private reference/compiler configured as in CONTRIBUTING.md:

```sh
python -B contribute/tools/native_verify.py dev "$REFERENCE" "$VC" \
  --source src/game/resource_cache.cpp \
  --target '0x006a6510=ResourceCache::Lookup' --out build/cache-dev
python -B contribute/tools/native_verify.py full "$REFERENCE" "$VC" \
  --target '0x006a6510=ResourceCache::Lookup' --out build/cache-full
python -B contribute/tools/publication_check.py --worktree
```

The full run used Python relocation decoding; optional Rust was not requested.
Full report SHA-256:
`caab945f32eced828e1a3720366d4b4dc17a490dcd3ee07facdc19a4656eb4f5`.
All 11 recorded source/document/map hashes from the preceding checkpoint were
checked against pre-change copies or the full verifier's captured inputs.

This continuation adds `src/game/resource_cache.cpp`,
`tools/test_resource_cache.py`, and this document. It updates `README.md`,
`docs/native-reconstruction.md`, `docs/native-verification.json`,
`engine/functions.csv`, `engine/native-evidence.json` and `engine/progress.svg`.
Earlier dirty mesh/stream sources, suites and pack-loading notes are preserved.
Detailed reports, the diagnostic script/fixtures, source hashes and recovery state
remain private and ignored. Worktree publication-content checks pass with no
findings; this is a local check, not publication or approval to publish.

Post-promotion Python matching independently reproduces all 3,376 matches with
zero new addresses and zero regressions. All 63 object hashes and all captured
source/test/tooling inputs remain identical to the full verification run.
