"""Blender background rendering with explicit transparent back faces.

Usage: blender --background --threads 2 --python this.py -- MODEL OUTPUT YAW.
Keeps imported front-face materials; excludes back faces even on double-sided
source materials so orientation failures cannot be concealed by two-sided shading.
"""
import math
from pathlib import Path
import sys
import json
import bpy
from mathutils import Vector,Matrix

args=sys.argv[sys.argv.index('--')+1:]
source,output=map(Path,args[:2]);yaw=float(args[2]) if len(args)>2 else 0
root=Path(__file__).resolve().parents[1]/'.local/assets'
if not output.resolve().is_relative_to(root):raise ValueError('render must remain private')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source.resolve()))
for ob in bpy.context.scene.objects:
    if ob.animation_data:
        ob.animation_data.action=None
        for track in ob.animation_data.nla_tracks:track.mute=True
    if ob.type=='ARMATURE':
        for bone in ob.pose.bones:bone.matrix_basis=Matrix.Identity(4)
    if ob.type=='MESH' and ob.data.shape_keys and ob.data.shape_keys.animation_data:
        ob.data.shape_keys.animation_data.action=None
        for track in ob.data.shape_keys.animation_data.nla_tracks:track.mute=True
    if ob.type=='MESH' and ob.data.shape_keys:
        for key in ob.data.shape_keys.key_blocks:key.value=0
bpy.context.view_layer.update()
for material in bpy.data.materials:
    if not material.use_nodes:continue
    nodes=material.node_tree.nodes;links=material.node_tree.links
    out=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
    original=out.inputs['Surface'].links[0].from_socket
    geometry=nodes.new('ShaderNodeNewGeometry');transparent=nodes.new('ShaderNodeBsdfTransparent')
    mix=nodes.new('ShaderNodeMixShader')
    links.new(geometry.outputs['Backfacing'],mix.inputs[0])
    links.new(original,mix.inputs[1]);links.new(transparent.outputs[0],mix.inputs[2])
    links.new(mix.outputs[0],out.inputs['Surface'])
positions=[ob.matrix_world@v.co for ob in bpy.context.scene.objects if ob.type=='MESH' for v in ob.data.vertices]
lo=Vector([min(v[i] for v in positions) for i in range(3)])
hi=Vector([max(v[i] for v in positions) for i in range(3)])
center=(lo+hi)/2;span=max(hi-lo);angle=math.radians(yaw)
region=None
if len(args)>4:
    region=[float(v) for v in args[3].split(',')];radius=float(args[4])
    if len(region)!=3 or radius<=0:raise ValueError('region is source x,y,z and positive radius')
    center=Vector((region[0],-region[2],region[1]));span=radius*2
bpy.ops.object.camera_add(location=center+Vector((math.sin(angle)*span*2,-math.cos(angle)*span*2,span*.3)))
camera=bpy.context.object;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=span*1.2;camera.data.clip_end=span*20
scene=bpy.context.scene;scene.camera=camera;scene.render.engine='CYCLES'
scene.cycles.samples=16;scene.cycles.device='CPU'
scene.world=bpy.data.worlds.new('Inspection world');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.4,.4,.4,1)
scene.render.resolution_x=420;scene.render.resolution_y=420;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.render.filepath=str(output.resolve());scene.view_settings.view_transform='Standard'
output.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.render.render(write_still=True)
output.with_suffix('.framing.json').write_text(json.dumps(dict(source=str(source),yaw=yaw,
    region_source_xyz=region,span=span,bind_pose_reset=True,
    purpose='inspection framing only; no asset geometry changed'),indent=2)+'\n')
