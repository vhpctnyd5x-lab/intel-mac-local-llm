"""1枚絵と相対深度から、隔離した Blender で小さく動く2.5D動画を作る。"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

try:
    from .okuyuki import depth as estimate_depth, soften_edges
except ImportError:
    from okuyuki import depth as estimate_depth, soften_edges


BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
SANDBOX = Path("/usr/bin/sandbox-exec")
FPS = 24
WIDTH, HEIGHT = 1280, 720


_BLENDER_SCRIPT = r'''import bpy, json, math, sys
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
with open(args[0], "r", encoding="utf-8") as f:
    cfg = json.load(f)
scene = bpy.context.scene
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.materials, bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
    pass
image = bpy.data.images.load(cfg["texture"], check_existing=False)
depth_image = bpy.data.images.load(cfg["depth"], check_existing=False)
depth_image.colorspace_settings.name = "Non-Color"
width, height = image.size
aspect = width / height
nx = min(240, max(100, int(180 * min(aspect, 1.8))))
ny = min(180, max(72, int(nx / aspect)))
verts, faces, uvs = [], [], []
for j in range(ny + 1):
    v = j / ny
    for i in range(nx + 1):
        u = i / nx
        # 深度の変位を控えめにし、画面外周では滑らかにゼロへ落とす。
        edge = min(u, 1-u, v, 1-v)
        t = max(0.0, min(1.0, edge / 0.07))
        fade = t*t*(3-2*t)
        px = min(width-1, max(0, round(u*(width-1))))
        py = min(height-1, max(0, round((1-v)*(height-1))))
        d = depth_image.pixels[(py*width + px)*4]
        z = (d - 0.5) * cfg["strength"] * fade
        verts.append(((u-0.5)*aspect*2, z, (v-0.5)*2))
for j in range(ny):
    for i in range(nx):
        a = j*(nx+1)+i
        faces.append((a, a+1, a+nx+2, a+nx+1))
mesh = bpy.data.meshes.new("DepthGrid")
mesh.from_pydata(verts, [], faces)
mesh.update()
uv = mesh.uv_layers.new(name="UVMap")
for poly in mesh.polygons:
    for loop_index in poly.loop_indices:
        vertex_index = mesh.loops[loop_index].vertex_index
        j, i = divmod(vertex_index, nx+1)
        uv.data[loop_index].uv = (i/nx, j/ny)
obj = bpy.data.objects.new("2.5D image", mesh)
scene.collection.objects.link(obj)
mat = bpy.data.materials.new("Source image")
mat.use_nodes = True
nodes, links = mat.node_tree.nodes, mat.node_tree.links
# 10/8 実機: 名前で探すと None だった（言語設定で名前が変わる）。種類で探す
for node in [n for n in nodes if n.type == "BSDF_PRINCIPLED"]:
    nodes.remove(node)
tex = nodes.new("ShaderNodeTexImage")
tex.image = image
tex.interpolation = "Linear"
emission = nodes.new("ShaderNodeEmission")
links.new(tex.outputs["Color"], emission.inputs["Color"])
links.new(emission.outputs["Emission"], nodes.get("Material Output").inputs["Surface"])
obj.data.materials.append(mat)
cam_data = bpy.data.cameras.new("Camera")
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam_data.lens = 32
cam.location = (0, -3.35, 0)
cam.rotation_euler = (math.radians(90), 0, 0)
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x, scene.render.resolution_y = cfg["width"], cfg["height"]
scene.render.resolution_percentage = 100
scene.render.fps = cfg["fps"]
scene.frame_start, scene.frame_end = 1, cfg["frames"]
scene.world.color = (0.025, 0.025, 0.025)
scene.view_settings.view_transform = "Standard"
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.filepath = cfg["preview"]
scene.frame_set(1)
bpy.ops.render.render(write_still=True)
base = Vector((0, -3.35, 0))
for frame in range(1, cfg["frames"]+1):
    t = (frame-1) / max(1, cfg["frames"]-1)
    if cfg["motion"] == "dolly":
        offset = Vector((0, -0.10 + 0.20*t, 0))
    elif cfg["motion"] == "pan":
        offset = Vector((-0.11 + 0.22*t, 0, 0))
    else:
        angle = math.radians(-3.0 + 6.0*t)
        offset = Vector((math.sin(angle)*0.12, 0, math.cos(angle)*0.03-0.03))
    cam.location = base + offset
    cam.keyframe_insert(data_path="location", frame=frame)
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
scene.render.ffmpeg.ffmpeg_preset = "GOOD"
scene.render.filepath = cfg["video"]
scene.render.use_file_extension = True
scene.frame_set(1)
bpy.ops.render.render(animation=True)
'''


def _profile(out_dir: Path, work_dir: Path) -> str:
    quote = lambda p: json.dumps(str(p.resolve()), ensure_ascii=False)
    paths = (out_dir, work_dir, Path("/private/var/folders"), Path("/dev"))
    return "\n".join(("(version 1)", "(allow default)", "(deny network*)",
        "(deny file-write* (require-not (require-any " + " ".join(
            f"(subpath {quote(p)})" for p in paths) + ")))"))


def make(image_path, out_dir, seconds=5, motion="dolly", strength=0.3):
    """作成した動画・下見PNG・深度PNGのパスを seisei と同じ形式で返す。"""
    output = Path(out_dir).expanduser()
    if output.is_symlink():
        raise ValueError("出力先にシンボリックリンクは使えません")
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("出力先は新規または空のフォルダだけです（上書き禁止）")
    source = Path(image_path).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("入力は PNG/JPEG/WebP 画像にしてください")
    if source.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("入力画像は100MiB以内にしてください")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 1 <= seconds <= 10:
        raise ValueError("seconds は1〜10秒です")
    if motion not in {"dolly", "orbit", "pan"}:
        raise ValueError('motion は "dolly" / "orbit" / "pan" です')
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= 0.6:
        raise ValueError("strength は0〜0.6です")
    if not BLENDER.is_file():
        return _result(False, f"Blender がありません: {BLENDER}", output)
    if sys.platform != "darwin" or not SANDBOX.is_file():
        return _result(False, "macOS の sandbox-exec が必要です（隔離なしでは実行しません）", output)
    output.mkdir(parents=True, exist_ok=True)
    depth_path = output / "depth.png"
    texture_path = output / "texture_soft.png"
    preview_path = output / "preview.png"
    video_path = output / "video.mp4"
    process = None
    try:
        estimate_depth(source, depth_path)
        soften_edges(source, texture_path)
        with tempfile.TemporaryDirectory(prefix="douga25d-") as raw:
            work = Path(raw).resolve()
            payload = work / "payload.json"
            script = work / "scene.py"
            report = {
                "texture": str(texture_path), "depth": str(depth_path),
                "preview": str(preview_path), "video": str(video_path),
                "motion": motion, "strength": float(strength),
                "fps": FPS, "frames": round(float(seconds) * FPS),
                "width": WIDTH, "height": min(HEIGHT, round(WIDTH / 16 * 9)),
            }
            payload.write_text(json.dumps(report), encoding="utf-8")
            script.write_text(_BLENDER_SCRIPT, encoding="utf-8")
            profile = work / "sandbox.sb"
            profile.write_text(_profile(output, work), encoding="utf-8")
            env = {
                "PATH": "/usr/bin:/bin", "HOME": str(work), "TMPDIR": str(work),
                "LANG": "en_US.UTF-8", "OMP_NUM_THREADS": "2",
                "BLENDER_USER_CONFIG": str(work / "config"),
                "BLENDER_USER_SCRIPTS": str(work / "scripts"),
                "BLENDER_USER_DATAFILES": str(work / "datafiles"),
            }
            command = [str(SANDBOX), "-f", str(profile), str(BLENDER),
                       "--background", "--factory-startup", "--python", str(script), "--", str(payload)]
            with (output / "blender.log").open("xb+") as log:
                process = subprocess.Popen(command, cwd=work, env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True)
                try:
                    code = process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise RuntimeError("Blender が1800秒で時間切れになりました")
            if code:
                tail = (output / "blender.log").read_text(encoding="utf-8", errors="replace")[-1800:]
                raise RuntimeError(f"Blender が終了コード {code} を返しました: {tail}")
        missing = [p.name for p in (preview_path, video_path) if not p.is_file() or p.stat().st_size == 0]
        if missing:
            raise RuntimeError("Blender の出力がありません: " + ", ".join(missing))
        return _result(True, f"{seconds:g}秒・{FPS}fps の2.5D動画を作成しました", output,
                       (preview_path,), 動画=str(video_path), 奥行き=str(depth_path))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        return _result(False, "2.5D動画の作成に失敗しました: " + str(exc)[:2200], output)


def _result(ok, text, out=None, images=(), **extra):
    return {"ok": bool(ok), "結果": text, "画像": [str(p) for p in images],
            "場所": str(out) if out is not None else "", **extra}
