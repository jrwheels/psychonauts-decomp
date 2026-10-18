# Native model-loading call graph

All addresses refer to the Steam Windows reference, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
The four lookup bodies in [native-mesh-lookup.md](native-mesh-lookup.md) and six
[replacement/ID bodies](native-mesh-replacement.md), plus six
[resource-stream bodies](native-resource-stream.md), are now matched. Other edges
below come from bounded disassembly,
RTTI or relocations in already matched script implementations.

| Function or role | Address | Mapped bytes | Evidence/status |
| --- | --- | ---: | --- |
| LoadNewPlayerMesh_impl | 0x005c0a60 | 266 | Existing match |
| EPlayerControl::LoadMesh | 0x005ef390 | 892 | Existing caller relocation; not reconstructed |
| LoadMesh_impl | 0x005c2a40 | 437 | Existing named, unmatched script implementation |
| Shared backpack animation setup | 0x005eb370 | 569 | Calls with receiver at player+0x128; not a mesh decoder |
| EMeshEntity mesh replacement, slot +0x6c | 0x0043c980 | 323 | Matched; RTTI-confirmed vtables |
| Mesh manager acquisition | 0x00454bc0 | 500 | Called by mesh replacement; not reconstructed |
| Mesh path preparation | 0x00454dc0 | 67 | Called before cache lookup; not reconstructed |
| File-backed resource acquisition | 0x0041f1b0 | 143 | Matched owning EFileReader bridge |
| Reader dispatch | 0x0041f240 | 519 | Receives EFileReader; not reconstructed |

## Player and script callers

The existing LoadNewPlayerMesh_impl obtains the player, preserves its physics
matrix, calls the member at 0x005ef390 with filename, flags 3 and a boolean,
then restores the matrix with flags 0xb. The shared header's EPlayerControl is
a partial caller view; it is not an independently confirmed RTTI class name.

The native member preserves or chooses an animation name, invokes virtual slot
+0x6c and tests AL. On success it reconnects named joints, requests the helmet
default pose, refreshes backpack animations, optionally restores the saved
animation and loads the default animation-state file when player+0xac is null.
The explicit AL result is evidence that its existing void declaration is
incomplete; this batch leaves that upstream declaration unchanged pending a
full member reconstruction. The 200-byte animation-name buffer, inlined list
iterator and repeated animation-parameter initializers still need their exact
RTM layouts. No speculative implementation of this 892-byte member was added.

LoadMesh_impl uses the same virtual slot on an entity. Its flags depend on a
Lua argument and GameApp's low-detail-mesh bit. It handles load failure, and
only calls backpack setup when the entity is the current player. Thus the
shared callee is a player-specific post-load step, not the common mesh loader.

RTTI confirms EMeshEntity vtable 0x00703efc and EPlayerEntity vtable 0x0071345c.
Both have slot +0x6c pointing to 0x0043c980. This resolves the virtual edge in
both callers without guessing an override.

## Resource and skeleton route

0x0043c980 initializes the mesh manager if necessary, then calls 0x00454bc0.
The manager prepares a 300-byte path through 0x00454dc0, looks up a cached
resource at 0x006a6510, and on a miss reaches GameApp+0x81b4 through 0x0041f1b0.
It caches successful results through 0x006a63a0 and calls resource slot +0x04.
Failure branches and low-detail/production-loading policy remain unreconstructed.

0x0041f1b0 opens the path through the existing file factory at 0x00781d90 with
options 0x400 and mode 0. Its stack object writes vtables for RTTI-confirmed
EStream (0x00703650), EFileStream (0x00703640), then EFileReader (0x00703630),
passes that reader and flags to 0x0041f240, and destroys the reader. This connects
the model route to the recovered native/package/buffered file dispatch. The
reader dispatcher calls 0x0041c670, 0x0047b980 and 0x0041c720 before constructing
or processing the returned resource; their format roles remain unresolved.

After acquisition, 0x0043c980 conditionally creates animation state through
0x0043ae60, binds the new mesh through 0x0043cad0, handles model+0xa4 through
entity slot +0x14, and calls 0x0043cc00 with `headJA_1`. That helper calls the
newly matched FindBone. The model+0x78 flag and model+0x6c data participate in
animation-state setup but are not yet verified serialized skeleton fields.

The final helper 0x004370f0 propagates context into 0x90-byte per-fragment
records and child meshes. Its exact material/rendering role is unresolved.
Existing matched script relocations identify SetProperty at 0x004399b0 and
SetMaterialProperty at 0x00439aa0; no direct loader-to-texture-decoder edge was
established here. Do not infer material or texture reconstruction from those
names alone.

## Verified continuation and next targets

The replacement method now matches, together with lazy state initialization
0x0043ae60, empty-mesh creation 0x00454eb0, blend-shape binding 0x0048e480,
GetId 0x00492cc0 and native ID packing 0x0049a920. Constructor RTTI confirms that
the existing ETriggerA8 view is EMesh, derived from EInstancable. Its spelling
is retained to avoid an unrelated caller-wide rename.

SetMesh 0x0043cad0 is still external. Its initialization path ignores an incoming
replacement when the entity has no existing mesh; its replacement path releases
the old instance, then installs an argument or an empty sentinel. The original
helper executes in differential tests. Its private C++ probe remains blocked on
a register phase difference after manager release; no matching criterion changed.

Next follow EFileReader dispatch at 0x0041f240 and its small stream helpers into
the serialized resource reader. Lazy-state constructor 0x0048d990 is a smaller
bounded initialization target. Return to SetMesh when its accessor/ownership
interfaces are better understood. Do not duplicate existing file or asset tools.
The player-specific 0x005ef390 wrapper still needs exact iterator and parameter
layouts. The matched common operation now provides a verified endpoint for it.

The EFileReader file bridge now matches, along with its Read/ReadBytes, file
name/destructor and context result-list PopFront at 0x006a5460. The dispatcher
still depends on unreconstructed context construction 0x0041c670, destruction
0x0041c720 and parser 0x0047b980. Recover those smaller lifetime/reader dependencies
before assembling its complete 519-byte body. No new exporter was introduced.

The [context lifetime continuation](native-resource-context.md) matches the
context destructor 0x0041c720 and list constructor/destructor 0x006a5030/0x006a50e0.
Context construction 0x0041c670 remains blocked on frame/local allocation;
array Clear 0x0041ffa0 is behaviorally tested but also unmatched. Before the
larger dispatcher/parser, resolve the list wrapper/+0x4c construction and
association member destructor 0x00420320. Native parser header reads confirm
CYSP and stream+0x08 version-word handling without decoding mesh payloads.
