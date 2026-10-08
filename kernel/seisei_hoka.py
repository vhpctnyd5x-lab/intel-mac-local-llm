"""生成の追加部品。標準ライブラリ・macOS 標準コマンド・Blender 4.5 のみ。

kernel/ は読み取りのみ。本体への接続は Claude が行う。
out_dir は未作成または新規の空フォルダ（seisei.new_folder の返り値も可）。
利用済みフォルダへの追記・上書きは禁止。Blender の実行確認は外で行う。
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
HAIKEI = HERE / "bin" / "haikei"
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
SAY = "/usr/bin/say"
AFCONVERT = "/usr/bin/afconvert"
SANDBOX = "/usr/bin/sandbox-exec"
SWIFTC = "/usr/bin/swiftc"


def _result(ok, text, out=None, images=(), **extra):
    return {"ok": bool(ok), "結果": text, "画像": [str(p) for p in images],
            "場所": str(out) if out is not None else "", **extra}


def _new_output(out_dir):
    if out_dir is None or not str(out_dir).strip():
        raise ValueError("out_dir に新しいフォルダを指定してください")
    path = Path(out_dir).expanduser()
    if path.is_symlink():
        raise ValueError("出力先にシンボリックリンクは使えません")
    path = path.resolve()
    if path == Path(path.anchor):
        raise ValueError("出力先にルートは使えません")
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError("出力先は新規または空のフォルダだけです（上書き禁止）")
    else:
        path.mkdir(parents=True, exist_ok=False)
    # 同じ空フォルダを二つの依頼が同時に使っても、一つしか受け付けない。
    with (path / ".seisei-job.json").open("x", encoding="utf-8") as file:
        json.dump({"部品": "seisei_hoka", "上書き": False}, file, ensure_ascii=False)
    return path


def _input(path, suffixes):
    if path is None:
        raise ValueError("入力ファイルが指定されていません")
    value = Path(path).expanduser().resolve(strict=True)
    if not value.is_file() or value.suffix.lower() not in suffixes:
        raise ValueError("入力の種類が違います: " + ", ".join(sorted(suffixes)))
    if value.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("入力ファイルは100MiB以内にしてください")
    return value


def _timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout は正の秒数にしてください")
    return value


def _env(work):
    # 認証・秘密の環境変数を子へ渡さない。
    return dict(PATH="/usr/bin:/bin", HOME=str(work), TMPDIR=str(work),
                LANG="en_US.UTF-8", XDG_CACHE_HOME=str(work / "cache"),
                OMP_NUM_THREADS="2", BLENDER_USER_CONFIG=str(work / "config"),
                BLENDER_USER_SCRIPTS=str(work / "scripts"),
                BLENDER_USER_DATAFILES=str(work / "datafiles"))


def _profile(out, work):
    # kernel/sanjigen.py と同じ形。ネットワーク禁止、キャッシュと /dev は例外。
    quote = lambda p: json.dumps(str(p), ensure_ascii=False)
    paths = (out.resolve(), work.resolve(), Path("/private/var/folders"), Path("/dev"))
    return "\n".join(("(version 1)", "(allow default)", "(deny network*)",
        "(deny file-write* (require-not (require-any " + " ".join(
            f"(subpath {quote(p)})" for p in paths) + ")))",))


def _sandbox(command, out, work):
    if sys.platform != "darwin" or not Path(SANDBOX).is_file():
        raise RuntimeError("macOS の sandbox-exec が必要です（隔離なしでは実行しません）")
    profile = work / "sandbox.sb"
    body = _profile(out, work)
    if profile.exists():
        if profile.read_text(encoding="utf-8") != body:
            raise RuntimeError("既存の隔離設定は変更しません")
    else:
        with profile.open("x", encoding="utf-8") as file:
            file.write(body)
    return [SANDBOX, "-f", str(profile), *map(str, command)]


def _execute(command, work, timeout, log_name="process.log"):
    """ログは作業先のファイルへ。時間切れは子プロセス群も回収する。再試行なし。"""
    _timeout(timeout)
    process = None
    with (work / log_name).open("xb+") as log:
        try:
            process = subprocess.Popen(command, cwd=work, env=_env(work),
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
            with (work / (log_name + ".pid.json")).open("x", encoding="utf-8") as file:
                json.dump({"pid": process.pid, "command": list(command)}, file, ensure_ascii=False)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError(f"{timeout}秒で時間切れ（プロセス群を停止しました）")
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        log.seek(0, 2)
        size = log.tell()
        log.seek(0)
        head = log.read(min(size, 1500)) if size > 8000 else b""
        log.seek(max(0, size - 8_000))
        tail = (head + log.read()).decode("utf-8", "replace")
    if code != 0:
        why = f"終了信号 {-code}（再実行していません）" if code < 0 else f"終了コード {code}"
        lines = tail.splitlines()
        excerpt = lines if len(lines) <= 12 else lines[:4] + ["…"] + lines[-8:]
        raise RuntimeError(why + ": " + "\n".join(excerpt)[:1600])
    return tail


def _present(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"出力がありません: {path.name}")


def koe_list():
    """インストール済みの ja_JP 音声だけ。声=[名前,...] も返す。取得のみ。"""
    try:
        done = subprocess.run([SAY, "-v", "?"], capture_output=True, text=True,
                              timeout=15, check=True, env={"PATH": "/usr/bin:/bin"})
        voices = []
        for line in done.stdout.splitlines():
            match = re.match(r"^(.+?)\s+ja_JP\s+#", line)
            if match:
                voices.append(match.group(1).strip())
        if not voices:
            raise RuntimeError("インストール済みの日本語音声がありません")
        return _result(True, "日本語の声: " + "、".join(voices), 声=voices)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return _result(False, "声の一覧を取得できません: " + str(exc), 声=[])


def koe(text, voice="Kyoko", rate=None, out_dir=None):
    """2000字以内の日本語を AIFF → AAC/M4A に。引数はシェルを通さない。"""
    out = None
    try:
        if not isinstance(text, str) or not text.strip() or len(text) > 2000 or "\0" in text:
            raise ValueError("文は空でない2000字以内の文字列にしてください")
        voices = koe_list()
        if not voices["ok"]:
            raise RuntimeError(voices["結果"])
        if voice not in voices["声"]:
            raise ValueError("インストール済みの日本語の声を koe_list() から選んでください")
        if rate is not None and (isinstance(rate, bool) or not isinstance(rate, int) or not 80 <= rate <= 500):
            raise ValueError("rate は80〜500の整数（語/分）にしてください")
        out = _new_output(out_dir)
        work = out / ".work"
        work.mkdir()
        source = out / "text.txt"
        source.write_text(text, encoding="utf-8")
        aiff, m4a = out / "koe.aiff", out / "koe.m4a"
        command = [SAY, "-v", voice, "-o", str(aiff), "-f", str(source)]
        if rate is not None:
            command += ["-r", str(rate)]
        _execute(command, work, 300, "say.log")
        _present(aiff)
        _execute([AFCONVERT, "-f", "m4af", "-d", "aac", "-b", "64000",
                  str(aiff), str(m4a)], work, 60, "afconvert.log")
        _present(m4a)
        return _result(True, f"読み上げを作りました（{voice}）: {m4a.name}", out)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return _result(False, "読み上げに失敗: " + str(exc), out)


def build_haikei(timeout=300):
    """swiftc -O で kernel/bin/haikei を新規ビルド。既存バイナリは上書きしない。"""
    binary_dir = HAIKEI.parent
    try:
        _timeout(timeout)
        source = HERE / "haikei.swift"
        if HAIKEI.exists() or HAIKEI.is_symlink():
            if HAIKEI.is_symlink() or not HAIKEI.is_file() or not os.access(HAIKEI, os.X_OK):
                raise RuntimeError("既存の haikei は実行ファイルではありません（上書き禁止）")
            if HAIKEI.stat().st_mtime_ns < source.stat().st_mtime_ns:
                raise RuntimeError("既存の haikei が古いです。別に退避してからビルドしてください（上書き禁止）")
            return _result(True, "ビルド済みの haikei を使います", binary_dir)
        if sys.platform != "darwin" or not Path(SWIFTC).is_file():
            raise RuntimeError("macOS の既存 swiftc が必要です。追加ダウンロードはしません")
        binary_dir.mkdir(parents=True, exist_ok=True)
        cache = binary_dir / ".module-cache"
        # 初回失敗時のキャッシュも再利用。毎回標準モジュールを作り直さない。
        if not cache.exists():
            previous = sorted(binary_dir.glob("build-*/module-cache"))
            if previous:
                previous[0].rename(cache)
        cache.mkdir(exist_ok=True)
        # ビルドのログ・PIDを残す。コンパイラの後処理と一時領域の削除を競合させない。
        work = Path(tempfile.mkdtemp(prefix="build-", dir=binary_dir))
        target = work / "haikei"
        _execute([SWIFTC, "-O", "-j", "2", "-module-cache-path", str(cache),
                  str(source), "-o", str(target)], work, timeout, "swiftc.log")
        _present(target)
        # 同一ファイルシステムの hard link で排他的に設置。既存パスに置換しない。
        os.link(target, HAIKEI)
        return _result(True, f"背景除去をビルドしました: {HAIKEI.name}", binary_dir)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return _result(False, "背景除去のビルドに失敗: " + str(exc), binary_dir)


def haikei(image_path, out_dir):
    """ビルド済み Apple Vision ヘルパーで透明 PNG。失敗時の再実行はしない。"""
    out = None
    try:
        image = _input(image_path, {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff"})
        if not HAIKEI.is_file() or not os.access(HAIKEI, os.X_OK):
            raise RuntimeError("先に build_haikei() を実行してください")
        out = _new_output(out_dir)
        work = out / ".work"
        work.mkdir()
        target = out / "haikei.png"
        text = _execute([str(HAIKEI), str(image), str(target)], work, 120)
        _present(target)
        info = json.loads(text.strip().splitlines()[-1])
        note = info.get("note", "")
        return _result(True, "透明PNGを作りました: haikei.png" + ("\n" + note if note else ""),
                       out, [target], 方法=info.get("method", ""))
    except (OSError, TypeError, ValueError, RuntimeError, IndexError) as exc:
        return _result(False, "背景除去に失敗（再実行していません）: " + str(exc), out)


def douga(kind, out_dir, *, images=None, image_path=None, glb_path=None,
          audio_path=None, seconds=None, fps=24, width=1280, height=720,
          motion="zoom", engine="WORKBENCH", timeout=300):
    """gazou: Ken Burns / 3d: GLB一周。実行確認は Claude が砂箱の外から行う。

    images は1〜8枚。motion は zoom / pan。音は m4a / wav。
    engine は WORKBENCH / EEVEE。最大30秒・24fps・1280x720。
    """
    out = None
    try:
        if kind not in {"gazou", "3d"}:
            raise ValueError("動画の kind は gazou / 3d です")
        if seconds is None:
            seconds = 6 if kind == "gazou" else 4
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= 30:
            raise ValueError("seconds は0より大きく30以下にしてください")
        for name, value, low, high in (("fps", fps, 1, 24), ("width", width, 64, 1280), ("height", height, 64, 720)):
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} は{low}〜{high}の整数にしてください")
        if width % 2 or height % 2:
            raise ValueError("H.264 の幅と高さは偶数にしてください")
        if motion not in {"zoom", "pan"} or engine not in {"WORKBENCH", "EEVEE"}:
            raise ValueError("motion は zoom/pan、engine は WORKBENCH/EEVEE です")
        _timeout(timeout)
        frames = round(seconds * fps)
        if frames < 2:
            raise ValueError("動画は2フレーム以上必要です")
        paths, model = [], None
        if kind == "gazou":
            if image_path is not None and images is not None:
                raise ValueError("image_path と images はどちらか一方です")
            items = [image_path] if image_path is not None else images
            if not isinstance(items, (tuple, list)) or not 1 <= len(items) <= 8:
                raise ValueError("images は1〜8枚のパスのリストです")
            if frames < 2 * len(items):
                raise ValueError("各画像に2フレーム以上必要です")
            paths = [str(_input(p, {".png", ".jpg", ".jpeg", ".tif", ".tiff"})) for p in items]
        else:
            model = str(_input(glb_path, {".glb"}))
        audio = str(_input(audio_path, {".m4a", ".wav"})) if audio_path is not None else None
        if not BLENDER.is_file():
            raise RuntimeError("Blender 4.5 が見つかりません。追加ダウンロードはしません")
        out = _new_output(out_dir)
        work = out / ".work"
        work.mkdir()
        payload = work / "payload.json"
        report = work / "report.json"
        data = dict(kind=kind, images=paths, glb_path=model, audio_path=audio,
                    frames=frames, fps=fps, width=width, height=height, motion=motion,
                    engine=engine, out_dir=str(out), report=str(report))
        payload.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        command = _sandbox([str(BLENDER), "-b", "--factory-startup", "--disable-autoexec",
            "-t", "2", "--python-exit-code", "1", "--python", str(Path(__file__).resolve()),
            "--", "--douga-worker", str(payload)], out, work)
        _execute(command, work, timeout, "blender.log")
        done = json.loads(report.read_text(encoding="utf-8"))
        if not done.get("ok"):
            raise RuntimeError(str(done.get("error", "Blender の台本が失敗しました")))
        video, preview = out / "douga.mp4", out / "preview.png"
        _present(video)
        _present(preview)
        return _result(True, f"動画を作りました（{frames / fps:g}秒・{fps}fps・{width}×{height}）: douga.mp4",
                       out, [preview])
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return _result(False, "動画づくりに失敗: " + str(exc), out)


def _douga_worker(payload_path):
    """Blender 専用。外部から受けたコードは実行せず、固定の台本だけ使う。"""
    import bpy
    from mathutils import Vector

    data = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    out = Path(data["out_dir"])
    report = {"ok": False}
    try:
        scene = bpy.context.scene
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        scene.render.engine = "BLENDER_WORKBENCH" if data["engine"] == "WORKBENCH" else "BLENDER_EEVEE_NEXT"
        scene.render.threads_mode = "FIXED"
        scene.render.threads = 2
        scene.render.resolution_x = data["width"]
        scene.render.resolution_y = data["height"]
        scene.render.resolution_percentage = 100
        scene.render.fps = data["fps"]
        scene.frame_start, scene.frame_end = 1, data["frames"]
        scene.render.use_file_extension = True
        scene.render.use_overwrite = False
        scene.view_settings.view_transform = "Standard"
        scene.render.film_transparent = False
        if data["kind"] == "gazou":
            editor = scene.sequence_editor_create()
            scene.render.use_sequencer = True
            # Workbench でも空シーン用のカメラを用意。絵は VSE から出る。
            camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
            scene.collection.objects.link(camera)
            scene.camera = camera
            count = len(data["images"])
            for index, path in enumerate(data["images"]):
                start = 1 + data["frames"] * index // count
                end = 1 + data["frames"] * (index + 1) // count
                image = bpy.data.images.load(path, check_existing=False)
                iw, ih = image.size
                if not iw or not ih or iw * ih > 40_000_000:
                    raise ValueError("画像は4000万画素以内にしてください")
                scale = max(data["width"] / iw, data["height"] / ih)
                bpy.data.images.remove(image)
                strip = editor.strips.new_image(f"Image{index + 1}", path, channel=1,
                                                frame_start=start, fit_method="ORIGINAL")
                strip.frame_final_end = end
                strip.blend_type = "REPLACE"
                transform = strip.transform
                if data["motion"] == "zoom":
                    for frame, factor in ((start, 1.02), (end - 1, 1.14)):
                        transform.scale_x = transform.scale_y = scale * factor
                        transform.keyframe_insert(data_path="scale_x", frame=frame)
                        transform.keyframe_insert(data_path="scale_y", frame=frame)
                else:
                    transform.scale_x = transform.scale_y = scale * 1.16
                    for frame, direction in ((start, -1), (end - 1, 1)):
                        transform.offset_x = direction * data["width"] * 0.04
                        transform.keyframe_insert(data_path="offset_x", frame=frame)
        else:
            # GLB は埋め込み素材。ユーザー設定・自動実行は読み込まない。
            bpy.ops.import_scene.gltf(filepath=data["glb_path"])
            scene.frame_set(1)
            deps = bpy.context.evaluated_depsgraph_get()
            corners = [obj.matrix_world @ Vector(corner)
                       for obj in scene.objects if obj.type == "MESH"
                       for corner in obj.evaluated_get(deps).bound_box]
            if not corners:
                raise ValueError("GLB に表示できるメッシュがありません")
            low = Vector(tuple(min(v[i] for v in corners) for i in range(3)))
            high = Vector(tuple(max(v[i] for v in corners) for i in range(3)))
            center = (low + high) / 2
            radius = max((point - center).length for point in corners)
            if not math.isfinite(radius) or radius <= 0:
                raise ValueError("GLB の大きさが不正です")
            camera_data = bpy.data.cameras.new("TurntableCamera")
            camera_data.lens = 50
            camera_data.sensor_fit = "HORIZONTAL"
            horizontal = 2 * math.atan(camera_data.sensor_width / (2 * camera_data.lens))
            vertical = 2 * math.atan(math.tan(horizontal / 2) * data["height"] / data["width"])
            distance = radius / math.sin(min(horizontal, vertical) / 2) * 1.15
            camera_data.clip_start = max(radius / 1000, 0.001)
            camera_data.clip_end = max(distance + radius * 10, 100)
            pivot = bpy.data.objects.new("TurntablePivot", None)
            pivot.location = center
            scene.collection.objects.link(pivot)
            camera = bpy.data.objects.new("TurntableCamera", camera_data)
            scene.collection.objects.link(camera)
            camera.parent = pivot
            camera.location = (distance * 0.94 / math.sqrt(2),
                               -distance * 0.94 / math.sqrt(2), distance * 0.342)
            camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
            scene.camera = camera
            def orbit(current_scene):
                pivot.rotation_euler.z = math.tau * (current_scene.frame_current - 1) / data["frames"]
            bpy.app.handlers.frame_change_pre.append(orbit)
            scene.display.shading.light = "STUDIO"
            scene.display.shading.color_type = "MATERIAL"
            scene.display.shading.show_shadows = True
            scene.display.shading.show_cavity = True
            scene.display.shading.background_type = "WORLD"
            scene.world.color = (0.08, 0.08, 0.08)
            if data["engine"] == "EEVEE":
                light_data = bpy.data.lights.new("Key", "AREA")
                light_data.energy = 1500 * radius * radius
                light_data.shape, light_data.size = "DISK", radius * 4
                light = bpy.data.objects.new("Key", light_data)
                scene.collection.objects.link(light)
                light.location = center + Vector((radius * 3, -radius * 4, radius * 5))
                light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
        if data["audio_path"]:
            editor = scene.sequence_editor_create()
            sound = editor.strips.new_sound("Sound", data["audio_path"], channel=2, frame_start=1)
            if sound.frame_final_end > data["frames"] + 1:
                sound.frame_final_end = data["frames"] + 1
        # 3D＋音声は、音ストリップだけの VSE に映像を置き換えさせない。
        # 音声は FFmpeg へ混ぜ、映像は3Dレンダーから出す。
        if data["kind"] == "3d":
            scene.render.use_sequencer = False
        scene.frame_set(1)
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.filepath = str(out / "preview.png")
        bpy.ops.render.render(write_still=True)
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.use_autosplit = False
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.ffmpeg.ffmpeg_preset = "GOOD"
        scene.render.ffmpeg.audio_codec = "AAC" if data["audio_path"] else "NONE"
        scene.render.ffmpeg.audio_bitrate = 128
        scene.render.filepath = str(out / "douga.mp4")
        bpy.ops.render.render(animation=True)
        report["ok"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        Path(data["report"]).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


HINTS = {
    "koe": "tsukuru(kind=koe, text=2000字以内の文, voice=Kyoko, rate=任意の語/分)。日本語の読み上げをm4aにする。声はkoe_listで確認。",
    "haikei": "tsukuru(kind=haikei, image_path=手元の画像)。人物・物・動物の背景を透明PNGにする。注目領域での近似になる場合もある。",
    "douga": "tsukuru(kind=douga, video_kind=gazou, images=[手元の画像], seconds=6, audio_path=任意のm4a/wav)。寄り・横流しの動画。\n3D一周はvideo_kind=3d, glb_path=手元のglb, seconds=4。動画は24fps・720p以下、最初のフレームを下見にする。",
}


def hint(request=""):
    """本体の hint より先に判定する文案。空文字なら全種の案を返す。"""
    patterns = {"koe": r"読み上げ|音声|ナレーション|声|koe",
                "haikei": r"背景.*(?:除去|消|透明)|切り抜|haikei",
                "douga": r"動画|映像|一周|ターンテーブル|Ken.?Burns|douga"}
    return "\n".join(value for key, value in HINTS.items()
                     if not request or re.search(patterns[key], str(request), re.I))


if __name__ == "__main__" and "--douga-worker" in sys.argv:
    _douga_worker(sys.argv[sys.argv.index("--douga-worker") + 1])
