# Script-state transition and thread lifetime

Boyd's Lua actors use shared ActionActor state changes. The existing matched
APISetState wrapper at 0x005be880 reaches EScriptObject::SetState at 0x005cb1e0.
This continuation reconstructs that body and three of its direct dependencies,
rather than treating the wrapper match as complete actor behavior.

Supported reference: Steam Windows PE32 SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
VC++ 2008 RTM x86 15.00.21022.08, unchanged `/Od /Oy /Ob1 /Oi /MD /GS-`.
Names and status meanings remain provisional.

| Address | Body | Mapped bytes |
| --- | --- | ---: |
| 0x005cb1e0 | EScriptObject::SetState | 323 |
| 0x005cdef0 | EScriptManager::GetThread | 49 |
| 0x005ca870 | EScriptThread::Reset | 48 |
| 0x005ce220 | EScriptManager::ReleaseThread | 147 |

## Original behavior

SetState requires at least one Lua stack element. Index 1 must be a table and
index 2 must be either a function or Lua nil; absence is not equivalent to nil.
It pushes the literal CurrentState key and a copy of index 2, then assigns into
the table at index 1. It reads the type of index 2 again after that assignment,
setting object byte +0x1c bit 2 for nil and clearing that bit otherwise. Other
bits are preserved. A callback that changes observable Lua/object state during
the table write must not be folded away by a reconstruction.

Object byte +0x1f is a one-based thread token. Zero bypasses thread handling.
A nonzero token calls the manager at GameApp+0x9a34 and reads thread+0x4c. Only
numeric status 4 causes immediate cleanup: clear the object's token first, reset
the thread, then release it through a freshly loaded global manager. The other
statuses keep the thread/token. No scheduler-state enum name is asserted.

GetThread returns null for token zero; otherwise it narrows the decremented
index back to an unsigned byte and reads manager+0x138+4*index. It does not test
active bits or enforce a 64-slot bound. The release helper, in contrast, scans
only 64 slots. The two active-bit words are at manager+0x238. Release clears the
first active matching slot's bit and stops; it does not clear the pointer, delete
the thread, or clear every duplicate. A null target can match an active null slot.

Reset sets Lua state's top to its stack base (not Cbase), then clears thread
fields +0x58 and +0x4c. It does not call a Lua API or run a coroutine. Thus the
manager reload following Reset is observable if the Lua-state pointer aliases
the global manager pointer; an integrated fixture exercises that case.

The shared header adds only observed views: object token +0x1f, manager slot/bit
ranges, and a local partial thread view in script_state.cpp. The thread view is
not used to allocate complete engine objects. Existing member offsets remain
unchanged. Getter access beyond the observed pool capacity retains original
compiled x86 behavior; it is not a portable safe-container API.

## Compilation and behavioral evidence

The state body and Reset matched on their first targeted RTM compile. GetThread
needed the original integer-promotion/narrowing expression instead of byte
predecrement. Release's bit test materializes an integer conditional before its
Boolean return; its compound assignment uses a reference-returning word accessor.
That reproduces the original unnamed address temporary after the enclosing this
slot. A named local reference had seven differing stack displacements; a direct
array compound assignment repeated address calculation and changed extent.
No padding locals, output patching, changed flags or matcher relaxation were used.
Hash-checked source variants and failed reports remain private.

tools/test_script_state.py adds 1,709 independent expected/original/rebuilt cases:
677 transition cases, 512 token lookup cases, 8 reset cases and 512 release cases.
All four reconstructed bodies execute together; only Lua APIs are mocked. Cases
cover argument/type guards, the post-table-write type reread, surrounding flag
bits, status values, token/word boundaries, high caller argument bits, every byte
token, sparse/full/empty bitmaps, duplicate and null pointers, exact call order,
all fixture heap bytes, nonvolatile registers and stack cleanup. Six controlled
null-thread faults preserve the original unchecked dereference. Global-manager
redirection verifies that Reset is followed by a new manager load. Error callbacks
return in the fixtures; real Lua error longjmp and table/metamethod semantics are
not established by those mocks.

Private development reports are under build/native-boyd-20261110/. dev-03
preserves a child-interpreter dependency-path failure; dev-04 preserves the
remaining stack mismatch; dev-05 passes all four byte-compatibility checks and
1,709 fresh fixtures. Compilation/compatible bytes are distinct from global
matching. The fresh full run and promotion evidence are recorded below when
verification completes.

## Integration limits and next work

This establishes how a pending actor state is stored and how one existing thread
is detached/reset/released under status 4. It does not execute the new state,
recover the coroutine scheduler, interpret the ActionFile transition matrix,
blend animations, move Boyd along paths, schedule speech or implement lipsync.
Those remain live native targets. No game/assets/installation/save changes,
commits, pushes, ZIP or publication accompany this work.

## Verified checkpoint

Fresh full verification rebuilds **67 sources**, passes **102 required tooling
tests without skips**, and runs **15,697 differential cases across 37 suites**,
plus **44 separate original-only CYSP cases**. Optional Rust was not requested
in this run. Full-object matching uniquely selects exactly these four requested
bodies, preserving all **3,392** previous matching addresses with zero regressions.
The source batch adds four bodies /567 mapped bytes, not its trailing alignment
padding: **3,396 functions /304,109 mapped bytes** afterward.

Only the four reviewed CSV rows changed. Post-promotion review compares the new
rows and all prior matches with the unchanged fresh matcher result; it is a
metadata reconciliation, not a second matcher run. The full report's earlier CSV
hash remains correct for its pre-promotion input. Source/object hashes stay bound
to that full report. The generated progress map is refreshed from the reviewed CSV.
Private evidence: `build/native-boyd-20261110/full-01/verification.json`,
`comparison.json`, `test_script_state.json`, and
`.local/native-boyd-20261110/map-review.json`.

Canonical project is `<canonical-checkout>`; active engine
worktree is `.local/worktrees/native-pack-strings-20261021`. Resume via the current
native pointer, which records these hashes and this checkpoint. Next recover the
consumer that starts/runs CurrentState and the thread status transitions, or the
ActionFile lookup path, while retaining Boyd's unresolved waypoint/navigation and
lipsync work. All previous source/asset snapshots remain intact; none is silently
upgraded to this new checkpoint.
