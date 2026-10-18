# Native resource-file streams

Reference: Steam Windows PE32 x86, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
Compiler: VC++ 2008 RTM 15.00.21022.08, `/Od /Oy /Ob1 /Oi /MD /GS-`.
Stream class names are RTTI confirmed; MeshResourceReader, ResourceList and
new method/member names are provisional partial views.

| Body | Original address | Mapped bytes |
| --- | --- | ---: |
| EFileStream destructor | 0x0040adf0 | 78 |
| EFileStream::GetName | 0x0040ae40 | 28 |
| EFileReader::Read | 0x0040ae90 | 29 |
| EFileReader::ReadBytes | 0x0040aeb0 | 87 |
| MeshResourceReader::LoadFile | 0x0041f1b0 | 143 |
| ResourceList::PopFront | 0x006a5460 | 91 |

## Stream input and lifetime

The RTTI chain is EStream -> EFileStream -> EFileReader, with vtables
0x00703650, 0x00703640 and 0x00703630. The file adapter is 24 bytes. Stream
construction initializes +0x04 to zero and error byte +0x0c to false; +0x08
remains untouched. The adapter adds EFile pointer +0x10 and owned byte +0x14.
Its GetName slot +0x04 returns the file's name pointer at +0x04 without copying
or adding a null-file check. Reader slot +0x08 forwards to ReadBytes.

For nonnull data, ReadBytes calls the existing EFile Read slot and compares the
raw returned count with the request. Any unequal count sets +0x0c; a later full
read does not clear it. For null data it calls Seek(size, 1), even for zero size,
and ignores the seek result. That branch does not update the error flag. These
are void stream operations, not a new read-count API or an EOF policy.

The file-stream destructor installs its own vtable, and when owned is true,
closes a nonnull file through slot +0x04 and clears +0x10. Borrowed files remain
untouched. Base destruction installs the EStream vtable. No additional file
release or error propagation has been inserted.

## Resource bridge and transfer

The matched file bridge opens through the existing factory with options 0x400
and mode zero. An open failure returns null. Success constructs an owning local
EFileReader, passes it and unchanged flags into external dispatch 0x0041f240,
and destroys the reader before returning the dispatch result, including a null
result. A direct return expression preserves the original destructor/return
stack layout. The owned constructor mode is compared with 1.

Dispatch builds a context through 0x0041c670, invokes parser 0x0047b980 and tears
it down through 0x0041c720 on every return. It requires context+0x1c to equal
one before detaching that list's first result. The newly matched PopFront reads
its node payload, advances first at +0x14, clears the new first's previous link,
or clears last at +0x10 when empty, then calls external node recycling at
0x006a5260 and returns the payload. It does not itself destroy the payload or
check for an empty input list. Full node-pool/count bookkeeping is unresolved.

This gives a verified input/lifetime bridge from the mesh manager to resource
dispatch, and a verified result-transfer endpoint. The parser and context still
need their exact layouts, container lifetimes and auxiliary association record
at 0x0041f450. No CYSP/PLB magic, texture decoding or original asset contents were
verified here. Existing asset parsers remain separate from these native views.

## Verification

The full Rust-assisted upstream matcher adds six unique addresses /456 bytes
and retains all previous 3,345 matching rows. Total: 3,351 /10,930 functions and
298,120 /2,935,679 mapped bytes. Python and Rust relocation decoding agree for
every new body. No matching rules or Rust backend code changed.

Four short supporting COMDAT bodies also compile and pass behavior checks:
EStream::GetName and the EStream/EFileStream/EFileReader deleting wrappers.
Their original slots are known from vtables, but matcher selection remains
ambiguous among identical bodies. Their CSV rows were not promoted and they
are not included in the six new matches.

All 60 sources compile strictly; all 29 tooling tests pass. The 266 new
original/rebuilt/independent-expected x86 fixtures cover direct and virtual reader
chains, read/skip/count edges, sticky errors, owned/borrowed destruction,
deleting flags, null names, open/parser failures, flag forwarding, and one/two
node transfers. A parser mock calls the actual virtual reader twice before the
real destructor closes the file. Tests check traces, complete fixture heap,
results and return ABI. I/O, parser behavior, close/free and node recycling are
bounded mocks; no file or asset was read by this test suite.

All 59 previous objects reproduce their old SHA-256 when only each four-byte
COFF timestamp is restored. Their 5,672 established cases remain applicable
without rerunning them: 266 fresh plus 5,672 cached, 5,938 total. Reports and
hashes are recorded in [native-verification.json](native-verification.json).

```sh
python3 -B tools/test_resource_stream.py "$REFERENCE" --report build/resource-stream/behavior.json
```

Next recover the context constructor/destructor 0x0041c670/0x0041c720 and parser
entry 0x0047b980 before insisting on a complete 519-byte dispatch match. The
larger dispatcher remains external; its context and parser are not speculative
C++ implementations. Matching objects are not a linked or playable engine.
