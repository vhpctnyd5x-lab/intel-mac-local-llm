# 持ち帰った model.glb の下見を Mac の Blender で描く（VM には bpy が無い。10/10）。
# 使い方: Blender -b --factory-startup -P shitami.py -- model.glb preview.png
import sys

import bpy
from mathutils import Vector

glb, png = sys.argv[sys.argv.index('--') + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not objects:
    raise SystemExit('GLBにメッシュなし')
corners = [o.matrix_world @ Vector(x) for o in objects for x in o.bound_box]
lo = Vector(tuple(min(v[i] for v in corners) for i in range(3)))
hi = Vector(tuple(max(v[i] for v in corners) for i in range(3)))
center = (lo + hi) / 2
radius = max((hi - lo).length, 0.1)
bpy.ops.object.camera_add(location=center + Vector((1.2, -1.8, 1.0)) * radius)
camera = bpy.context.object
camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = radius * 1.1
scene = bpy.context.scene
scene.camera = camera
scene.world = bpy.data.worlds.new('背景')
scene.world.color = (0.3, 0.3, 0.3)
for offset in [(1, -2, 3), (-2, -1, 1)]:
    bpy.ops.object.light_add(type='AREA', location=center + Vector(offset) * radius)
    light = bpy.context.object
    light.data.energy = 400 * radius ** 2
    light.data.size = radius * 2
    light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 12
scene.render.resolution_x = scene.render.resolution_y = 512
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = png
bpy.ops.render.render(write_still=True)
