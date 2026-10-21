> Historical technical evidence, not the current setup/checkpoint. Use
> [CONTRIBUTING](../contribute/README.md) and [current native status](native-reconstruction.md).
> Original local report references identify private evidence, not required downloads.

# Upstream synchronization — 2026-10-17

Repository: https://github.com/DrDecki/psychonauts-decomp (MIT, unchanged).
Successfully fetched origin/main at **6959341ed94edeb17d77ad39c3b59ae5dd8f5011**.
Previous comparison/base: 2b04c7ea160b75433371b7d0fba9e548531647f3.
Local branch codex-engine-decomp stays at a9a0eba; no commits or pushes.
The branch contains 30 local commits beyond the common base plus preserved
tracked/untracked changes. Local main remains at its old reference intentionally.

## Comparison and adoption

Four new merged commits (9b6cb96, 943177c, aa44950, 6959341) add **382 mapped
matches /56,669 bytes** over the earlier upstream baseline. Upstream CSV now
records 3,252 matches /286,485 bytes. Address/size ranges are unchanged across
all 10,930 rows, and executable SHA-1 remains our established Steam reference.
These claims were computed from Git contents, not the stale web README cache.
Native Lua registrations remain a separate 1,134-entry map.

Immediately before integration, local verification had **2,917 matches
/235,948 bytes**, including 47 independent local additions /6,132 bytes over
the common base. None of those added addresses overlap upstream's 382.
The expected combined union is **3,299 matches /292,617 bytes**.

New upstream matches by recorded source object: script 222, dialog 105,
debug-menu 47, trigger 3, savegame 3, freeze 2 (the latter groups include emitted
header helpers). These are not new asset extraction work. Upstream improves
physics/entity/script/GameApp layouts, matrices/vectors/quaternions, arrays,
dialog/UI interfaces and Win32 declarations. Its matcher adds decorated-import
lookup, repeated-string validation, COMDAT handling and short-function anchors.
Build adds `/Oy` for aligned locals; compiler remains VC++ 2008 RTM x86.

Integrated the changed source/header/build/matcher files and README changes
without merging commits or replacing local sound/file/diagnostic source.
Resolved EEntity name/sound fields, sleeping/echo flag views, GameApp flags and
sound interface by combining observed offsets. Upstream's object-local
ESoundManager definition duplicated our richer shared class: its DumpSounds
and DumpChannels slots +0x100/+0x104 now extend the shared class instead.
No conflict markers or unresolved Git conflicts remain. Upstream CSV/progress
SVG were retained privately for comparison, not blindly copied over local data.
Only verified matches will be promoted in the canonical CSV.

One conservative matcher guard adds an image-bound check before accepting
an identical-string alias. A negative VA offset must not exploit Python's
negative indexing to match bytes near the image end. Six new synthetic tests
cover valid duplicate strings, different strings, below-image pointers, import
decoration, explicit-address precedence and missing imports.

## Preservation and remote status

Recoverable tracked/untracked archive, per-file hashes, binary working patches,
refs, repository bundle, upstream files and API snapshots are private under
.local/checkpoints/upstream-sync-20261017/. The archive covers 275 files and
leaves ignored reference/toolchain/analysis files in place. Both earlier dense
files and existing contribution patches are preserved. There was no reset,
checkout, rebase, staging, history rewrite or Git merge commit.

GitHub public API reported only main, no pull requests (state=all), no open
issues, and discussions disabled. API snapshots are the evidence; inaccessible
web issue pages were not treated as empty. Initial sandbox DNS failure was
resolved by the approved network fetch. Sources:
[commits](https://github.com/DrDecki/psychonauts-decomp/commits/main/),
[repository API](https://api.github.com/repos/DrDecki/psychonauts-decomp),
[pulls API](https://api.github.com/repos/DrDecki/psychonauts-decomp/pulls?state=all&per_page=100),
[issues API](https://api.github.com/repos/DrDecki/psychonauts-decomp/issues?state=open&per_page=100).

## Verification and continuation

Combined source compiles all 56 files; strict audit
build/audit/20261017T235146Z/summary.json. An initial integration compile exposed
the duplicate ESoundManager declaration; it was resolved as above before a
clean strict build. All **108 repository tests** and **2,826 differential cases**
pass against the combined build, with existing mocked-callee limitations.
Reports are build/upstream-sync-tests/*.json. Full relocation-aware comparison
build/upstream-sync-20261017.json confirms exactly the expected union: **3,299
functions /292,617 bytes**, including every previous local and upstream matching
address, with zero regressions. The 382 reviewed CSV promotions and hashes are
in build/upstream-sync-map-update.json. Per-function compiled/matching evidence
was generated; individual behavior/signature/class claims remain unset.

Upstream's note that rejected inlining still reserves caller stack space
resolved the buffered writer Write/Seek mismatch. A private probe moved the
already recovered Flush body inside the partial class; compiler kept the call
and emitted the original unused frame slots. All three bodies match there.
Batch 16 subsequently adopted and verified Write/Seek: +2 functions /225 bytes,
final **3,301 matches /292,842 bytes**, zero regressions; 453 buffered cases
pass (252 new). See native-buffered-session-20261017.md. No dummy locals or
injected instructions were needed.

Next synchronization: fetch origin, compare against 6959341, preserve local
source and evidence again, and prove the union of previous verified addresses.
Only advances to the supported executable and compiler workflow should be
adopted automatically; experimental branches require separate review.
