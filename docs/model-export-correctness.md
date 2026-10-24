# Model export correctness and portability

This bounded extraction batch fixes visual front-face conversion, distinguishes
serialized joint labels from runtime indices, and handles the identity-rotation
sentinel. Native C++ reconstruction and matching metadata are unchanged.

## Repository relationship

GitHub metadata confirms `jrwheels/psychonauts-decomp` is a fork of
`DrDecki/psychonauts-decomp`. Local `origin` and `upstream` already name those
repositories respectively; remote configuration was not changed. Work is isolated
on `asset-export-correctness`, based on the preserved asset-tool checkout. Older
dirty worktrees and the accepted Boyd library remain intact.

## Fixes and evidence

* Visual triangle lists and strips now convert source clockwise front faces to
  glTF counterclockwise order. The pinned MIT noclip renderer explicitly selects
  `GfxFrontFaceMode.CW`; original packed normals independently support that
  orientation. Only triangle indices are reversed. Positions, UVs, normals,
  weights, morph arrays and animation arrays remain unchanged for Boyd. Separate
  collision topology is not reinterpreted by this visual-stream correction.
* The Steam reader `0x0049a040` assigns runtime byte indices before recursive
  `0x00492010` consumes serialized ushort IDs. Parser metadata now records the
  traversal ordinal, byte index, parent and next-sibling byte indices separately.
  The raw ID and its uninterpreted bit fields are retained. Formerly guessed
  `joint_index`/`skeleton_index` names become `serialized_id_low12`/`high4`.
  Missing parent/sibling metadata is null; initialized runtime records use 255.
* Parsing retains duplicate serialized labels because the original reader ignores
  those IDs. Export still fails closed on ambiguous labels. Palette mapping is
  deliberately unchanged: existing exports map source palette labels into the
  flattened joint list. For tested single-skeleton rigs, labels equal preorder
  indices. General multi-skeleton/encoded-label runtime mapping is not established.
* Only an exact `(-1,-1,-1)` Euler triplet selects identity, as directly observed
  in `0x00492010`. Partial sentinel values remain ordinary Euler rotations.
  Scanning 50 PPF archives found 264 distinct character payloads: 262 parse, with
  207 skeletons/11,392 joints; two payloads stop on unsupported affector types.
  Two sentinel joints occur in Censor variants, none in Boyd. Both are unweighted
  leaves. The old conversion introduced approximately 1.737 degrees of bind
  rotation there; fixing it changes joint metadata/bind transforms but has no
  demonstrated visible weighted-vertex effect in these two models.

Binary evidence uses the supported Steam PE32 executable, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`. Original-reader execution on four real
model hierarchies passed eight cases, including replacing every child ID by
65535. Observed index writes, parent/sibling links, traversal return and sentinel
bypass agree. Stream reads, name ownership and Euler conversion were mocked;
this does not establish general rotation mathematics or allocation behavior.

## Verified outputs

| Asset | Vertices | Triangles | Rig / animation |
| --- | ---: | ---: | --- |
| Boyd LOD1 | 3,456 | 4,050 | 119 joints, 29 clips |
| Boyd LOD2 | 1,396 | 1,530 | 119 joints, 29 clips |
| Boyd + crate | 4,118 | 4,698 | 129 joints, 14 clips |
| Censor level 2, each of two variants | 2,541 | 2,524 | 68 joints, 2 original clips |
| Chalk prop | 30 | 24 | Static |
| OneUp collectible | 449 | 484 | Static |
| SACU serialized visual scene | 688 | 380 | Eight mesh entries, 14 textures |
| SACU collision | 56 | 104 | Separate raw collision geometry |

All nine deliverable GLBs pass Khronos Validator 2.0.0-dev.3.10 with zero errors
and warnings. SACU retains informational unused-resource notices. These are
serialized static scene/collision snapshots, not a complete playable level.

Original-data comparisons independently unpack triangles, packed normals, UVs,
palette bytes, weights and base-material/texture assignments. Collision indices and
vertices are also scalar-unpacked directly from the retained original scene. Boyd LOD1 has 4,050 face/normal agreements and zero
oppositions; crate has 4,698/0; both Censors have 2,524/0. Boyd LOD2 preserves one
opposing coincident source face (1,529 agreements/1 opposition). Its existing
fragment with a zero source normal still omits NORMAL rather than inventing it.

Blender 4.2.23 checks cover 684 samples of exported game clips (648 Boyd-family,
36 Censor) and 594 samples of 66 synthetic rotation probes across five rigs.
Maximum sampled source-unit position errors: Boyd family 0.004919, Censor
0.003323, diagnostic probes 0.000321. These pass the existing model-relative
tolerance and include the documented slerp key densification in saved Blender
projects. Synthetic probes are explicitly not recovered animations. Static
Blender imports verify full coordinate multisets and triangle counts for OneUp,
SACU visual and collision exports. Textured Cycles renders with transparent back
faces were inspected for old/new Boyd, corrected front/back Boyd, crate, Censor,
OneUp and SACU. This confirms visible exterior correction, not shader fidelity.

94 synthetic unit tests pass, including four new export tests. Five deliberately
corrupted original-data exports (position, normal, UV, weight and winding) are
rejected by the checker. All 259 accepted Boyd package hashes remain unchanged.
For replacement Boyd models every position/normal/UV/weight, morph, bind-matrix
and animation array compares exactly to the accepted package; only triangle
orientation and metadata change. The existing source-key/morph checker also
passes on all three replacements. Two Censor idle comparisons additionally
validate source bone bounds and nine source-derived CPU deformation poses each.

## Reproduction

Use the existing NumPy/Pillow environment and privately owned Steam archives.
Keep every output under this checkout's ignored `.local/assets/` directory.

```sh
python -B tools/psyexport.py "$PACKS/BVRB.ppf" --common "$PACKS/common.ppf" \
  --model characters/censorlevel2.plb --lod-mask 1 --output "$OUT/Censor.glb"
python -B tools/check_model_export.py "$PACKS/BVRB.ppf" "$OUT/Censor.glb" \
  --model characters/censorlevel2.plb --lod-mask 1 --report "$OUT/Censor-source.json"
# Omit --model to check a main scene. Scene names need not be unique.
python -B tools/probe_model_deformation.py "$OUT/Censor.glb" "$OUT/probes/Censor.glb"
blender --background --threads 2 --python-exit-code 1 \
  --python tools/blender_model_check.py -- "$OUT" probes
blender --background --threads 2 --python-exit-code 1 \
  --python tools/blender_model_render.py -- "$OUT/Censor.glb" "$OUT/Censor.png" 15
python -B -m unittest discover -s tests -v
```

The rig verifier supports one skinned mesh/armature per GLB, with optional morph
targets. Static verification supports multiple meshes. Mixed groups must be
checked separately. Blender checks save new .blend files inside the supplied
private output group; never point them at the accepted archive.

Detailed reports, source hashes, original-reader fixtures, preservation checks,
render images and replacement artifacts are private in `.local/assets/correctness`.
The replacement Boyd library is in `replacement/`, Censor clips in
`unrelated-animated/`, representative static exports in `survey/`, and synthetic
fixtures in `probes/`. No game installation, save, destination project or remote
repository was modified. Nothing was pushed or published.

## Limits and next work

Valid glTF and consistent Blender playback do not prove original-game appearance
or timing for every asset. Materials remain documented base-texture/unlit
approximations; detail/gloss/reflection, cubemap axes, transparency nuances,
dynamic placement, lights and animation-event behavior are incomplete. The
descending-time Boyd JAN remains explicitly unsupported. Six scanned skeletons
have serialized labels differing from local preorder; their runtime palette
interpretation needs targeted evidence before broadening that claim.

Next prioritize a manifest-driven extraction survey across props, independent
characters and environment scenes, recording attempted/exported/validated counts
and precise failure reasons. Preserve separate raw and converted outputs. Godot,
Unity and Unreal import/playback are not tested by this batch.
