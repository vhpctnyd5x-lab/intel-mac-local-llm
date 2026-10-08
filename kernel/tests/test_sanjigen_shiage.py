"""通常は Blender を絶対に起動しない。SEISEI_BLENDER=1 だけ実機試験（Claude 用）。"""

import ast
from collections import namedtuple
import importlib.util
import math
import json
import signal
import textwrap
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import sanjigen_shiage as s


class OfflineTests(unittest.TestCase):
    def test_cage_distance_uses_independent_bvh_and_local_units(self):
        class Vector(tuple):
            def __new__(cls, values):
                return tuple.__new__(cls, values)

            def __sub__(self, other):
                return Vector(a - b for a, b in zip(self, other))

            @property
            def length(self):
                return math.sqrt(sum(v * v for v in self))

        class Matrix:
            def __init__(self, scales):
                self.scales = scales

            def __matmul__(self, vector):
                return Vector(a * b for a, b in zip(self.scales, vector))

            def inverted(self):
                return Matrix(tuple(1 / a for a in self.scales))

            def to_3x3(self):
                return SimpleNamespace(col=[Vector(a if i == j else 0 for j in range(3))
                                            for i, a in enumerate(self.scales)])

        corners = [Vector((0, 0, 0)), Vector((1, 1, 1))]
        vertices = [Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0))]
        faces = [(0, 1, 2)]
        source = (Matrix((2, 2, 2)), corners, vertices, faces, [])
        target = (Matrix((4, 2, 1)), corners, [Vector((.5, .5, .5))], [], [])
        nearest = Mock(return_value=(Vector((1, 0, 0)), None, 0, 0))
        tree = SimpleNamespace(find_nearest=nearest)
        factory = Mock(return_value=tree)
        fake_math = SimpleNamespace(Vector=Vector, bvhtree=SimpleNamespace(
            BVHTree=SimpleNamespace(FromPolygons=factory)))
        fake_bpy = SimpleNamespace(context=SimpleNamespace(
            view_layer=SimpleNamespace(update=lambda: None), evaluated_depsgraph_get=lambda: None))
        with patch.object(s, 'bpy', fake_bpy), patch.object(s, 'mathutils', fake_math), patch.object(
                s, '_geometry_snapshot', side_effect=[source, target, source, target]):
            cage, distance = s._bake_geometry(None, None)
            expected = math.sqrt(.5) * 1.5 + math.sqrt(3) * .005
            self.assertAlmostEqual(cage, expected)
            self.assertAlmostEqual(distance, math.sqrt(24) + expected * 8)
            factory.assert_called_once_with(vertices, faces)
            nearest.assert_called_once_with(Vector((1, .5, .25)))
            cage, distance = s._bake_geometry(None, None, cage=0)
            self.assertEqual(cage, 0)
            self.assertAlmostEqual(distance, math.sqrt(24))
            self.assertEqual(factory.call_count, 1)

    def test_restore_does_not_touch_deleted_rna(self):
        class Object:
            mode, hide_render, removed = 'OBJECT', False, False

            @property
            def name(self):
                if self.removed:
                    raise ReferenceError('削除済み RNA')
                return '消す物体'

            def hide_get(self):
                return False

        class Objects(dict):
            def __iter__(self):
                return iter(self.values())

        obj = Object()
        objects = Objects({obj.name: obj})
        objects.active = obj
        update = Mock()
        context = SimpleNamespace(object=None, selected_objects=[obj],
                                  view_layer=SimpleNamespace(objects=objects, update=update))
        fake_bpy = SimpleNamespace(context=context, ops=SimpleNamespace(
            object=SimpleNamespace(select_all=Mock(), mode_set=Mock())))
        with patch.object(s, 'bpy', fake_bpy):
            state = s._state()
            obj.removed = True
            objects.clear()
            objects.active = None
            s._restore(state)
        self.assertIsNone(objects.active)
        update.assert_called_once_with()

    def test_uv_pixel_coverage(self):
        from shindan_bake import uv_pixels
        points = [(0, 0), (1, 0), (0, 1), (1, 1)]
        mesh = SimpleNamespace(
            calc_loop_triangles=lambda: None,
            uv_layers=SimpleNamespace(active=SimpleNamespace(
                data=[SimpleNamespace(uv=p) for p in points])),
            loop_triangles=[SimpleNamespace(loops=(0, 1, 2)),
                            SimpleNamespace(loops=(1, 3, 2))])
        self.assertEqual(uv_pixels(mesh, 8, 8), set(range(64)))
        mesh.loop_triangles = [SimpleNamespace(loops=(0, 1, 2))] * 2
        self.assertEqual(len(uv_pixels(mesh, 8, 8)), 36)
        mesh.loop_triangles = [SimpleNamespace(loops=(0, 0, 0))]
        self.assertEqual(uv_pixels(mesh, 8, 8), set())

    def test_sources_and_import_contract(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'sanjigen_shiage.py').read_text())
        imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                   for alias in node.names]
        self.assertEqual(set(imports), {'bpy', 'bmesh', 'mathutils', 'mathutils.bvhtree', 'math'})
        self.assertFalse(any(isinstance(n, ast.ImportFrom) for n in ast.walk(tree)))
        functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        self.assertEqual(len(functions), len(set(functions)))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                self.assertTrue(ast.get_docstring(node), node.name)
        self.assertLessEqual(len((root / 'sanjigen_shiage.md').read_text()), 2000)
        for name, code in BLENDER_STAGES:
            ast.parse(_blender_script(name, code))
        # 台本から呼ぶ公開名は既存の門番を通る。run/worker は呼ばない。
        spec = importlib.util.spec_from_file_location('shiage_gate', root / 'sanjigen.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        gate.validate('import kit\n' + '\n'.join('kit.' + n + '(None)' for n in s.TOOLS))

    def test_bad_arguments_before_blender(self):
        cases = [
            (s.import_model, ('x.blend',), {}),
            (s.clean, (None,), {'merge_by_distance': -1}),
            (s.clean, (None,), {'max_hole_edges': 2}),
            (s.split_parts, (None,), {'how': 'guess'}),
            (s.split_parts, (None,), {'min_faces': 0}),
            (s.split_parts, (None,), {'color_threshold': math.nan}),
            (s.remesh, (None,), {'kind': 'magic'}),
            (s.remesh, (None,), {'target_faces': 4.5}),
            (s.remesh, (None,), {'target_faces': True}),
            (s.keep_shape_for_thin_parts, (None,), {'ratio': 0}),
            (s.smart_uv, (None,), {'angle': 90}),
            (s.uv_pack, (None,), {'margin': -1}),
            (s.uv_layout_png, (None, 'x.png'), {'size': 0}),
            (s.apply_texture, (None, ''), {}),
            (s.bake_from_original, (None, None), {'size': 8193}),
            (s.bake_from_original, (None, None), {'cage': -1}),
            (s.project_views, (None, {}), {}),
            (s.project_views, (None, {'rear': 'x.png'}), {}),
            (s.project_views, (None, {'front': ''}), {}),
            (s.auto_rig, (None,), {'kind': 'cat'}),
            (s.animate, (None,), {'kind': 'run'}),
            (s.animate, (None,), {'seconds': math.inf}),
            (s.turntable_video, ('x.mp4',), {'seconds': -1}),
            (s.turntable_video, ('x.mp4',), {'engine': 'METAL'}),
            (s.render_animation_mp4, ('x.gif',), {}),
        ]
        for fn, args, kwargs in cases:
            with self.subTest(fn=fn.__name__, kwargs=kwargs), patch.object(s, 'bpy', None):
                with self.assertRaises(ValueError):
                    fn(*args, **kwargs)

    def test_output_requires_trusted_resolver(self):
        with patch.object(s, '_resolve_output', None):
            with self.assertRaises(RuntimeError):
                s._output('uv.png', ('.png',))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            def resolve(name):
                path = (root / name).resolve()
                if Path(name).is_absolute() or not path.is_relative_to(root) or path == root:
                    raise ValueError('出力先の外')
                path.parent.mkdir(parents=True, exist_ok=True)
                return path
            with patch.object(s, '_resolve_output', resolve):
                self.assertEqual(s._output('parts/x.png', ('.png',)), str(root / 'parts/x.png'))
                for name in ('../x.png', '/tmp/x.png'):
                    with self.assertRaises(ValueError):
                        s._output(name, ('.png',))
                (root / 'link').symlink_to(root.parent, target_is_directory=True)
                with self.assertRaises(ValueError):
                    s._output('link/x.png', ('.png',))

    def test_overlap_area_not_only_bounding_boxes(self):
        a = [(0, 0), (1, 0), (0, 1)]
        self.assertAlmostEqual(s._intersection_area(a, a), 0.5)
        self.assertAlmostEqual(s._intersection_area(a, list(reversed(a))), 0.5)
        self.assertEqual(s._intersection_area(a, [(1, 0), (1, 1), (0, 1)]), 0)
        self.assertEqual(s._intersection_area(a, [(2, 2), (3, 2), (2, 3)]), 0)
        self.assertGreater(s._intersection_area(a, [(0.2, 0.2), (0.8, 0.2), (0.2, 0.8)]), 0)

    def test_uv_islands_and_overlap_without_blender(self):
        vector = namedtuple('UV', 'x y')
        def mesh(vertices, coordinates):
            loops = [SimpleNamespace(vertex_index=i) for i in vertices]
            faces = [SimpleNamespace(index=i, loop_indices=range(i * 3, i * 3 + 3)) for i in range(2)]
            return SimpleNamespace(
                polygons=faces, loops=loops,
                uv_layers=SimpleNamespace(active=SimpleNamespace(
                    data=[SimpleNamespace(uv=vector(*p)) for p in coordinates])),
                loop_triangles=[SimpleNamespace(loops=f.loop_indices, polygon_index=f.index) for f in faces],
                calc_loop_triangles=lambda: None)
        joined = mesh([0, 1, 2, 1, 3, 2], [(0, 0), (1, 0), (0, 1), (1, 0), (1, 1), (0, 1)])
        result = s._uv_report(joined)
        self.assertEqual((result['uv_islands'], result['uv_overlap_pairs']), (1, 0))
        self.assertTrue(result['uv_overlap_complete'])
        overlap = mesh([0, 1, 2, 3, 4, 5], [(0, 0), (1, 0), (0, 1)] * 2)
        result = s._uv_report(overlap)
        self.assertEqual((result['uv_islands'], result['uv_overlap_pairs']), (2, 1))
        self.assertFalse(s._uv_report(overlap, max_pairs=0)['uv_overlap_complete'])
        outside = mesh([0, 1, 2, 3, 4, 5], [(0, 0), (1, 0), (0, 1), (2, 2), (3, 2), (2, 3)])
        result = s._uv_report(outside)
        self.assertEqual(result['uv_outside_loops'], 3)
        self.assertEqual(result['uv_overlap_pairs'], 0)


# 段ごとに別プロセス。初段以外は直前の .blend を CLI で開く。
# 一時フォルダは旧版も毎回新規だった。再実行を旧結果で合格させないため、
# 回ごと/段ごとに一意な場所を使い、終了コード・完了印・checkpoint を全て確認。
# 失敗後の自動再試行はしない（クラッシュ報告を増やさない）。ログと .blend は残す。
BLENDER_COMMON = r'''
import bpy
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sanjigen_shiage as s
root = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
checkpoint = Path(sys.argv[sys.argv.index('--') + 2]).resolve()
def output(name):
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root) or path == root:
        raise ValueError('出力先の外')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
s.configure_output(output)
scene = bpy.context.scene
scene.render.threads_mode = 'FIXED'
scene.render.threads = 1
scene.render.resolution_x = scene.render.resolution_y = 64
scene.render.resolution_percentage = 100
scene.render.fps = 4
scene.cycles.samples = 1

def cube(name, x=0, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_cube_add(location=(x, 0, 0))
    obj = bpy.context.object
    obj.name, obj.scale = name, scale
    return obj

def color(obj, rgba):
    attr = obj.data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
    obj.data.color_attributes.active_color = attr
    for item in attr.data:
        item.color = rgba

def assert_file(name, magic):
    path = root / name
    assert path.is_file() and path.stat().st_size > 32, name
    assert path.read_bytes().startswith(magic), name

'''

BLENDER_STAGES = (
    ('setup', r'''
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.context.view_layer.update()
# 色と UV を持つ、離れた二つの塊を1オブジェクトにする。
a, b = cube('原本', -2), cube('塊B', 2)
color(a, (0.9, 0.02, 0.01, 1))
color(b, (0.9, 0.02, 0.01, 1))
bpy.ops.object.select_all(action='DESELECT')
a.select_set(True)
b.select_set(True)
bpy.context.view_layer.objects.active = a
bpy.ops.object.join()
del b
scene['shiage_test_source'] = a.name
'''),
    ('clean', r'''
# 共有メッシュの清掃でも、もう一方の形/UV/色を変えない。
peer = bpy.data.objects.new('清掃共有', a.data)
scene.collection.objects.link(peer)
peer_mesh = peer.data
before = (len(peer_mesh.vertices), len(peer_mesh.polygons))
assert s.clean(a)['non_manifold_edges'] == 0
assert a.data != peer_mesh and peer.data == peer_mesh
assert (len(peer_mesh.vertices), len(peer_mesh.polygons)) == before
assert a.data.uv_layers.active and a.data.color_attributes.active_color
s._remove_object(peer)
'''),
    ('split_loose', r'''
parts = s.split_parts(a, 'loose', min_faces=1)
assert len(parts) == 2
assert sum(len(p.data.polygons) for p in parts) == len(a.data.polygons)
assert all(p.data.color_attributes.active_color is not None for p in parts)
assert all(p.data.uv_layers.active is not None for p in parts)
assert a.hide_get() and a.hide_render
scene['shiage_test_parts'] = json.dumps([p.name for p in parts], ensure_ascii=False)
scene['shiage_test_target'] = parts[0].name
'''),
    ('import_export', r'''
saved = s.save_parts('parts')
assert len(saved) == 2
for path in saved:
    assert Path(path).read_bytes()[:4] == b'glTF'
imported = s.import_model(saved[0])
assert len(imported) == 1 and imported[0].data.polygons
# obj/fbx の読込も小さい実ファイルで確認。
for ext in ('obj', 'fbx'):
    s._active(parts[0])
    if ext == 'obj':
        bpy.ops.wm.obj_export(filepath=str(output('input.obj')), export_selected_objects=True)
    else:
        bpy.ops.export_scene.fbx(filepath=str(output('input.fbx')), use_selection=True, bake_anim=False)
    found = s.import_model(str(root / ('input.' + ext)))
    assert found and all(o.type == 'MESH' for o in found)
    for obj in found:
        s._remove_object(obj)
s._remove_object(imported[0])

'''),
    ('split_modes', r'''
for repeat in range(2):
    # 材質・法線・頂点色分割。min_faces が大きくても面は失わない。
    for how in ('material', 'normal_angle', 'vertex_color'):
        obj = cube('分割_' + how)
        if how == 'material':
            for i in range(2):
                obj.data.materials.append(bpy.data.materials.new('色' + str(i)))
            for face in obj.data.polygons:
                face.material_index = face.index % 2
        if how == 'vertex_color':
            color(obj, (1, 0, 0, 1))
            for i in obj.data.polygons[0].loop_indices:
                obj.data.color_attributes.active_color.data[i].color = (0, 0, 1, 1)
        split = s.split_parts(obj, how, min_faces=1)
        assert len(split) >= 2, how
        assert sum(len(p.data.polygons) for p in split) == 6
        for part in split:
            s._remove_object(part)
        s._remove_object(obj)
    tiny = cube('小片')
    small = s.split_parts(tiny, 'normal_angle', min_faces=100)
    assert sum(len(p.data.polygons) for p in small) == 6
    for part in small + [tiny]:
        s._remove_object(part)

'''),
    ('remesh', r'''
# 薄い板では voxel を呼ばず減面。閉じた球では voxel/quadriflow を実行。
thin = cube('艤装板', scale=(1, 1, 0.01))
assert s.keep_shape_for_thin_parts(thin)
s.remesh(thin, 'voxel', 8)
assert thin['shiage_remesh_used'] == 'decimate'
for kind in ('voxel', 'quadriflow', 'decimate'):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
    obj = bpy.context.object
    assert not s.keep_shape_for_thin_parts(obj)
    before = len(obj.data.polygons)
    s.remesh(obj, kind, 80)
    assert len(obj.data.polygons) > 0
    if kind == 'decimate':
        assert len(obj.data.polygons) < before
    s._remove_object(obj)

'''),
    ('uv', r'''
# 同じ data の複製を残して UV 操作。単一ユーザー化の安全経路も通す。
peer = bpy.data.objects.new('UV共有', target.data)
scene.collection.objects.link(peer)
source_mesh = peer.data
s.remesh(target, 'decimate', 8)
s.smart_uv(target)
s.uv_pack(target)
stats = s._uv_report(target.data)
assert stats['uv_islands'] > 0 and stats['uv_overlap_complete']
assert stats['uv_overlap_pairs'] == 0 and stats['uv_outside_loops'] == 0, stats
s.uv_layout_png(target, 'uv.png', 64)
assert_file('uv.png', b'\x89PNG\r\n\x1a\n')
pixels = list(bpy.data.images.load(str(root / 'uv.png')).pixels)
assert min(pixels) < 0.01 and max(pixels) > 0.99
assert target.data != source_mesh and peer.data == source_mesh
assert peer.data.uv_layers.active and peer.data.color_attributes.active_color
s._remove_object(peer)
'''),
    ('bake_vertex', r'''
engine = scene.render.engine
hidden = a.hide_get(), a.hide_render
old_materials = list(a.data.materials)
baked = s.bake_from_original(a, target, 64, path='bake.png')
assert_file('bake.png', b'\x89PNG\r\n\x1a\n')
assert scene.render.engine == engine and (a.hide_get(), a.hide_render) == hidden
assert list(a.data.materials) == old_materials
data = list(baked.pixels)
reds = sum(data[i] > 0.5 and data[i + 1] < 0.1 for i in range(0, len(data), 4))
# FLOAT_COLOR の値と float 焼き先はともに線形。byte/sRGB の .152 を .02 と比較しない。
assert baked.is_float, ('焼き先が線形floatでない', baked.colorspace_settings.name)
assert baked.packed_file, 'PNGと別に線形画像を保存していない'
assert reds > 64, ('頂点色が焼けていない', reds)
from shindan_bake import uv_pixels
covered = uv_pixels(target.data, 64, 64)
inside_reds = sum(data[i * 4] > .5 and data[i * 4 + 1] < .1 for i in covered)
# margin の赤だけで合格しない。均一な赤の原本なので UV 内部の90%以上が赤のはず。
assert covered and inside_reds >= len(covered) * .9, ('UV内部の未転写', inside_reds, len(covered))
s.apply_texture(target, str(root / 'bake.png'))

'''),
    ('bake_texture', r'''
engine = scene.render.engine
# テクスチャ材質からの selected-to-active と、失敗時の材質/設定復元。
dst = bpy.data.objects.new('転写先', target.data)
s._unique_mesh(dst)
dst.matrix_world = target.matrix_world.copy()
scene.collection.objects.link(dst)
second = s.bake_from_original(target, dst, 64)
assert second.packed_file
assert any(second.pixels[i] > 0.5 for i in range(0, len(second.pixels), 4))
# PNG保存時の sRGB 化と、再読込後の自動線形化が往復で色を変えないこと。
roundtrip = list(second.pixels)
from shindan_bake import uv_pixels   # 段ごとに別の Blender なので、この段でも読む
covered_second = uv_pixels(dst.data, 64, 64)
matching = sum(all(abs(roundtrip[i * 4 + c] - (.9, .02, .01)[c]) < .04
                   for c in range(3)) for i in covered_second)
assert matching >= len(covered_second) * .9, ('PNG色空間の往復', matching, len(covered_second))
slots = list(dst.data.materials)
old_bake = s._bake
def fail(*args, **kwargs):
    raise RuntimeError('復元試験')
s._bake = fail
try:
    try:
        s.bake_from_original(target, dst, 64)
        assert False
    except RuntimeError:
        assert list(dst.data.materials) == slots
        assert scene.render.engine == engine
finally:
    s._bake = old_bake
s._remove_object(dst)

'''),
    ('projection', r'''
# 六方向の異なる色を同じ箱へ投影し、各面の向きと混色を UV の中心で確認。
projection = cube('投影確認', x=6)
s.smart_uv(projection)
directions = {'front': (1, 0, 0, 1), 'back': (0, 1, 0, 1),
              'left': (0, 0, 1, 1), 'right': (1, 1, 0, 1),
              'top': (1, 0, 1, 1), 'bottom': (0, 1, 1, 1)}
views = {}
for name, rgba in directions.items():
    image = bpy.data.images.new(name, width=16, height=16, alpha=True)
    image.pixels.foreach_set(list(rgba) * (16 * 16))
    image.filepath_raw, image.file_format = str(output(name + '.png')), 'PNG'
    image.save()
    views[name] = image.filepath_raw
result = s.project_views(projection, views, 64, path='views.png')
assert_file('views.png', b'\x89PNG\r\n\x1a\n')
uv = projection.data.uv_layers.active
for face in projection.data.polygons:
    name = max(directions, key=lambda n: face.normal.dot(s.mathutils.Vector(s._DIRECTIONS[n])))
    center = sum((uv.data[i].uv for i in face.loop_indices), s.mathutils.Vector((0, 0))) / len(face.loop_indices)
    x, y = min(63, int(center.x * 64)), min(63, int(center.y * 64))
    actual = result.pixels[(y * 64 + x) * 4:(y * 64 + x) * 4 + 3]
    assert all(abs(actual[i] - directions[name][i]) < 0.12 for i in range(3)), (name, tuple(actual))
diagonal = s.project_views(projection, {'front_left': views['front']}, 64)
assert diagonal.packed_file

# 同じ UV を二重に重ね、レポートが面積のある重なりを検出する。
overlap = cube('重なり')
for face in overlap.data.polygons:
    for index, loop in enumerate(face.loop_indices):
        overlap.data.uv_layers.active.data[loop].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[index]
stats = s._uv_report(overlap.data)
assert stats['uv_overlap_pairs'] == 15 and stats['uv_overlap_complete'], stats
assert not s._uv_report(overlap.data, max_pairs=1)['uv_overlap_complete']
s._remove_object(overlap)

'''),
    ('rig', r'''
# 人型 A ポーズを、重複のない閉じた塊から作る。骨熱ウェイトを実際に確認。
body_parts = []
for loc, scale in [((0, 0, 1.2), (.22, .12, .38)), ((0, 0, 1.8), (.17, .14, .2)),
                   ((.36, 0, 1.45), (.2, .08, .08)), ((-.36, 0, 1.45), (.2, .08, .08)),
                   ((.12, 0, .45), (.075, .09, .4)), ((-.12, 0, .45), (.075, .09, .4))]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, location=loc)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    body_parts.append(obj)
bpy.ops.object.select_all(action='DESELECT')
for obj in body_parts:
    obj.select_set(True)
bpy.context.view_layer.objects.active = body_parts[0]
bpy.ops.object.join()
body = body_parts[0]
body_parts.clear()
del obj
body.name = '試験人型'
attachment = cube('固定艤装', x=.4, scale=(.05, .05, .05))
attachment.location.z = 1.2
bpy.context.view_layer.update()
world = attachment.matrix_world.copy()
rig = s.auto_rig(body, parts=[attachment])
assert len(rig.data.bones) == 17 and body.parent == rig
assert attachment.parent_type == 'BONE' and attachment.parent == rig
bpy.context.view_layer.update()
assert all(abs(world[i][j] - attachment.matrix_world[i][j]) < 1e-5
           for i in range(4) for j in range(4))
assert all(any(g.weight > 0 for g in v.groups) for v in body.data.vertices)
scene['shiage_test_body'] = body.name
scene['shiage_test_rig'] = rig.name
'''),
    ('animate', r'''
for kind in ('idle', 'walk', 'wave', 'turn'):
    action = s.animate(rig, kind, .5)
    assert action and rig.animation_data.action == action
    assert action.frame_range[1] >= 2
s.animate(rig, 'idle', .5)

'''),
    ('report', r'''
summary = s.report()
assert summary['parts'] >= 2 and summary['faces'] > 0
assert any(item['textures'] for item in summary['objects'])
'''),
    ('turntable', r'''
camera_before, frame_before, engine = scene.camera, scene.frame_current, scene.render.engine
s.turntable_video('turn.mp4', .5, 'CYCLES')
assert scene.camera == camera_before and scene.frame_current == frame_before
assert scene.render.engine == engine
assert not any(o.name.startswith('仕上げ回転カメラ') for o in scene.objects)
assert (root / 'turn.mp4').read_bytes()[4:8] == b'ftyp'
'''),
    ('render', r'''
# 現カメラでのアニメ描画も独立に確認。
camera_data = bpy.data.cameras.new('アニメカメラ')
camera = bpy.data.objects.new('アニメカメラ', camera_data)
scene.collection.objects.link(camera)
camera.location = (0, -5, 2)
camera.rotation_euler = (s.mathutils.Vector((0, 0, 1)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = camera
scene.render.engine = 'CYCLES'
old_path, old_format = scene.render.filepath, scene.render.image_settings.file_format
s.render_animation_mp4('animation.mp4')
assert scene.render.filepath == old_path and scene.render.image_settings.file_format == old_format
assert (root / 'animation.mp4').read_bytes()[4:8] == b'ftyp'
'''),
)


def _blender_script(name, code):
    module_dir = Path(s.__file__).resolve().parent
    common = BLENDER_COMMON.replace(
        "str(Path(__file__).resolve().parent)", repr(str(module_dir)))
    # RNA を持つ局所変数は段が終わると捨て、次プロセスへは名前だけ渡す。
    bindings = """
a = bpy.data.objects.get(scene.get('shiage_test_source', ''))
parts = [bpy.data.objects[n] for n in json.loads(scene.get('shiage_test_parts', '[]'))]
target = bpy.data.objects.get(scene.get('shiage_test_target', ''))
body = bpy.data.objects.get(scene.get('shiage_test_body', ''))
rig = bpy.data.objects.get(scene.get('shiage_test_rig', ''))
"""
    return (common + '\ndef check_stage():\n' +
            textwrap.indent(bindings + code, '    ') +
            "\ncheck_stage()\nbpy.context.view_layer.update()\n" +
            "bpy.ops.wm.save_as_mainfile(filepath=str(checkpoint), check_existing=False)\n" +
            "print('SHIAGE_STAGE_OK " + name + "', flush=True)\n")


def _run_blender_stages(blender, root, stages=BLENDER_STAGES):
    root = Path(root).resolve()
    if root.exists():
        raise ValueError('段の出力先は新しいフォルダにしてください: ' + str(root))
    root.mkdir(parents=True)
    previous = None
    records = []
    manifest = root / 'stages.json'
    for index, (name, code) in enumerate(stages, 1):
        label = f'{index:02d}_{name}'
        script, checkpoint, log = (root / (label + suffix)
                                   for suffix in ('.py', '.blend', '.log'))
        script.write_text(_blender_script(name, code))
        command = [str(blender), '--background', '--factory-startup',
                   '--disable-autoexec', '--threads', '1']
        if previous is not None:
            command.append(str(previous))
        command += ['--python-exit-code', '1', '--python', str(script),
                    '--', str(root), str(checkpoint)]
        record = dict(stage=name, input=str(previous) if previous else None,
                      checkpoint=str(checkpoint), log=str(log), command=command,
                      state='running')
        records.append(record)
        manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(f'仕上げ試験 {label}: {log}', flush=True)
        try:
            with log.open('w') as stream:
                result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                        stdout=stream, stderr=subprocess.STDOUT,
                                        text=True, timeout=900)
        except subprocess.TimeoutExpired:
            record['state'] = 'timeout'
            manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
            raise AssertionError(f'{label}: 時間切れ。ログ: {log}') from None
        except OSError as error:
            record.update(state='launch_failed', error=str(error))
            manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
            raise AssertionError(f'{label}: 起動失敗。ログ: {log}: {error}') from error
        record['returncode'] = result.returncode
        output = log.read_text(errors='replace')
        ok = (result.returncode == 0 and f'SHIAGE_STAGE_OK {name}' in output and
              checkpoint.is_file() and checkpoint.stat().st_size > 32)
        record['state'] = 'ok' if ok else 'failed'
        if result.returncode < 0:
            record['signal'] = signal.Signals(-result.returncode).name
        manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        if not ok:
            reason = record.get('signal', f'終了コード {result.returncode}')
            raise AssertionError(f'{label}: {reason}（完了印/保存も確認）。ログ: {log}\n' +
                                 '\n'.join(output.splitlines()[-70:]))
        previous = checkpoint
    return previous


class StageRunnerTests(unittest.TestCase):
    """subprocess は必ず偽物。Codex が実機を起動せず引継ぎ/失敗を検査する。"""

    @staticmethod
    def _success(command, **kwargs):
        script = Path(command[command.index('--python') + 1])
        stage = script.stem.split('_', 1)[1]
        Path(command[-1]).write_bytes(b'BLENDER' + bytes(64))
        kwargs['stdout'].write('SHIAGE_STAGE_OK ' + stage + '\n')
        return SimpleNamespace(returncode=0)

    def test_separate_processes_and_fresh_runs(self):
        stages = (('first', 'pass\n'), ('second', 'pass\n'))
        with tempfile.TemporaryDirectory() as directory, patch.object(
                subprocess, 'run', side_effect=self._success) as run:
            for repeat in (1, 2):
                root = (Path(directory) / str(repeat)).resolve()
                final = _run_blender_stages('/never-launch-blender', root, stages)
                first, second = run.call_args_list[-2:]
                # '--' 後にも保存先 .blend がある。CLI の読込引数だけを比較する。
                loaded = []
                for call in (first, second):
                    cli = call.args[0][:call.args[0].index('--python-exit-code')]
                    loaded.append([arg for arg in cli if arg.endswith('.blend')])
                self.assertEqual(loaded, [[], [str(root / '01_first.blend')]])
                self.assertEqual(final, root / '02_second.blend')
                self.assertEqual([r['state'] for r in json.loads(
                    (root / 'stages.json').read_text())], ['ok', 'ok'])
            self.assertEqual(run.call_count, 4)
            with self.assertRaisesRegex(ValueError, '新しいフォルダ'):
                _run_blender_stages('/never-launch-blender', root, stages)
            self.assertEqual(run.call_count, 4)

    def test_crash_on_exit_does_not_accept_checkpoint_or_retry(self):
        def crash(command, **kwargs):
            self._success(command, **kwargs)
            return SimpleNamespace(returncode=-signal.SIGSEGV)
        with tempfile.TemporaryDirectory() as directory, patch.object(
                subprocess, 'run', side_effect=crash) as run:
            root = Path(directory) / 'crash'
            with self.assertRaisesRegex(AssertionError, '01_first: SIGSEGV'):
                _run_blender_stages('/never-launch-blender', root,
                                    (('first', 'pass\n'), ('second', 'pass\n')))
            self.assertEqual(run.call_count, 1)
            record = json.loads((root / 'stages.json').read_text())[0]
            self.assertEqual((record['state'], record['signal']), ('failed', 'SIGSEGV'))
            self.assertTrue((root / '01_first.log').is_file())

    def test_missing_checkpoint_is_not_success(self):
        def incomplete(command, **kwargs):
            kwargs['stdout'].write('SHIAGE_STAGE_OK first\n')
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as directory, patch.object(
                subprocess, 'run', side_effect=incomplete) as run:
            with self.assertRaisesRegex(AssertionError, '01_first'):
                _run_blender_stages('/never-launch-blender', Path(directory) / 'missing',
                                    (('first', 'pass\n'),))
            self.assertEqual(run.call_count, 1)

    def test_timeout_preserves_stage_log(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
                subprocess, 'run', side_effect=subprocess.TimeoutExpired('fake', 900)) as run:
            root = Path(directory) / 'timeout'
            with self.assertRaisesRegex(AssertionError, '01_first: 時間切れ'):
                _run_blender_stages('/never-launch-blender', root, (('first', 'pass\n'),))
            self.assertEqual(run.call_count, 1)
            self.assertEqual(json.loads((root / 'stages.json').read_text())[0]['state'],
                             'timeout')
            self.assertTrue((root / '01_first.log').is_file())


@unittest.skipUnless(os.environ.get('SEISEI_BLENDER') == '1', 'Blender は明示時だけ（Claude が外で実行）')
class BlenderTests(unittest.TestCase):
    def test_real_pipeline(self):
        blender = Path(os.environ.get('BLENDER_BIN', '/Applications/Blender.app/Contents/MacOS/Blender'))
        self.assertTrue(blender.is_file(), str(blender))
        repeats = int(os.environ.get('SHIAGE_BLENDER_RUNS', '2'))
        self.assertGreaterEqual(repeats, 1)
        self.assertLessEqual(repeats, 10)
        # 成功/失敗とも段のログと .blend を残す。指定先内でも毎回 mkdtemp で分離。
        parent = os.environ.get('SHIAGE_TEST_DIR')
        if parent:
            Path(parent).mkdir(parents=True, exist_ok=True)
        session = Path(tempfile.mkdtemp(prefix='shiage-stages-', dir=parent)).resolve()
        print('仕上げ試験の保存先: ' + str(session), flush=True)
        for repeat in range(1, repeats + 1):
            root = session / f'run_{repeat:02d}'
            _run_blender_stages(blender, root)
            self.assertEqual(struct.unpack('>II', (root / 'uv.png').read_bytes()[16:24]), (64, 64))


if __name__ == '__main__':
    unittest.main()
