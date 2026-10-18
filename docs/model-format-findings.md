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
runtime strides. Recover the constructor/reader that builds the flat array
before connecting those representations.

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
