> Historical technical evidence, not the current setup/checkpoint. Use
> [CONTRIBUTING](../CONTRIBUTING.md) and [current native status](native-reconstruction.md).
> Original local report references identify private evidence, not required downloads.

# Native buffered-file checkpoint — 2026-10-17

Reference: Steam Windows 2016 PE32, SHA-256
cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3.
Current verified combined state: **3,301/10,930 matching functions,
292,842/2,935,679 mapped bytes**, zero regressions. Upstream comparison and
recovery snapshot: upstream-sync.md.

HEAD a9a0eba; earlier uncommitted native work preserved. No game/mod/asset work,
launch, dependency install, commit or push. No 2005 retail equivalence claimed.

## Batch 14: buffered reader

EReadBufferedFile::Read 0x006a9ee0 (313 bytes) and Refill 0x006aa080 (60 bytes)
match uniquely with full relocation constraints. Total 2,915/10,930 functions,
235,836/2,935,679 mapped bytes; no regressions. All 56 sources compile with
VC++ 2008 RTM x86; strict audit build/audit/20261017T234410Z/summary.json.
Read explicitly compares both minima as signed int while arithmetic remains
unsigned and wrapping. The direct-read capacity threshold is unsigned.
Remaining count equal to capacity triggers refill; larger counts bypass it.
A short/failed refill is attempted once. Fields and opaque class layout are
documented in src/game/buffered_file.cpp; no inheritance/lifetime reconstruction.

148 new differential cases pass, checking the real Read/Refill chain, all
fixture heap bytes, call traces, return values and ABI. Normal fixtures model
memcpy with bounded bytes; six exceptional fixtures trace huge/invalid copy
requests without dereferencing them. Those fixtures establish integer/call
behavior, not CRT validity of bad pointers. Underlying file reads are mocked.
Report build/batch-14-behavior.json. Existing unchanged tests are not rerun
in this batch. Cumulative verified cases: 2,773 (prior 2,625 plus 148).

Full check build/batch-14-final.json, reviewed CSV update and hashes
build/batch-14-map-update.json, backup .local/checkpoints/batch-14-functions.csv.
Function evidence overlay updated. Reports intentionally bind pre-update CSV.

Read initially differed in local stack slots. Moving its six locals into one
scope and using semantic aliases reproduced the layout. Mechanical probes
tested 512 then 2,048 naming variants in under two seconds of compiler time;
18 second-pass variants matched, with the first accepted. Only local names
and declaration scopes varied; no instructions or behavior were injected.
Private sources/COFF/results are .local/buffered-read-{variants,more}.* and
.local/buffered-read-more-matches.json. These names are not recovered names.

## Related native work in progress

Buffered writer Write 0x006a9ca0 (175), Flush 0x006a9d50 (80), Seek
0x006a9c00 (50) were inspected from cached exports. Flush writes pending bytes
once, ignores the write result, and clears pending count/start even on failure.
Empty flush preserves start. A local provisional Flush already matches.
Write/Seek prototypes have unexplained unused stack slots; direct and existing
three-argument forwarding probes are retained in .local/buffered-writer-probe.*.
Do not invent unused source variables to force those matches. Next verify Flush
and reader Size (0x006aa020) and refine shared virtual returns from observations.


## Batch 15: writer flush and size forwarding

EWriteBufferedFile::Flush 0x006a9d50 (80 bytes) and EReadBufferedFile::Size
0x006aa020 (32 bytes) match. Total 2,917/10,930 functions,
235,948/2,935,679 bytes; no regressions. Strict build:
build/audit/20261017T234732Z/summary.json; all 56 sources compile.
Full comparison build/batch-15-final.json; reviewed map hashes/backup in
build/batch-15-map-update.json. The shared file interface now captures raw EAX
from Write and Seek, and Size at slot +0x14. Semantic types remain provisional.
Flush clears pending/start even on short/failed writes; empty flush preserves
start. Its incidental EAX is not treated as a meaningful return value.

201 buffered cases (148 existing plus 53 new), 385 package-accessor cases,
717 file-manager cases and 192 diagnostics pass: 1,495 cases run this batch.
All 102 repository tests pass. Cumulative independent case set: 2,826.
Writer Write/Seek remain private probes; unexplained stack slots are deferred.
The newest user request now adds upstream synchronization before further code.


## Upstream integration and batch 16

Successfully fetched and manually integrated DrDecki main 6959341 (four new
commits); see upstream-sync.md. Its 382 independent verified additions add
56,669 bytes. Combined check build/upstream-sync-20261017.json establishes
3,299 matches /292,617 bytes, retaining all 47 local additions at that point.
All 108 repository tests and the complete 2,826-case differential set passed
against that combined build. Updated compiler flags include /Oy; compiler and
reference binary stay unchanged. CSV union/promotions and backups are recorded
in build/upstream-sync-map-update.json. Upstream function records distinguish
compiled/binary-matched evidence from unperformed individual behavioral tests.

The upstream explanation of unused inline temporaries directly resolved the
writer mismatch. Keeping the recovered Flush body inside the partial class
preserves the call while reproducing caller stack allocation. Write and Seek
now match without dummy locals or injected instructions:

| New body | Address | Mapped bytes |
| --- | --- | ---: |
| EWriteBufferedFile::Write | 0x006a9ca0 | 175 |
| EWriteBufferedFile::Seek | 0x006a9c00 | 50 |

All six buffered methods now match. Session's independent native gain over
2,913 matches: **6 bodies /710 bytes**, separately from upstream's 382 bodies
/56,669 bytes. Combined final **3,301 matches /292,842 bytes**, zero regressions.
Cumulative independent local gain over common base: 49 bodies /6,357 bytes.
Full report build/batch-16-final.json; two reviewed CSV changes/hashes in
build/batch-16-map-update.json. Strict audit
build/audit/20261017T235503Z/summary.json: 56 fresh sources, 3,307 COFF records.
Subsequent source formatting changed whitespace only (explicit comparison).

453 buffered differential cases pass, including 252 new Write/Seek cases and
201 regressions. They execute the real Write/Flush and Seek/Flush chains,
check complete fixture heap/call traces/ABI, zero/equal/greater-capacity writes,
short/failed flush, raw seek results, unsupported origins forwarded unchanged,
pending-count overflow and return-count wrap. Large direct-write requests are
traced without dereferencing source; file I/O is mocked. An initially omitted
Flush relocation in the expanded test harness was added before the passing
run. Report build/batch-16-behavior.json. Cumulative verified set: **3,078**.
The other 2,625 cases passed on the combined build and were unaffected by this
last source change. All 108 repository tests passed during integration.

Next foundational work: EFile/buffered-file lifetime and ownership.
Cached destructor 0x006a9dd0 (writer,126 bytes) flushes, closes nonnull file,
deletes buffer +0x18, releases nonnull base field +4 through 0x006a6e30 with
arguments `(field,0x18,1)`, and resets base vtable 0x0071d8c4. Reader destructor
0x006aa0f0 (118 bytes) follows the same path without flush, using buffer +0xc.
Scalar deleting wrappers 0x006a9da0/0x006aa0c0 each check flags&1. Helper
0x006a6e30 (27 bytes) passes only its first argument to IAT 0x00700298; extra
argument meanings, exact allocation/delete form and ownership remain unresolved.
No lifetime source or runtime guarantee was invented from these observations.

Checkpoint metadata: native-buffered-session-20261017.json. No commit/push,
launch, asset/mod/save/config change, or dependency installation occurred.
