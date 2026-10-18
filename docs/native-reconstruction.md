# Native reconstruction checkpoint

Based on DrDecki upstream main `6959341ed94edeb17d77ad39c3b59ae5dd8f5011`.
The contribution adds 49 native C++ matches / 6,357 mapped bytes to upstream's
3,252 matches / 286,485 bytes: **3,301 / 10,930 functions and
292,842 / 2,935,679 mapped bytes**. Existing upstream matching rows, names,
addresses, sizes and provenance are preserved. The progress SVG is generated
with the unchanged upstream `tools/progressmap.py`.

The fresh contribution check compiled all 56 sources, retained every previous
match, and passed 18 native tooling unit tests and all 3,078 isolated differential
cases. [Verification metadata](native-verification.json) records the results,
new addresses, toolchain and report hashes.

## Scope and integration

Recovered bodies cover sound bindings and handle helpers, one camera default,
the diagnostic chain, EFileManager dispatch, pooled package access, and all six
buffered reader/writer methods. Partial class layouts retain observed offsets
and virtual slots. External storage and initialization remain external where
lifetime or ownership is unresolved. Names and semantic types are provisional
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

Next bounded targets are EFile and buffered-file lifetime/ownership. Writer
0x006a9dd0 and reader 0x006aa0f0 destructors are analyzed only; scalar deleting
wrappers and helper 0x006a6e30 require allocation/ownership evidence before
source reconstruction. No replacement initialization or ownership model is
asserted by this contribution.
