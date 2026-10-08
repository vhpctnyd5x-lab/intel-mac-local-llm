"""画像由来メッシュを仕上げる kit 用部品。Blender 外では引数だけ検査できる。

組込側は configure_output(既存kitの_output) を呼び、TOOLS の関数を登録する。
原本を残してから加工すること。座標は Z 上・正面 -Y・人物の左は +X。
"""

import math

try:
    import bpy
    import bmesh
    import mathutils
    import mathutils.bvhtree
except ModuleNotFoundError:
    bpy = bmesh = mathutils = None


TOOLS = (
    'import_model', 'clean', 'split_parts', 'save_parts', 'remesh',
    'keep_shape_for_thin_parts', 'smart_uv', 'uv_pack', 'uv_layout_png',
    'apply_texture', 'bake_from_original', 'project_views', 'auto_rig',
    'animate', 'turntable_video', 'render_animation_mp4', 'report',
)
_resolve_output = None
_DIRECTIONS = {
    'front': (0, -1, 0), 'back': (0, 1, 0),
    'left': (1, 0, 0), 'right': (-1, 0, 0),
    'top': (0, 0, 1), 'bottom': (0, 0, -1),
    'front_left': (1, -1, 0), 'front_right': (-1, -1, 0),
    'back_left': (1, 1, 0), 'back_right': (-1, 1, 0),
}


def configure_output(resolver):
    """組込側専用。相対名を検査し、親フォルダを用意する既存の _output を渡す。"""
    if not callable(resolver):
        raise ValueError('出力先を検査する関数が必要です')
    global _resolve_output
    _resolve_output = resolver


def _number(value, name, low=0, high=None, integer=False, strict=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + ' は数値です')
    if not math.isfinite(value) or (value <= low if strict else value < low):
        raise ValueError(name + ' が範囲外です')
    if high is not None and value > high:
        raise ValueError(name + ' が大きすぎます')
    if integer and (not isinstance(value, int)):
        raise ValueError(name + ' は整数です')
    return value


def _choice(value, values, name):
    if value not in values:
        raise ValueError(name + ' は ' + '/'.join(values) + ' です')


def _path(path, extensions=None):
    if not isinstance(path, str) or not path.strip() or '\x00' in path:
        raise ValueError('パスは空でない文字列です')
    if extensions and not any(path.lower().endswith(e) for e in extensions):
        raise ValueError('対応拡張子: ' + '/'.join(extensions))
    return path


def _output(path, extensions):
    _path(path, extensions)
    if _resolve_output is None:
        raise RuntimeError('組込側で configure_output(既存kitの_output) を設定してください')
    return str(_resolve_output(path))


def _require():
    if bpy is None:
        raise RuntimeError('この操作は Blender 内で使ってください')


def _mesh(obj):
    _require()
    if obj is None or obj.type != 'MESH' or not obj.data.polygons:
        raise ValueError('面のあるメッシュを指定してください')
    if obj.library or obj.data.library:
        raise ValueError('リンクしたメッシュは先にローカル化してください')
    if obj.mode != 'OBJECT':
        raise ValueError('対象メッシュはオブジェクトモードにしてください')
    bpy.context.view_layer.update()
    return obj


def _active(obj):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _state():
    active = bpy.context.view_layer.objects.active
    # 削除済み RNA を後から触らない。保存するのは名前と値だけ。
    return ([o.name for o in bpy.context.selected_objects], active.name if active else None,
            active.mode if active else 'OBJECT',
            [(o.name, o.hide_get(), o.hide_render) for o in bpy.context.view_layer.objects])


def _restore(state):
    selected, active, mode, hidden = state
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for name, hide, render in hidden:
        obj = bpy.context.view_layer.objects.get(name)
        if obj is not None:
            obj.hide_set(hide)
            obj.hide_render = render
    for name in selected:
        obj = bpy.context.view_layer.objects.get(name)
        if obj is not None:
            obj.select_set(True)
    active = bpy.context.view_layer.objects.get(active) if active else None
    if active is not None:
        bpy.context.view_layer.objects.active = active
        if mode != 'OBJECT' and not active.hide_get():
            bpy.ops.object.mode_set(mode=mode)
    else:
        bpy.context.view_layer.objects.active = None
    bpy.context.view_layer.update()


def _mesh_from_bmesh(bm, source):
    """未リンクの新規 ID に書く。mesh.copy() の共有 runtime を持ち込まない。"""
    # 共有そのものは正常な設計。今回の stack だけでは Blender 側の不具合と断定しない。
    # 根拠: https://github.com/blender/blender/blob/v4.5.10/source/blender/blenkernel/intern/mesh.cc
    # 類例（測定 tool、今回とは別経路）: https://projects.blender.org/blender/blender/pulls/149321
    data = bpy.data.meshes.new(source.name + '_仕上げ')
    for material in source.materials:
        data.materials.append(material)
    bm.to_mesh(data)
    # BMesh の custom data は UV/色/変形ウェイトを含む。使用レイヤーも戻す。
    if source.uv_layers.active:
        active = data.uv_layers.get(source.uv_layers.active.name)
        if active is not None:
            data.uv_layers.active = active
    for uv in source.uv_layers:
        target = data.uv_layers.get(uv.name)
        if target is not None:
            target.active_render = uv.active_render
    for setting in ('active_color_index', 'render_color_index'):
        index = getattr(source.color_attributes, setting)
        if 0 <= index < len(source.color_attributes):
            index = data.color_attributes.find(source.color_attributes[index].name)
            if index >= 0:
                setattr(data.color_attributes, setting, index)
    data.update()
    return data


def _unique_mesh(obj):
    if obj.data.users > 1:
        if obj.data.shape_keys:
            raise ValueError('共有シェイプキーは先に単一ユーザー化してください')
        bpy.context.view_layer.update()
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            data = _mesh_from_bmesh(bm, obj.data)
        finally:
            bm.free()
        obj.data = data
        bpy.context.view_layer.update()


def _remove_object(obj):
    """評価を完了してから unlink。未使用データの purge/即時削除はしない。"""
    bpy.context.view_layer.update()
    bpy.data.objects.remove(obj, do_unlink=True)
    del obj
    bpy.context.view_layer.update()


def _bounds(obj):
    points = [obj.matrix_world @ mathutils.Vector(p) for p in obj.bound_box]
    low = mathutils.Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = mathutils.Vector(tuple(max(p[i] for p in points) for i in range(3)))
    return low, high


def _parts_collection():
    collection = bpy.data.collections.get('部品')
    if collection is None:
        collection = bpy.data.collections.new('部品')
    if collection.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(collection)
    return collection


def import_model(path):
    """glb/obj/fbx を追加し、取り込んだメッシュのリストを返す。既存物は消さない。"""
    _path(path, ('.glb', '.obj', '.fbx'))
    _require()
    state = _state()
    before = set(bpy.data.objects)
    try:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        path = bpy.path.abspath(path)
        ext = path.rsplit('.', 1)[-1].lower()
        if ext == 'glb':
            result = bpy.ops.import_scene.gltf(filepath=path)
        elif ext == 'obj':
            result = bpy.ops.wm.obj_import(filepath=path)
        else:
            result = bpy.ops.import_scene.fbx(filepath=path)
        meshes = sorted((o for o in bpy.data.objects if o not in before and o.type == 'MESH'),
                        key=lambda o: o.name)
        if 'FINISHED' not in result or not meshes:
            raise RuntimeError('面を持つモデルを読み込めませんでした')
        return meshes
    finally:
        _restore(state)


def clean(obj, merge_by_distance=0.0001, fill_holes=True, max_hole_edges=12):
    """近接点・小穴・法線を直す。大穴は残し、非多様体辺などの数を返す。距離はローカル単位。"""
    _number(merge_by_distance, 'merge_by_distance', strict=False)
    _number(max_hole_edges, 'max_hole_edges', low=2, integer=True)
    if not isinstance(fill_holes, bool):
        raise ValueError('fill_holes は真偽値です')
    _mesh(obj)
    if obj.data.shape_keys:
        raise ValueError('清掃はシェイプキーを付ける前に行ってください')
    state = _state()
    bm = bmesh.new()
    try:
        _active(obj)
        bm.from_mesh(obj.data)
        before = len(bm.verts)
        if merge_by_distance:
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=merge_by_distance)
        boundary_before = sum(e.is_boundary for e in bm.edges)
        holes = []
        if fill_holes:
            holes = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary],
                                         sides=max_hole_edges)['faces']
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        stats = dict(merged_vertices=before - len(bm.verts), filled_faces=len(holes),
                     boundary_edges_before=boundary_before,
                     boundary_edges=sum(e.is_boundary for e in bm.edges),
                     non_manifold_edges=sum(not e.is_manifold for e in bm.edges),
                     wire_edges=sum(e.is_wire for e in bm.edges), faces=len(bm.faces))
        obj.data = _mesh_from_bmesh(bm, obj.data)
        return stats
    finally:
        bm.free()
        _restore(state)


def _face_colors(mesh):
    attribute = mesh.color_attributes.active_color
    if attribute is None:
        raise ValueError('頂点色がありません。loose/material/normal_angle を使ってください')
    colors = []
    for face in mesh.polygons:
        indices = face.vertices if attribute.domain == 'POINT' else face.loop_indices
        colors.append(tuple(sum(attribute.data[i].color[c] for i in indices) / len(indices)
                            for c in range(3)))
    return colors


def split_parts(obj, how='loose', min_faces=8, angle=50, color_threshold=0.15):
    """隣り合う面を連結/材質/法線角（度）/頂点色差で分割。「部品」に保管し原本は隠す。

    小片は境界で接する最大部品へ寄せ、孤立小片は「小片」にまとめる。面は捨てない。
    体と艤装の意味は判断しない。返した部品の name を本人または頭脳が付け直す。
    """
    _choice(how, ('loose', 'material', 'normal_angle', 'vertex_color'), 'how')
    _number(min_faces, 'min_faces', integer=True)
    _number(angle, 'angle', high=180)
    _number(color_threshold, 'color_threshold', high=math.sqrt(3), strict=False)
    _mesh(obj)
    if obj.data.shape_keys:
        raise ValueError('部品分割はシェイプキーを付ける前に行ってください')
    mesh = obj.data
    colors = _face_colors(mesh) if how == 'vertex_color' else None
    # loose は頂点だけで接する面も同じ島とする。他の方式は辺を共有する面のみ。
    links = {}
    neighbors = [set() for p in mesh.polygons]
    for face in mesh.polygons:
        keys = list(face.vertices) if how == 'loose' else list(face.edge_keys)
        for key in keys:
            links.setdefault(key, []).append(face.index)
    for faces in links.values():
        for a in faces:
            neighbors[a].update(b for b in faces if b != a)

    def same(a, b):
        fa, fb = mesh.polygons[a], mesh.polygons[b]
        if how == 'material':
            return fa.material_index == fb.material_index
        if how == 'normal_angle':
            return fa.normal.angle(fb.normal, math.pi) <= math.radians(angle)
        if how == 'vertex_color':
            return sum((colors[a][i] - colors[b][i]) ** 2 for i in range(3)) <= color_threshold ** 2
        return True

    groups, owner = [], {}
    for start in range(len(mesh.polygons)):
        if start in owner:
            continue
        stack, group = [start], set()
        owner[start] = len(groups)
        while stack:
            face = stack.pop()
            group.add(face)
            for other in neighbors[face]:
                if other not in owner and same(face, other):
                    owner[other] = len(groups)
                    stack.append(other)
        groups.append(group)
    large = {i for i, g in enumerate(groups) if len(g) >= min_faces}
    pending = set(range(len(groups))) - large
    # 小さい島の鎖も大きい島へ辿って吸収する。
    while pending:
        moved = False
        for index in sorted(pending):
            adjacent = {owner[n] for f in groups[index] for n in neighbors[f]} & large
            if adjacent:
                target = max(adjacent, key=lambda i: (len(groups[i]), -i))
                groups[target].update(groups[index])
                for face in groups[index]:
                    owner[face] = target
                groups[index].clear()
                pending.remove(index)
                moved = True
        if not moved:
            break
    small = set().union(*(groups[i] for i in pending)) if pending else set()
    chosen = [(g, False) for i, g in enumerate(groups) if i in large]
    if small:
        chosen.append((small, True))
    chosen.sort(key=lambda item: (-len(item[0]), min(item[0])))
    collection, result = _parts_collection(), []
    for index, (faces, tiny) in enumerate(chosen, 1):
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in faces], context='FACES')
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
            data = _mesh_from_bmesh(bm, mesh)
        finally:
            bm.free()
        part = bpy.data.objects.new(obj.name + ('_小片_' if tiny else '_部品_') + f'{index:03d}', data)
        part.matrix_world = obj.matrix_world.copy()
        collection.objects.link(part)
        part['shiage_part'] = True
        part['shiage_source'] = obj.name
        result.append(part)
        bpy.context.view_layer.update()
    obj['shiage_original'] = True
    obj.hide_render = True
    obj.hide_set(True)
    bpy.context.view_layer.update()
    return result


def save_parts(dir):
    """「部品」のメッシュを個別 glb に保存。dir は出力先内の相対フォルダ名。"""
    _path(dir)
    # resolver でフォルダと名前を最終検査する。名前をパスとして解釈させない。
    _require()
    collection = bpy.data.collections.get('部品')
    if not collection:
        raise ValueError('「部品」コレクションがありません')
    parts = sorted((o for o in collection.objects if o.type == 'MESH'), key=lambda o: o.name)
    paths = []
    for index, obj in enumerate(parts, 1):
        name = ''.join(c if c.isalnum() or c in '_-' else '_' for c in obj.name)[:80]
        paths.append(_output(dir.rstrip('/') + '/' + f'{index:03d}_' + name + '.glb', ('.glb',)))
    state = _state()
    try:
        for obj, path in zip(parts, paths):
            _active(obj)
            if 'FINISHED' not in bpy.ops.export_scene.gltf(filepath=path, export_format='GLB',
                                                         use_selection=True):
                raise RuntimeError('部品を書き出せませんでした: ' + obj.name)
        return paths
    finally:
        _restore(state)


def keep_shape_for_thin_parts(obj, ratio=0.06, boundary_ratio=0.15):
    """薄い/開いた部品なら True。外形の厚み比と境界辺率で保守的に判定する。"""
    _number(ratio, 'ratio', high=1)
    _number(boundary_ratio, 'boundary_ratio', high=1)
    _mesh(obj)
    # ワールド軸では斜めの板を見逃すので、物体ローカルの寸法を用いる。
    points = [mathutils.Vector(p) for p in obj.bound_box]
    spans = [max(p[i] for p in points) - min(p[i] for p in points) for i in range(3)]
    spans = [abs(obj.scale[i]) * spans[i] for i in range(3)]
    # メッシュ自身が斜めでも板を見つける。大きい面の法線方向の厚さを測る。
    world = [obj.matrix_world @ v.co for v in obj.data.vertices]
    normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
    thickness = min(spans)
    normals = set()
    for face in sorted(obj.data.polygons, key=lambda f: f.area, reverse=True)[:32]:
        normal = (normal_matrix @ face.normal).normalized()
        key = tuple(round(c, 3) for c in normal)
        if key not in normals:
            normals.add(key)
            projections = [p.dot(normal) for p in world]
            thickness = min(thickness, max(projections) - min(projections))
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        boundary = sum(e.is_boundary for e in bm.edges) / max(1, len(bm.edges))
    finally:
        bm.free()
    return thickness / max(max(spans), 1e-12) < ratio or boundary >= boundary_ratio


def remesh(obj, kind='voxel', target_faces=8000, protect_thin=True):
    """形を組み直す。薄い物の voxel は decimate に切替。面数は目安、UV/色は原本から焼く。"""
    _choice(kind, ('voxel', 'quadriflow', 'decimate'), 'kind')
    _number(target_faces, 'target_faces', low=3, integer=True)
    if not isinstance(protect_thin, bool):
        raise ValueError('protect_thin は真偽値です')
    _mesh(obj)
    if obj.data.shape_keys or any(m.type == 'ARMATURE' for m in obj.modifiers):
        raise ValueError('リメッシュはリグ・シェイプキーを付ける前に行ってください')
    state = _state()
    requested = kind
    try:
        _active(obj)
        _unique_mesh(obj)
        if kind == 'voxel' and protect_thin and keep_shape_for_thin_parts(obj):
            kind = 'decimate'
        # スケール確定で voxel の距離と法線を揃える。
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        if kind == 'decimate':
            obj.data.calc_loop_triangles()
            triangles = len(obj.data.loop_triangles)
            if triangles > target_faces:
                modifier = obj.modifiers.new('仕上げ_減面', 'DECIMATE')
                modifier.ratio = min(1.0, target_faces / triangles)
                modifier.use_collapse_triangulate = True
                bpy.ops.object.modifier_apply(modifier=modifier.name)
        elif kind == 'voxel':
            area = sum(f.area for f in obj.data.polygons)
            obj.data.remesh_voxel_size = max(math.sqrt(area / target_faces), 1e-6)
            if 'FINISHED' not in bpy.ops.object.voxel_remesh():
                raise RuntimeError('voxel リメッシュが完了しませんでした')
        else:
            if 'FINISHED' not in bpy.ops.object.quadriflow_remesh(
                    mode='FACES', target_faces=target_faces, use_mesh_symmetry=False,
                    use_preserve_sharp=True, use_preserve_boundary=True):
                raise RuntimeError('Quadriflow が失敗しました。非多様体と法線を確認してください')
        obj['shiage_remesh_requested'] = requested
        obj['shiage_remesh_used'] = kind
        obj['shiage_target_faces'] = target_faces
        return obj
    finally:
        _restore(state)


def _uv_edit(obj, operation, **settings):
    _mesh(obj)
    state = _state()
    tool = bpy.context.scene.tool_settings
    margin = getattr(tool, 'uvcalc_margin', None)   # 4.5 には無い（10/8 実機で落ちた）
    try:
        _active(obj)
        _unique_mesh(obj)
        if obj.data.uv_layers.active is None:
            obj.data.uv_layers.new(name='UVMap')
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.select_all(action='SELECT')
        if 'FINISHED' not in operation(**settings):
            raise RuntimeError('UV 操作が完了しませんでした')
    finally:
        _restore(state)
        if margin is not None:
            tool.uvcalc_margin = margin
    return obj


def smart_uv(obj, angle=66, margin=0.02):
    """スマート UV 展開。angle は度、margin は0〜1の島間隔。"""
    _number(angle, 'angle', high=89)
    _number(margin, 'margin', high=0.5, strict=False)
    _require()
    return _uv_edit(obj, bpy.ops.uv.smart_project, angle_limit=math.radians(angle),
                    island_margin=margin, correct_aspect=True, scale_to_bounds=True)


def uv_pack(obj, margin=0.02):
    """既存 UV の島を0〜1に詰め直す。ピンは外す。"""
    _number(margin, 'margin', high=0.5, strict=False)
    _mesh(obj)
    if obj.data.uv_layers.active is None:
        raise ValueError('UV がありません。smart_uv を先に使ってください')
    _unique_mesh(obj)
    values = obj.data.uv_layers.active.data
    low = mathutils.Vector((min(v.uv.x for v in values), min(v.uv.y for v in values)))
    span = max(max(v.uv.x for v in values) - low.x, max(v.uv.y for v in values) - low.y)
    if span <= 1e-12:
        raise ValueError('UV に面積がありません。smart_uv を先に使ってください')
    for item in obj.data.uv_layers.active.data:
        item.pin_uv = False
        item.uv = (item.uv - low) / span
    # UI の active UDIM に影響されず、正規化済み外接範囲へ詰める。
    return _uv_edit(obj, bpy.ops.uv.pack_islands, rotate=True, margin=margin,
                    udim_source='ORIGINAL_AABB', scale=True, pin=False)


def uv_layout_png(obj, path, size=1024):
    """UV の輪郭を白地・黒線の PNG に CPU で保存する。外の AI に渡す下絵。"""
    _number(size, 'size', low=15, high=4096, integer=True)
    path = _output(path, ('.png',))
    _mesh(obj)
    uv = obj.data.uv_layers.active
    if uv is None:
        raise ValueError('UV がありません')
    pixels = [1.0] * (size * size * 4)
    for face in obj.data.polygons:
        loops = list(face.loop_indices)
        for a, b in zip(loops, loops[1:] + loops[:1]):
            x0, y0 = uv.data[a].uv * (size - 1)
            x1, y1 = uv.data[b].uv * (size - 1)
            # 巨大/範囲外 UV の描画量を増やさない。展開図は0〜1タイル専用。
            if not all(0 <= c <= size - 1 for c in (x0, y0, x1, y1)):
                raise ValueError('UV が0〜1の外です。uv_pack を先に使ってください')
            steps = max(1, math.ceil(max(abs(x1 - x0), abs(y1 - y0))))
            for step in range(steps + 1):
                t = step / steps
                x, y = round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)
                offset = (y * size + x) * 4
                pixels[offset:offset + 3] = (0.0, 0.0, 0.0)
    image = bpy.data.images.new('UV下絵', width=size, height=size, alpha=True)
    try:
        image.pixels.foreach_set(pixels)
        image.filepath_raw, image.file_format = path, 'PNG'
        image.save()
    finally:
        bpy.data.images.remove(image)
    return path


def _texture_material(obj, image, name='仕上げテクスチャ'):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    shader = tree.nodes.get('Principled BSDF')
    texture = tree.nodes.new('ShaderNodeTexImage')
    texture.image = image
    coords = tree.nodes.new('ShaderNodeUVMap')
    coords.uv_map = obj.data.uv_layers.active.name
    tree.links.new(coords.outputs['UV'], texture.inputs['Vector'])
    tree.links.new(texture.outputs['Color'], shader.inputs['Base Color'])
    tree.nodes.active = texture
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for face in obj.data.polygons:
        face.material_index = 0
    return material


def apply_texture(obj, image_path):
    """UV に画像を貼る。旧材質を残したまま、新しい単一材質へ置換する。"""
    _path(image_path, ('.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.exr', '.bmp'))
    _mesh(obj)
    if obj.data.uv_layers.active is None:
        raise ValueError('UV がありません。smart_uv を先に使ってください')
    image = bpy.data.images.load(bpy.path.abspath(image_path), check_existing=True)
    _unique_mesh(obj)
    _texture_material(obj, image)
    return image


def _slots(obj):
    return list(obj.data.materials), [p.material_index for p in obj.data.polygons]


def _restore_slots(obj, slots):
    materials, indices = slots
    obj.data.materials.clear()
    for material in materials:
        obj.data.materials.append(material)
    for face, index in zip(obj.data.polygons, indices):
        face.material_index = index


def _emission_material(original, color_attribute=None):
    # 色だけを焼く。光・陰・金属の反射を混入させない。
    mat = original.copy() if original else bpy.data.materials.new('原色一時')
    was_nodes = bool(original and original.use_nodes)
    mat.use_nodes = True
    tree = mat.node_tree
    output = next((n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL'
                   and n.is_active_output and n.target in ('ALL', 'CYCLES')), None)
    if output is None:
        output = tree.nodes.new('ShaderNodeOutputMaterial')
    # 未接続の Principled を拾わず、出力につながる枝から基本色を探す。
    pending = [link.from_node for link in output.inputs['Surface'].links]
    reachable = []
    while pending:
        node = pending.pop()
        if node in reachable:
            continue
        reachable.append(node)
        pending.extend(link.from_node for socket in node.inputs for link in socket.links)
    shader = next((n for n in reachable if n.type == 'BSDF_PRINCIPLED'), None)
    if not was_nodes:
        shader = None
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1
    if was_nodes and shader and shader.inputs['Base Color'].is_linked:
        tree.links.new(shader.inputs['Base Color'].links[0].from_socket, emission.inputs['Color'])
    elif color_attribute:
        attribute = tree.nodes.new('ShaderNodeVertexColor')
        attribute.layer_name = color_attribute
        tree.links.new(attribute.outputs['Color'], emission.inputs['Color'])
    elif was_nodes and shader:
        emission.inputs['Color'].default_value = shader.inputs['Base Color'].default_value
    elif original:
        emission.inputs['Color'].default_value = original.diffuse_color
    else:
        emission.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1)
    # EEVEE 専用出力や displacement を引き継がない。
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.target = 'ALL'
    output.is_active_output = True
    tree.links.new(emission.outputs[0], output.inputs['Surface'])
    return mat


def _geometry_snapshot(obj, depsgraph, bounds_only=False):
    """評価済み RNA はこの読み取り中だけ。更新を跨ぐのは独立した値だけ。"""
    evaluated = obj.evaluated_get(depsgraph)
    matrix = evaluated.matrix_world.copy()
    corners = [mathutils.Vector(tuple(p)) for p in evaluated.bound_box]
    if bounds_only:
        return matrix, corners
    mesh = evaluated.data
    return (matrix, corners,
            [mathutils.Vector(tuple(v.co)) for v in mesh.vertices],
            [tuple(p.vertices) for p in mesh.polygons],
            [mathutils.Vector(tuple(p.center)) for p in mesh.polygons])


def _snapshot_bounds(matrix, corners):
    points = [matrix @ p for p in corners]
    return (mathutils.Vector(tuple(min(p[i] for p in points) for i in range(3))),
            mathutils.Vector(tuple(max(p[i] for p in points) for i in range(3))))


def _bake_geometry(src, dst, cage=None):
    """独立 BVH で形状差を測る。評価 mesh の共有 BVH/to_mesh は使わない。"""
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    source_matrix, source_corners, vertices, faces, _ = _geometry_snapshot(src, depsgraph)
    target_matrix, corners, points, _, centers = _geometry_snapshot(dst, depsgraph)
    del depsgraph
    low, high = _snapshot_bounds(target_matrix, corners)
    inverse = target_matrix.inverted()
    local_span = max(mathutils.Vector(tuple(max(p[i] for p in corners) - min(p[i] for p in corners)
                                           for i in range(3))).length, 1e-5)
    if cage is None:
        # v4.5.10 mesh_copy_data は法線/三角形/BVH を共有する。
        # rna_Object_closest_point_on_mesh も評価 mesh の bvh_corner_tris を使う。
        # Python の座標/面番号から作り、MeshRuntime と無関係の BVH を所有する。
        tree = mathutils.bvhtree.BVHTree.FromPolygons(vertices, faces)
        points.extend(centers)
        source_inverse = source_matrix.inverted()
        gap = 0.0
        step = max(1, math.ceil(len(points) / 1024))
        for point in points[::step]:
            nearest, _, _, _ = tree.find_nearest(source_inverse @ (target_matrix @ point))
            if nearest is not None:
                gap = max(gap, (inverse @ (source_matrix @ nearest) - point).length)
        cage = max(local_span * 0.025, gap * 1.5 + local_span * 0.005, 1e-5)
        del tree
    src_low, src_high = _snapshot_bounds(source_matrix, source_corners)
    span = mathutils.Vector(tuple(max(high[i], src_high[i]) - min(low[i], src_low[i])
                                 for i in range(3))).length
    scale = max(target_matrix.to_3x3().col[i].length for i in range(3))
    # cage*2 は低解像度側のずれ・非一様スケールに対して短すぎる。
    # 全体寸法で有限に制限する。原本内の別部品の裏写りは cage で調整する。
    return cage, max(span + cage * scale * 2, 1e-5)


def _bake(dst, image, sources=(), cage=0, ray_distance=0):
    scene = bpy.context.scene
    state = _state()
    engine, device, samples = scene.render.engine, scene.cycles.device, scene.cycles.samples
    bake = scene.render.bake
    bake_state = (bake.use_selected_to_active, bake.use_cage, bake.cage_extrusion,
                  bake.max_ray_distance, bake.margin, bake.use_clear, bake.target,
                  bake.cage_object, bake.save_mode, bake.margin_type)
    nodes_added = []
    try:
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 1
        _active(dst)
        dst.hide_render = False
        for material in dst.data.materials:
            nodes = material.node_tree.nodes
            old_active = nodes.active
            node = nodes.new('ShaderNodeTexImage')
            nodes_added.append((nodes, node, old_active))
            node.image = image
            node.select = True
            nodes.active = node
        for src in sources:
            src.hide_set(False)
            src.hide_render = False
            src.select_set(True)
        bpy.context.view_layer.objects.active = dst
        if 'FINISHED' not in bpy.ops.object.bake(
                type='EMIT', use_selected_to_active=bool(sources), use_clear=True,
                use_cage=bool(sources) and cage > 0, cage_extrusion=cage,
                max_ray_distance=ray_distance,
                cage_object='', uv_layer=dst.data.uv_layers.active.name,
                margin=max(2, min(16, image.size[0] // 128)), target='IMAGE_TEXTURES',
                save_mode='INTERNAL', margin_type='EXTEND'):
            raise RuntimeError('テクスチャを焼けませんでした')
    finally:
        scene.cycles.device, scene.cycles.samples = device, samples
        scene.render.engine = engine
        (bake.use_selected_to_active, bake.use_cage, bake.cage_extrusion,
         bake.max_ray_distance, bake.margin, bake.use_clear, bake.target,
         bake.cage_object, bake.save_mode, bake.margin_type) = bake_state
        for nodes, node, old_active in nodes_added:
            nodes.remove(node)
            nodes.active = old_active
        _restore(state)


def bake_from_original(src_obj, dst_obj, size=1024, cage=None, path=None):
    """原本の頂点色/Principled の基本色を Cycles CPU で UV へ焼く。画像を返す。

    線形 float 画像へ selected-to-active・実形状差入り自動 cage で焼く。
    別の位置へ動かさない。cage（焼き先ローカル距離、0 は cage 無し）で裏写りを調整。
    path は任意の出力相対 PNG 名（sRGB コピー）。返す線形画像は常に blend 内へ pack。
    """
    _number(size, 'size', low=15, high=8192, integer=True)
    if cage is not None:
        _number(cage, 'cage', strict=False)
    if path is not None:
        path = _output(path, ('.png',))
    _mesh(src_obj)
    _mesh(dst_obj)
    if src_obj == dst_obj or src_obj.data == dst_obj.data:
        raise ValueError('原本と仕上げ先は別のメッシュデータにしてください')
    if dst_obj.data.uv_layers.active is None:
        raise ValueError('仕上げ先に UV がありません')
    _unique_mesh(src_obj)
    _unique_mesh(dst_obj)
    old_render_uv = next((u for u in dst_obj.data.uv_layers if u.active_render), None)
    src_slots, dst_slots = _slots(src_obj), _slots(dst_obj)
    state = _state()
    temporary = []
    # byte/sRGB の pixels は線形色ではない（緑 0.02 → 約0.152）。
    # float の既定色空間は scene-linear。Non-Color として色管理を逃がさない。
    image = bpy.data.images.new(dst_obj.name + '_原色', width=size, height=size,
                                alpha=True, float_buffer=True)
    success = False
    try:
        # 隠した原本も形状差を測る間は評価対象にする。
        # _bake 内で隠しを戻すだけでは、先に呼ぶ幾何診断に間に合わない。
        src_obj.hide_set(False)
        dst_obj.hide_set(False)
        src_obj.hide_render = dst_obj.hide_render = False
        dst_obj.data.uv_layers.active.active_render = True
        attr = src_obj.data.color_attributes.active_color
        for original in src_slots[0] or [None]:
            temporary.append(_emission_material(original, attr.name if attr else None))
        src_obj.data.materials.clear()
        for material in temporary:
            src_obj.data.materials.append(material)
        # clear/append の途中で材質番号が変わる場合に備え復元。
        for face, index in zip(src_obj.data.polygons, src_slots[1]):
            face.material_index = min(index, len(temporary) - 1)
        target = _texture_material(dst_obj, image, '焼き先一時')
        temporary.append(target)
        cage, ray_distance = _bake_geometry(src_obj, dst_obj, cage)
        _bake(dst_obj, image, sources=(src_obj,), cage=cage, ray_distance=ray_distance)
        if path:
            # save() は generated 画像を byte/sRGB 出力として更新する場合がある。
            # 返す線形画像を変えず、コピーだけを PNG にする（AgX を通さない）。
            saved = image.copy()
            try:
                # Image.copy はキャッシュ（焼いた画素）をコピーしない。
                buffer = memoryview(bytearray(len(image.pixels) * 4)).cast('f')
                image.pixels.foreach_get(buffer)
                saved.pixels.foreach_set(buffer)
                del buffer
                saved.filepath_raw, saved.file_format = path, 'PNG'
                saved.save()
            finally:
                bpy.data.images.remove(saved)
        # float の pack は EXR。PNG と線形画像の色空間を混ぜず blend 再読込にも耐える。
        image.pack()
        _texture_material(dst_obj, image)
        dst_obj['shiage_cage'] = cage
        dst_obj['shiage_ray_distance'] = ray_distance
        dst_obj['shiage_bake_space'] = image.colorspace_settings.name
        success = True
        return image
    finally:
        _restore_slots(src_obj, src_slots)
        if old_render_uv:
            old_render_uv.active_render = True
        if not success:
            _restore_slots(dst_obj, dst_slots)
            bpy.data.images.remove(image)
        for material in temporary:
            bpy.data.materials.remove(material)
        _restore(state)


def _math_node(tree, operation, a, b):
    node = tree.nodes.new('ShaderNodeMath')
    node.operation = operation
    for index, value in enumerate((a, b)):
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value
        else:
            tree.links.new(value, node.inputs[index])
    return node.outputs[0]


def _vector_node(tree, operation, a, b=None):
    node = tree.nodes.new('ShaderNodeVectorMath')
    node.operation = operation
    for index, value in enumerate((a, b)):
        if value is None:
            continue
        if isinstance(value, (tuple, list, mathutils.Vector)):
            node.inputs[index].default_value = value
        else:
            tree.links.new(value, node.inputs[index])
    return node.outputs['Value' if operation == 'DOT_PRODUCT' else 'Vector']


def project_views(obj, views, size=1024, path=None, sharpness=4):
    """正面 -Y/背面 +Y/左 +X/右 -X/上 +Z/下 -Z/斜めの正投影を法線で混ぜ、1枚に焼く。

    views は方向名→画像パス。各絵は同じ物体・背景透明・余白と姿勢を揃える。
    カメラは物の外接箱を画像縦横比に収める。遮蔽・服の意味・絵のずれは解決しない。
    """
    _number(size, 'size', low=15, high=8192, integer=True)
    _number(sharpness, 'sharpness', high=32)
    if not isinstance(views, dict) or not views:
        raise ValueError('views は方向名と画像パスの空でない辞書です')
    for name, value in views.items():
        _choice(name, tuple(_DIRECTIONS), '方向')
        _path(value, ('.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.exr', '.bmp'))
    if path is not None:
        path = _output(path, ('.png',))
    _mesh(obj)
    if obj.data.uv_layers.active is None:
        raise ValueError('UV がありません')
    # 先に全画像を読む。途中の読み込み失敗では材質を変えない。
    obj.data.uv_layers.active.active_render = True
    images = {name: bpy.data.images.load(bpy.path.abspath(p), check_existing=True)
              for name, p in views.items()}
    _unique_mesh(obj)
    slots = _slots(obj)
    material = bpy.data.materials.new('多方向投影一時')
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    geometry = tree.nodes.new('ShaderNodeNewGeometry')
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    emission = tree.nodes.new('ShaderNodeEmission')
    tree.links.new(emission.outputs[0], output.inputs['Surface'])
    low, high = _bounds(obj)
    center = (low + high) / 2
    corners = [obj.matrix_world @ mathutils.Vector(p) for p in obj.bound_box]
    normal = _vector_node(tree, 'NORMALIZE', geometry.outputs['Normal'])
    cameras, total, color = [], 0, None
    image = None
    success = False
    try:
        for name, source in images.items():
            direction = mathutils.Vector(_DIRECTIONS[name]).normalized()
            # 真上/真下にも安定した up を用意する。
            up = mathutils.Vector((0, 1, 0) if abs(direction.z) > 0.99 else (0, 0, 1))
            right = up.cross(direction).normalized()
            up = direction.cross(right).normalized()
            width = max(abs((p - center).dot(right)) * 2 for p in corners)
            height = max(abs((p - center).dot(up)) * 2 for p in corners)
            aspect = source.size[0] / max(1, source.size[1])
            height = max(height, width / aspect, 1e-5) * 1.02
            width = height * aspect
            camera_data = bpy.data.cameras.new('投影_' + name)
            camera = bpy.data.objects.new('投影_' + name, camera_data)
            bpy.context.scene.collection.objects.link(camera)
            cameras.append(camera)
            camera.location = center + direction * max((high - low).length * 2, 1)
            basis = mathutils.Matrix((right, up, direction)).transposed().to_4x4()
            basis.translation = camera.location
            camera.matrix_world = basis
            camera.data.type = 'ORTHO'
            camera.data.ortho_scale = max(width, height)
            # カメラのローカル XY を正投影する。奥行き Z は画像座標に使わない。
            coords = tree.nodes.new('ShaderNodeTexCoord')
            coords.object = camera
            axes = tree.nodes.new('ShaderNodeSeparateXYZ')
            tree.links.new(coords.outputs['Object'], axes.inputs[0])
            u = _math_node(tree, 'ADD', _math_node(tree, 'DIVIDE',
                           axes.outputs['X'], width), 0.5)
            v = _math_node(tree, 'ADD', _math_node(tree, 'DIVIDE',
                           axes.outputs['Y'], height), 0.5)
            combine = tree.nodes.new('ShaderNodeCombineXYZ')
            tree.links.new(u, combine.inputs['X'])
            tree.links.new(v, combine.inputs['Y'])
            texture = tree.nodes.new('ShaderNodeTexImage')
            texture.image, texture.extension = source, 'CLIP'
            tree.links.new(combine.outputs[0], texture.inputs['Vector'])
            facing = _math_node(tree, 'MAXIMUM',
                                _vector_node(tree, 'DOT_PRODUCT', normal, direction), 0)
            weight = _math_node(tree, 'MULTIPLY', _math_node(tree, 'POWER', facing, sharpness),
                                texture.outputs['Alpha'])
            scale = tree.nodes.new('ShaderNodeVectorMath')
            scale.operation = 'SCALE'
            tree.links.new(texture.outputs['Color'], scale.inputs[0])
            tree.links.new(weight, scale.inputs['Scale'])
            color = scale.outputs[0] if color is None else _vector_node(tree, 'ADD', color, scale.outputs[0])
            total = _math_node(tree, 'ADD', total, weight)
        inverse = _math_node(tree, 'DIVIDE', 1, _math_node(tree, 'MAXIMUM', total, 1e-8))
        normalize = tree.nodes.new('ShaderNodeVectorMath')
        normalize.operation = 'SCALE'
        tree.links.new(color, normalize.inputs[0])
        tree.links.new(inverse, normalize.inputs['Scale'])
        tree.links.new(normalize.outputs[0], emission.inputs['Color'])
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for face in obj.data.polygons:
            face.material_index = 0
        image = bpy.data.images.new(obj.name + '_多方向', width=size, height=size, alpha=False)
        _bake(obj, image)
        if path:
            image.filepath_raw, image.file_format = path, 'PNG'
            image.save()
        else:
            image.pack()
        _texture_material(obj, image)
        success = True
        return image
    finally:
        if not success:
            _restore_slots(obj, slots)
            if image:
                bpy.data.images.remove(image)
        bpy.data.materials.remove(material)
        for camera in cameras:
            _remove_object(camera)
        cameras.clear()
        bpy.context.view_layer.update()


def _bone_distance(point, a, b):
    delta = b - a
    t = max(0, min(1, (point - a).dot(delta) / max(delta.length_squared, 1e-12)))
    return (point - (a + delta * t)).length_squared


def auto_rig(obj, kind='humanoid', parts=None):
    """Z 上の正面 -Y の人型に自作17骨を当て自動ウェイト。parts の艤装は近い骨に固定。

    A/T ポーズの下書き用。髪/服は体へ合わせ、艤装だけ parts に渡す。
    省略時は「部品」の他のメッシュを艤装扱いする。骨位置・ウェイトの手直しは必要。
    """
    _choice(kind, ('humanoid',), 'kind')
    _mesh(obj)
    if obj.data.shape_keys or any(m.type == 'ARMATURE' for m in obj.modifiers):
        raise ValueError('既存リグ/シェイプキーのない体メッシュを指定してください')
    if parts is None:
        collection = bpy.data.collections.get('部品')
        parts = [o for o in collection.objects if o != obj and o.type == 'MESH'
                 and not o.get('shiage_original')] if collection else []
    else:
        parts = list(parts)
    for part in parts:
        _mesh(part)
        if part == obj:
            raise ValueError('parts に体自身は入れないでください')
        if part.data.shape_keys or any(m.type == 'ARMATURE' for m in part.modifiers):
            raise ValueError('艤装は既存リグのないメッシュを指定してください')
    low, high = _bounds(obj)
    width, height = high.x - low.x, high.z - low.z
    if height <= 1e-6 or width <= 1e-6:
        raise ValueError('高さ・幅のある人型が必要です')
    x, y, z = (low.x + high.x) / 2, (low.y + high.y) / 2, low.z
    # 腕を含む外接幅に合わせる。腕下ろしの姿勢では編集モードで合わせ直す。
    def p(dx, dz, dy=0):
        return (x + dx * width, y + dy * height, z + dz * height)
    specs = [
        ('root', p(0, 0.48), p(0, 0.54), None),
        ('spine', p(0, 0.54), p(0, 0.67), 'root'),
        ('chest', p(0, 0.67), p(0, 0.79), 'spine'),
        ('neck', p(0, 0.79), p(0, 0.85), 'chest'),
        ('head', p(0, 0.85), p(0, 0.98), 'neck'),
    ]
    for side, sign in (('L', 1), ('R', -1)):
        specs.extend([
            ('upper_arm.' + side, p(sign * 0.13, 0.77), p(sign * 0.31, 0.72), 'chest'),
            ('forearm.' + side, p(sign * 0.31, 0.72), p(sign * 0.44, 0.67), 'upper_arm.' + side),
            ('hand.' + side, p(sign * 0.44, 0.67), p(sign * 0.49, 0.65), 'forearm.' + side),
            ('thigh.' + side, p(sign * 0.07, 0.49), p(sign * 0.07, 0.27), 'root'),
            ('shin.' + side, p(sign * 0.07, 0.27), p(sign * 0.07, 0.055), 'thigh.' + side),
            ('foot.' + side, p(sign * 0.07, 0.055), p(sign * 0.07, 0.025, -0.075), 'shin.' + side),
        ])
    state = _state()
    _unique_mesh(obj)
    old_parent = (obj.parent, obj.parent_type, obj.parent_bone, obj.matrix_parent_inverse.copy(),
                  obj.matrix_world.copy())
    old_modifiers = set(obj.modifiers)
    old_groups = [(g.name, [(v.index, item.weight) for v in obj.data.vertices
                           for item in v.groups if item.group == g.index]) for g in obj.vertex_groups]
    part_parents = [(p, p.parent, p.parent_type, p.parent_bone, p.matrix_parent_inverse.copy(),
                     p.matrix_world.copy(), p.get('shiage_attachment')) for p in parts]
    data = bpy.data.armatures.new(obj.name + '_骨')
    rig = bpy.data.objects.new(obj.name + '_人型', data)
    bpy.context.scene.collection.objects.link(rig)
    rig.location = (x, y, z)
    rig.show_in_front = True
    success = False
    try:
        _active(rig)
        bpy.ops.object.mode_set(mode='EDIT')
        for name, head, tail, parent in specs:
            bone = data.edit_bones.new(name)
            bone.head = mathutils.Vector(head) - rig.location
            bone.tail = mathutils.Vector(tail) - rig.location
            if parent:
                bone.parent = data.edit_bones[parent]
                bone.use_connect = (bone.head - bone.parent.tail).length < 1e-6
        bpy.ops.object.mode_set(mode='OBJECT')
        obj.hide_set(False)
        obj.select_set(True)
        if 'FINISHED' not in bpy.ops.object.parent_set(type='ARMATURE_AUTO'):
            raise RuntimeError('自動ウェイトに失敗しました')
        obj.matrix_world = old_parent[-1]
        bone_groups = {g.index for g in obj.vertex_groups if g.name in data.bones}
        missing = sum(not any(g.group in bone_groups and g.weight > 1e-8 for g in v.groups)
                      for v in obj.data.vertices)
        if missing:
            raise RuntimeError(f'{missing} 頂点にウェイトがありません。骨位置・重複面を確認してください')
        for part in parts:
            a, b = _bounds(part)
            center = (a + b) / 2
            nearest = min(data.bones, key=lambda bone: _bone_distance(
                center, rig.matrix_world @ bone.head_local, rig.matrix_world @ bone.tail_local))
            world = part.matrix_world.copy()
            part.parent, part.parent_type, part.parent_bone = rig, 'BONE', nearest.name
            bpy.context.view_layer.update()
            part.matrix_world = world
            part['shiage_attachment'] = nearest.name
        rig['shiage_rig'] = 'humanoid'
        success = True
        return rig
    finally:
        _restore(state)
        if not success:
            for modifier in list(obj.modifiers):
                if modifier not in old_modifiers:
                    obj.modifiers.remove(modifier)
            obj.vertex_groups.clear()
            for name, weights in old_groups:
                group = obj.vertex_groups.new(name=name)
                for index, weight in weights:
                    group.add([index], weight, 'REPLACE')
            obj.parent, obj.parent_type, obj.parent_bone, obj.matrix_parent_inverse, obj.matrix_world = old_parent
            for part, parent, parent_type, bone, inverse, world, tag in part_parents:
                part.parent, part.parent_type, part.parent_bone = parent, parent_type, bone
                part.matrix_parent_inverse, part.matrix_world = inverse, world
                if tag is not None:
                    part['shiage_attachment'] = tag
                elif 'shiage_attachment' in part:
                    del part['shiage_attachment']
            _remove_object(rig)
        bpy.context.view_layer.update()


def animate(rig, kind='idle', seconds=3):
    """自作人型に待機/その場歩き/手振り/一回転の新しい Action を作る。歩きは IK なし。"""
    _choice(kind, ('idle', 'walk', 'wave', 'turn'), 'kind')
    _number(seconds, 'seconds', high=600)
    _require()
    if rig is None or rig.type != 'ARMATURE' or rig.get('shiage_rig') != 'humanoid':
        raise ValueError('auto_rig が返した人型リグを指定してください')
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    end = max(2, round(seconds * fps))
    rig.animation_data_create()
    action = bpy.data.actions.new(rig.name + '_' + kind)
    rig.animation_data.action = action
    original = rig.rotation_euler.copy()
    frame = scene.frame_current
    poses = [(bone, bone.rotation_mode, bone.rotation_euler.copy(), bone.location.copy())
             for bone in rig.pose.bones]
    for bone, mode, rotation, location in poses:
        bone.rotation_mode = 'XYZ'
    try:
        frames = sorted(set([1, end] + list(range(1, end + 1, max(1, round(fps / 12))))))
        for current in frames:
            phase = (current - 1) / (end - 1)
            cycle = 2 * math.pi * phase * max(1, round(seconds))
            for bone, mode, rotation, location in poses:
                bone.rotation_euler = (0, 0, 0)
                bone.location = (0, 0, 0)
            if kind == 'idle':
                rig.pose.bones['chest'].rotation_euler.x = 0.025 * math.sin(cycle)
                rig.pose.bones['head'].rotation_euler.z = 0.04 * math.sin(cycle)
            elif kind == 'walk':
                for side, sign in (('L', 1), ('R', -1)):
                    stride = math.sin(cycle) * sign
                    rig.pose.bones['thigh.' + side].rotation_euler.x = 0.4 * stride
                    rig.pose.bones['shin.' + side].rotation_euler.x = 0.5 * max(0, -stride)
                    rig.pose.bones['upper_arm.' + side].rotation_euler.x = -0.25 * stride
            elif kind == 'wave':
                rig.pose.bones['upper_arm.L'].rotation_euler.z = -1.2
                rig.pose.bones['forearm.L'].rotation_euler.z = -0.6 + 0.3 * math.sin(cycle * 2)
            else:
                rig.rotation_euler = original
                rig.rotation_euler.z += 2 * math.pi * phase
                rig.keyframe_insert(data_path='rotation_euler', frame=current)
            if kind != 'turn':
                for bone, mode, rotation, location in poses:
                    bone.keyframe_insert(data_path='rotation_euler', frame=current)
        scene.frame_start, scene.frame_end = 1, end
        return action
    finally:
        for bone, mode, rotation, location in poses:
            bone.rotation_euler, bone.location = rotation, location
            bone.rotation_mode = mode if kind == 'turn' else 'XYZ'
        rig.rotation_euler = original
        scene.frame_set(frame)
        bpy.context.view_layer.update()


def render_animation_mp4(path):
    """現在のカメラとフレーム範囲を Blender 内蔵 FFmpeg/MPEG4/H.264 で保存する。"""
    path = _output(path, ('.mp4',))
    _require()
    scene = bpy.context.scene
    if scene.camera is None:
        raise ValueError('カメラがありません')
    render = scene.render
    formats = {v.identifier for v in render.image_settings.bl_rna.properties['file_format'].enum_items}
    if 'FFMPEG' not in formats or not hasattr(render, 'ffmpeg'):
        raise RuntimeError('この Blender は内蔵 FFmpeg 動画出力に対応していません（4.5 LTS を推奨）')
    previous = (render.filepath, render.image_settings.file_format, render.use_file_extension,
                render.ffmpeg.format, render.ffmpeg.codec, render.ffmpeg.constant_rate_factor,
                render.ffmpeg.audio_codec, render.ffmpeg.use_autosplit, render.use_multiview,
                scene.frame_current)
    try:
        render.filepath, render.use_file_extension = path, True
        render.image_settings.file_format = 'FFMPEG'
        render.ffmpeg.format, render.ffmpeg.codec = 'MPEG4', 'H264'
        render.ffmpeg.constant_rate_factor, render.ffmpeg.audio_codec = 'MEDIUM', 'NONE'
        render.ffmpeg.use_autosplit, render.use_multiview = False, False
        if 'FINISHED' not in bpy.ops.render.render(animation=True):
            raise RuntimeError('動画を描画できませんでした')
        return path
    finally:
        (render.filepath, render.image_settings.file_format, render.use_file_extension,
         render.ffmpeg.format, render.ffmpeg.codec, render.ffmpeg.constant_rate_factor,
         render.ffmpeg.audio_codec, render.ffmpeg.use_autosplit, render.use_multiview,
         frame) = previous
        scene.frame_set(frame)
        bpy.context.view_layer.update()


def turntable_video(path, seconds=3, engine='BLENDER_EEVEE_NEXT'):
    """見えているメッシュの周囲をカメラで一周する mp4。仮カメラ・照明・設定は元へ戻す。"""
    _number(seconds, 'seconds', high=600)
    _choice(engine, ('BLENDER_EEVEE_NEXT', 'CYCLES'), 'engine')
    _path(path, ('.mp4',))
    _require()
    scene = bpy.context.scene
    objects = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render
               and not o.get('shiage_original')]
    if not objects:
        raise ValueError('描画するメッシュがありません')
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        matrix, corners = _geometry_snapshot(obj, depsgraph, bounds_only=True)
        points.extend(matrix @ p for p in corners)
    del depsgraph
    low = mathutils.Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = mathutils.Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center, diameter = (low + high) / 2, max((high - low).length, 0.01)
    previous = (scene.camera, scene.render.engine, scene.frame_start, scene.frame_end,
                scene.frame_current, scene.cycles.device)
    created = []
    try:
        data = bpy.data.cameras.new('仕上げ回転カメラ')
        camera = bpy.data.objects.new('仕上げ回転カメラ', data)
        scene.collection.objects.link(camera)
        created.append(camera)
        scene.camera = camera
        scene.render.engine = engine
        if engine == 'CYCLES':
            scene.cycles.device = 'CPU'
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = 1
        frame_points = camera.data.view_frame(scene=scene)
        frame_width = max(p.x for p in frame_points) - min(p.x for p in frame_points)
        frame_height = max(p.y for p in frame_points) - min(p.y for p in frame_points)
        camera.data.ortho_scale = diameter * 1.15 / max(1e-6, min(frame_width, frame_height))
        camera.data.clip_start = min(0.1, diameter * 0.01)
        camera.data.clip_end = max(100, diameter * 10)
        camera.rotation_mode = 'QUATERNION'
        end = max(2, round(seconds * scene.render.fps / scene.render.fps_base))
        for frame in range(1, end + 1):
            angle = (frame - 1) / (end - 1) * 2 * math.pi
            camera.location = center + mathutils.Vector((math.sin(angle) * 2,
                                                         -math.cos(angle) * 2, 0.6)) * diameter
            camera.rotation_quaternion = (center - camera.location).to_track_quat('-Z', 'Y')
            camera.keyframe_insert(data_path='location', frame=frame)
            camera.keyframe_insert(data_path='rotation_quaternion', frame=frame)
        for index, offset in enumerate(((1, -1, 2), (-1, 1, 1))):
            light_data = bpy.data.lights.new('仕上げ照明' + str(index), 'AREA')
            light = bpy.data.objects.new(light_data.name, light_data)
            scene.collection.objects.link(light)
            created.append(light)
            light.location = center + mathutils.Vector(offset) * diameter
            light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
            light_data.energy, light_data.size = 200 * diameter ** 2, diameter
        scene.frame_start, scene.frame_end = 1, end
        return render_animation_mp4(path)
    finally:
        scene.camera, scene.render.engine, scene.frame_start, scene.frame_end, frame, device = previous
        scene.cycles.device = device
        scene.frame_set(frame)
        for obj in created:
            _remove_object(obj)
        created.clear()
        bpy.context.view_layer.update()


def _signed_area(points):
    return sum(a[0] * b[1] - a[1] * b[0]
               for a, b in zip(points, points[1:] + points[:1])) / 2


def _intersection_area(a, b):
    # 凸三角形同士のクリップ。共有辺/点は面積0なので重なりとはしない。
    subject = list(a)
    clip = list(b) if _signed_area(list(b)) >= 0 else list(reversed(b))
    for p, q in zip(clip, clip[1:] + clip[:1]):
        old, subject = subject, []
        if not old:
            break
        def side(v):
            return (q[0] - p[0]) * (v[1] - p[1]) - (q[1] - p[1]) * (v[0] - p[0])
        for u, v in zip(old, old[1:] + old[:1]):
            su, sv = side(u), side(v)
            if (su >= 0) != (sv >= 0):
                t = su / (su - sv)
                subject.append((u[0] + (v[0] - u[0]) * t, u[1] + (v[1] - u[1]) * t))
            if sv >= 0:
                subject.append(v)
    return abs(_signed_area(subject)) if len(subject) >= 3 else 0.0


def _uv_report(mesh, max_pairs=200000):
    uv = mesh.uv_layers.active
    if uv is None:
        return dict(uv_islands=0, uv_overlap_pairs=None, uv_overlap_complete=False,
                    uv_outside_loops=0, uv_degenerate_triangles=0)
    edges, neighbors = {}, [set() for f in mesh.polygons]
    for face in mesh.polygons:
        loops = list(face.loop_indices)
        for a, b in zip(loops, loops[1:] + loops[:1]):
            key = tuple(sorted((mesh.loops[i].vertex_index,
                                round(uv.data[i].uv.x, 6), round(uv.data[i].uv.y, 6)) for i in (a, b)))
            others = edges.setdefault(key, [])
            for other in others:
                neighbors[face.index].add(other)
                neighbors[other].add(face.index)
            others.append(face.index)
    unseen, islands = set(range(len(mesh.polygons))), 0
    while unseen:
        stack = [unseen.pop()]
        islands += 1
        while stack:
            adjacent = neighbors[stack.pop()] & unseen
            unseen.difference_update(adjacent)
            stack.extend(adjacent)
    mesh.calc_loop_triangles()
    triangles, bins, tested, overlaps = [], {}, set(), set()
    degenerate, complete = 0, True
    for tri in mesh.loop_triangles:
        points = [tuple(uv.data[i].uv) for i in tri.loops]
        if abs(_signed_area(points)) < 1e-12:
            degenerate += 1
            continue
        xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
        ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
        # グリッドの端へ範囲外もまとめる（見逃しを生まない保守的候補）。
        x0, x1 = max(0, min(31, math.floor(xmin * 32))), max(0, min(31, math.floor(xmax * 32)))
        y0, y1 = max(0, min(31, math.floor(ymin * 32))), max(0, min(31, math.floor(ymax * 32)))
        cells = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
        candidates = set(j for cell in cells for j in bins.get(cell, ()))
        index = len(triangles)
        for other in candidates:
            other_points, face_index, box = triangles[other]
            pair = (other, index)
            if face_index == tri.polygon_index or pair in tested:
                continue
            if len(tested) >= max_pairs:
                complete = False
                break
            tested.add(pair)
            if xmax <= box[0] or xmin >= box[1] or ymax <= box[2] or ymin >= box[3]:
                continue
            if _intersection_area(points, other_points) > 1e-10:
                overlaps.add(tuple(sorted((tri.polygon_index, face_index))))
        triangles.append((points, tri.polygon_index, (xmin, xmax, ymin, ymax)))
        for cell in cells:
            bins.setdefault(cell, []).append(index)
        if not complete:
            break
    return dict(uv_islands=islands, uv_overlap_pairs=len(overlaps), uv_overlap_complete=complete,
                uv_overlap_tested_pairs=len(tested), uv_degenerate_triangles=degenerate,
                uv_outside_loops=sum(not all(-1e-6 <= c <= 1 + 1e-6 for c in item.uv)
                                     for item in uv.data))


def report():
    """原本を除くメッシュの面数・部品数・UV島/重なり・画像寸法を返す。重なりは上限付き検査。"""
    _require()
    results = []
    collection = bpy.data.collections.get('部品')
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        if obj.type != 'MESH' or obj.get('shiage_original'):
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        images = {}
        for material in mesh.materials:
            if material and material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        images[node.image.name] = tuple(node.image.size)
        stats = dict(name=obj.name, vertices=len(mesh.vertices), faces=len(mesh.polygons),
                     triangles=len(mesh.loop_triangles), textures=images)
        stats.update(_uv_report(mesh))
        results.append(stats)
    return dict(parts=sum(o.type == 'MESH' and not o.get('shiage_original')
                          for o in collection.objects) if collection else 0,
                faces=sum(s['faces'] for s in results), objects=results)
