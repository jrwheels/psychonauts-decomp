"""Generic Blender entry point: single-mesh rigs or static multi-mesh scenes.

Rig checks reuse the existing sampled skin/morph verifier. Static checks compare
all imported world-space vertices and triangle totals with a separate glTF CPU
reader. Neither establishes original-game shader or placement equivalence.
"""
from pathlib import Path
import json
import runpy
import sys
import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from glb_skin import read,pose

args=sys.argv[sys.argv.index('--')+1:]
package=Path(args[0]).resolve();subdir=args[1] if len(args)>1 else 'models'
root=Path(__file__).resolve().parents[1]/'.local/assets'
if not package.is_relative_to(root):raise ValueError('private package required')
files=sorted((package/subdir).glob('*.glb'))
if not files:raise ValueError('no GLB inputs')
rigged=[bool(read(p)[0].get('skins')) for p in files]
if all(rigged):
    runpy.run_path(str(Path(__file__).with_name('blender_boyd_check.py')),run_name='__main__')
elif any(rigged):
    raise ValueError('validate static and rigged groups separately')
else:
    rows=[]
    for path in files:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(path))
        g,access=read(path);parts=pose(g,access)
        expected=np.concatenate(list(parts.values()))[:,[0,2,1]];expected[:,1]*=-1
        objects=[ob for ob in bpy.context.scene.objects if ob.type=='MESH']
        actual=np.array([list(ob.matrix_world@v.co) for ob in objects for v in ob.data.vertices])
        assert actual.shape==expected.shape
        # Importer may reorder nodes. Compare the full coordinate multiset.
        def ordered(values):
            values=np.round(values,3)
            return values[np.lexsort((values[:,2],values[:,1],values[:,0]))]
        np.testing.assert_allclose(ordered(actual),ordered(expected),atol=.002,rtol=0)
        triangles=sum(len(ob.data.loop_triangles) for ob in objects)
        wanted=sum(access(p['indices']).size//3 for m in g['meshes'] for p in m['primitives'])
        assert triangles==wanted
        bpy.ops.wm.save_as_mainfile(filepath=str(path.with_suffix('.blend')))
        rows.append(dict(file=path.name,vertices=len(actual),triangles=triangles,
                         coordinate_rounding=.001,comparison_tolerance=.002,status='passed'))
    (package/'validation').mkdir(exist_ok=True)
    (package/'validation'/('blender-static-'+subdir+'.json')).write_text(json.dumps(dict(
        blender_version=bpy.app.version_string,models=rows,
        limitations=['coordinate multiset, not per-face seam correspondence','no material or original-game fidelity proof']),indent=2)+'\n')
    print('ALL STATIC IMPORT CHECKS PASSED')
