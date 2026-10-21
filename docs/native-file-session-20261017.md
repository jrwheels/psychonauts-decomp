> Historical technical evidence, not the current setup/checkpoint. Use
> [CONTRIBUTING](../contribute/README.md) and [current native status](native-reconstruction.md).
> Original local report references identify private evidence, not required downloads.

# Native file-manager checkpoint — 2026-10-17

Resumed at HEAD a9a0eba with prior native/cast work preserved. Added two
reconstructed native bodies, relocation-aware matched at their unique VAs:
EFileManager::Open 0x006a9140 (197 bytes) and AcquirePackedFile 0x006aac10
(143 bytes). Current **2,908/10,930 functions; 235,180/2,935,679 mapped bytes**,
zero regressions. Cumulative gain over upstream: 38 functions / 5,364 bytes.
Reference remains the 2016 Steam Windows PE32, not the 2005 retail executable.

RTTI confirms EFileManager and EPackageFile::EPackageFileAccessor. Behavior,
offsets, vtable bounds, constructor dependencies and next method targets are
in native-file-manager.md. Partial source layouts must not be allocated.
Factory and four-slot pool globals remain external; no zero-initialized stub.

Verification:

* 55 fresh RTM x86 source objects compiled; audit
  build/audit/20261017T232908Z/summary.json. No compiler/install change.
* Full comparison build/batch-12-final.json: exactly two new matching
  addresses, no prior-match regressions. Report binds to pre-update CSV.
* Only two reviewed CSV rows updated. Backup
  .local/checkpoints/batch-12-functions.csv; before/after hashes and addresses
  in build/batch-12-map-update.json.
* 717 new original/rebuilt x86 differential cases pass, including all 256
  pool occupancy states, real dispatch/allocator chain, independent expected
  traces/mutations, calling convention and preserved-register checks.
  Report build/batch-12-behavior.json. Resolver/physical opener mocked.
* Existing 192 diagnostic cases rerun and pass after EFileManager type
  refinement: build/batch-12-diagnostics.json. Prior 1,331 sound cases/harness
  unchanged, not rerun. Cumulative verified case set: 2,240.
* All 102 repository tests pass. Cached index refreshed to include new evidence;
  10,930 function rows and 1,134 native Lua registrations. No full analysis.
* Both pre-existing dense-section files retain their checkpointed hashes.
  Prior source patches preserved. New cumulative source-only patch at
  .local/native-contribution-20261017-file-manager.patch passes reverse apply
  check; includes the new untracked file_manager.cpp. Hash in companion JSON.

Next bounded unit: accessor Read 0x006aad60 and helper 0x006aabb0, then Seek
0x006aadc0/Close 0x006aad40. Cached target exports already exist. Model only
observed layouts and preserve 32-bit overflow/underflow before adding safety
policy. Mock underlying virtual I/O to verify boundary behavior. EFileManager
constructor/destructor remain analyzed only, pending path/container ownership.
StopSound's older stack-read/accessor uncertainty remains deferred.

No game launch, asset/save/config/mod edits, dependency install, commit or push.
All changes remain uncommitted. See native-file-session-20261017.json for metrics
and engine/native-evidence.json for per-function milestones and limitations.
