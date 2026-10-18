# Native opener and streaming-file reconstruction

All addresses refer to the Steam Windows 2016 PE32, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
The compiler remains VC++ 2008 RTM x86 with `/Od /Oy /Ob1 /Oi /MD /GS-`.

| Body | Original address | Mapped bytes |
| --- | --- | ---: |
| Streaming producer, slot +0x20 | 0x006a78a0 | 232 |
| Streaming startup, slot +0x24 | 0x006a7990 | 39 |
| Thread entry | 0x006a79c0 | 31 |
| EWin32StreamingFile constructor | 0x006a79e0 | 170 |
| Unsupported streaming Write | 0x006a7a90 | 16 |
| Streaming scalar deleting destructor | 0x006a7aa0 | 45 |
| Streaming destructor | 0x006a7ad0 | 144 |
| OpenNativeFile | 0x006a8180 | 700 |

## Opener

Read/write bits 0x400/0x800 select GENERIC_READ/GENERIC_WRITE. No access, or
write combined with streaming bit 0x1000, returns null. Bit 0x4000 enables
FILE_SHARE_READ. Creation bits 0x000/0x100/0x200/0x300 select
OPEN_EXISTING/OPEN_ALWAYS/TRUNCATE_EXISTING/CREATE_ALWAYS. Attributes normally
contain 0x80; bit 0x8000 selects raw value 0x60000001 instead. The raw opener
does not apply EFileManager::Open's separate option mask.

An INVALID_HANDLE_VALUE result calls GetLastError. Error 3, bit 0x100 and the
first attempt together cause an unchecked copy into the 260-byte local path,
parent-directory creation and one retry. The retry label reproduces the original
control flow; a loop emits extra RTM instructions. No path-length guard or
allocation-failure cleanup has been added.

Success creates a 12-byte EWin32File or a 72-byte EWin32StreamingFile. Both
use aligned allocation. Streaming passes block size 0x8000 and count 12, then
calls slot +0x24. A failed plain object allocation returns null without closing
the opened handle. A failed streaming object allocation still attempts the
virtual call through null. The differential fixture records that invalid read
instead of treating it as a valid return path.

## Streaming state and lifetime

RTTI confirms EWin32StreamingFile and its EWin32File base. Vtable 0x0071d874
has the eight inherited slots, followed by producer +0x20 and startup +0x24.
The constructor initializes field +0x0c, block size/count +0x28/+0x2c, their
32-bit product +0x34, positions/count +0x38/+0x3c/+0x40, and stop flag +0x44.
It allocates the product at alignment 16 into +0x30 and initializes the 24-byte
x86 critical section at +0x10. Null filename behavior is inherited unchanged.

Startup passes object+0x0c as CreateThread's thread-ID output and discards the
returned handle. The destructor nevertheless passes that field to
GetExitCodeThread and CloseHandle. The import table and original instructions
confirm this unusual behavior. Microsoft's [CreateThread contract](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createthread)
distinguishes those two values; the reconstruction preserves the binary.

For a nonzero +0x0c field, destruction sets stop, polls the exit code with
Sleep(0) after every query, and repeats while the stored status is 259. Query
failure leaves the previous status in place; no BOOL check was inserted.
It then closes that value, releases a nonnull buffer, deletes the critical
section, and runs the real base destructor. The scalar deleting wrapper also
releases the object when flags&1. The thread entry calls virtual slot +0x20 and
returns zero. Unsupported Write returns 0xffffffff.

The producer waits with Sleep(0) when signed capacity-minus-available is below
block size. Otherwise it reads at buffer+write-position, locks, adds the raw
transferred count to the write position and availability, resets a position at
or beyond capacity to zero, then unlocks. A signed short count ends the loop.
ReadFile's BOOL is retained but unused; no new failure policy was introduced.
This is the observed RTM x86 arithmetic, not a portability claim for signed
overflow or invalid buffer requests.

## Verification

`tools/test_native_opener.py` checks 548 original/rebuilt x86 fixtures against
independent expected traces, full fixture heap, counter, results and ABI.
It covers all combinations of the seven relevant option bits, directory retry
limits, filename/buffer/object allocation failures, null streaming allocation,
counter/product wrap, thread startup with unchanged failure output, exit-query
failure, teardown order, signed position edges and bounded producer sequences.
Real constructor/destructor, directory-helper and producer call chains execute.
Win32, allocation, filename helpers and scheduling are mocked. Huge or invalid
buffer requests are traced without dereferencing them. No game, actual thread
or filesystem test was performed.

The full matcher retains all previous 3,326 addresses and adds these eight
bodies /1,377 bytes. Total: 3,334 matches /296,054 bytes. All 58 sources compile,
18 tooling tests and 4,326 differential cases pass. Exact reports and hashes
are in [native-verification.json](native-verification.json).

A supplementary COFF review used Rust-based [objdiff-cli 3.8.2](https://github.com/encounter/objdiff/releases/tag/v3.8.2).
All 14 previously defined native-file bodies, including repeated base virtuals,
compare at 100%. This compares two reconstructed objects; upstream objmatch
and the hash-gated executable comparison establish actual binary matches.
The optional tool and its reports remain local; it adds no engine/build dependency.

Streaming Read at 0x006a7730 remains external. Real concurrency, complete file
ownership, original helper/member names and safe use of invalid inputs remain
unresolved. Matching objects are not a linked or playable engine.
