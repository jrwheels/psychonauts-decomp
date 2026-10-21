# Native reconstruction status

This is the primary technical status page. Subsystem documents retain detailed
investigation history; their older totals describe those checkpoints rather
than superseding the current totals here.

The supported target is the Steam Windows PE32 executable, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
It is distinct from the unacquired 2005 retail build. Compilation uses VC++ 2008
RTM x86 `15.00.21022.08`, flags `/Od /Oy /Ob1 /Oi /MD /GS-`.

| Measurement | Current local result |
| --- | ---: |
| Matching functions | 3,375 / 10,930 |
| Matching mapped bytes | 300,735 / 2,935,679 (10.24%) |
| Additions over upstream `6959341` | 123 functions / 14,250 bytes |
| Fresh C/C++ source objects | 62 |
| Required synthetic tooling tests | 74 passed; 9 additional Rust tests passed when requested |
| Fresh original/rebuilt differential cases | 8,190 across 26 suites |
| Separate original-only CYSP cases | 44 |
| Lost previously matching addresses | 0 |

The [local pack-loading continuation](native-pack-loading.md) adds the 209-byte
two-byte string helper and 273-byte mesh unload body after full verification.
The 279-byte mesh-pack reader remains deferred on local-layout evidence.

The initial native publication was based on fork main `8154808` (3,360 functions /
298,986 bytes) and added 13 verified resource-list bodies /1,267 bytes. The local
integration on contributor-folder base `f1d0b46` adds the two pack-loading
dependencies /482 bytes and passes fresh complete verification. The older
clean reproduction is recorded in [clean review](native-clean-review.md). Both
[resource-list](native-resource-list.md) and [copy/lifetime](native-list-copy.md)
work are included; historical counts/timings in those documents describe their
original checkpoints. Required Python coverage and optional Rust are separate.
See [publication scope](../contribute/docs/publication-scope.md) and `native-verification.json` for
fresh candidate verification. All current matches must survive; matching remains
object-level and no linking/gameplay result is implied.

## Evidence levels and limits

**Confirmed:** matching uses the pinned binary and RTM compiler, full object-set
relocation constraints, and all preceding matching addresses. Independent
expected/original/rebuilt fixtures check bounded heap changes, call order,
returns and ABI. They use mocked allocation, file, Lua, audio or engine endpoints.
No game, save, installed mod or original asset changes are involved.

**Inferred:** many class/member/method names are provisional partial views.
Recorded offsets and observed dispatch slots are stronger evidence than those
names. RTTI identifies the existing `ETriggerA8` view as EMesh, but its current
spelling remains until a coordinated rename can preserve all caller layouts.
Runtime strides do not establish serialized record layouts.

**Unresolved:** the reconstructed engine is not linked or playable. Physical
I/O, actual resource loading, allocation failure integration and gameplay are
not established by mocked tests. Larger context/parser/mesh reader bodies remain
external. `EStream::ReadAllocatedString` is compiled and behaviorally tested but
has four unmatched temporary displacements and is excluded from match totals.

## Original behavior that must remain visible

- `ResourceContext::SetName` frees old storage before copying its input. An
  input aliasing that storage has an original-behavior lifetime hazard. Tests
  establish ordering only; they do not make a freed pointer safe to read.
- `ContextListBase` initializes an otherwise unused local to 10. Original
  instruction `0x006a5039` writes that local separately from member +0x08. Keep
  the initialization for binary matching; it is not speculative padding.
- `EMeshEntity::LoadMesh` passes pointer value 1 to `SetMesh` as an empty-mesh
  request on null-name/load-failure paths. It is a sentinel consumed by that
  callee, not a dereferenceable object pointer.
- Stream length operations preserve signed comparisons, wrapping counts and
  absent terminator/short-read checks. Matching source is not a hardened parser
  for arbitrary malformed input.

The constructor at `0x0041c670`, association Clear at `0x0041ffa0` and allocating
string helper at `0x006a5de0` are deferred on documented layout blockers. New
neighboring lifetime/inline evidence should precede further compiler probing.
These blockers are now machine-readable in the optional evidence workflow.

## Continue and reproduce

Start with [the native workflow](../contribute/docs/native-workflow.md): rank a focused dependency
neighborhood, review a small/medium/complex batch, compile affected objects,
check targets, then run relevant tests. Development compatibility never marks a
function globally matching. Full strict build and all-object regression checks
remain mandatory before any reviewed map promotion.

The original manual reproduction commands remain available:

```sh
python3 -B tools/strictbuild.py "$VC"
python3 -B tools/checkbaseline.py "$REFERENCE" engine/functions.csv \
  build/game/*.obj build/lua/*.obj --report build/reproduction/comparison.json
python3 -B contribute/tools/run_tooling_tests.py
for suite in tools/test_*.py; do
  python3 -B "$suite" "$REFERENCE" \
    --report "build/reproduction/$(basename "$suite" .py).json" || exit 1
done
```

Install contribute/requirements-dev.txt (including the numerical reference-test dependencies)
and put working Wine/winepath on PATH. The tooling runner omits optional Rust
explicitly unless requested, and rejects every required skip or failure. Binaries, compiler media, object files, logs, generated
plans and disassembly remain ignored. The canonical CSV and independent evidence
milestones are separate. Generated proposals do not alter either automatically.

## Detailed evidence by subsystem

| Area | Evidence |
| --- | --- |
| Reference/compiler | [Binary versions](binary-versions.md), [compiler research](compiler-research.md) |
| Diagnostic and file dispatch | [Diagnostics](native-diagnostics.md), [file manager](native-file-manager.md) |
| File/buffered lifetime and I/O | [Lifetimes](file-lifetime.md), [Win32 files](native-win32-file.md), [streaming](native-file-streaming.md) |
| Mesh/runtime skeleton | [Lookup](native-mesh-lookup.md), [replacement and IDs](native-mesh-replacement.md) |
| Resource input and lifetimes | [Streams](native-resource-stream.md), [contexts](native-resource-context.md) |
| CYSP dependencies and owners | [Parser investigation](native-resource-parser.md), [format distinctions](model-format-findings.md) |
| Pack-loading dependencies | [Two-byte strings, mesh unload and pack-reader blocker](native-pack-loading.md) |
| Recent bounded helpers | [Context name](native-context-name.md), [model input](native-model-input.md), [resource lists/pools](native-resource-list.md) |
| Tooling/data | [Function database](function-database.md), [Lua map](lua-api-map.md), [matching acceleration](../contribute/docs/matching-acceleration.md) |

The next engine work remains the resource-loading and mesh dependency path.
Measure verified bytes and useful dependency edges as well as function count.
