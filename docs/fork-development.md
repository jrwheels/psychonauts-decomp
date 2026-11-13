# Fork development checkpoint

Current publication checkout: branch `development/verified-native-and-assets`;
public destination: `jrwheels/psychonauts-decomp`, `main`. The branch name is
historical; this update contains pure native decomp work. The canonical research
checkout and its active native worktree remain selected by the private native
pointer. Existing dirty research worktrees and recovery evidence are preserved.

As of 12 November 2026: **3,396 matching functions /304,109 mapped bytes**,
up from the fork's 3,389 /303,359. All seven new matching rows were reviewed;
all previous published matching rows remain unchanged. See
[native status](native-reconstruction.md), [skeleton helpers](native-skeleton-helpers.md)
and [script state](native-script-state.md).

The recorded full checkpoint rebuilt 67 sources, preserved every previous match,
passed 102 required tooling tests, and passed 15,697 differential cases across
37 suites plus 44 separate original-only cases. Rust was not requested.
Publication integration passes **110 required tooling tests without skips** and
re-executes **3,573 differential cases** (script state, skeleton helpers and
recursive reader) against hash-verified existing objects, with no fresh compile.
Private integration reports were retained outside the public repository.

This publication integration independently checked every native source against
that report's SHA-256 inputs; it does not claim a new native compile.
The sanitized source manifest and report digest are in
[native-verification.json](native-verification.json), `checkpoint_20261110`.

Later [action research](native-boyd-actions.md) executed 3,072 original-only
fixtures. Dispatcher, playback, Lua context switching, audio sync and actual
gameplay remain open. That research adds no matches and does not establish a
linked or playable engine. Names remain provisional and mocks remain explicit.

Next native research: start with dispatcher
`0x00441240`, animation opcode 1 and Lua opcode 3, then `LoadAnim_impl` at
`0x005c3520`. The native Windows compiler/verifier path needs validation before
new matching claims. Keep the pinned compiler and flags unchanged.

Protected operations: preserve research checkouts, original game/compiler files,
private reports, installations and saves. This checkpoint does not authorize installations or game launches. Proprietary reference
inputs and local evidence stay private. Earlier asset tooling already present in
the fork is unchanged by this update.
