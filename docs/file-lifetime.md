# Buffered-file lifetime

Reference: Windows Steam PE32, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
This continuation starts at fork commit `d2c5583` and upstream `6959341`.

RTTI identifies EFile, EReadBufferedFile and EWriteBufferedFile. The two
buffered classes each have EFile as their sole base at offset zero. Its
vtable has eight slots, including four pure virtual methods. The shared
source retains the name DiagnosticFile to avoid colliding with the existing
provisional file wrapper called EFile in script_lua.cpp.

Both constructors copy the underlying file's string at +4, allocate a buffer
with 16-byte alignment, and initialize their counters. The copied string and
buffer belong to the buffered object. Destructors close the nonnull underlying
file, release the buffer and string, and restore the base vtable. Writer
teardown first flushes; a short or failed write does not prevent teardown.
Close is a virtual operation and can itself destroy the wrapped object; the
buffered destructor does not separately delete that pointer.

IAT 0x00700288 is MSVCR90!_aligned_malloc; 0x00700298 is _aligned_free.
The latter is distinct from the ordinary operator-delete import at 0x00700198.
Scalar deleting destructors use the aligned release when flags&1 and return
this. The original base destructor has no filename-release body; buffered
teardown performs that release explicitly.

| Body | Original address | Mapped bytes |
| --- | --- | ---: |
| CopyFileName | 0x006a6e10 | 21 |
| FreeFileName | 0x006a6e30 | 27 |
| StrDup | 0x006a6e50 | 121 |
| EFile scalar deleting destructor | 0x006a9940 | 46 |
| Writer constructor | 0x006a9b30 | 139 |
| Writer Read | 0x006a9bc0 | 50 |
| Writer Size | 0x006a9c40 | 42 |
| Writer slot +0x18 forwarder | 0x006a9c70 | 42 |
| Writer scalar deleting destructor | 0x006a9da0 | 47 |
| Writer destructor | 0x006a9dd0 | 126 |
| Reader constructor | 0x006a9e50 | 139 |
| Reader slot +0x18 forwarder | 0x006aa040 | 32 |
| Reader scalar deleting destructor | 0x006aa0c0 | 47 |
| Reader destructor | 0x006aa0f0 | 118 |

StrDup is the existing upstream declaration, independently anchored by
AddFrozen_impl. It allocates strlen+1 bytes aligned to 16 and copies the
terminator. It returns null for a null input, but does not check allocation
failure before memcpy. CopyFileName/FreeFileName are provisional names; the
meaning of category 0x18 and the release helper's third argument is unresolved.
Slot +0x18 forwards raw EDX:EAX. The subsequent
[Win32 file reconstruction](native-win32-file.md) identifies last-write FILETIME
for that implementation; no signedness or universal meaning is claimed. Repeated short byte patterns require relocation/caller/vtable
constraints; a raw masked hit alone does not establish an identity.

The constructors' allocation locals and destructors' release local correspond
to values actually used by the CRT calls. They reproduce RTM's observed stack
layout without dummy or uninitialized locals. In-class destructor and Flush
bodies preserve the compiler's unused caller slots. Existing buffered methods
retain their original code after the base-class and buffer-type refinement.

`tools/test_file_lifetime.py` checks 329 original/rebuilt x86 cases with the
real filename-copy, constructor, destructor and deleting-wrapper chains. It
checks every fixture heap byte, call order, return values, stack cleanup and
nonvolatile registers. It covers empty/non-ASCII/1023-byte names, zero and large
capacity requests, null fields, delete-flag combinations, failed/short flushes,
and both halves of the 64-bit forwarding result. File calls and allocation are
mocked. Failed string allocations trace the ensuing invalid memcpy without
dereferencing it; they do not establish safe real CRT failure handling.

The four repeated base/unsupported virtual bodies remain unpromoted because
the matcher cannot uniquely assign them. Constructors require a valid wrapped
file and a null or terminated filename; real I/O, ownership sharing, concurrent
close, allocation strategy and an executable engine remain outside these tests.

This lifetime checkpoint compiled 57 fresh sources before the subsequent
Win32/streaming additions. Full relocation-aware matching
finds 14 additional functions /997 mapped bytes: 3,315 functions /293,839 bytes,
with every previous matching address retained. All 18 unit tests and all 3,407
differential cases pass. [native-verification.json](native-verification.json)
records exact reports, hashes, addresses and the before/after CSV promotion.
