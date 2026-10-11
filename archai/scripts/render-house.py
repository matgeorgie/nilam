"""Run with Blender: blender --background --python scripts/render-house.py -- house.glb render.png
Use the viewer's furnished GLB export; the script renders that exact house.
"""
import sys
from pathlib import Path
import bpy
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:]
source=Path(args[0]).resolve();target=Path(args[1]).resolve()
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(source))
objects=[obj for obj in bpy.context.scene.objects if obj.type=='MESH']
points=[obj.matrix_world@Vector(corner) for obj in objects for corner in obj.bound_box]
lo=Vector(tuple(min(p[i] for p in points) for i in range(3)));hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
center=(lo+hi)/2;extent=max(hi.x-lo.x,hi.y-lo.y,hi.z-lo.z)
bpy.ops.object.camera_add(location=center+Vector((extent*.62,-extent*.85,extent*1.1)))
camera=bpy.context.object;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=extent*1.35
scene=bpy.context.scene;scene.camera=camera
bpy.ops.object.light_add(type='SUN',location=(0,0,20));sun=bpy.context.object;sun.data.energy=2;sun.rotation_euler=(.5,-.35,-.5);sun.data.angle=.08
bpy.ops.object.light_add(type='AREA',location=center+Vector((0,0,extent)));area=bpy.context.object;area.data.energy=1800;area.data.shape='DISK';area.data.size=extent
scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.7,.78,.88,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.35
scene.render.engine='CYCLES';scene.cycles.samples=48;scene.cycles.use_denoising=True
scene.render.resolution_x=1600;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(target)
scene.view_settings.view_transform='AgX'
bpy.ops.wm.save_as_mainfile(filepath=str(target.with_suffix('.blend')))
bpy.ops.render.render(write_still=True)
