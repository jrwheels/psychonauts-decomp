#!/usr/bin/env python3
"""Write private portable-package instructions and content hashes after checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    ap=argparse.ArgumentParser();ap.add_argument('package',type=Path);args=ap.parse_args();p=args.package.resolve()
    root=Path(__file__).resolve().parents[1]/'.local/assets'
    if root not in p.parents:ap.error('private package required')
    m=json.loads((p/'metadata/manifest.json').read_text());bl=json.loads((p/'validation/blender-import.json').read_text())
    assert len(bl['models'])==3
    original=json.loads((p/'validation/original-data.json').read_text());assert all(v['status']=='passed' for v in original.values())
    assert (p/'validation/blender-import-engine_scale_0p01.json').exists()
    for folder in ['models','props','engine_scale_0p01']:
        for glb in (p/folder).rglob('*.glb'):
            v=json.loads(glb.with_suffix('.glb.report.json').read_text());assert v['issues']['numErrors']==v['issues']['numWarnings']==0
            shutil.copy2(glb.with_suffix('.glb.report.json'),p/'validation'/(folder+'-'+glb.name+'.report.json'))
    backups=root/'export-backups/BoydCooper';backups.mkdir(parents=True,exist_ok=True)
    for old in p.rglob('*.blend1'):shutil.move(str(old),str(backups/(old.parent.name+'-'+old.name)))
    rows='\n'.join('| %s | %s | %.6f | %d |'%(v['name'].replace('\\','/'),','.join(v['variants']),v['seconds'],v['facial_channels']) for v in m['clips'])
    text='''# Boyd Cooper — original Psychonauts portable package

This private package imports and plays without the Psychonauts runtime. It is a recovered character library, not an integration into any particular game. Keep original-asset licensing and ownership requirements when using it; no redistribution is supplied by this project.

## Contents

* models/Boyd_LOD1.glb and .blend: 119-joint Boyd, 3,456 vertices/4,050 source triangles, 29 independently selectable clips, 17 facial target slots.
* models/Boyd_LOD2.glb and .blend: the same rig/library, 1,396 vertices/1,530 source triangles. Original low LOD has no facial delta streams; target slots are zero for clip compatibility.
* models/BoydMilkCrate_LOD1.glb and .blend: separate 129-joint variant, 4,118 vertices/4,698 triangles, 14 independently selectable clips, 17 facial slots. Crate/bottles/clothing are already part of the original rigged mesh; no speculative accessory separation.
* props/BoydChalk.glb: original separate 30-vertex/24-triangle prop. Hand attachment/gameplay timing is not supplied.
* textures/: seven original references: body/head, detail and gloss maps, plus LiliSparkleCubeMap. All original compressed mip/face payloads and raw .psytexture records are retained; 96 PNG mip/face surfaces plus convenient base PNGs. GLBs embed base PNGs. Detail/gloss/reflection shaders require destination materials.
* animations/: every clip's source key/channel/morph/event JSON; source_records/: original JAN payloads, including the unsupported record. metadata/manifest.json gives IDs, offsets, hashes and associations.
* engine_scale_0p01/: optional uniformly converted GLB and Blender copies. Conversion is a deliberate destination choice (100 source units become one unit), NOT a recovered original metre constant. It scales vertices, morph deltas, joint translations, inverse binds and animated translations together; direction vectors and rotations stay unchanged. Source originals remain in models/.
* validation/: Khronos, original-data, Blender-import and unit-conversion results. previews/: representative posed images.

## Coordinate and portability rules

Source numerical units are preserved in models/. Export is Y-up; Blender's official importer maps that to Blender Z-up. No claim is made about the game's real-world metre scale. At optional scale 0.01, Boyd's bind-pose height is roughly 2.21 destination units. Use a different explicit factor through tools/scale_character_glb.py if needed. Skeletons are distinct; do not retarget by joint index across variants.

Root motion in boydchalk_walk, boydchalk_180 and boydchalk_rant01 is exported once on ROOTJ_1: the APF position keys exactly duplicate JAN translations. Decide whether your destination uses joint motion, an actor motion track, or an in-place controller. Do not apply that translation twice.

## Blender import and playback

Open a supplied .blend or use File > Import > glTF 2.0 for a GLB. Blender 4.2.23 LTS was independently tested. All clips have separate NLA tracks on the armature and, when needed, the shape-key datablock. To isolate a clip, clear active actions and mute every other NLA track on BOTH owners; unmute matching track names. Files are saved with tracks muted at bind pose. Source frame 0 appears at Blender frame 1; set scene FPS to 30. The armature, material meshes and shape keys are editable; images are embedded.

Raw Blender quaternion FCurves interpolate components rather than glTF slerp. The supplied projects add slerp-derived keys so each residual angular span is at most ten degrees. Nine samples per clip then agree within 0.00492 source units, or 0.0000493 after 0.01 scaling. Use tools/blender_boyd_check.py after a fresh GLB import to apply this correction and verify playback. Blender removes one reversed duplicate face from low LOD; GLB keeps both, while Blender renders the coincident surface two-sided. This is documented importer behavior, not unexplained geometry loss. No exact original-runtime animation equivalence is claimed.

## Destination-engine preparation

Godot: import GLB as a scene, inspect the skeleton, morph targets and AnimationPlayer clips; choose import scale or the converted library. Unity/Unreal: use a glTF importer supporting skins, blendshapes and multiple clips, or import the Blender project and perform a separately tested conversion. No unverified FBX is supplied. Use a generic/custom rig; a humanoid retargeting profile is not supplied. Build materials from base/detail/gloss/cube maps, map alpha/double-sided flags, and configure LOD selection, collision, hand attachments and animation state transitions. Hook exported events into your own audio/gameplay code.

## Known missing or uncertain data

* boyd_pickupbottle_freeze is preserved but not playable: rotation keys descend from frame 35 to 17. Runtime handling needs original loader evidence; keys were not arbitrarily sorted.
* Cubemap face numbers preserve stored order; axis orientation has not been independently verified. Original detail/gloss/reflection lighting and blendshapes' exact runtime normal/shader semantics are not independently verified against the original renderer. Position deltas and PBA samples do match source records.
* Animation event data are exported as metadata, not executed. ChalkWrite has 14 timed entries; destination event handlers must be implemented.
* No extra costume was inferred. ASGR/MMI1 Boyd model payloads are identical; the crate model is a genuine separate rig. Environmental objects with Boyd in their name are not treated as character accessories without attachment evidence.
* No Unity/Unreal/Godot runtime test is claimed. Independent Blender import, rig/morph deformation and sampled independent playback passed. Original-data checks cover every exported key and facial weight, but Blender samples nine evenly spaced poses per clip; continuous playback is not exhaustively proven.

## Recovered clips

| Original/source identifier | Variant | Seconds | Facial channels |
| --- | --- | ---: | ---: |
'''+rows+'\n'
    (p/'README.md').write_text(text)
    hashes={str(f.relative_to(p)):hashlib.file_digest(f.open('rb'),'sha256').hexdigest() for f in sorted(p.rglob('*')) if f.is_file() and f.name!='SHA256.json'}
    (p/'SHA256.json').write_text(json.dumps(hashes,indent=2)+'\n');print('Package finalized',len(hashes),'files',len(m['clips']),'clips')


if __name__=='__main__':main()
