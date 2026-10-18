# Native model-loading targets

Continue from the Steam Windows reference used by the native checkpoint:
SHA-256 `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
The following addresses are evidence anchors, not newly reconstructed bodies.

| Function | Address | Mapped bytes | Evidence |
| --- | --- | ---: | --- |
| LoadNewPlayerMesh_impl | 0x005c0a60 | 266 | Existing matched Lua implementation |
| EPlayerControl::LoadMesh | 0x005ef390 | 892 | Relocation from that matched implementation |
| LoadMesh_impl | 0x005c2a40 | 437 | Existing named, unmatched Lua implementation |
| Shared native callee, provisional purpose | 0x005eb370 | 569 | Direct calls from both mesh-loading paths |

The matched LoadNewPlayerMesh implementation calls LoadMesh with the existing
EPlayerControl declaration's filename, flags and keep arguments. Its resolved
COFF relocation binds that member to 0x005ef390. Bounded disassembly confirms
that this member and LoadMesh_impl both call 0x005eb370. Recover the shared
callee's signature, ownership and error paths before assigning it a class or
claiming it decodes meshes. Follow verified calls into file/serialization and
resource-management functions rather than reconstructing unrelated subsystems.

The private asset research already distinguishes MPAK model records, CYSP/PLB
mesh and skeleton records, PPAK textures, and APF/JAN animation records. Those
are hypotheses to connect to native readers, not proof of engine semantics.
Prioritize serialized joint IDs and hierarchy, fragment palettes and weights,
bind transforms, animation versions, root motion and interpolation. Validate
native behavior against owned records and independent fixtures as each path
becomes understood. Runtime transform and animation behavior remains distinct
from successful format parsing or glTF validation.

A complete engine decompilation is not required for useful extraction. Recover
the necessary file/serialization functions, then mesh, skeleton, texture and
animation loaders. Keep exporter utilities, generated assets and experiments
separate from the matching C++ contribution. No asset or export is included in
this checkpoint.
