> Historical technical evidence, not the current setup/checkpoint. Use
> [CONTRIBUTING](../contribute/README.md) and [current native status](native-reconstruction.md).
> Original local report references identify private evidence, not required downloads.

# Native package-accessor checkpoint — 2026-10-17

Resumed at HEAD a9a0eba with existing uncommitted work preserved. Five native
bodies now match at unique expected addresses, adding **283 mapped bytes**:

| Body (method names provisional) | Address | Bytes |
| --- | --- | ---: |
| ReadPackedData | 0x006aabb0 | 89 |
| PackedFileSlot::Close | 0x006aad40 | 31 |
| PackedFileSlot::Read | 0x006aad60 | 73 |
| PackedFileSlot::Seek | 0x006aadc0 | 70 |
| PackedFileSlot::Size | 0x006aae10 | 20 |

Total **2,913/10,930 functions; 235,463/2,935,679 mapped bytes**, zero
regressions. Cumulative gain over upstream: 43 bodies /5,647 bytes. Reference
remains Steam Windows 2016 PE32; no 2005 retail reference has been acquired.

Source remains in file_manager.cpp. PackedFileSlot is a partial opaque view
of RTTI-confirmed EPackageFile::EPackageFileAccessor. Its vtable/lifetime are
not reconstructed or instantiated. Factory/pool globals remain external.
DiagnosticFile slot +8 now models the observed two-argument Read signature.
Read preserves wrapping 32-bit arithmetic and past-end count underflow; Seek
supports origins zero/one only; Close preserves cursor; Size reads entry+0xc.
Detailed evidence and limitations are in native-file-manager.md.

Verification:

* All 55 sources compile with RTM x86; 2,918 COFF function records. Strict
  audit build/audit/20261017T233406Z/summary.json, no compiler failures.
* build/batch-13-final.json: five new relocation-aware matches, no regressions.
  Five CSV rows reviewed individually; backup
  .local/checkpoints/batch-13-functions.csv and hashes in
  build/batch-13-map-update.json. Report binds to pre-update CSV.
* 385 new differential cases pass: actual Read/helper chain, explicit boundary
  fixtures, all fixture-heap bytes, ABI and nonvolatile registers. Underlying
  file calls mocked; no real filesystem/lifetime equivalence claimed.
* Existing 717 file-manager and 192 diagnostic cases rerun and pass after
  shared interface/source changes. This batch ran 1,294 cases. Prior 1,331
  sound cases/harness unchanged, not rerun. Cumulative verified set: 2,625.
* All 102 repository tests pass. Evidence overlay and cached index refreshed;
  no full discovery or Ghidra rerun. Existing dense-section files retain hashes.
* Separate cumulative source patch
  .local/native-contribution-20261017-package-accessor.patch includes untracked
  source and passes reverse apply check. Earlier patches preserved.

Next bounded unit is RTTI-confirmed EReadBufferedFile::Read 0x006a9ee0
(313 bytes) and Refill 0x006aa080 (60 bytes). Cached exports and control-flow
notes are ready. Read uses signed minimum comparisons but an unsigned
capacity threshold and refills at most once; recover types deliberately.
Its copy thunk 0x006ed156 jumps through 0x007002c0 to MSVCR90.dll memcpy,
independently verified from the import table. No buffered source claimed yet.
Constructor/destructor path/ownership questions and older StopSound accessor
uncertainty remain deferred.

No game launch, asset/save/config/mod changes, dependency installation, commit
or push. Changes remain uncommitted. Companion JSON retains counts/hashes;
engine/native-evidence.json records distinct per-function milestones.
