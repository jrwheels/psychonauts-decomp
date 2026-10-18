# CYSP parser and serialization dependencies

Reference: Steam Windows PE32 x86, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
VC++ 2008 RTM x86 15.00.21022.08, `/Od /Oy /Ob1 /Oi /MD /GS-`.
New method, container and record names are provisional. EStream's RTTI identity
and the existing EMesh constructor identity are established by earlier batches.

| Matched body | Original address | Mapped bytes |
| --- | --- | ---: |
| ResourceNode::SetOwner | 0x00464150 | 186 |
| ContextListBase::Clear | 0x006a5090 | 71 |
| ResourceList::GetFromBack | 0x006a5620 | 67 |
| EStream::ReadString | 0x006a5d10 | 203 |

Four matches add 527 bytes. Full comparison retains all previous 3,354 matches:
**3,358 /10,930 functions, 298,852 /2,935,679 mapped bytes**. The parser itself
remains unmatched; its control flow below is bounded native analysis plus the
explicitly limited original-only fixtures, not a speculative C++ implementation.

## Header and dependency table

Parser 0x0047b980 is a bool-returning thiscall with four stack arguments
(context, stream, byte-sized option, integer mode), `ret 0x10`. It creates a
TLS-associated temporary guard, increments receiver+0x188 and saves +0x15f.
The direct header sequence is:

| Stream offset | Width | Native use |
| --- | ---: | --- |
| 0x00 | 4 | Compare little-endian 0x50535943, bytes `CYSP` |
| 0x04 | 4 | Store stream+0x08; accept unsigned 317 through 319 |
| 0x08 | 4 | Header flags; retain at receiver+0x04 when nonzero and no prior value |
| 0x0c | 4 | Dependency count; used for pointer-table allocation and a signed loop |
| 0x10 | variable | Repeated name, first flag byte, second flag byte |

The native diagnostic explicitly calls the second word a PLB version. It does
not identify the entire CYSP container as an individual mesh. Existing local
asset research already uses CYSP for both scene/PLB records and shared resource
packs; that research's mesh decoder is not replaced here. Its lower-bound-only
version acceptance is not proof of native acceptance beyond version 319.

A dependency name is transferred through the newly matched ReadString with
capacity 0x104. Writing mode 1 uses strlen+1, including a terminator. Reading
uses the encoded four-byte length without independently appending or validating
a terminator. The two following bytes are tested separately for zero/nonzero,
not simply consumed as a single native 16-bit bitmask. Existing local asset
research calls these texture references; native lookup reaches the existing
EResourceManager view at GameApp+0x19c, whose full loader remains unreconstructed.

The integer mode contributes these lookup flags: 1 -> 0x10001, 2 -> 0x20000,
3 -> 0x30000, 4 -> 0x40000; other tested modes add zero. A nonzero first byte
adds 0x02, and a zero second byte adds 0x10. Lookup returns are stored in the
allocated pointer table, including null, then passed to context reader
0x0041d510 with stream, version, the byte option and mode.

The count-times-four allocation uses the compiler's unsigned overflow sequence
and passes 0xffffffff on multiplication overflow. The loop comparison is signed.
A synthetic count of 0xffffffff therefore requests that saturated allocation
size and skips the loop; the mocked context reader determines failure in that
fixture. No new bounds check or claim of safe malformed-input handling is added.

## Errors, cleanup and optional sections

Bad magic sets the return flag false. An unsupported version builds a diagnostic
with stream GetName, actual/minimum/maximum version, releases its temporary
array, then returns false. A false context-reader result obtains GetName and
also reaches the common failure exit. All these exits decrement +0x188 and
destroy the temporary guard before returning AL. The complete allocator/guard
ownership implementation remains external; no blanket allocation-failure or
exception-cleanup guarantee is asserted.

ReadBytes marks unequal transfer counts as a sticky stream error, but this
parser body does not explicitly branch on that error byte. Header locals can
retain unread bytes. Truncated-header fixtures use a fixed 0xa5 stack pattern;
their observed failure is not proof that every short read is reliably rejected.
The ReadString comparison is signed and strictly length < capacity. Zero and
oversized lengths transfer to null; reading mode 0 then zeros the destination's
first byte. Negative lengths can take the data path as a large unsigned request.
No matching criteria or original behavior was hardened to hide those cases.

After a successful context read, a further DWORD controls an optional structure.
When nonzero, the parser selects a newly produced result through GetFromBack,
allocates a 128-byte node at result+0x34, calls reader 0x0045b220 with stream,
version and that DWORD, then SetOwner with the result object. Header bit 0
separately controls a 44-byte object read by 0x00489780. It is installed at
receiver+0x140 if absent, or destroyed/freed if a value already exists. These
structures' exact serialized types remain provisional; their allocation sizes
are runtime sizes, not fixed serialized record strides.

At the outermost level, when the saved +0x15f flag is false, the parser drains
receiver+0x16c's deferred work: +0x160 selects a stream-based 0x0041ee40 route
or a filename-based 0x0041f070 route. Item cleanup at 0x0047ae80 releases its
+0x04 allocation, the item is freed, and the list is cleared. Nested calls skip
this drain. Optional sections and deferred processing are disassembled paths,
not covered by the original-only header fixtures.

## Direct call graph

The following table groups repeated direct calls. Indirect stream slots +0x04
and +0x08 are GetName and Read. The parser also calls TlsGetValue through IAT
0x007000dc and aligned allocation/free through 0x00700288/0x00700298.
All addresses in this table are relative to the hash-pinned reference above.

| Callee | Mapped bytes | Role/status |
| --- | ---: | --- |
| 0x00408d40 / 0x00408db0 | 104 /104 | Temporary guard construction/destruction; external |
| 0x0040aeb0 | 87 | Matched EFileReader::ReadBytes |
| 0x0040a7c0 / 0x005d40b0 | 45 /13 | Diagnostic formatting/sink; external |
| 0x0040afb0 / 0x00408960 | 67 /277 | Existing array Clear / shared Reserve; map status unchanged |
| 0x00408ca0 | 157 | Temporary allocation; external |
| 0x006a5d10 | 203 | Matched string operation |
| 0x00482a00 | 13 | Two-argument no-op hook; not promoted |
| 0x0047fcc0 | 1554 | Resource lookup/load through GameApp+0x19c; external |
| 0x0041d510 | 5802 | Context/domain reader and recursive contexts; external |
| 0x006a5620 | 67 | Matched result-list node lookup from last |
| 0x0045ac00 / 0x0045b220 | 170 /1470 | 128-byte node construction / recursive reading; external |
| 0x00464150 | 186 | Matched recursive owner association |
| 0x004896a0 / 0x00489780 / 0x004896e0 | 56 /674 /145 | Optional 44-byte object lifetime/read; external |
| 0x0041ee40 / 0x0041f070 | 545 /143 | Deferred stream/file operations; external |
| 0x0047ae80 | 30 | Deferred item cleanup; external |
| 0x006a5090 | 71 | Matched list Clear |

Following 0x0041d510 gives a concrete model-loading edge: it reads a name and
two 12-byte values, initializes context name +0x44 through 0x0041f670 when
absent, constructs RTTI-confirmed EMesh through 0x00435480 and calls its larger
reader 0x00435f40. Later it calls the previously investigated entity SetMesh
0x0043cad0. Its child-context path calls constructor 0x0041c670, recursively
0x0041d510, destructor 0x0041c720 on failure, and list insertion 0x006a5300 on
success, then stores the parent context at child+0x68. This is a supported
resource-to-runtime-mesh path, not an established material/skeleton decoder.

## Matched data structures and blockers

List Clear zeros count, first, last and cursor, releases pool+0x04 through
0x006a4fe0 without inserting a null guard, then zeros the pool. GetFromBack
rejects unsigned index >= count, begins at last+0x10 and follows node+0x00.
It returns the node; the parser accesses payload+0x08 separately.

SetOwner writes node+0x64, recursively visits children through packed array
+0x4c with 128-byte runtime stride, then updates each child's records through
array+0x58 with 44-byte runtime stride. It writes record+0x08 and the low byte
of record+0x0c, preserving the other bits. Ordinals above 255 truncate. The
receiver's own records are not updated unless a parent processes them. These
are owner links and child ordinals; no bone-ID or skin-weight interpretation
is established.

Context constructor 0x0041c670 still has its prior 0x14 versus 0x40 frame
mismatch. The array Clear at 0x0041ffa0 still differs only in its established
frame/temp allocation. A test instantiation of the byte-array member produced
a 79-byte destructor matching masked bytes at 0x00420320 but no unique full
matcher selection. Replacing the opaque member with that template regressed
the context destructor's frame, so the experiment was reverted and remains
private. No padding locals or shared-template changes were introduced.

## Verification

All 62 sources compile strictly; all 29 tooling tests pass. There are 454 fresh
original/rebuilt/independent-expected differential cases: 108 string/list, 266
stream regressions, 70 context/list cleanup and 10 recursive node cases. Graph
fixtures include depth, branching, null owners, a 257-child ordinal boundary,
whole-heap preservation and return ABI. Stream/pool/larger cleanup callbacks are
bounded mocks. Python and Rust agree on all four new relocation target sets.

All 59 other objects reproduce their prior SHA-256 after restoring only COFF
timestamps. Their 5,672 prior cases remain applicable: 454 fresh +5,672 cached
=6,126 differential cases. Separately, 44 synthetic original-parser fixtures
verify headers, version failures, poisoned short reads, dependency flags/null
lookup, overflow allocation requests and context-reader failure. These 44 cases
are not counted as rebuilt-parser equivalence. No asset payload or game launch
was used. Reports/hashes: [native-verification.json](native-verification.json).

Next recover context name ownership 0x0041f670 (61 bytes), then bounded reader
helpers reached by EMesh reader 0x00435f40 (3,971 bytes). Resolve the container
wrapper/frame issue before another full constructor attempt; keep the 1,911-byte
parser and 5,802-byte context reader external until their dependencies justify
complete reconstruction. Existing asset tooling remains separate and unchanged.
