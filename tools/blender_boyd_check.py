"""General rigged GLB import/playback validation. Run with isolated Blender --background --threads 2 --python this.py -- PACKAGE.

Imports each GLB, selects every clip independently and compares evaluated mesh
positions to separate glTF CPU skin+morph evaluation. Writes private .blend files.
"""
import sys
import json
from collections import Counter
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix,Quaternion
import math
sys.path.insert(0,str(Path(__file__).resolve().parent))
from glb_skin import read,pose

package=Path(sys.argv[sys.argv.index('--')+1]).resolve()
if Path(__file__).resolve().parents[1]/'.local/assets' not in package.parents:raise ValueError('private package required')
subdir=sys.argv[sys.argv.index('--')+2] if len(sys.argv)>sys.argv.index('--')+2 else 'models'
report={'blender_version':bpy.app.version_string,'models':[]}
for path in sorted((package/subdir).glob('*.glb')):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps=30
    bpy.ops.import_scene.gltf(filepath=str(path))
    # Blender's LINEAR quaternion FCurves interpolate components, whereas glTF
    # requires spherical interpolation. Add mathematically derived slerp keys
    # so each remaining component-interpolation span is at most ten degrees.
    added=0
    for action in bpy.data.actions:
        groups={}
        for fc in action.fcurves:
            if fc.data_path.endswith('rotation_quaternion'):groups.setdefault(fc.data_path,{})[fc.array_index]=fc
        for curves in groups.values():
            if set(curves)!={0,1,2,3}:raise ValueError('incomplete imported quaternion channel')
            times=sorted({k.co.x for fc in curves.values() for k in fc.keyframe_points})
            qs=[Quaternion([curves[k].evaluate(t) for k in range(4)]).normalized() for t in times]
            additions=[]
            for t0,t1,q0,q1 in zip(times,times[1:],qs,qs[1:]):
                angle=2*math.acos(min(1,abs(q0.dot(q1))))
                spans=max(1,math.ceil(angle/math.radians(10)))
                for step in range(1,spans):
                    f=step/spans;additions.append((t0+(t1-t0)*f,q0.slerp(q1,f)))
            for time,q in additions:
                for k in range(4):curves[k].keyframe_points.insert(time,q[k],options={'FAST'})
                added+=1
            for fc in curves.values():
                for key in fc.keyframe_points:key.interpolation='LINEAR'
                fc.update()
    meshes=[o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith('DomainFirstMesh')]
    arms=[o for o in bpy.data.objects if o.type=='ARMATURE']
    assert len(meshes)==len(arms)==1
    ob,arm=meshes[0],arms[0];g,access=read(path)
    assert len(arm.data.bones)==len(g['skins'][0]['joints'])
    assert len(ob.data.vertices)==sum(access(p['attributes']['POSITION']).shape[0] for p in g['meshes'][0]['primitives'])
    orig=[];offset=0
    for primitive in g['meshes'][0]['primitives']:
        orig.extend(tuple(sorted(t+offset)) for t in access(primitive['indices']).reshape(-1,3))
        offset+=len(access(primitive['attributes']['POSITION']))
    actual=Counter(tuple(sorted(p.vertices)) for p in ob.data.polygons);missing=Counter(orig)-actual
    assert not (actual-Counter(orig)), 'import added/reindexed triangles'
    assert all(actual[t]>0 and Counter(orig)[t]>1 for t in missing), 'unexplained missing geometry'
    suppressed_duplicate_faces=sum(missing.values())
    assert (len(ob.data.shape_keys.key_blocks)-1 if ob.data.shape_keys else 0)==len(g['meshes'][0].get('weights',[]))
    owners=[arm,ob]+([ob.data.shape_keys] if ob.data.shape_keys else []);clips=[]
    source_positions=np.concatenate([access(p['attributes']['POSITION']) for p in g['meshes'][0]['primitives']])
    tolerance=float(np.ptp(source_positions,axis=0).max())*.001
    for ai,a in enumerate(g.get('animations',[])):
        for owner in owners:
            if owner.animation_data:
                owner.animation_data.action=None
                for t in owner.animation_data.nla_tracks:t.mute=True
        for pb in arm.pose.bones:pb.matrix_basis=Matrix.Identity(4)
        for key in (ob.data.shape_keys.key_blocks if ob.data.shape_keys else []):key.value=0
        activated=[]
        for owner in owners:
            if owner.animation_data:
                for t in owner.animation_data.nla_tracks:
                    if t.name==a['name']:t.mute=False;activated.append(owner.name)
        assert activated,'clip could not be independently selected'
        duration=max(float(access(s['input'])[-1,0]) for s in a['samplers'])
        errors=[]
        sample_times=[duration*k/8 for k in range(9)]
        for seconds in sample_times:
            frame=seconds*30+1;bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame))
            bpy.context.view_layer.update();ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh()
            actual=np.array([list(ev.matrix_world@v.co) for v in me.vertices]);ev.to_mesh_clear()
            parts=pose(g,access,seconds,ai);expected=np.concatenate([parts[(0,pi)] for pi in range(len(g['meshes'][0]['primitives']))])
            # Blender's official importer maps glTF Y-up to Blender Z-up.
            expected=expected[:,[0,2,1]];expected[:,1]*=-1
            err=float(np.max(np.abs(actual-expected)));errors.append(err)
            if err>tolerance:raise ValueError('%s %s frame %g import/pose discrepancy %g'%(path.name,a['name'],frame,err))
        clips.append({'name':a['name'],'seconds':duration,'max_position_error':max(errors),'sample_frames':[t*30 for t in sample_times]})
    for owner in owners:
        if owner.animation_data:
            owner.animation_data.action=None
            for t in owner.animation_data.nla_tracks:t.mute=True
    for pb in arm.pose.bones:pb.matrix_basis=Matrix.Identity(4)
    for key in (ob.data.shape_keys.key_blocks if ob.data.shape_keys else []):key.value=0
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());me=ev.to_mesh()
    actual=np.array([list(ev.matrix_world@v.co) for v in me.vertices]);ev.to_mesh_clear()
    parts=pose(g,access);expected=np.concatenate([parts[(0,pi)] for pi in range(len(g['meshes'][0]['primitives']))])
    expected=expected[:,[0,2,1]];expected[:,1]*=-1
    bind_error=float(np.max(np.abs(actual-expected)))
    if bind_error>tolerance:raise ValueError('independent bind-pose discrepancy %g'%bind_error)
    bpy.ops.wm.save_as_mainfile(filepath=str(package/subdir/(path.stem+'.blend')))
    report['models'].append({'file':path.name,'bones':len(arm.data.bones),'vertices':len(ob.data.vertices),'faces':len(ob.data.polygons),
        'morph_targets':len(ob.data.shape_keys.key_blocks)-1 if ob.data.shape_keys else 0,'position_tolerance':tolerance,'source_duplicate_faces_suppressed_by_blender':suppressed_duplicate_faces,'slerp_keys_added_for_blender':added,'clips':clips,'bind_pose_error':bind_error,'result':'independent import and bind pose passed'})
(package/'validation').mkdir(exist_ok=True)
(package/('validation/blender-import'+('-'+subdir if subdir!='models' else '')+'.json')).write_text(json.dumps(report,indent=2)+'\n')
print('ALL BLENDER IMPORT/PLAYBACK CHECKS PASSED')
