# Model input helpers — 2026-10-20

Reference Steam Windows SHA-1 `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`;
SHA-256 `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
Compiler VC++2008 RTM x86, unchanged `/Od /Oy /Ob1 /Oi /MD /GS-`.

## Matched model name ownership

EModel::SetName at0x00455900 uniquely matches73bytes. EMesh reader0x00435f40
passes its +0x18 model pointer, corroborating the existing partial model view.
The name pointer replaces opaque padding at model+0; all other offsets stay
unchanged. Names remain provisional; full model identity/lifetime is not claimed.
The setter frees nonnull old storage with category7/flag1, explicitly zeros it,
then copies nonnull input with category7. Tests observe the cleared field at
the copy callback. Null input skips copying; copy failure stores null. Aliases
are traced without reading freed memory. No self-assignment guard was added.

## Behaviorally verified, unmatched stream helper

EStream::ReadAllocatedString at0x006a5de0 reads a signed four-byte length.
For length<=1 it transfers that count to null and returns null. Negative lengths
become large unsigned transfer counts. For length>1 it calls aligned allocation
with alignment16, transfers into the result (including null on allocation
failure), then returns it. No terminator, transfer-count or allocation-failure
check was inserted. EMesh caller supplies category0x1a; existing MemAlloc drops
that argument in the inline body. Source semantics and high-level name remain
provisional. The131-byte body differs at four inline temporary displacement
bytes. A bounded12-name/declaration-scope probe did not resolve them. No further
compiler guessing, padding locals or matcher relaxation; CSV row stays unmatched.

## Verification

All62 sources compile strictly. Full comparison retains all3359preceding
matching addresses and adds only the73-byte setter: **3360/10930 functions,
298986/2935679 mapped bytes**, zero regressions. Python/Rust targets agree for
the promoted body. One CSV row backed up/reviewed/hash recorded.

352new differential cases:12model-name and340allocating-stream fixtures cover
null/alias/replacement, allocation failure, signed-length edges, nonterminated
synthetic payloads, short transfers, poisoned partial headers, ignored categories
and modes, full fixture heaps, call order, returns and saved-register/stack ABI.
Oversized transfers/allocations are traced without dereference. Allocation,
copy/free and virtual stream transfers are mocks. Existing774mesh,388replacement,
266stream and108parser-dependency cases rerun:1888fresh cases, plus4602cached
unaffected cases =6490applicable.60other objects are identical after masking
only COFF timestamp bytes.29tooling tests pass. Larger mesh/parser bodies,
actual allocation, resource formats and gameplay remain unverified.

Reports: `build/model-input/`; exact report/object hashes in
[native-verification.json](native-verification.json). The comparison precedes
one reviewed CSV promotion. Compiler probes stay private under `.local/probe/`.

Next prioritize bounded reader dependencies and serialization dataflow; defer
retrying unchanged constructor/template frame blockers. No ReSkate/assets/game
state changed. This is object reconstruction, not a playable engine.
