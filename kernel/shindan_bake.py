"""Blender 内専用の焼き診断。Codex は実行しない。

Claude が砂箱外で実行する例（引数無しは失敗した試験と同じ二つの箱）:
  Blender --background --factory-startup --python kernel/shindan_bake.py
既存 .blend の指定物を診断:
  Blender model.blend --background --python kernel/shindan_bake.py -- --src 原本 --dst 部品
--size 64 --cage 0.1 も指定可。ファイルへの保存・元のメッシュの加工はしない。
"""

import argparse
import math
from pathlib import Path
import sys


def uv_pixels(mesh, width, height):
    """UV 三角形内部の画素中心の集合。margin を含めず、重なりは重複計上しない。"""
    mesh.calc_loop_triangles()
    layer = mesh.uv_layers.active
    if layer is None:
        return set()
    covered = set()
    for triangle in mesh.loop_triangles:
        a, b, c = [tuple(layer.data[i].uv) for i in triangle.loops]
        cross = lambda p, q, r: ((q[0] - p[0]) * (r[1] - p[1])
                                  - (q[1] - p[1]) * (r[0] - p[0]))
        area = cross(a, b, c)
        if abs(area) < 1e-12:
            continue
        sign = 1 if area > 0 else -1
        xmin = max(0, math.ceil(min(a[0], b[0], c[0]) * width - .5))
        xmax = min(width - 1, math.floor(max(a[0], b[0], c[0]) * width - .5))
        ymin = max(0, math.ceil(min(a[1], b[1], c[1]) * height - .5))
        ymax = min(height - 1, math.floor(max(a[1], b[1], c[1]) * height - .5))
        for y in range(ymin, ymax + 1):
            for x in range(xmin, xmax + 1):
                p = ((x + .5) / width, (y + .5) / height)
                if all(sign * cross(v, w, p) >= -1e-10
                       for v, w in ((a, b), (b, c), (c, a))):
                    covered.add(y * width + x)
    return covered


def node_report(obj):
    print('ノード', obj.name, flush=True)
    for material in obj.data.materials:
        if not material or not material.use_nodes:
            print('  材質', getattr(material, 'name', None), 'ノード無し')
            continue
        tree = material.node_tree
        print('  材質', material.name, 'active=', getattr(tree.nodes.active, 'name', None))
        for node in tree.nodes:
            if node.type == 'TEX_IMAGE':
                image = node.image
                print('  画像', node.name, getattr(image, 'name', None),
                      '色空間=', image.colorspace_settings.name if image else None)
            elif node.type == 'VERTEX_COLOR':
                print('  頂点色', node.name, 'layer=', node.layer_name)
            elif node.type == 'OUTPUT_MATERIAL':
                print('  出力', node.name, 'active=', node.is_active_output, 'target=', node.target)
            elif node.type in ('BSDF_PRINCIPLED', 'EMISSION'):
                socket = node.inputs.get('Base Color') or node.inputs.get('Color')
                print('  色', node.name, tuple(socket.default_value))
        for link in tree.links:
            print('   ', link.from_node.name + '.' + link.from_socket.name, '->',
                  link.to_node.name + '.' + link.to_socket.name)


def image_report(obj, image, label):
    width, height = image.size
    covered = uv_pixels(obj.data, width, height)
    pixels = list(image.pixels)
    red = lambda i: pixels[4 * i] > .5 and pixels[4 * i + 1] < .1
    reds = sum(red(i) for i in range(width * height))
    inside = sum(red(i) for i in covered)
    black = sum(max(pixels[4 * i:4 * i + 3]) < .01 for i in covered)
    linear = lambda value: value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
    if not image.is_float and image.colorspace_settings.name == 'sRGB':
        linear_reds = sum(linear(pixels[4 * i]) > .5 and linear(pixels[4 * i + 1]) < .1
                          for i in covered)
    else:
        linear_reds = inside
    mean = tuple(sum(pixels[4 * i + c] for i in covered) / max(1, len(covered))
                 for c in range(3))
    print(label, 'UV内部画素=', len(covered), 'UV被覆率=', len(covered) / (width * height),
          '赤画素=', reds, 'UV内部の赤=', inside, 'UV内部の黒=', black,
          '線形換算UV内部の赤=', linear_reds,
          'UV内部平均RGB=', mean, 'float=', image.is_float,
          '色空間=', image.colorspace_settings.name, flush=True)


def main():
    import bpy
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sanjigen_shiage as s
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src')
    parser.add_argument('--dst')
    parser.add_argument('--size', type=int, default=64)
    parser.add_argument('--cage', type=float)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if bool(args.src) != bool(args.dst):
        parser.error('--src と --dst は両方指定してください')
    if not 16 <= args.size <= 512:
        parser.error('診断の size は16〜512（本処理は8192まで）')
    scene = bpy.context.scene
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2
    print('Blender=', bpy.app.version_string, 'CPU', flush=True)
    if args.src:
        # 診断では指定物を複製し、元の材質・UV・非表示を触らない。
        copies = []
        for name in (args.src, args.dst):
            original = bpy.data.objects[name]
            obj = original.copy()
            obj.data = original.data.copy()
            scene.collection.objects.link(obj)
            copies.append(obj)
        src, dst = copies
    else:
        bpy.ops.mesh.primitive_cube_add(location=(-2, 0, 0))
        src = bpy.context.object
        attribute = src.data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
        src.data.color_attributes.active_color = attribute
        for item in attribute.data:
            item.color = (.9, .02, .01, 1)
        dst = src.copy()
        dst.data = src.data.copy()
        scene.collection.objects.link(dst)
        bpy.ops.mesh.primitive_cube_add(location=(2, 0, 0))
        other = bpy.context.object
        attribute = other.data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
        other.data.color_attributes.active_color = attribute
        for item in attribute.data:
            item.color = (.9, .02, .01, 1)
        bpy.ops.object.select_all(action='DESELECT')
        src.select_set(True)
        other.select_set(True)
        bpy.context.view_layer.objects.active = src
        bpy.ops.object.join()
        s.remesh(dst, 'decimate', 8)
        s.smart_uv(dst)
        s.uv_pack(dst)
    print('原本/焼き先=', src.name, dst.name, '頂点/面=', len(dst.data.vertices), len(dst.data.polygons))
    print('UV検査=', s._uv_report(dst.data))
    attr = src.data.color_attributes.active_color
    print('頂点色=', (attr.name, attr.domain, attr.data_type) if attr else None)
    if attr:
        print('頂点色先頭（線形）=', tuple(attr.data[0].color))
    node_report(src)
    original_bake = s._bake

    def observed(target, image, sources=(), cage=0, ray_distance=0):
        print('焼き設定 EMIT selected-to-active=', bool(sources), 'use_cage=', cage > 0,
              'cage（local）=', cage, 'max_ray_distance（world）=', ray_distance,
              'margin=', max(2, min(16, image.size[0] // 128)), 'margin_type=EXTEND', flush=True)
        for source in sources:
            node_report(source)
        node_report(target)
        # 同じ幾何・ノードで旧 byte/sRGB も焼き、色空間だけを切り分ける。
        byte = bpy.data.images.new('診断byte', width=args.size, height=args.size, alpha=True)
        try:
            original_bake(target, byte, sources, cage, ray_distance)
            image_report(target, byte, 'byte/sRGB比較')
        finally:
            bpy.data.images.remove(byte)
        # 旧 cage/ray のまま float だけに替え、幾何と色空間を独立に比較する。
        if args.cage is None:
            low, high = s._bounds(target)
            legacy_cage = max((high - low).length * .025, 1e-5)
            legacy = bpy.data.images.new('診断旧光線float', width=args.size, height=args.size,
                                         alpha=True, float_buffer=True)
            try:
                print('旧光線比較 cage=', legacy_cage, 'max_ray_distance=', legacy_cage * 2)
                original_bake(target, legacy, sources, legacy_cage, legacy_cage * 2)
                image_report(target, legacy, '旧光線float/linear')
            finally:
                bpy.data.images.remove(legacy)
        original_bake(target, image, sources, cage, ray_distance)
        image_report(target, image, '修正版float/linear')

    s._bake = observed
    try:
        image = s.bake_from_original(src, dst, args.size, cage=args.cage)
        image_report(dst, image, 'pack後')
    finally:
        s._bake = original_bake


if __name__ == '__main__':
    main()
