# Fork development checkpoint

## Upstream integration

The fork merge combines the previous fork tip `135c50b` with upstream
`8674306`. The supported Steam executable still yields **3,963 matching
functions / 403,495 mapped bytes** after rebuilding all 67 sources with
VC++ 2008 RTM x86. This retains all 3,396 previous fork matches and all
3,955 upstream matches. The function map and progress image reflect this
combined result. The full run passed 110 required tooling tests, nine optional
Rust tests, 15,697 differential cases across 37 suites, and 44 original-only
cases against the supported executable.

The array element loop is retained for pointer and class arrays. The
`char` specialization skips the loop, preserving the fork's existing
savegame match. Upstream license terms and earlier MIT notices are preserved
in the repository license files.

## Previous native checkpoint

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
