# Native mesh and skeleton lookup

Reference: Steam Windows PE32 x86, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
Compiler: VC++ 2008 RTM 15.00.21022.08, `/Od /Oy /Ob1 /Oi /MD /GS-`.
Names and partial class views follow existing script callers; new names are
provisional. No original asset or disassembly is included.

| Body | Original address | Mapped bytes |
| --- | --- | ---: |
| EBone::GetNext | 0x004378b0 | 85 |
| ETriggerA8::FindBone | 0x00438b70 | 103 |
| ETriggerA8::FindJoint | 0x00438be0 | 187 |
| EBone::Find | 0x00492c10 | 175 |

## Lookup behavior

The mesh's packed array at +0x54 stores category in five low bits and count in
27 high bits; +0x5c points to joint pointers. FindBone searches each joint's
bone at +0x08 recursively and returns the first match. FindJoint compares the
name at joint->info->name using case-sensitive strcmp and returns the joint.
The joint and bone lookup functions therefore differ in both result type and
name-comparison policy. No null-name or null-joint guards were added.

A runtime bone has skeleton pointer +0xa8, unsigned index +0xac, sibling index
+0xae and child-present bit 2 at +0xaf. Its name comes from skeleton+0x04,
index times 0x60, then record+0x5c. Recursive search uses _stricmp, checks self
first, then visits children depth first. The first child is this+0xb0 when the
child-present bit is set. Sibling traversal subtracts this bone's unsigned
index from its address, then adds the sibling index, both at stride 0xb0.
Sibling index 0xff returns null. This is an indexed flat runtime array, not a
heap-linked tree. No cycle detection or bounds checks were inserted.

The enclosing FindBone result variable is assigned before use. Its scope and
the FindJoint local spelling reproduce the observed RTM stack slots without
inline assembly, invented reads or dummy variables. These are compiler-layout
choices, not recovered original identifiers.

## Verification

The full Rust-assisted upstream matcher finds exactly four additions /550
mapped bytes and retains all 3,335 preceding matched addresses. Total:
3,339 /10,930 functions and 296,959 /2,935,679 bytes. Mapped sizes are unchanged;
COFF alignment padding is not counted as additional reconstruction.

All 59 sources compile strictly. `tools/test_mesh.py` passes 774 independent
expected/original/rebuilt x86 cases. The actual FindBone -> Find -> GetNext
chain executes, including nested children, skipped sibling indices, first-match
selection, empty arrays, name case, unsigned index 255 and unrelated packed
flag/category bits. Tests check comparison traces, return pointers, full
fixture memory and preserved registers/stack. Only ASCII _stricmp is mocked;
FindJoint executes the compiler's actual inline strcmp. Fixtures do not claim
safe behavior for cycles, corrupt indices, null names or invalid pointers.

All 58 previous objects were compared with the preceding strict-build hashes.
Restoring only each object's four-byte COFF timestamp reproduces its exact
previous SHA-256. Their previous 4,510 differential cases are reused on that
byte-level evidence, rather than rerun. Together with the 774 new cases, the
checkpoint has 5,284 applicable passing cases. The 29 tooling tests were rerun.
Rust and the authoritative Python decoder also agree on relocation targets for
each new body; the unchanged accelerator was not rebenchmarked.

Reports and hashes are recorded in [native-verification.json](native-verification.json).
Reproduce the new suite after the strict build with:

```sh
python3 -B tools/test_mesh.py "$REFERENCE" --report build/mesh/behavior.json
```

The [loading call graph](model-loading-next.md) distinguishes these matched
helpers from the still unreconstructed resource and mesh-loading bodies.
[Format findings](model-format-findings.md) keep exporter implications separate
from verified native behavior. No linked engine or animation playback is claimed.

The [mesh replacement continuation](native-mesh-replacement.md) subsequently
adds six matches /705 bytes and establishes pointer-derived native bone IDs.
It reruns all 774 lookup cases against the expanded module. The lookup numbers
above describe the preceding checkpoint; current totals and report hashes are
in native-verification.json.
