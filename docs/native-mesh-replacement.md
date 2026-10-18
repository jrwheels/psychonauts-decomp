# Native mesh replacement and bone identifiers

Reference: Steam Windows PE32 x86, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
VC++ 2008 RTM 15.00.21022.08, `/Od /Oy /Ob1 /Oi /MD /GS-`.

| Body | Original address | Mapped bytes |
| --- | --- | ---: |
| ETriggerA8::EnsureAnimState | 0x0043ae60 | 111 |
| EMeshEntity::LoadMesh | 0x0043c980 | 323 |
| EMeshManager::Create | 0x00454eb0 | 78 |
| EMeshAnimState::SetBlendShapes | 0x0048e480 | 22 |
| EBone::GetId | 0x00492cc0 | 29 |
| ESkeleton::GetBoneId | 0x0049a920 | 142 |

## Replacement and ownership

The replacement method is `bool __thiscall(const char *, int)`, with an AL
result and `ret 8`. RTTI-confirmed EMeshEntity and EPlayerEntity vtables both
point to it at slot +0x6c. It is the common replacement operation reached by
LoadMesh_impl and the player-specific member called by the already matched
LoadNewPlayerMesh_impl. The player member at 0x005ef390 remains external.

For a nonnull filename, replacement lazily initializes the mesh manager and
calls acquisition at 0x00454bc0 with the unchanged flags. A successful result
whose model+0x78 flag is nonzero gets animation state initialized. The method
then stores model+0x6c into animation-state+0x20. That data remains opaque;
its serialized skeleton type has not been established.

A null filename or failed acquisition selects pointer sentinel 1 and a false
result. Both paths still call SetMesh at 0x0043cad0, process the resulting mesh,
optionally call entity slot +0x14 with model+0xa4, select `headJA_1` through
0x0043cc00, and propagate entity+0x34 through 0x004370f0. Failure is not an
immediate return. No additional null checks or cleanup policy were added.

The inline mesh view follows +0x08 when it is neither null nor -1; those two
sentinels use the object itself. Names and scopes retain the RTM stack layout,
including an empty branch and a named inline return temporary. No dummy reads,
inline assembly or compiler-flag changes were used.

Bounded disassembly of the still external SetMesh establishes two different
paths. If entity+0xa8 is null, it creates an empty mesh and ignores the incoming
mesh and boolean. Otherwise it releases the existing object through 0x00454f70,
clears +0xa8, and handles a null argument, sentinel 1 or supplied pointer.
Supplied objects receive their owner at +0x14. The boolean can mark link +0x08
as -1; replacement passes false. Physics refresh and context propagation follow
installation on this latter path. These behaviors execute in the tests using
the original SetMesh body; they are not claimed as a new reconstruction.

The manager's newly matched Create allocates 0x210 bytes at alignment 16, calls
constructor 0x00435480, then writes the entity at +0x14. The constructor installs
RTTI-confirmed EInstancable vtable 0x007035fc and then EMesh vtable 0x00703e2c.
The existing upstream ETriggerA8 spelling is retained as a partial EMesh view.
Allocation failure still reaches a write at null+0x14. Constructors and the
release helper remain external; reference-count semantics are not established.

Lazy animation setup preserves existing state. Otherwise it allocates 0x224
bytes at alignment 16, calls constructor 0x0048d990, stores the result at
mesh+0x1d4 and binds GameApp+0x10, the existing blend-shape-manager field, into
state+0x18. Allocation failure retains the original subsequent null+0x18 write.
No destructor or complete animation-state layout is claimed.

## Bone identifiers

GetId delegates through bone+0xa8 to the matched ID packer. The packer searches
the owning group's packed array at +0x54/+0x5c for this skeleton, using an
unsigned-short counter. A missing skeleton selects index zero. It computes:

```text
ushort((group_index << 12) | ushort((bone_address - runtime_array) / 0xb0))
```

The runtime array pointer is skeleton+0x10; group pointer is skeleton+0x0c.
The assembly uses signed division, then truncates the bone offset to 16 bits;
it does not mask that offset to 12 bits. The bone's own +0xac byte is not read.
The group search is explicitly inlined to retain the observed /Od code and
stack slots. Partial structure and method names remain provisional.

This establishes native ID construction, not serialized-to-runtime ordering.
See [format findings](model-format-findings.md) for the conditional relationship
to the existing PLB 4/12-bit research.

## Verification and remaining work

The full Rust-assisted upstream matcher retains every previous 3,339 address
and finds exactly six additions /705 mapped bytes: total 3,345 /10,930 functions
and 297,664 /2,935,679 bytes. Mapped boundaries and alignment-byte accounting
are unchanged. Python and Rust relocation targets agree for every new body.

All 59 sources compile strictly and all 29 tooling tests pass. Fresh differential
verification passes 388 replacement/ID cases and all 774 preceding lookup cases.
The former executes both the direct/virtual replacement entry and the original
SetMesh -> reconstructed Create chain, lazy state/setter chains and ID delegation.
It checks independent expected traces, full fixture memory, results and return
ABI, including specified invalid writes on allocation failures. Constructors,
lookup, release, physics and rendering endpoints are mocked. Raw ID arithmetic
fixtures do not establish safe use of invalid pointers or oversized groups.

All 58 other objects reproduce their previous SHA-256 by restoring only the
four-byte COFF timestamp. Their 4,510 prior cases remain applicable without
rerunning them: 1,162 fresh plus 4,510 cached cases, 5,672 total. Reports and
hashes are in [native-verification.json](native-verification.json). Reproduce:

```sh
python3 -B tools/test_mesh_replacement.py "$REFERENCE" --report build/mesh-replacement/behavior.json
python3 -B tools/test_mesh.py "$REFERENCE" --report build/mesh-replacement/lookup-behavior.json
```

SetMesh's 301-byte C++ probe reproduces its instruction pattern but still has a
register-allocation phase mismatch after the release accessor, producing 300
bytes. It remains private rather than being promoted. Resource reader dispatch
0x0041f240 and its small stream dependencies are the next serialization targets;
state constructor 0x0048d990 is a smaller initialization target. Material/texture
resolution, actual constructor/destructor chains and asset decoding remain
unverified. No game, actual animation playback or model exporter was run.
