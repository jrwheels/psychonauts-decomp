> Historical technical evidence, not the current setup/checkpoint. Use
> [CONTRIBUTING](../contribute/README.md) and [current native status](native-reconstruction.md).
> Original local report references identify private evidence, not required downloads.

# Native continuation checkpoint — 2026-10-17

Starting state: HEAD a9a0eba, previous uncommitted native work preserved,
2,898 matching functions / 233,880 mapped bytes. No commit, push, game launch,
dependency installation, save/config/asset/mod-state change. Original reference
and toolchain are unchanged. The Steam 2016 target is not a 2005 retail reference.

## Verified additions

| Reconstructed body | VA | Mapped bytes |
| --- | --- | ---: |
| GetSoundName_impl | 0x00597fc0 | 260 |
| StopSoundsOnEntity_impl | 0x005991d0 | 108 |
| StopSoundInstance_impl | 0x005992a0 | 144 |
| EEntity::StopSounds (provisional method name) | 0x00421520 | 59 |
| NativeDiagnostic (provisional name) | 0x00402300 | 49 |
| DiagnosticSink::Write (provisional class/method names) | 0x004024d0 | 81 |
| DiagnosticSink::VPrintf (provisional class/method names) | 0x00402560 | 72 |
| DiagnosticStream::Write (provisional class/method names) | 0x006a4ee0 | 187 |

Eight source bodies add **960 matched bytes**. Final coverage:
**2,906 / 10,930 functions**, **234,840 / 2,935,679 mapped bytes**, zero
regressions. Cumulative gain over upstream: 36 functions / 5,024 bytes.
All **54 sources compile**, **102 repository tests** and **1,523 differential
cases pass**. Of those, 1,065 are the preserved prior cases; this continuation
adds 266 name/stop/native-entity cases and 192 diagnostic cases. Callees are
mocked as documented. This is object-level matching, not a linked/playable engine.

GetSoundName uses +0x28, correcting the previous checkpoint's provisional
+0x24 forecast. A zero handle diagnoses and returns no Lua values; unsigned
nonzero handles proceed. Missing manager/unavailable/name-null paths push
"Unknown". The diagnostic really executes; the existing disabled DebugPrintf
macro remains untouched. Native entity stop tests field +0x38 and dispatches
sound +0x38 without clearing the field. Its caller guards null entity/manager.
StopSoundInstance obtains both raw handles before the manager guard and calls
+0x30 with `(sound,0,instance)`, including zero handle values.

The recovered diagnostic chain and partial data/virtual interfaces are explained
in native-diagnostics.md. The native stream returns AL=true after successful
open even when downstream calls report failure. Formatter/file behavior remains
mocked; no real I/O or runtime-lifetime equivalence is claimed. Original class
names/sizes, factory option meanings, ignored virtual return types, and the
inline byte-count helper's original declaration are unknown.

## Reproducible evidence

* Full regressions: build/batch-09-10-final.json (seven additions),
  build/batch-11-extern-final.json (one addition), no lost addresses.
* Reviewed CSV backups: .local/checkpoints/batch-09-10-functions.csv and
  batch-11-functions.csv; corresponding build/*-map-update.json record
  before/after hashes. Reports bind to pre-update CSV, intentionally.
* Latest strict compiler audit: build/audit/20261017T231500Z/summary.json.
* Differential reports: build/native-continuation/*.json and
  build/batch-11-behavior.json. Unit log: build/native-continuation-unit-tests.log.
* Cached targets: build/native-index/target-ADDRESS.json. Curated records:
  engine/native-evidence.json; unknown milestones remain independent/null.
* Private bounded inline-overload/template compiler probe:
  .local/diagnostic-stream-layout.{cpp,obj,asm}. Only the overload model matches.

The first direct strlen expression folded a multiply and differed in temporary
layout; an explicit local added a copy. The bounded two-form probe resolved
that mismatch without assembly tricks. A short formatter mock initially omitted
its terminator; both binaries agreed on scanning the untouched bytes. The mock
was fixed and deliberate nontermination/boundary cases retained.

Reference data readback found the factory global initially points to 0x00795a38;
the newly introduced zero definition was removed before final validation.
It remains extern until original static object storage/construction is recovered.
build/diagnostic-extern-verification.json confirms all four diagnostic function
byte hashes stayed identical across that data-definition correction. The final
fresh build and full comparison verify the corrected source state.

## Next bounded work and blockers

1. Factory initializer 0x006fb930 calls 0x006a88b0 with ECX=0x00795a38 and
   registers 0x006fbd30 through 0x006ed27b. The latter calls 0x006a8ab0 on the
   same storage. Inspect those constructor/destructor targets, RTTI and actual
   static object extent before defining any instance or initializer in source.
2. StopSound_impl 0x005990a0 is deliberately still TODO. Its nonnull-entity path
   reads stack -0x10 into a temporary then overwrites it from entity+0x38.
   The accessor/temporary model is unresolved. No uninitialized-source fiction
   was added. Its bounded export/notes are saved; do not repeat broad analysis.
3. Follow the factory's native filesystem dispatch toward resource loading.
   Reuse cached GetResourceArg and package research; asset parsing success is
   not proof of equivalent native loader behavior.

Preserve both originally untracked dense-section files, all existing cast work,
and the prior contribution patch. No Git history changes were made. The latest
compact metrics and source-patch location are in native-continuation-20261017.json.
