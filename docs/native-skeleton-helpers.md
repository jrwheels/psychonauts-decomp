# Skeleton name ownership and parent lookup

Verified local continuation, 2026-10-29. Base checkout `bf6104a` plus the preserved
local reconstruction checkpoint. Supported Steam PE32 SHA-256:
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
VC++ 2008 RTM x86 15.00.21022.08; unchanged `/Od /Oy /Ob1 /Oi /MD /GS-`.

| Address | Provisional function | Bytes | Result |
|---|---|---:|---|
| 0x00491ab0 | BoneInfo::SetName | 77 | Newly reconstructed; unique full-object match |
| 0x00492720 | RuntimeBone::GetParent | 85 | Newly reconstructed; unique full-object match |
| 0x00491a90 | BoneInfo::~BoneInfo | 21 | Existing body newly disambiguated by SetName relocation |

**3,389 → 3,392 matching functions; 303,359 → 303,542 matched bytes.**
All previous matching addresses remain. The gain is two new source bodies /162
bytes plus one already reconstructed destructor /21 bytes, not three newly
written bodies. Only these three function-map rows were promoted.

## Original semantics

The name setter owns the pointer at info offset +0x5c. When nonnull, it calls
`FreeFileName(old, 8, 1)` and then clears the member. A nonnull input subsequently
calls `CopyFileName(input, 8)` and stores its result, including null on failure.
The original frees before copying even when input aliases the old name. Tests
establish ordering without dereferencing freed memory; this is not an alias-safety
fix. Category 8 differs from the existing model-name category 7.

Parent lookup treats +0xac as an unsigned byte index and +0xad as an unsigned
byte parent index. Parent 0xff returns null. Otherwise it computes
`this - index + parent` with the established 0xb0-byte runtime-record stride.
It does not read the owner pointer, follow the owner's allocation pointer, validate
indices, or dereference the result. Runtime byte indices must not be confused
with the serialized 16-bit joint IDs read by the recursive loader.

These helpers strengthen character-rig research: name ownership is a dependency
of joint input/destruction, and parent lookup corroborates contiguous runtime
record topology. They do not establish animation fidelity or export completeness.

## Verification

Both new bodies passed their first targeted RTM compile without nonrelocation
byte differences. The name setter has ordinary trailing INT3 alignment in its
object; only its mapped 77 bytes count. Full matching resolves both string-helper
relocations against the existing full object set. No output patching, compiler-flag
change, shared-layout change or matcher relaxation was used.

`tools/test_skeleton_helpers.py` adds **1,352** independent expected/original/rebuilt
fixtures: 72 name ownership cases and 1,280 parent lookup cases. Name fixtures
cover old/null pointers, null/alias/interior-alias/separate inputs, null/non-null
copy results and poisoned surrounding memory. Mock callbacks check category,
flags, member state and ordering while clobbering volatile registers. Parent
fixtures exercise every parent byte with five boundary index values, an unusable
owner pointer, unchanged heap bytes, return value and calling convention.

The existing construction/destruction tests reverify the 21-byte destructor.
The unchanged recursive reader passes its existing 512 bounded differential cases
but remains unmatched and excluded from matching progress.

Final full verification rebuilt **66 source objects**, passed **91 required
Python tooling tests and nine optional Rust tests**, and passed **13,988 fresh
differential cases across 36 suites**, with **44 separate original-only CYSP cases**.
The prior recorded 12,124 cases excluded the later 512-case recursive-reader suite;
this batch adds 1,352 cases, not the entire difference from that older total.

The Rust accelerator and its source matched the previously verified hashes; its
nine comparison tests ran again. The fresh pre-change baseline used the Python
matcher. Detailed private reports are under `build/advance-20261029/`:
`baseline-02`, `dev-01`, `full-01`, `full-02`, and `post-promotion.json`.
The first full run found the additional destructor and intentionally declined
promotion because only two addresses had been requested. The final run explicitly
selected all three addresses. No safeguard was bypassed.

## Checkpoint and limitations

This is a stopping checkpoint, with no commit, push, PR update or game launch.
All earlier dirty work and research remain preserved. No linked/playable engine
or actual allocation, copying, asset loading, animation or gameplay result is
claimed. Names remain provisional. Frozen reference data was not modified.

Resume through the existing private current-checkpoint pointer. The next related
work remains the recursive joint reader's structural/local-layout mismatch, using
these verified dependencies, or the animation-stub reader when new typed-layout
evidence becomes available. Do not repeat earlier layout probes unchanged or
promote the recursive reader merely because its bounded tests pass.
