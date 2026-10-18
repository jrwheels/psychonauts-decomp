# Resource context lifetimes

Reference: Steam Windows PE32 x86, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
VC++ 2008 RTM x86 15.00.21022.08, `/Od /Oy /Ob1 /Oi /MD /GS-`.
All new context, container and member names are provisional partial views.

| Body | Original address | Mapped bytes |
| --- | --- | ---: |
| ResourceContext destructor | 0x0041c720 | 102 |
| ContextListBase constructor | 0x006a5030 | 84 |
| ContextListBase destructor | 0x006a50e0 | 19 |

These three matches add 205 bytes. The context destructor's reference targets
constrain the otherwise short list destructor to this address; it is included
only after full matcher selection. The input stream work remains documented in
[native-resource-stream.md](native-resource-stream.md).

## Container and context ownership

The 24-byte list constructor accepts and ignores one stack argument. It sets
count +0x00, first +0x14, last +0x10, cursor +0x0c and pool +0x04 to zero, then
writes growth +0x08 as 10. The original also reserves a local initialized to 10;
the reconstruction retains it. List destruction calls external Clear at
0x006a5090. That routine clears links/count, releases pool +0x04 through
0x006a4fe0, then zeros the pool. The full pool allocator remains external.
The field roles beyond the previously matched PopFront links are provisional.

The context embeds lists at +0x04, +0x1c and +0x6c. Its destructor first invokes
Cleanup at 0x0041c790, then FreeFileName(context+0x44, 0x1a, 1). It destroys the
+0x6c list, clears the +0x34 array and calls Reserve(0, 0), then destroys the
+0x1c and +0x04 lists, in that order. The stored allocation is passed to free
even when null; no new guard is inserted. Remaining scalar fields are untouched
by this destructor outside the explicit cleanup callback.

The array uses the existing EArrayBase packed category/count/capacity layout
and 16-byte elements. Cleanup visits a member destructor at each element+0x04
through 0x00420320 before releasing array storage. The member's 12-byte partial
view is evidence from stride and call offset, not a decoded serialization type.
The type-specific TArray Clear uses the existing indexed accessor. Its machine
code remains unmatched: the 118-byte body uses a 0x24 frame and object temporary
at -0x08, versus original 0x28 and -0x0c. It is behaviorally tested but its CSV
row at 0x0041ffa0 is unchanged. No generic array implementation was modified.

## Constructor and parser boundaries

The context constructor at 0x0041c670 initializes the three lists with mode 1,
the array with (0, false), flags +0x40/+0x48 and allocation +0x44 to zero, a
24-byte member at +0x4c, the first argument at +0x64 and zero at +0x68. Its
second argument selects pointer +0x00, defaulting to address 0x00782fb4.
The pointee's allocator role is provisional. A bounded private C++ probe emits
the same 173-byte instruction sequence except stack frame/local displacements:
frame 0x14 versus original 0x40. It was not promoted or added to native source;
no artificial padding locals were introduced to force the result.

Bounded inspection of parser entry 0x0047b980 confirms the header sequence:

- At 0x0047ba17 it reads four bytes through EFileReader::ReadBytes, then at
  0x0047ba25 compares them with 0x50535943, little-endian bytes `CYSP`.
- A mismatch sets a failure flag and jumps to 0x0047c0bf.
- At 0x0047ba37 it reads a second four-byte header word, stores it in reader
  +0x08 at 0x0047ba57, and checks the unsigned range 0x13d through 0x13f.
  Values outside that range reach diagnostic construction; the whole error path
  has not been reconstructed or tested.

This identifies native signature/version handling and the previously untouched
stream word's use. It does not establish complete parsing success, record order,
skeleton creation, texture decoding or compatibility with every existing asset
parser. No original asset payload was needed for these observations.

## Verification and next targets

Full Rust-assisted comparison: 3,354 /10,930 functions, 298,325 /2,935,679 mapped
bytes, with every previous 3,351 matching row retained. Python and Rust agree
on each new body's relocation targets. All 61 sources compile strictly and all
29 tooling tests pass. No matching criteria or Rust backend changes.

The 68 fresh original/rebuilt/independent-expected fixtures check whole fixture
heaps, callback order, constructor return and callee-saved/stack ABI. They cover
ignored constructor modes, null/non-null pools and stored allocations, zero/one/
three association records, category edges and packed flag preservation. Actual
list Clear, filename free and array Reserve chains execute; complete context
cleanup, entry destruction, pool release and aligned free use bounded mocks.
No parser, actual allocation, asset or gameplay behavior was tested.

All 60 previous objects reproduce their previous SHA-256 after restoring only
the four-byte COFF timestamp. Their 5,938 existing differential cases remain
applicable without rerunning: 68 fresh plus 5,938 cached, 6,006 total.
[Verification metadata](native-verification.json) binds report and object hashes.

```sh
python3 -B tools/test_resource_context.py "$REFERENCE" --report build/resource-context/behavior.json
```

Next investigate list wrapper and +0x4c member constructor lifetimes to resolve
0x0041c670's frame mismatch. Inspect entry destructor 0x00420320 and cleanup
0x0041c790 before the larger 519-byte dispatch and 1,911-byte parser. Keep the
CYSP header evidence separate from any claim of a reconstructed mesh decoder.
