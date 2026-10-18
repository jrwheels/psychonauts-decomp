# Model-format questions from native loading

These observations use the same Steam Windows executable hash as
[native mesh lookup](native-mesh-lookup.md). Runtime structure recovery and
serialized format parsing are separate evidence sources.

The matched native lookup functions establish 0xb0-byte runtime bones,
0x60-byte skeleton information records, unsigned byte indices, a 0xff sibling
sentinel and an implicit first child immediately after its parent. The existing
PLB research instead records packed 12-bit joint and four-bit skeleton IDs,
recursive names and local transforms. Do not treat the runtime byte index as
the complete serialized joint ID, or change the exporter hierarchy from these
runtime strides. The continuation below establishes native ID packing. Recover
the constructor or reader that builds the flat array before asserting
serialized-to-runtime ordering.

Bone lookup uses case-insensitive comparison and depth-first first-match
selection. Joint lookup uses case-sensitive comparison through a separate name
record. Export tools should preserve original spelling and IDs; a convenient
case-insensitive lookup is not proof that distinct serialized names are aliases.

Player mesh replacement reconnects `hatRoot_1` to `headJEnd_1`, and when present
`PackRootJ_1` to `spineJC_1`, through 0x0049a480. The exact constraint semantics
remain unresolved. A coherent bind-pose export alone cannot establish the
correct runtime attachment transform.

The shared backpack callee 0x005eb370 requests two JAN animations after finding
`PackRootJ_1`, then sets animation fields and flags. It is an animation setup
consumer, not evidence that JAN channels or PLB skeletons are decoded there.
The existing JAN version, interpolation and root-motion research should guide
later reader tests without assuming that successful parsing reproduces playback.

The resource path reaches RTTI-confirmed EStream/EFileStream/EFileReader and the
existing native file factory before dispatching into 0x0041f240. This is a
concrete bridge for investigating CYSP/PLB parsing. Neither the file's magic nor
its complete mesh/material/skeleton decoder has yet been established by this
batch. Keep owned-record fixtures and generated exports private and reuse the
existing asset parsers when testing a recovered reader.

## Native ID packing and animation association

Matched GetId 0x00492cc0 and its callee 0x0049a920 now establish the ID dataflow:
search the owning group's skeleton-pointer array, shift the found ordinal by
12, then OR a 16-bit pointer-derived bone ordinal at stride 0xb0. A missing
group entry uses ordinal zero. The runtime bone's +0xac byte is not the input
used to construct this ID. Existing lookup still uses that byte for other
operations, including name-record indexing and sibling traversal.

For group ordinals below 16 and bone ordinals below 4096, the result has the
4/12-bit split seen in PLB research. Native code does not enforce those bounds
or independently mask the bone ordinal to 12 bits. Larger values can overlap
fields or truncate on return. This agreement is useful for testing a reader;
it does not prove how serialized joint ordering becomes the runtime arrays.

The matched replacement method binds model+0x6c data into animation-state+0x20
only when model+0x78 is nonzero. Its lazy state also receives the game's blend
shape manager at +0x18. This separates group/ID lookup from animation-state
association. The exact model+0x6c serialized type, bind-transform construction,
skinning records and JAN playback remain unresolved; the C++ view keeps that
pointer opaque. No exporter or asset data changed in this batch.

## Resource input and ownership boundary

The file bridge at 0x0041f1b0 now matches. It owns its EFileReader and closes the
underlying EFile even when resource dispatch returns null. The stream records
unequal read counts in a sticky error byte, while a null destination means a
relative seek without an error update. Future reader fixtures should test both
paths; parsing success is not established by a single full-length read.

The dispatch context requires one result before PopFront at 0x006a5460 detaches
its payload and recycles the node. It then clears mesh context before later
association work. These observations establish ownership boundaries, not the
serialized model format. Context cleanup, parser 0x0047b980, and auxiliary
association records remain unresolved. No original file magic or asset payload
was used to claim these matches.
