# Boyd action behavior continuation

Canonical root: `<canonical-checkout>`. This work lives in the
native worktree selected by `.local/native-pack-strings-current.json`:
`.local/worktrees/native-pack-strings-20261021`. Character inputs remain in the
separately selected `asset-coverage-environments` worktree. No original input,
portable asset, native C++ body, object, function-map row or match was changed.

## Newly executed original behavior

`tools/original_boyd_actions.py` adds **3,072 original-only fixtures** against the
supported Steam PE32, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
Private result: `build/boyd-behavior-20261111/actions-final.json`. The report binds
the tool, ActionFile and original executable hashes, selected body hashes,
fixture inputs/results and explicit service adapters. Required tooling checks:
`build/boyd-behavior-20261111/tooling-tests-final.json` (102 pass, no required skips;
optional Rust not requested).

| Address | Observed role | Mapped bytes | Evidence |
| --- | --- | ---: | --- |
| `0x00407d70` | Case-sensitive action-name lookup, first match, miss `0xffff` | 170 | Original execution with all 16 Boyd names and three misses |
| `0x00407e80` | Bounds-checked transition matrix lookup | 197 | Original execution of all 256 Boyd action pairs |
| `0x00440c00` | Named action switch | 108 | Original execution including repeat and missing names |
| `0x00440bb0` | Named action switch with override pointer | 80 | Original execution with lookup and forwarding |
| `0x00440b30` | Indexed override forwarding | 117 | Original execution, repeat/debug/null-table cases |
| `0x00440c70` | Main action switch and callback ordering | 734 | Original execution with interpreter/notification adapters |
| `0x00441b00` | Instruction-cursor advancement/wait wrapper | 234 | Separate original execution with single-instruction dispatcher adapted |
| `0x00440ac0` | Action-name accessor, `-1` means current | 79 | Executes in debug-path fixtures |
| `0x00407cf0` / `0x00407d30` | Header/name accessors | 52 / 52 | Execute with the switches/debug queries |
| `0x00407e20` / `0x00407e50` | Entry/exit matrix accessors | 34 / 34 | Execute with the switches |
| `0x00407b70` | Cursor constructor | 41 | Executes with the switches |

These are provisional roles, not newly promoted C++ names. Match totals remain
**3,396 functions /304,109 mapped bytes**. The previous full verification remains
`build/native-boyd-20261110/full-01/verification.json`; it is historical evidence
for that unchanged native source/object set, not a fresh full build this batch.

## Runtime layout and switching rules

Observed actor fields: table pointer `+0xac`, current action (32-bit) `+0xb0`,
previous action `+0xb4`, override pointer `+0xb8`, persistent cursor pointer
`+0xbc`. The table has packed count `first DWORD >> 5`, eight-byte header rows through
`+8`, a row-major unsigned-short transition-index matrix through `+0xc`, and
24-byte instruction records through `+0x18`. Matrix index `0xffff` means absent.
The entry/exit pseudo-action indices at table `+0x1c/+0x1e` are staged as absent
in these fixtures; their actual parser-produced values remain unverified.

The main switch does the following, in observed order:

1. Null table returns false. Initial current action `-1` is replaced by the
   index of `Init`, or zero if that name is absent (the fallback is assembly
   evidence; fixtures use Boyd's real `Init`).
2. Same current/requested ID returns true without restarting. Requested `-1`
   returns false if it was not already the current ID after initialization.
3. A nonzero header byte `+4` on the current action rejects a different action.
   Boyd's 16 source headers have zero here; nonzero tests are synthetic probes.
4. Missing matrix entry returns false. Otherwise construct and copy a new cursor
   to persistent storage **before** invoking the old action's exit interpreter.
5. If the exit callback changes current action, return true without assigning
   the requested action, previous ID or override. This is tested by an explicit
   reentrant adapter; it does not establish which Boyd callbacks do this live.
6. Otherwise save previous/current/override, interpret entry instructions, then
   call virtual slot `+0x24`. If the immediate byte is nonzero and current still
   equals requested, interpret the persistent transition with argument zero.

Named switch checks same-action before rejecting a `0xffff` lookup result.
Named override forwards that result without a separate miss check. Indexed
override checks same-action before forwarding, even with a null table. Its
second argument controls debug-name queries, not a proven force-interruption
mode. Do not unify these differently ordered guards.

Cursor `+0` is the current instruction pointer, `+4` an unnamed phase/status,
and `+8` an unnamed byte. The constructor sets pointer/status/byte but leaves
three trailing padding bytes unspecified. The wrapper clears pointer/status on
an initial opcode 8; a completed dispatcher call advances 24 bytes and resets
status, repeating until an end marker or pending instruction. Pending opcode 1
returns true only if **both low instruction-flag bits are set and cursor status
is nonzero**. The meaning of those bits requires dispatcher recovery. Other
pending cases return false; that return must not be renamed “animation done.”

## Real source connections and exclusions

The retained `package/movement/action-files/boyd.asd` contains 16 names and 144
sections, including `Linked` references. The harness resolves those source links
and stages synthetic runtime rows/matrix/pointers. It does **not** execute the
1,940-byte ActionFile parser `0x00407f50`; instruction payloads are placeholders.
Switch tests adapt interpreter `0x00441b00` and virtual notification. Separate
cursor tests execute `0x00441b00`, adapting dispatcher `0x00441240`. No fixture
claims real instruction dispatch, clip loading, blending, root-motion or Lua
execution. Out-of-range current IDs that would dereference a null header are
excluded from valid-runtime fixtures, not silently repaired in engine source.

`ScriptBase.setNewAction` calls `SetNewAction_impl` (`0x005bdad0`, already matched),
which selects the named native route. **Animator overrides `setNewAction`**, so
ordinary inherited Boyd calls instead delegate to `setAnim`.
`Global.Props.Animator.setAnim`, inherited by `ActionActor` and Boyd, calls
`LoadAnim_impl` (`0x005c3520`, unmatched)
or priority loading (`0x005c3a20`, unmatched). Both interfaces use a script
`currentAction` field, but this does not prove they synchronize native action IDs.
The ActionFile explicitly connects back to Lua in section `[11,7]` with
`self:setState('TransitionFromOpenGate')`; execution of that opcode remains open.
Its presence alone does not establish that Boyd loads or traverses that table
during the recovered script states.

## CurrentState consumer and next bounded target

Hash-gated literal-reference scanning and targeted disassembly identify
`0x005ce7c0` (861 bytes) as the pending `CurrentState` consumer; the other literal
user is the newly matched assignment `0x005cb1e0`. Private indexes are under
`build/boyd-behavior-20261111/`, and reference hits are retained in
`.local/boyd-behavior-20261111/string-xrefs.json`.

Observed, not newly execution-tested: the consumer handles dead/paused flags,
dispatches queued messages (`0x005cb9c0`), allocates/binds a thread when needed,
gets the object's Lua reference, reads `CurrentState`, pushes the object and
calls `lua_call(L,1,0)` (`0x006b08e0`) after a stack switch. It uses setjmp/longjmp;
thread status 4 retains the token and bypasses normal stack-pop/reset/release.
Error handling can clear `CurrentState` and set object bit 2 or call `0x005cfa80`.
This is not a verified coroutine implementation or a gameplay observation.

Next implement/test the single-instruction dispatcher `0x00441240`, beginning
with animation opcode 1 and Lua opcode 3. Resolve its playback/completion
dependencies before attaching blend-time meaning to the ActionFile's floats.
Then extend the original fixtures through actual instruction dispatch and the
`[11,7]` Lua state callback. Retain the separate `LoadAnim` route and context
switching consumer as explicit dependencies. No compiler-layout retry is needed.

Reproduce from this native worktree using the established Python 3.13 environment:

```sh
PYTHONPATH=.venv/lib/python3.13/site-packages "$PY313" -B tools/original_boyd_actions.py \
  "$REFERENCE" \
  ../asset-coverage-environments/.local/assets/boyd-complete-20261110/package/movement/action-files/boyd.asd \
  --report build/boyd-behavior-next/actions.json
```

`PY313` is the already installed CPython 3.13 executable, not system Python 3.14.
Reports must be new private files. No commits, pushes, game launches, installed
files, saves, prefixes, ZIPs or publication were involved.
