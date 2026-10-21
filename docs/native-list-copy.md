> Historical verification record; the complete publication candidate includes this work.
> Current coverage/results are in [native status](native-reconstruction.md) and [publication scope](publication-scope.md).

# Native list copy and neighboring operations

Continued from the actual uncommitted 3,368-function native worktree checkpoint.
HEAD remains 8154808. Existing workflow, recovery archives and deferred
ReadAllocatedString body preserved. No commit/push/game/install/ReSkate changes.
Reference Steam PE32 SHA-1 `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`,
SHA-256 `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
VC++ 2008 RTM x86 15.00.21022.08; `/Od /Oy /Ob1 /Oi /MD /GS-` unchanged.

| Provisional name | Address | Matching bytes |
| --- | --- | ---: |
| AppendList | 0x006a5360 | 68 |
| PrependList | 0x006a53b0 | 67 |
| RefillNodes | 0x006a5100 | 136 |
| InsertBefore | 0x006a5540 | 112 |
| RemoveNode | 0x006a55b0 | 109 |

Five unique matches add 492 bytes: **3,373 / 10,930 functions and
300,253 / 2,935,679 bytes**, zero regressions.

Copy does not clear destination or clone payload objects. Append walks first/next
and PushBack; prepend walks last/previous and PushFront, preserving source order.
Empty source does nothing, including allocation. Links drive traversal; source
count is ignored. Null source is not guarded. Each iteration saves its traversal
link before insertion. Empty/singleton self-copy terminates; self-copy with two
or more valid nodes follows links altered by previous insertions and keeps growing.
The initial snapshot oracle exposed this edge case; original source behavior was
preserved and the test corrected. Bounded self-copy fixtures compare 12 completed
insertions and stop at insertion 13; no termination/final ABI claim for those runs.

Copy reuses free nodes and allocates growth-sized pools only on exhaustion through
the existing insertion path. No eager bulk allocation/failure recovery. Null and
duplicate payload pointer values are copied without dereference/destruction.

RefillNodes is the separately callable pool/free-chain block also in AllocateNode.
Nonempty free chain is a no-op. Otherwise it prepends a pool and links nodes in
descending address order with a signed growth-minus-one loop. Count/endpoints and
payloads are untouched. Zero/0xffffffff growth requests wrap as observed and skip
the node loop; repeated calls allocate again because free head remains null.
Actual huge allocations, allocation failure and malformed-list safety unverified.

InsertBefore(null,data) calls PushFront; otherwise it repairs preceding/first links.
RemoveNode repairs last/next first, then first/previous, then ReleaseNode; singleton
removal releases all pools through Clear. No payload destructor/return or invalid
position guard is inferred.

One meaningful traversal-local rename resolved RTM stack slots. Refill and the
neighboring pair needed no layout probing. No dummy locals/injected instructions,
compiler output edits or matcher changes. Final affected check: 1,302 cases /25.37s.
Full strict verification: 62 sources, 46 tooling tests, 7,066 fresh differential
cases in 24 suites plus 44 separate original-only cases. List suite: 576 cases,
248 new. Actual list/pool/Clear x86 executes; only aligned allocation/free mocked.
Full timings: compile 13.14s, matching 12.01s, testing 122.59s, total 148.27s.
Saved CSV before promotion; exactly five reviewed rows change and every old row
is exact. Full Rust/final read-only Python matching agree on every selected
address/symbol/object; final report has zero new addresses/regressions.
Private evidence and before-source/test/map backups: `build/list-copy/`.

Next: 0x006a5670 (82 bytes), backward payload lookup starting before an optional
node, then its search/remove callers 0x0042ca60 and 0x00462bf0. 0x006a56d0
(78 bytes) walks from last and returns a node index or -1. 0x006a5720 (138 bytes)
repeatedly compares adjacent payloads and swaps only on callback return exactly 1;
callback semantics/termination unresolved. These are analyzed only. Loading bridge
0x0041f070 (143 bytes) still depends on external 0x0041ee40. Prefer these observed
resource/lifetime callers over unrelated small targets. Engine remains unlinked;
no physical I/O, resource parsing or gameplay integration established.
