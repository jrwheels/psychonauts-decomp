# Native reconstruction checkpoint

Based on DrDecki upstream main `6959341ed94edeb17d77ad39c3b59ae5dd8f5011`.
The contribution adds108matched native bodies /12,501mapped bytes beyond that
baseline: **3,360/10,930 functions and298,986/2,935,679mapped bytes**.
All preceding matching rows, addresses and provenance are preserved.

Latest: [model input helpers](native-model-input.md). All62sources compile
strictly;29tooling tests and1,888fresh differential cases pass.60unaffected
objects preserve4,602prior cases:6,490applicable total. The allocating stream
helper is behaviorally verified but remains unmatched at four temporary stack
offsets; it is excluded from matching totals. Real I/O/gameplay and a linked
playable engine remain outside this verification.

## Scope and integration

Recovered bodies cover sound bindings and handle helpers, one camera default,
the diagnostic chain, EFileManager dispatch, pooled package access, buffered
reader/writer methods and lifetimes, native Win32 file methods, streaming
consumer/producer/lifetime methods, mesh replacement, animation-state setup and
skeleton lookup/IDs. Partial class layouts retain observed offsets and virtual
slots. External storage and initialization remain
external where lifetime or ownership is unresolved. Names and semantic types are provisional
unless independently corroborated.

Upstream's four latest commits added 382 matches / 56,669 bytes over the earlier
common base. The contribution is based directly on those commits. It combines
the shared ESoundManager declaration with upstream debug-menu dispatch while
preserving upstream entity flags and GameApp layout. It retains upstream's
`/Oy` flag and its matcher, with one additional bounds guard for duplicate
string relocation pointers. A below-image address must not match through
Python negative indexing. Dedicated synthetic tests cover that guard and
upstream import-decoration/duplicate-string behavior.

Local names and scopes reproduce VC++ 2008 stack layout without claiming
recovered original identifiers. Keeping buffered Flush inside its partial class
reproduces the caller's unused temporary slots, following upstream's compiler
evidence. No inline assembly or invented uninitialized locals were added.

## Reproduction

Use an owned copy of the Windows Steam reference; binaries and compiler media
are deliberately absent. Reference SHA-1:
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`; SHA-256:
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
This later Steam executable is distinct from an unverified 2005 retail build.
See [binary identities](binary-versions.md) and [compiler evidence](compiler-research.md).

Set `VC` to VC++ 2008 RTM x86 (15.00.21022.08), `REFERENCE` to the owned
executable, and put working Wine/winepath and Python dependencies on PATH.
Python dependencies used for this checkpoint are pefile 2024.8.26,
Capstone 5.0.9 and Unicorn 2.1.4. Current flags:
`/Od /Oy /Ob1 /Oi /MD /GS-`.

```sh
python3 -B tools/strictbuild.py "$VC"
python3 -B tools/checkbaseline.py "$REFERENCE" engine/functions.csv \
  build/game/*.obj build/lua/*.obj --report build/github-preparation/comparison.json
python3 -B -m unittest discover -s tests -v
for suite in tools/test_*.py; do
  python3 -B "$suite" "$REFERENCE" \
    --report "build/github-preparation/$(basename "$suite" .py).json" || exit 1
done
```

The strict wrapper invokes unchanged upstream build.sh, captures actual compiler
exits that its pipeline can mask, rejects the wrong compiler, and verifies fresh
parseable objects for every source. The read-only comparison hash-gates the
reference and checks every previously matching CSV address; it never writes
the map. Reports and objects stay under ignored `build/`.

`engine/native-evidence.json` is a curated overlay, separate from the canonical
CSV. It preserves independent analyzed/reconstructed/compiled/behavior/matching
properties and unresolved findings. Historical report paths in it refer to
local ignored evidence, not artifacts distributed with this source contribution.
Current rerun commands above regenerate the comparison and differential reports.
See [database schema](function-database.md) and [Lua registrations](lua-api-map.md).
The index's optional disassembly and original binary data remain ignored.

## Verification limits and next work

Differential tests execute original and reconstructed x86 with mocked callees,
checking return values, call traces, state, ABI and bounded arithmetic edges.
The buffered tests execute the Read/Refill and Write/Flush/Seek chains. Selected
huge or invalid copy requests are traced without dereferencing them. These
cases establish observed integer/call behavior, not safe CRT handling of invalid
pointers or actual filesystem, Lua, audio or gameplay equivalence.

File-manager RTTI and dispatch details are in [native-file-manager.md](native-file-manager.md).
Diagnostic behavior and formatting limits are in [native-diagnostics.md](native-diagnostics.md).
The canonical map counts matches independently from individual behavioral tests.
A collection of matching objects is not a linked or playable engine.

The [buffered-file lifetime continuation](file-lifetime.md) adds 14 matches /997
bytes over fork d2c5583: constructors, destructors, aligned filename helpers,
scalar deleting wrappers and additional file forwarders. All previous 3,301
matching rows remain unchanged. The 329 new lifetime cases and all 3,078 prior
cases pass against the same strict build.

The [Win32 file continuation](native-win32-file.md) adds 11 matches /838
bytes over that lifetime checkpoint. All 3,315 preceding matching rows are
unchanged. The 371 new file cases and all 3,407 preceding cases pass against
58 freshly compiled sources.

The [native opener and streaming continuation](native-file-streaming.md) adds
eight matches /1,377 bytes. All 3,326 preceding matching rows remain unchanged.
Its 548 cases and all 3,778 preceding cases pass. The latest full comparison ran
against the previous CSV before these eight reviewed promotions; its map-update
report binds those exact edits to the comparison. No compiled code changed
afterward. Supplementary Rust objdiff review confirms the 14 previously defined
native-file bodies remain unchanged; it adds no engine or build dependency.

Streaming Read at 0x006a7730 now matches /355 bytes, preserving all previous
3,334 addresses. The fresh 58-source strict build, 29 tooling tests and 4,510
differential cases pass. Its consumer fixture adds 184 cases, including bounded
waits after data runs out; the original has no consumer EOF/stop check.

The [native mesh and skeleton lookup](native-mesh-lookup.md) adds four matches
/550 bytes and 774 fresh original/rebuilt/expected x86 cases. All previous
3,335 matching rows are unchanged. The 59-source strict build and full matcher
pass; prior differential evidence is reused with byte-level COFF parity.

The [mesh replacement and ID continuation](native-mesh-replacement.md) adds
six matches /705 bytes. EMeshEntity::LoadMesh 0x0043c980 now matches, with
empty-instance creation, lazy animation state, blend-shape binding and bone-ID
packing. All preceding 3,339 matching rows are unchanged; the fresh suites pass
388 replacement/ID and 774 lookup cases. The original external SetMesh executes
in both test chains, while constructors and resource/rendering services are mocked.

The [model-loading call graph](model-loading-next.md) connects the common loader
to EFileReader dispatch at 0x0041f240, the next serialization target. SetMesh
0x0043cad0 remains blocked on a compiler register phase difference. RTTI confirms
that the existing ETriggerA8 view is EMesh; its provisional spelling is retained.
[Format findings](model-format-findings.md) separate native ID packing from the
still unverified serialized-to-runtime ordering and actual animation behavior.

The [resource-stream continuation](native-resource-stream.md) adds six matches
/456 bytes: EFileReader input, file-stream lifetime/name forwarding, the owning
file-to-resource bridge and first-result transfer. All 3,345 previous matching
rows are unchanged. The larger resource dispatcher remains external while its
context, parser and auxiliary record lifetimes are recovered. Four supporting
short COMDAT bodies are behaviorally tested but remain outside match totals.

[Optional Rust relocation decoding](matching-acceleration.md) reduces the measured
matching phase from 102.1 to 10.8 seconds while preserving all match, candidate
and known-symbol results. The 29 tooling tests include nine optional Rust tests.
It changes no engine source, compiler flags, reference identity or map entries.

The [resource-context continuation](native-resource-context.md) adds three
matches /205 bytes for context destruction and list construction/destruction.
Context constructor and array-clear probes remain unmatched. Bounded parser
inspection confirms native CYSP signature and version-word handling; it does
not establish complete model decoding.

The [CYSP dependency continuation](native-resource-parser.md) adds four matches
/527 bytes: string transfer, list lookup/cleanup and recursive owner propagation.
Header and dependency fixtures establish native version/flag behavior and a
context-to-EMesh reader edge. Constructor, association Clear and the larger
parser/context reader remain unmatched; no existing match was sacrificed.

Latest continuation: [context name ownership](native-context-name.md), one body
/61bytes;62sources compile,82affected differential and29tooling tests pass.
Parent upstream checked2026-10-20:6959341 unchanged;no merge required.
