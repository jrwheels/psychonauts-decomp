# Native reconstruction checkpoint

Based on DrDecki upstream main `6959341ed94edeb17d77ad39c3b59ae5dd8f5011`.
The contribution adds 82 native C++ matches / 9,569 mapped bytes to upstream's
3,252 matches / 286,485 bytes: **3,334 / 10,930 functions and
296,054 / 2,935,679 mapped bytes**. Existing upstream matching rows, names,
addresses, sizes and provenance are preserved. The progress SVG is generated
with the unchanged upstream `tools/progressmap.py`.

The fresh contribution check compiled all 58 sources, retained every previous
match, and passed 18 native tooling unit tests and all 4,326 isolated differential
cases. [Verification metadata](native-verification.json) records the results,
new addresses, toolchain and report hashes.

## Scope and integration

Recovered bodies cover sound bindings and handle helpers, one camera default,
the diagnostic chain, EFileManager dispatch, pooled package access, buffered
reader/writer methods and lifetimes, native Win32 file methods, and native
opening/streaming lifetime/producer methods. Partial class layouts retain
observed offsets and virtual slots. External storage and initialization remain
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

Next bounded targets are streaming Read 0x006a7730 and file-manager construction
0x006a88b0. Slot +0x18 is identified as last-write FILETIME for EWin32File.
Original filename-helper spellings, allocation category meanings, complete
runtime ownership and concurrent streaming behavior remain unresolved. No full
EFile runtime is claimed.
