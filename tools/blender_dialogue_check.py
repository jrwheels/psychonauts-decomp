"""Blender import vs original-code facial weights at selected subframe times.

Run in bounded Blender background mode with -- RUNTIME_REPORT OUTPUT_DIR.
The expected deformation uses original weights plus existing validated GLB mesh
and morph deltas/skin math; it is not the original native vertex deformer.
"""
import copy
import hashlib
import json
import sys
from pathlib import Path
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from glb_skin import read,pose

args=sys.argv[sys.argv.index('--')+1:];report=json.loads(Path(args[0]).read_text());out=Path(args[1]).resolve()
root=Path(__file__).resolve().parents[1]/'.local/assets'
if not out.is_relative_to(root) or out.exists():raise ValueError('new private output required')
path=Path(report['glb']);assert hashlib.sha256(path.read_bytes()).hexdigest()==report['glb_sha256'];out.mkdir(parents=True)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=30;bpy.ops.import_scene.gltf(filepath=str(path))
g,access=read(path);names=g['meshes'][0]['extras']['targetNames']
arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE'];assert len(arms)==1
widgets={bone.custom_shape for arm in arms for bone in arm.pose.bones if bone.custom_shape}
objects=[o for o in bpy.context.scene.objects if o.type=='MESH' and o not in widgets]
assert len(objects)==1,[(o.name,o.parent.name if o.parent else None) for o in objects]
ob=objects[0];keys=ob.data.shape_keys
assert keys and all(name in keys.key_blocks for name in names)
clip=g['animations'][0];owners=list(bpy.context.scene.objects)+[keys]
for owner in owners:
 if owner.animation_data:
  owner.animation_data.action=None
  for track in owner.animation_data.nla_tracks:track.mute=track.name!=clip['name']
sampler=clip['samplers'][0];checks=[];selected=[]
for target in (0,.008333333,.025,.05,.075,.1,.15,.2,.3,.4,.5,.56666666,.7):
 entry=min(report['validation'],key=lambda x:abs(x['seconds']-target))
 if entry not in selected:selected.append(entry)
for entry in sorted(report['validation'],key=lambda x:x['max_weight_error'],reverse=True)[:3]:
 if entry not in selected:selected.append(entry)
for entry in selected:
 seconds=entry['seconds'];frame=1+seconds*30;bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame));bpy.context.view_layer.update()
 actual_weights=np.array([keys.key_blocks[name].value for name in names]);expected_weights=np.asarray(entry['original']);weight_error=float(np.max(abs(actual_weights-expected_weights)))
 if weight_error>1e-5:raise ValueError('Blender/native weight discrepancy %g'%weight_error)
 def native_access(i):
  if i==sampler['input']:return np.array([[0.]])
  if i==sampler['output']:return expected_weights.reshape(-1,1)
  return access(i)
 parts=pose(g,native_access,0);expected=np.concatenate([parts[(0,i)] for i in range(len(g['meshes'][0]['primitives']))]);expected=expected[:,[0,2,1]];expected[:,1]*=-1
 ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh();actual=np.array([list(ev.matrix_world@v.co) for v in me.vertices]);ev.to_mesh_clear();position_error=float(np.max(abs(actual-expected)))
 if position_error>.001:raise ValueError('Blender/native-weight deformation discrepancy %g'%position_error)
 checks.append(dict(seconds=seconds,max_weight_error=weight_error,max_position_error=position_error,vertices=len(actual)))
bpy.context.scene.frame_set(1);bpy.ops.wm.save_as_mainfile(filepath=str(out/'Milla-MITU066MI.blend'))
result=dict(status='passed',blender_version=bpy.app.version_string,glb_sha256=report['glb_sha256'],importer_bone_widgets=[o.name for o in widgets],checks=checks,max_weight_error=max(x['max_weight_error'] for x in checks),max_position_error=max(x['max_position_error'] for x in checks),limits=report['limits']+['expected vertex positions use original controller weights plus GLB CPU morph/skin; no native vertex deformer execution'])
(out/'blender-native-face.json').write_text(json.dumps(result,indent=2)+'\n');print('ORIGINAL WEIGHT / BLENDER FACE CHECKS PASSED',len(checks),result['max_position_error'])
