"""頭脳の bpy 台本を検査し、書込先を限定した Blender で実行する。"""

import ast
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import types


BLENDER = Path('/Applications/Blender.app/Contents/MacOS/Blender')
_IMPORTS = frozenset(('bpy', 'bmesh', 'mathutils', 'math', 'random', 'kit'))
_FORBIDDEN = frozenset(('__import__', 'open', 'exec', 'eval', 'compile',
                        'os', 'sys', 'subprocess', 'socket', 'shutil', 'pathlib',
                        'builtins', 'getattr', 'setattr', 'delattr', 'globals',
                        'locals', 'vars', 'dir', 'input', 'breakpoint', 'help',
                        'as_module', 'run_script', 'python_file_run', 'execfile',
                        'load_scripts', 'driver_namespace', 'url_open'))


def validate(script):
    """許可した import と公開 API だけの台本か、実行前に AST で確かめる。"""
    if not isinstance(script, str) or len(script) > 100_000:
        raise ValueError('台本は10万字以内の文字列にしてください')
    tree = ast.parse(script, filename='<台本>')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name not in _IMPORTS for a in node.names):
                raise ValueError('許可されていない import')
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module not in _IMPORTS:
                raise ValueError('許可されていない import from')
            if any(a.name == '*' for a in node.names):
                raise ValueError('import * は使えません')
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.alias):
            names.extend((node.name, node.asname or node.name))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.append(node.name)
        if any(n in _FORBIDDEN or n.startswith('_') for n in names):
            raise ValueError('禁止された名前・属性を使用しています')
    return tree


def _profile(out_dir, temp_dir):
    # Metal/IOKit を妨げない、実機確認済みの形。hako は参照のみ。
    # macOS の描画用キャッシュと /dev は例外。機密の読み取り隔離ではない。
    quote = lambda p: json.dumps(str(p), ensure_ascii=False)
    return '\n'.join((
        '(version 1)', '(allow default)',
        '(deny network*)',
        '(deny file-write* (require-not (require-any ' + ' '.join(
            f'(subpath {quote(p)})' for p in
            (Path(out_dir).resolve(), Path(temp_dir).resolve(),
             Path('/private/var/folders'), Path('/dev'))) + ')))',
    ))


def _files(out_dir):
    return sorted(str(p) for p in out_dir.rglob('*')
                  if p.is_file() and p.resolve().is_relative_to(out_dir))


def run(script: str, out_dir: Path, timeout=300) -> dict:
    """台本を砂箱内で実行。ok/files/stats/preview/log/error を返す。"""
    result = dict(ok=False, files=[], stats=[], preview=None, log='', error=None)
    process = None
    try:
        validate(script)
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout は正の秒数です')
        out_dir = Path(out_dir).expanduser().resolve()
        if out_dir == Path(out_dir.anchor):
            raise ValueError('出力先にルートディレクトリは選べません')
        if not BLENDER.is_file():
            raise RuntimeError(f'Blender がありません: {BLENDER}')
        if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
            raise RuntimeError('macOS の sandbox-exec が必要です（砂箱なしでは実行しません）')
        out_dir.mkdir(parents=True, exist_ok=True)
        before = {p: (p.stat().st_mtime_ns, p.stat().st_size)
                  for p in out_dir.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory(prefix='sanjigen-') as raw:
            tmp = Path(raw).resolve()
            payload = tmp / 'payload.json'
            report = tmp / 'report.json'
            payload.write_text(json.dumps(dict(script=script, out_dir=str(out_dir),
                                               report=str(report))), encoding='utf-8')
            profile = tmp / 'sandbox.sb'
            profile.write_text(_profile(out_dir, tmp), encoding='utf-8')
            # 親の秘密・認証環境は渡さず、設定・キャッシュも専用一時領域に置く。
            env = dict(PATH='/usr/bin:/bin', HOME=str(tmp), TMPDIR=str(tmp),
                       XDG_CACHE_HOME=str(tmp / 'cache'), LANG='en_US.UTF-8',
                       OMP_NUM_THREADS='2', BLENDER_USER_CONFIG=str(tmp / 'config'),
                       BLENDER_USER_SCRIPTS=str(tmp / 'scripts'),
                       BLENDER_USER_DATAFILES=str(tmp / 'datafiles'))
            command = ['/usr/bin/sandbox-exec', '-f', str(profile), str(BLENDER),
                       '-b', '--factory-startup', '--disable-autoexec',
                       '-t', '2', '--python-exit-code', '1',
                       '--python', str(Path(__file__).resolve()), '--', '--worker', str(payload)]
            # ログはメモリを膨らませず一時ファイルへ。子もタイムアウトで回収。
            with (tmp / 'blender.log').open('w+b') as log:
                process = subprocess.Popen(command, cwd=tmp, env=env,
                                           stdin=subprocess.DEVNULL, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    code = -1
                    result['error'] = f'{timeout}秒で時間切れ'
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 64_000))
                result['log'] = '\n'.join(log.read().decode('utf-8', 'replace').splitlines()[-40:])
            if report.is_file():
                data = json.loads(report.read_text(encoding='utf-8'))
                result.update(stats=data.get('stats', []), preview=data.get('preview'))
                result['error'] = result['error'] or data.get('error')
                result['ok'] = code == 0 and data.get('ok', False)
            if not result['ok'] and not result['error']:
                result['error'] = f'Blender/砂箱が終了コード {code} で失敗しました'
        result['files'] = [p for p in _files(out_dir)
                           if Path(p) not in before or
                           (Path(p).stat().st_mtime_ns, Path(p).stat().st_size) != before[Path(p)]]
    except (ValueError, SyntaxError, OSError, RuntimeError) as exc:
        result['error'] = str(exc)
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    return result


# 以下は Blender の中でだけ使う道具箱。bpy/bmesh/Vector は _worker が設定。
def _active(obj):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def _primitive(operator, name, location, scale, _rotation=None, _color=None, **kwargs):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    operator(location=location, **kwargs)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    # 10/8: 頭脳は基本形に rotation（度）・color も渡しがち（雪だるまの試しで cone(rotation=…) が落ちた）
    if _rotation is not None:
        obj.rotation_euler = tuple(math.radians(v) for v in _rotation)
    bpy.ops.object.transform_apply(location=False, rotation=_rotation is not None, scale=True)
    if _color is not None:
        material(obj, color=tuple(_color) + ((1,) if len(_color) == 3 else ()))
    return obj


def cube(name='Cube', size=2, location=(0, 0, 0), scale=(1, 1, 1), rotation=None, color=None):
    """立方体を作る。size は一辺、scale は各軸の倍率。"""
    return _primitive(bpy.ops.mesh.primitive_cube_add, name, location, scale, rotation, color, size=size)


def uv_sphere(name='Sphere', radius=1, segments=16, rings=8, location=(0, 0, 0), scale=(1, 1, 1), rotation=None, color=None):
    """経緯線の球を作る。小さい分割数で軽くする。"""
    return _primitive(bpy.ops.mesh.primitive_uv_sphere_add, name, location, scale, rotation, color,
                      radius=radius, segments=segments, ring_count=rings)


def cylinder(name='Cylinder', radius=1, depth=2, vertices=16, location=(0, 0, 0), scale=(1, 1, 1), rotation=None, color=None):
    """円柱を作る。depth は高さ。"""
    return _primitive(bpy.ops.mesh.primitive_cylinder_add, name, location, scale, rotation, color,
                      radius=radius, depth=depth, vertices=vertices)


def cone(name='Cone', radius=1, depth=2, vertices=12, location=(0, 0, 0), scale=(1, 1, 1), rotation=None, color=None):
    """円錐を作る。vertices を減らすと低ポリになる。"""
    return _primitive(bpy.ops.mesh.primitive_cone_add, name, location, scale, rotation, color,
                      radius1=radius, radius2=0, depth=depth, vertices=vertices)


def torus(name='Torus', major_radius=1, minor_radius=.25, location=(0, 0, 0), scale=(1, 1, 1), rotation=None, color=None):
    """輪を作る。大半径と管の半径を指定する。"""
    return _primitive(bpy.ops.mesh.primitive_torus_add, name, location, scale, rotation, color,
                      major_radius=major_radius, minor_radius=minor_radius,
                      major_segments=24, minor_segments=8)


def plane(name='Plane', size=2, location=(0, 0, 0), scale=(1, 1, 1), rotation=None, color=None):
    """平面を作る。"""
    return _primitive(bpy.ops.mesh.primitive_plane_add, name, location, scale, rotation, color, size=size)


def monkey(name='Monkey', location=(0, 0, 0), scale=(1, 1, 1), rotation=None, color=None):
    """頭の下書きに使える Suzanne を作る。"""
    return _primitive(bpy.ops.mesh.primitive_monkey_add, name, location, scale, rotation, color)


def transform(obj, location=None, rotation=None, scale=None, apply=True):
    """位置・回転（度）・倍率を設定。apply=True なら回転と倍率を確定。"""
    _active(obj)
    if location is not None:
        obj.location = location
    if rotation is not None:
        obj.rotation_euler = tuple(math.radians(v) for v in rotation)
    if scale is not None:
        obj.scale = scale
    if apply:
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def _mesh_edit(obj, operation):
    _active(obj)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        operation(bm)
        bm.normal_update()
        bm.to_mesh(obj.data)
        obj.data.update()
    finally:
        bm.free()
    return obj


def extrude(obj, faces=None, distance=.2, direction=(0, 0, 1)):
    """面番号の領域を指定方向へ押し出す。faces=None は全ての面。"""
    def edit(bm):
        selected = list(bm.faces) if faces is None else [bm.faces[i] for i in faces]
        result = bmesh.ops.extrude_face_region(bm, geom=selected)
        verts = [v for v in result['geom'] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=verts, vec=Vector(direction).normalized() * distance)
        bmesh.ops.delete(bm, geom=selected, context='FACES_ONLY')
    return _mesh_edit(obj, edit)


def inset(obj, faces=None, thickness=.1, depth=0):
    """面番号の領域を内側へインセット。faces=None は全ての面。"""
    def edit(bm):
        selected = list(bm.faces) if faces is None else [bm.faces[i] for i in faces]
        bmesh.ops.inset_region(bm, faces=selected, thickness=thickness, depth=depth,
                               use_boundary=True, use_even_offset=True)
    return _mesh_edit(obj, edit)


def _modifier(obj, kind, apply, **settings):
    _active(obj)
    mod = obj.modifiers.new(kind.title(), kind)
    for key, value in settings.items():
        setattr(mod, key, value)
    if apply:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj


def bevel(obj, width=.1, segments=2, apply=True):
    """角を丸める。既定では形状に確定する。"""
    return _modifier(obj, 'BEVEL', apply, width=width, segments=segments)


def subdivision(obj, levels=1, apply=True):
    """Catmull-Clark で細分化する。重くなるので段数は控えめに。"""
    return _modifier(obj, 'SUBSURF', apply, levels=levels, render_levels=levels)


def mirror(obj, axis='X', apply=True):
    """物体の原点を中心に X/Y/Z 軸でミラー。"""
    axis = axis.upper()
    if axis not in ('X', 'Y', 'Z'):
        raise ValueError('axis は X/Y/Z です')
    return _modifier(obj, 'MIRROR', apply, use_axis=tuple(a == axis for a in 'XYZ'))


def array(obj, count=2, offset=(1.2, 0, 0), apply=True):
    """物体の寸法に対する相対間隔で複製を並べる。"""
    return _modifier(obj, 'ARRAY', apply, count=count, relative_offset_displace=offset)


def boolean(obj, cutter, operation='DIFFERENCE', apply=True):
    """DIFFERENCE/UNION/INTERSECT。切削物体は自動では消さない。"""
    return _modifier(obj, 'BOOLEAN', apply, object=cutter, operation=operation, solver='EXACT')


def decimate(obj, ratio=.5, apply=True):
    """面数を比率で減らす。UV や形の変化は下見で確認する。"""
    return _modifier(obj, 'DECIMATE', apply, ratio=ratio)


def voxel_remesh(obj, voxel_size=.1):
    """ボクセルで再構築する。既存 UV は失われるので後から展開する。"""
    _active(obj)
    obj.data.remesh_voxel_size = voxel_size
    bpy.ops.object.voxel_remesh()
    return obj


def quadriflow(obj, faces=500):
    """QuadriFlow が使える場合に四角面へ再構築。UV は展開し直す。"""
    _active(obj)
    if not hasattr(bpy.ops.object, 'quadriflow_remesh'):
        raise RuntimeError('この Blender に QuadriFlow がありません')
    bpy.ops.object.quadriflow_remesh(mode='FACES', target_faces=faces, use_preserve_sharp=True)
    return obj


def normals(obj):
    """面の法線を一貫した向きにそろえる。"""
    return _mesh_edit(obj, lambda bm: bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces)))


def shade(obj, smooth=True):
    """スムーズシェード。smooth=False ならフラット。"""
    for poly in obj.data.polygons:
        poly.use_smooth = smooth
    return obj


def _uv(obj, operation, **kwargs):
    _active(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.mesh.select_all(action='SELECT')
        operation(**kwargs)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    return obj


def smart_project(obj, angle=66, margin=.03):
    """角度（度）で自動 UV 展開する。"""
    return _uv(obj, bpy.ops.uv.smart_project, angle_limit=math.radians(angle), island_margin=margin)


def cube_project(obj, size=2):
    """立方体投影で UV を作る。"""
    return _uv(obj, bpy.ops.uv.cube_project, cube_size=size)


def unwrap(obj, angle=60, margin=.03):
    """隣接面の角度（度）と境界でシームを付けて UV 展開する。"""
    def seams(bm):
        limit = math.radians(angle)
        for edge in bm.edges:
            edge.seam = not edge.is_manifold or edge.calc_face_angle(0) >= limit
    _mesh_edit(obj, seams)
    return _uv(obj, bpy.ops.uv.unwrap, method='ANGLE_BASED', margin=margin)


def uv_islands(obj):
    """共有辺の両端 UV が連続する面をまとめて島数を数える。"""
    mesh = obj.data
    if not mesh.uv_layers.active or not mesh.polygons:
        return 0
    uv = mesh.uv_layers.active.data
    parent = list(range(len(mesh.polygons)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    edges = {}
    for poly in mesh.polygons:
        loops = list(poly.loop_indices)
        for i, a in enumerate(loops):
            b = loops[(i + 1) % len(loops)]
            va, vb = mesh.loops[a].vertex_index, mesh.loops[b].vertex_index
            ends = {va: tuple(uv[a].uv), vb: tuple(uv[b].uv)}
            key = tuple(sorted((va, vb)))
            for other, previous in edges.get(key, []):
                if all(abs(ends[v][j] - previous[v][j]) < 1e-6 for v in key for j in (0, 1)):
                    parent[root(poly.index)] = root(other)
            edges.setdefault(key, []).append((poly.index, ends))
    return len({root(p.index) for p in mesh.polygons})


def material(obj, name='Material', color=(.6, .6, .6, 1), metallic=0, roughness=.5):
    """Principled BSDF の色・金属度・粗さを設定して物体に付ける。"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    rgba = tuple(color) if len(color) == 4 else (*color, 1)
    mat.diffuse_color = rgba
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = rgba
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    obj.data.materials.append(mat)
    return mat


def _output(filename):
    if Path(filename).is_absolute():
        raise ValueError('出力名は出力先内の相対パスにしてください')
    path = (_OUT / filename).resolve()
    if path == _OUT or not path.is_relative_to(_OUT):
        raise ValueError('出力先の外には書けません')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def bake_texture(obj, kind='noise', filename='texture.png', resolution=128, scale=5):
    """noise/voronoi の色を Cycles CPU で PNG へベイクし、材質へ接続。"""
    if kind not in ('noise', 'voronoi') or not 16 <= resolution <= 512:
        raise ValueError('kind は noise/voronoi、resolution は16〜512です')
    path = _output(filename)
    _active(obj)
    if not obj.data.uv_layers.active:
        smart_project(obj)
    if not obj.data.materials:
        material(obj)
    # 全材質スロットを同じ画像へ焼き、後で Principled の色へつなぐ。
    image = bpy.data.images.new('BakedTexture', width=resolution, height=resolution)
    records = []
    scene = bpy.context.scene
    old_engine = scene.render.engine
    old_device, old_samples = scene.cycles.device, scene.cycles.samples
    try:
        for mat in dict.fromkeys(m for m in obj.data.materials if m):
            mat.use_nodes = True
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
            old_surface = [link.from_socket for link in output.inputs['Surface'].links]
            old_active = nodes.active
            texture = nodes.new('ShaderNodeTexNoise' if kind == 'noise' else 'ShaderNodeTexVoronoi')
            texture.inputs['Scale'].default_value = scale
            emission = nodes.new('ShaderNodeEmission')
            links.new(texture.outputs['Color'], emission.inputs['Color'])
            links.new(emission.outputs[0], output.inputs['Surface'])
            target = nodes.new('ShaderNodeTexImage')
            target.image = image
            nodes.active = target
            records.append((mat, output, old_surface, old_active, texture, emission, target))
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 1
        bpy.ops.object.bake(type='EMIT', margin=2)
        image.filepath_raw = str(path)
        image.file_format = 'PNG'
        image.save()
    finally:
        scene.render.engine = old_engine
        scene.cycles.device, scene.cycles.samples = old_device, old_samples
        for mat, output, old_surface, old_active, texture, emission, target in records:
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            nodes.remove(emission)
            nodes.remove(texture)
            for source in old_surface:
                links.new(source, output.inputs['Surface'])
            nodes.active = old_active
    for mat, *rest in records:
        target = rest[-1]
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        if bsdf:
            mat.node_tree.links.new(target.outputs['Color'], bsdf.inputs['Base Color'])
    return str(path)


def armature(obj, bones=None, name='Rig'):
    """(名前,始点,終点,親名) の骨列を作り自動ウェイト。既定は胴の2本。"""
    bones = bones or [('root', (0, 0, 0), (0, 0, 1), None),
                      ('upper', (0, 0, 1), (0, 0, 2), 'root')]
    _active(obj)
    data = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(rig)
    _active(rig)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        for bone_name, head, tail, parent in bones:
            bone = data.edit_bones.new(bone_name)
            bone.head, bone.tail = head, tail
            if parent:
                bone.parent = data.edit_bones[parent]
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(True)
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    if not obj.vertex_groups or any(not v.groups for v in obj.data.vertices):
        raise RuntimeError('自動ウェイトが付かない頂点があります。形・骨位置を調整してください')
    return rig


def export(filename='model.glb', objects=None):
    """出力先内の glb/obj/fbx/stl/blend へ保存。objects で対象を限定。"""
    path = _output(filename)
    ext = path.suffix.lower()
    if ext not in ('.glb', '.obj', '.fbx', '.stl', '.blend'):
        raise ValueError('対応形式は glb/obj/fbx/stl/blend です')
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    chosen = list(objects) if objects is not None else [o for o in bpy.context.scene.objects
                                                      if o.type in ('MESH', 'ARMATURE')]
    for obj in chosen:
        obj.select_set(True)
    if chosen:
        bpy.context.view_layer.objects.active = chosen[0]
    if ext == '.glb':
        bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True)
    elif ext == '.obj':
        bpy.ops.wm.obj_export(filepath=str(path), export_selected_objects=True)
    elif ext == '.fbx':
        bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, bake_anim=False)
    elif ext == '.stl':
        bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=True)
    else:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False)
    return str(path)


def preview(filename='preview.png', engine='BLENDER_WORKBENCH'):
    """正面斜めから512px PNG。Workbench/Eevee、明示時は Cycles CPU も可。"""
    path = _output(filename)
    if engine not in ('BLENDER_WORKBENCH', 'BLENDER_EEVEE_NEXT', 'CYCLES'):
        raise ValueError('下見エンジンが不正です')
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = [obj.matrix_world @ Vector(corner)
              for obj in scene.objects if obj.type == 'MESH' and not obj.hide_render
              for corner in obj.evaluated_get(depsgraph).bound_box]
    if not points:
        raise ValueError('下見するメッシュがありません')
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center, diameter = (low + high) / 2, max((high - low).length, .1)
    camera_data = bpy.data.cameras.new('PreviewCamera')
    camera = bpy.data.objects.new('PreviewCamera', camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((1.4, -2, 1.2)).normalized() * diameter * 2
    camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = diameter * 1.15
    camera_data.clip_end = max(100, diameter * 10)
    light_data = bpy.data.lights.new('PreviewLight', 'AREA')
    light_data.energy, light_data.size = 800, diameter * 2
    light = bpy.data.objects.new('PreviewLight', light_data)
    scene.collection.objects.link(light)
    light.location = center + Vector((1, -1, 2)) * diameter
    light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
    old_camera = scene.camera
    scene.camera = camera
    old = {k: getattr(scene.render, k) for k in
           ('engine', 'filepath', 'resolution_x', 'resolution_y', 'resolution_percentage', 'film_transparent')}
    old_format = scene.render.image_settings.file_format
    old_device, old_samples = scene.cycles.device, scene.cycles.samples
    old_denoising = scene.cycles.use_denoising
    shading = scene.display.shading
    old_shading = {k: getattr(shading, k) for k in
                   ('light', 'color_type', 'show_shadows', 'show_cavity')}
    try:
        scene.render.engine = engine
        scene.render.filepath = str(path)
        scene.render.resolution_x = scene.render.resolution_y = 512
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = False
        scene.render.image_settings.file_format = 'PNG'
        if engine == 'BLENDER_WORKBENCH':
            scene.display.shading.light = 'STUDIO'
            scene.display.shading.color_type = 'MATERIAL'
            scene.display.shading.show_shadows = True
            scene.display.shading.show_cavity = True
        elif engine == 'CYCLES':
            scene.cycles.device, scene.cycles.samples = 'CPU', 8
            scene.cycles.use_denoising = False
        bpy.ops.render.render(write_still=True)
    finally:
        scene.camera = old_camera
        for key, value in old.items():
            setattr(scene.render, key, value)
        scene.render.image_settings.file_format = old_format
        scene.cycles.device, scene.cycles.samples = old_device, old_samples
        scene.cycles.use_denoising = old_denoising
        for key, value in old_shading.items():
            setattr(shading, key, value)
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.objects.remove(light, do_unlink=True)
        bpy.data.cameras.remove(camera_data)
        bpy.data.lights.remove(light_data)
    global _PREVIEW
    _PREVIEW = str(path)
    return str(path)


_TOOLS = ('cube uv_sphere cylinder cone torus plane monkey transform extrude inset bevel '
          'subdivision mirror array boolean decimate voxel_remesh quadriflow normals shade '
          'smart_project cube_project unwrap uv_islands material bake_texture armature export preview').split()


def _statistics():
    stats = []
    graph = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            stats.append(dict(name=obj.name, vertices=len(mesh.vertices), faces=len(mesh.polygons),
                              triangles=len(mesh.loop_triangles), uv=bool(mesh.uv_layers.active),
                              uv_islands=uv_islands(types.SimpleNamespace(data=mesh)),
                              materials=[m.name for m in mesh.materials if m]))
        finally:
            evaluated.to_mesh_clear()
    return stats


def _worker(payload_path):
    global bpy, bmesh, Vector, _OUT, _PREVIEW
    import bpy
    import bmesh
    from mathutils import Vector
    data = json.loads(Path(payload_path).read_text(encoding='utf-8'))
    _OUT = Path(data['out_dir']).resolve()
    _PREVIEW = None
    report = dict(ok=False, stats=[], preview=None, error=None)
    try:
        validate(data['script'])
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.context.scene.render.threads_mode = 'FIXED'
        bpy.context.scene.render.threads = 2
        bpy.context.scene.render.use_file_extension = True
        kit = types.ModuleType('kit', '軽い3Dモデリングの道具箱')
        for name in _TOOLS:
            setattr(kit, name, globals()[name])
        sys.modules['kit'] = kit
        import builtins
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level or name not in _IMPORTS:
                raise ImportError('許可されていない import')
            return builtins.__import__(name, globals, locals, fromlist, level)
        safe = {name: getattr(builtins, name) for name in
                ('abs all any bool dict enumerate Exception float int isinstance len list '
                 'max min print range reversed round RuntimeError set sorted str sum tuple '
                 'TypeError ValueError zip').split()}
        safe['__import__'] = safe_import
        exec(compile(data['script'], '<台本>', 'exec'), {'__builtins__': safe})
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        report['stats'] = _statistics()
        if _PREVIEW is None:
            preview()
        report.update(ok=True, preview=_PREVIEW)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        report.update(error=f'{type(exc).__name__}: {exc}', preview=_PREVIEW)
    Path(data['report']).write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    if not report['ok']:
        raise RuntimeError(report['error'])


if __name__ == '__main__' and '--worker' in sys.argv:
    _worker(sys.argv[sys.argv.index('--worker') + 1])
