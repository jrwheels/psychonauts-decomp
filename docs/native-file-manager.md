# File dispatch and pooled package access — 2026-10-17

All addresses below belong exclusively to the Steam Windows 2016 PE32,
SHA-256 `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
This is not evidence about an unacquired 2005 retail build.

## Identity and recovered dispatch

The diagnostic factory is **EFileManager**, confirmed independently by its
constructor's vtable assignment and MSVC RTTI. Vtable 0x0071d920 has three code
entries: 0x006a9140, 0x006a9a00, 0x006a9a10. Its preceding complete object
locator is 0x0077b85c; type descriptor 0x00781de8 contains
`.?AVEFileManager@@`. Hierarchy 0x0077b870 has one base descriptor (self).
Do not extend this table into adjacent constant 0x2a or another table's locator.
The reproducible identity assertions are in tools/test_file_manager.py.

`EFileManager::Open` (0x006a9140, 197 mapped bytes) rejects null names and
options containing any bits outside 0x7f00. For mode zero, an empty packed
array count at object+0x20 selects mode 9; otherwise any options bits in 0xb00
select mode 4, and the remaining cases select mode 1. The count occupies the
upper 27 bits; low five bits do not participate. Explicit nonzero modes pass
through unchanged, including negative bit patterns.

The resolver 0x006a8ca0 receives `(name, mode, &first, &second)`, with both
outputs initialized null. If both outputs become nonnull, dispatch uses the
packed-file allocator regardless of the resolver's returned string. Otherwise,
a null string returns null and a nonnull string goes to 0x006a8180 with the
original options. The resolver remains unresolved; the native opener is reconstructed in
[native-file-streaming.md](native-file-streaming.md).
Names and handle meanings are provisional. Local spellings are RTM stack-layout
choices; they are not original source identifiers.

`AcquirePackedFile` (0x006aac10, 143 mapped bytes) scans four 20-byte records
at 0x00795c80. A slot is free only when BOTH fields at +8/+0xc are null.
It stores the two input pointers, resets cursor +0x10 to zero and returns the
slot address. Full pool returns null; half-initialized slots are occupied.
Passing two null inputs is permitted and leaves the chosen slot logically free.
Opaque first eight bytes, other slots and surrounding data are preserved.
The global array remains external; no replacement storage/initialization stub
was introduced. This group supports resource loading as well as diagnostics.

## Construction and lifetime: analyzed only

EFileManager constructor 0x006a88b0 (501 bytes) writes vtable 0x0071d920 and
initializes arrays at +0x14 and +0x20 through 0x0040af40/0x006a98d0.
It uses XboxDrive D/T/Z strings, `_getcwd`, special-folder/path helpers,
SHGetFolderPathA and GetDiskFreeSpaceA; fields +0x30/+0x34 become 0/0x40000.
Destructor 0x006a8ab0 (78 bytes) frees the cwd pointer at +0xc and destroys
the arrays. Shell/path policy, allocation ownership and complete layout remain
unrecovered. Factory pointer 0x00781d90 still refers to original static storage
0x00795a38 and remains external. Do not instantiate the partial declaration.

Pool initializer 0x006fb950 traverses four records, stride 0x14, installs base
vtable 0x0071d8c4 followed by derived 0x0071d990, and clears +8/+0xc/+0x10.
It leaves +4 untouched. It registers destructor wrapper 0x006fbd40, which
traverses in reverse and rewrites derived/base vtables. RTTI at locator
0x0077b93c identifies the pool records as
`EPackageFile::EPackageFileAccessor`. The current source uses a partial opaque
record rather than asserting full inheritance/destructor declarations.

Related verified table bounds: EWriteBufferedFile 0x0071d934 (locator
0x0077b8a4), EReadBufferedFile 0x0071d958 (locator 0x0077b8f0). Tables begin
after locators, not at 0x0071d944/0x0071d968. These are observations only.

## Package accessor reconstruction (batch 13)

The accessor table 0x0071d990 contains 0x006aae30, 0x006aad40,
0x006aad60, 0x006aadb0, 0x006aadc0, 0x006aae10, 0x006a9710, 0x006a9720.
Cached target exports already exist. Prioritize the useful related methods:

* Close 0x006aad40 clears +8/+0xc, preserving cursor.
* Read 0x006aad60 calls helper 0x006aabb0 with two handles, cursor,
  destination and requested count, then increments cursor by actual return.
* Seek 0x006aadc0 supports origin 0 (assign) and 1 (add, wrapping 32 bits).
  Other origins return 0xffffffff and preserve cursor.
* Helper 0x006aabb0 obtains underlying file at first handle+0x20. With entry
  offset +8 and length +0xc in second handle, it clamps count only if unsigned
  `(position + count) > length`, seeks to `entry.offset + position` with origin
  zero (virtual +0x10), and reads bytes (virtual +8). Addition wraps before
  comparison. Position past end can cause subtraction underflow; do not invent
  a safety guard. Underlying methods should be mocked when testing boundaries.

ReadPackedData, accessor Close/Read/Seek and Size (0x006aae10) are now
reconstructed in file_manager.cpp. Size returns the entry's DWORD at +0xc.
The source retains the PackedFileSlot partial view with an opaque vtable;
nonvirtual declarations expose recovered bodies without claiming reconstructed
inheritance, constructors or destructors. They are not a replacement runtime
class definition. Helper record names and unsigned semantic types remain
provisional; observed 32-bit bit patterns are preserved by the target compiler.

tools/test_package_accessor.py verifies the original/rebuilt Read-to-helper
chain and individual Close/Seek/Size bodies in 385 cases. Explicit fixtures
cover exhausted and past-end entries, wrapping addition before comparison,
underflowed counts, empty/short reads, deliberately unusual returned counts,
seek failure ignored by the helper, position wrap and unsupported origins.
It verifies every byte of the fixture heap, return values where meaningful,
stack cleanup and nonvolatile registers. Underlying file virtual calls are
mocked. This does not prove disk/package I/O, thread safety or validity of
arbitrary pointers; the mock writes only one bounded marker byte.

The shared DiagnosticFile slot +8 now has its observed two-argument Read
declaration. The full factory/diagnostic suites were rerun after this refinement.
No source for the accessor no-op Write or unresolved 64-bit slot was added.

## Buffered reader (subsequently reconstructed)

RTTI-confirmed EReadBufferedFile vtable 0x0071d958 selects Read at 0x006a9ee0
(313 bytes). Cached export confirms underlying file +8, buffer pointer +0xc,
capacity +0x10, valid bytes +0x14 and cursor +0x18. Read first copies the
smaller of requested count and available buffered bytes using **signed**
comparison, advancing cursor/destination. If data remains and its count is
**unsigned greater than** capacity, it forwards that remainder directly to the
underlying slot +8 and returns first-copy count plus actual result. Otherwise
it refills once through 0x006aa080, copies the signed minimum again and returns
the two copy counts. A short refill does not cause a loop.

Refill 0x006aa080 (60 bytes) calls underlying Read(buffer, capacity), stores its
raw return at +0x14 and sets cursor +0x18 to zero. Size 0x006aa020 forwards
slot +0x14; 0x006aa040 forwards slot +0x18 (return semantics still unresolved).
The Read copies call 0x006ed156, verified as an import thunk (`jmp [0x7002c0]`)
to MSVCR90.dll memcpy. Mixed signed/unsigned comparisons require type recovery and tests
before reconstruction. No buffered-reader source/behavioral verification is
claimed in that earlier analysis. Read/Refill/Size and buffered writer
Flush/Write/Seek are now reconstructed and verified; see
native-reconstruction.md for the current results and lifetime leads.

## Verification boundaries and reproducibility

Strict RTM x86 build, focused unique matches and full regression report:
build/audit/20261017T232908Z/summary.json, build/batch-12-final.json.
tools/test_file_manager.py runs 717 original/rebuilt x86 differential cases,
including the real two-body dispatch/allocator chain, independent expected
traces/state, ABI cleanup and nonvolatile-register checks. Resolver/native
opener are mocked. No real filesystem, package parsing, initialization,
concurrency or game execution is established. Invalid object pointers are out
of scope. Reports carry executable/object hashes in build/batch-12-behavior.json.
The existing 192 diagnostic cases also pass after the factory type refinement
(build/batch-12-diagnostics.json). Previous sound suites/harness are unchanged.

Batch 13 adds five matched bodies /283 mapped bytes. Full comparison
build/batch-13-final.json has no regressions; build/batch-13-map-update.json
records the five reviewed CSV changes. Strict build audit:
build/audit/20261017T233406Z/summary.json. Differential reports:
build/batch-13-behavior.json (385 new), build/batch-13-file-manager.json (717)
and build/batch-13-diagnostics.json (192). All 102 repository tests pass.

The six retained local layout probes in .local/file-open-layout-variants.json
did not match the target stack assignment. Inspection reduced the remaining
difference to two local slots; swapping their spellings achieved the observed
layout. No inline assembly or uninitialized reads were added. Full expensive
analysis was not rerun; all work used existing target exports and compiler.

Buffered constructors, destructors, aligned filename ownership and additional
forwarding methods are now reconstructed and tested; see [file-lifetime.md](file-lifetime.md).
The +0x18 return is forwarded as raw EDX:EAX; EWin32File uses last-write FILETIME.

## Native Win32 file continuation

[Native Win32 file methods](native-win32-file.md) documents the reconstructed
EFile Close, EWin32File lifetime and I/O, timestamp methods, and parent-directory
helper. The subsequent [native opener/streaming work](native-file-streaming.md)
adds opening and streaming lifetime/producer methods. Streaming Read remains
external, and real concurrency is unverified.
