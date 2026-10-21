> Historical verification record; the complete publication candidate includes this work.
> Current coverage/results are in [native status](native-reconstruction.md) and [publication scope](publication-scope.md).

# Native resource list and pool continuation

Reference: Steam Windows PE32 x86, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
Compiler: VC++ 2008 RTM x86 `15.00.21022.08`, unchanged
`/Od /Oy /Ob1 /Oi /MD /GS-`. All new names and high-level types are provisional.

| Recovered body | Address | Mapped bytes |
| --- | --- | ---: |
| AllocateResourceListPool | 0x006a4fa0 | 62 |
| ResourceListPool::Release | 0x006a4fe0 | 66 |
| ResourceList::AllocateNode | 0x006a5190 | 204 |
| ResourceList::ReleaseNode | 0x006a5260 | 62 |
| ResourceList::PushBack | 0x006a52a0 | 88 |
| ResourceList::PushFront | 0x006a5300 | 87 |
| ResourceList::PopBack | 0x006a5400 | 91 |
| ResourceList::InsertAfter | 0x006a54c0 | 115 |

Eight independent local matches add **775 mapped bytes** over the previous
3,360 functions / 298,986 bytes. New total: **3,368 / 10,930 functions and
299,761 / 2,935,679 mapped bytes**, with zero regressions. No upstream changes
were fetched or counted as local progress. This work remains uncommitted.

## Why this batch

Resource/mesh rankings were refreshed after inspecting the real worktree and
reviewing the preserved workflow. The existing PopFront and context-list Clear
provided binary anchors for ReleaseNode and pool release. PushFront is called
by the CYSP parser and context/mesh readers; following its direct allocator
edge selected the remaining small related methods. Rankings are heuristics;
every selected body was disassembled from the hash-gated reference first.
The batch was compiled together so its internal dependencies could be verified.

The workflow modules, compiler flags and matcher were not rewritten. Existing
workflow guard tests still pass. Development byte compatibility was kept
separate from full relocation-aware unique selection and behavioral checks.

## Recovered offsets and ownership behavior

The 24-byte list view keeps count +0x00, pool head +0x04, growth +0x08, free-node
head +0x0c, last +0x10 and first +0x14. The new fields replace opaque padding
without moving previously observed fields. Nodes have previous +0x00, next
+0x04 and payload +0x08, a 12-byte runtime stride. These are runtime container
observations, not serialized resource records or a complete original class.

Pool allocation requests `(count * stride + 8)` with 32-bit wrapping arithmetic
and alignment 16. It prepends a block to the header chain. Header +0x00 is the
next block; +0x04 remains opaque and untouched. Node storage begins at +0x08.
When the free list is empty, AllocateNode creates a block and links its nodes
backward into the free list. It removes one node, stores supplied links,
increments count and clears the payload. Existing free nodes bypass allocation.
Positive bounded growth is exercised; zero/huge growth and allocation failure
are not claimed safe. No new null guards or saturation checks were added.

ReleaseNode pushes a node onto the free list and decrements count. Reaching
zero calls the already matched list Clear body, which resets links/count,
releases all pool blocks and zeros the pool head. A zero input count wraps to
0xffffffff and does not trigger Clear. Pool release saves each next-block link
before freeing its current block. It does not clear its caller's head itself.

PushBack/PushFront set the payload and repair the appropriate neighboring/end
links. PopBack returns the payload saved before recycling the node, clearing
first when the list becomes empty. InsertAfter treats null position as append;
otherwise it repairs the next node's previous link or updates last. These
operations do not destroy or interpret payload objects. Empty pops, invalid
positions and payload ownership remain outside any safety guarantee.

## Development and full verification

Initial development found five compatible bodies. A second comparison resolved
the allocation local aliases and the insertion early-return scope, yielding
seven. One bounded eight-name pool-release probe found two compatible spellings;
the final source uses meaningful `pool`, `block`, `next` aliases. These are
compiler-layout spellings, not recovered original identifiers. No dummy locals,
inline assembly, matcher relaxation or modification of shared headers was used.
The first two development checks failed as expected on byte differences; those
candidates were not promoted. All eight passed the final targeted comparison.

| Verification | Time |
| --- | ---: |
| Initial targeted compilation/comparison | 4.09 s |
| Second targeted compilation/comparison | 3.96 s |
| Final development check with affected suites | 22.81 s |
| Full strict compilation | 13.04 s |
| Full relocation-aware matching | 11.97 s |
| Full testing | 114.14 s |
| Complete full verification | 139.68 s |

The standalone naming probe is separate from those development-command timings;
no whole-session reconstruction rate is inferred from verification throughput.

The final development run passed 1,054 cases: 328 new list/pool cases plus
266 stream, 108 parser-dependency and 352 model-input regressions. The new suite
executes all new bodies, existing PopFront and the existing matching Clear body
as original/rebuilt x86. Its Clear relocation aliases the observed same-layout
entry; it does not assert the provisional C++ classes have the same identity.
Only aligned allocation/free are mocked. Independent expected snapshots compare
whole synthetic heaps, link order, count updates, returned words, allocation/free
traces and stack/callee-saved ABI after every operation in a sequence.

Fixtures cover fresh/reused free nodes, end/middle/null insertion, null payloads,
count wrapping, requested allocation-size wrapping, multi-block cleanup, pool
reuse after draining, null pool release and free-time header poisoning. Huge
allocation requests are traced with bounded backing storage, not actually
allocated. Tests establish requests and machine behavior, not memory safety for
malformed sizes or actual allocator failure handling.

Full verification freshly compiles all 62 sources, passes all 46 tooling tests,
all 24 differential suites / **6,818 cases**, and 44 separate original-only CYSP
cases. The complete matcher retains every preceding 3,360 matching address and
selects exactly the eight new addresses. Python/Rust relocation targets agree.
Before promotion the original CSV was saved, only eight rows were reviewed and
changed, and all prior matching rows were checked unchanged. A final read-only
comparison uses the updated CSV and the same verified objects. Reports remain
ignored under `build/resource-list/`; current hashes are in
[native-verification.json](native-verification.json).

These are object-level and mocked execution results, not linking, physical I/O,
actual resource parsing, renderer or gameplay integration.

## Preserved work and next targets

Both existing working trees and Git history were archived and hash-verified
before edits. The prior objects and this batch's candidate source/tests were
also saved privately. Existing workflow changes remain uncommitted and intact.
No game, ReSkate, installed mod, save or original asset state changed. There was
no commit, push, reset, checkout replacement or branch deletion.

`EStream::ReadAllocatedString` at 0x006a5de0 remains deferred. Its source body
and evidence record are byte-exact to the pre-session checkpoint; its four
layout differences were not retried. Constructor/association Clear blockers
also remain unchanged.

Next inspect list-copy helpers 0x006a5360 (68 bytes) and 0x006a53b0 (67 bytes),
which now depend on reconstructed insertion methods. The deferred file bridge
0x0041f070 (143 bytes) is another bounded resource-stream target; its larger
0x0041ee40 stream handler remains external. Continue from actual reader
callers rather than assuming these container matches decode a model format.
