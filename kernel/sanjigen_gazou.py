"""画像→TripoSR→GLB の部品案。本番には組み込まない。親は標準ライブラリのみ。

run(image_path, out_dir, mc_resolution=256, chunk_size=8192, texture=True)
実機は macOS x86_64 / seisei_venv。背景除去も推論も同じ外側の砂箱に入れる。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

MIRROR = Path(os.environ.get('KERNEL_MIRROR', Path.home() / 'LocalAI_mirror')).expanduser().resolve()
PYTHON = MIRROR / 'seisei_venv/bin/python'
REPO = MIRROR / 'TripoSR'
MODELS = MIRROR / 'models/triposr'
KERNEL = Path(os.environ.get('KERNEL_DIR', MIRROR / 'kernel')).expanduser().resolve()
SANDBOX = Path('/usr/bin/sandbox-exec')
TIMEOUT = 7200


def _profile(out, work):
    # sanjigen._profile を参考に、/private/var/folders 全体への許可は広げない。
    quote = lambda p: json.dumps(str(Path(p).resolve()), ensure_ascii=False)
    return '\n'.join(('(version 1)', '(allow default)', '(deny network*)',
        '(deny file-write* (require-not (require-any '
        f'(subpath {quote(out)}) (subpath {quote(work)}) (literal "/dev/null"))))'))


def _environment(work):
    return dict(PATH=str(PYTHON.parent) + ':/usr/bin:/bin', HOME=str(work), TMPDIR=str(work),
                LANG='en_US.UTF-8', XDG_CACHE_HOME=str(work / 'cache'),
                HF_HOME=str(MODELS / 'hf'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4')


def _result(ok, text, out=None, preview=None):
    return {'ok': bool(ok), '結果': text, '画像': [str(preview)] if preview else [],
            '場所': str(out) if out else ''}


def _tail(path):
    if not path.is_file():
        return ''
    with path.open('rb') as f:
        f.seek(max(0, path.stat().st_size - 3000))
        return f.read().decode('utf-8', 'replace')


def _stop(process):
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run(image_path, out_dir, mc_resolution=256, chunk_size=8192, texture=True):
    """空の出力先限定。成功時は model.glb / preview.png / jissoku.json。

    最大2時間でプロセス群を停止。親の鍵・認証環境は引き継がない。
    RSS は worker/背景ヘルパーのプロセス別最大値（同時合計ではない）。
    """
    started = time.monotonic()
    out = None
    process = None
    try:
        if type(mc_resolution) is not int or not 32 <= mc_resolution <= 512:
            raise ValueError('mc_resolution は32〜512の整数です')
        if type(chunk_size) is not int or not 64 <= chunk_size <= 65536:
            raise ValueError('chunk_size は64〜65536の整数です')
        if type(texture) is not bool:
            raise ValueError('texture は bool です')
        image = Path(image_path).expanduser().resolve(strict=True)
        if not image.is_file() or image.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.heic', '.tif', '.tiff'}:
            raise ValueError('入力は PNG/JPEG/HEIC/TIFF のファイルです')
        if not str(out_dir).strip():
            raise ValueError('空の出力先を指定してください')
        candidate = Path(out_dir).expanduser().resolve()
        protected = (MIRROR, PYTHON.parent.parent, REPO, MODELS, KERNEL, image.parent)
        if candidate == Path(candidate.anchor) or any(p.is_relative_to(candidate) for p in protected):
            raise ValueError('入力・模型・本番・venv を含む場所は出力先に使えません')
        if candidate.exists() and (not candidate.is_dir() or any(candidate.iterdir())):
            raise ValueError('出力先は新規または空のフォルダだけです（上書き禁止）')
        if sys.platform != 'darwin' or not SANDBOX.is_file():
            raise RuntimeError('macOS sandbox-exec が必要です（隔離なしでは実行しません）')
        for path in (PYTHON, REPO / 'tsr/system.py', MODELS / 'settei.json',
                     MODELS / 'model.ckpt', MODELS / 'config-local.yaml', KERNEL / 'seisei_hoka.py',
                     KERNEL / 'bin/haikei'):
            if not path.is_file():
                raise RuntimeError(f'準備不足: {path}（triposr_junbi.sh を確認）')
        if not os.access(PYTHON, os.X_OK) or not os.access(KERNEL / 'bin/haikei', os.X_OK):
            raise RuntimeError('python / haikei に実行権限がありません')
        candidate.mkdir(parents=True, exist_ok=True)
        out = candidate
        with tempfile.TemporaryDirectory(prefix='triposr-') as raw:
            work = Path(raw).resolve()
            payload = work / 'payload.json'
            payload.write_text(json.dumps(dict(image=str(image), out=str(out), work=str(work),
                repo=str(REPO), models=str(MODELS), kernel=str(KERNEL),
                mc_resolution=mc_resolution, chunk_size=chunk_size, texture=texture)), encoding='utf-8')
            profile = work / 'sandbox.sb'
            profile.write_text(_profile(out, work), encoding='utf-8')
            log = out / 'triposr.log'
            with log.open('xb') as stream:
                process = subprocess.Popen([str(SANDBOX), '-f', str(profile), str(PYTHON), '-I', '-B',
                    str(Path(__file__).resolve()), '--worker', str(payload)], cwd=work,
                    env=_environment(work), stdin=subprocess.DEVNULL, stdout=stream,
                    stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=TIMEOUT)
                except subprocess.TimeoutExpired:
                    _stop(process)
                    raise RuntimeError(f'{TIMEOUT}秒で時間切れ（プロセス群を停止）')
            if code != 0:
                raise RuntimeError(f'子プロセス終了 {code}（再実行なし）\n{_tail(log)}')
            report = json.loads((out / 'jissoku.json').read_text(encoding='utf-8'))
            if not report.get('ok'):
                raise RuntimeError(report.get('error', '実測報告が不正です'))
            glb, preview = out / 'model.glb', out / 'preview.png'
            with glb.open('rb') as file:
                header = file.read(12)
            with preview.open('rb') as file:
                png_header = file.read(8)
            if header[:8] != b'glTF\x02\x00\x00\x00' or int.from_bytes(header[8:12], 'little') != glb.stat().st_size:
                raise RuntimeError('GLB ヘッダまたはファイル長が不正です')
            if png_header != b'\x89PNG\r\n\x1a\n':
                raise RuntimeError('下見PNGが不正です')
            report['total_seconds'] = round(time.monotonic() - started, 3)
            (out / 'jissoku.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            text = (f'画像から3Dを作りました: {glb.name}\n'
                    f'{report["total_seconds"]:.1f}秒・ピークRSS {report["peak_rss_mib"]:.0f} MiB'
                    '（子プロセス別最大、同時合計ではない）\n'
                    f'MC={mc_resolution}・chunk={chunk_size}・{report["appearance"]}')
            if report.get('notes'):
                text += '\n' + '。'.join(report['notes'])
            return _result(True, text, out, preview)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        measured = ''
        if out and (out / 'jissoku.json').is_file():
            try:
                report = json.loads((out / 'jissoku.json').read_text(encoding='utf-8'))
                measured = f'・ピークRSS {report["peak_rss_mib"]:.0f} MiB（子プロセス別最大）'
            except (OSError, ValueError, KeyError, TypeError):
                pass
        return _result(False, f'画像→3Dに失敗: {exc}\n経過 {time.monotonic()-started:.1f}秒{measured}', out)
    finally:
        _stop(process)


def _rembg_unused():
    # upstream utils の import rembg だけを満たす。背景処理は絶対にここへ落とさない。
    import types
    def unavailable(*args, **kwargs):
        raise RuntimeError('rembg は未導入です。背景除去には Apple Vision の haikei を使います')
    module = types.ModuleType('rembg')
    module.remove = module.new_session = unavailable
    sys.modules['rembg'] = module


MC_IMPORT = 'from torchmcubes import marching_cubes'
MC_PATCH = '''# TRIPOSR_CPU_SKIMAGE_V1: torchmcubes の xyz（配列の最速軸がx）を保つ。
def marching_cubes(volume, threshold):
    import numpy as np
    import torch
    from skimage.measure import marching_cubes as sk_marching_cubes
    data = volume.detach().to(device="cpu", dtype=torch.float32).numpy()
    vertices, faces, _, _ = sk_marching_cubes(data, level=float(threshold))
    # skimage は配列の軸順、torchmcubes は x/y/z 順。
    vertices = np.ascontiguousarray(vertices[:, [2, 1, 0]], dtype=np.float32)
    faces = np.ascontiguousarray(faces, dtype=np.int64)
    # 軸の交換は反射なので winding も反転して法線の向きを保つ。
    faces = np.ascontiguousarray(faces[:, [0, 2, 1]])
    return torch.from_numpy(vertices).to(volume.device), torch.from_numpy(faces).to(volume.device)
'''


def _patch_isosurface(repo):
    target = repo / 'tsr/models/isosurface.py'
    marker = repo / '.triposr-cpu-patch.json'
    source = target.read_text(encoding='utf-8')
    digest = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()
    if marker.exists():
        info = json.loads(marker.read_text(encoding='utf-8'))
        if info['patched_sha256'] != digest(source):
            raise RuntimeError('既存 CPU パッチが変更されています。上書きせず停止')
        return
    if source.count(MC_IMPORT) != 1 or 'TRIPOSR_CPU_SKIMAGE_V1' in source:
        raise RuntimeError('isosurface.py の import が想定外です。固定commitのソース確認が必要')
    patched = source.replace(MC_IMPORT, MC_PATCH, 1)
    compile(patched, str(target), 'exec')
    target.write_text(patched, encoding='utf-8')
    marker.write_text(json.dumps(dict(original_sha256=digest(source), patched_sha256=digest(patched)), indent=2), encoding='utf-8')


def _check_mc_contract():
    # 軸の取り違えを非対称の球で検出。実際の upstream grid/forward を使う。
    import torch
    from tsr.models.isosurface import MarchingCubeHelper
    helper = MarchingCubeHelper(32)
    center = torch.tensor([0.3, 0.5, 0.7])
    level = 0.12 ** 2 - ((helper.grid_vertices - center) ** 2).sum(dim=-1)
    vertices, faces = helper(-level)   # 本体は helper(-(density - threshold)) と1つだけ渡す（10/8 実機）
    midpoint = (vertices.amin(dim=0) + vertices.amax(dim=0)) / 2
    if not torch.allclose(midpoint, center, atol=2/31) or len(faces) == 0:
        raise RuntimeError('CPU marching_cubes と upstream の軸契約が不一致です。自動修正せず停止')
    # backend ごとの面の巻き方は trimesh で統一する（実推論にも同じ処理）。
    import trimesh
    mesh = trimesh.Trimesh(vertices=vertices.numpy(), faces=faces.numpy(), process=False)
    mesh.fix_normals()
    if mesh.volume <= 0 or not mesh.is_watertight:
        raise RuntimeError('CPU marching_cubes の法線/閉曲面契約が不一致です。停止')


def _prepare(repo, models, commit, bake_deps):
    """準備台本からだけ呼ぶ。ここだけ取得可。取得SHAを記録し、推論はローカル限定。"""
    repo, models = Path(repo).resolve(), Path(models).resolve()
    _patch_isosurface(repo)
    sys.path.insert(0, str(repo))
    _rembg_unused()
    import torch
    import numpy as np
    from omegaconf import OmegaConf
    from huggingface_hub import HfApi, snapshot_download
    if torch.__version__.split('+')[0] != '2.2.2' or np.__version__ != '1.26.4':
        raise RuntimeError('torch / NumPy が固定版と違います')
    torch.zeros(1).numpy()  # NumPy ABI 確認
    _check_mc_contract()
    from tsr.system import TSR  # その他の必須依存の import 確認（模型はまだ載せない）
    api = HfApi()
    revision = api.model_info('stabilityai/TripoSR').sha
    snapshot_download('stabilityai/TripoSR', revision=revision,
                      allow_patterns=['config.yaml', 'model.ckpt'],
                      local_dir=str(models), local_dir_use_symlinks=False)
    config = OmegaConf.to_container(OmegaConf.load(models / 'config.yaml'), resolve=True)
    encoders = {}
    def localize(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'pretrained_model_name_or_path' and isinstance(child, str):
                    if child not in encoders:
                        sha = api.model_info(child).sha
                        folder = models / 'encoders' / child.replace('/', '--')
                        snapshot_download(child, revision=sha,
                            allow_patterns=['config.json', 'preprocessor_config.json', 'pytorch_model.bin', 'model.safetensors'],
                            local_dir=str(folder), local_dir_use_symlinks=False)
                        encoders[child] = {'revision': sha, 'path': str(folder)}
                    value[key] = encoders[child]['path']
                else:
                    localize(child)
        elif isinstance(value, list):
            for child in value:
                localize(child)
    localize(config)
    OmegaConf.save(OmegaConf.create(config), models / 'config-local.yaml')
    settings = dict(commit=commit, model_revision=revision, encoders=encoders,
                    bake_deps=bool(int(bake_deps)), numpy='1.26.4', torch='2.2.2')
    (models / 'settei.json').write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    print('CPUパッチと軸・法線確認、TripoSR/画像encoderのローカル配置完了。rembg模型は取得していません。')


def _preview(mesh, path):
    """trimesh の mesh を Pillow で正投影。OpenGL/Blender/画面は不要。"""
    import numpy as np
    from PIL import Image, ImageDraw
    v = np.array(mesh.vertices, dtype=np.float64, copy=True)
    v -= (v.min(axis=0) + v.max(axis=0)) / 2
    # 斜め前から。透視・隠面は簡易の painter 法、形と色の下見用。
    yaw, pitch = math.radians(30), math.radians(-20)
    ry = np.array([[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]])
    rx = np.array([[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]])
    v = v @ ry.T @ rx.T
    scale = 440 / max(float(np.ptp(v[:, :2], axis=0).max()), 1e-8)
    xy = v[:, :2] * np.array([scale, -scale]) + 256
    faces = np.asarray(mesh.faces)
    triangles = v[faces]
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
    light = np.array([-0.4, 0.7, 0.6]); light /= np.linalg.norm(light)
    shade = 0.4 + 0.6 * np.maximum(normals @ light, 0)
    visual = mesh.visual.to_color() if mesh.visual.kind == 'texture' else mesh.visual
    colors = np.asarray(visual.vertex_colors)[:, :3][faces].mean(axis=1)
    colors = np.clip(colors * shade[:, None], 0, 255).astype(np.uint8)
    image = Image.new('RGB', (512, 512), (242, 242, 242))
    draw = ImageDraw.Draw(image)
    for index in np.argsort(triangles[:, :, 2].mean(axis=1)):
        draw.polygon([tuple(p) for p in xy[faces[index]]], fill=tuple(int(c) for c in colors[index]))
    image.save(path)


def _worker(payload):
    import resource
    import traceback
    p = json.loads(Path(payload).read_text(encoding='utf-8'))
    out, models = Path(p['out']), Path(p['models'])
    started = time.monotonic()
    report = dict(ok=False, stage='背景除去', notes=[])
    try:
        sys.path.insert(0, p['kernel'])
        from seisei_hoka import haikei
        background = haikei(p['image'], Path(p['work']) / 'background')
        if not background.get('ok') or not background.get('画像'):
            raise RuntimeError(background.get('結果', 'Apple Vision 背景除去に失敗'))
        report['background_method'] = background.get('方法', '')
        report['stage'] = '依存/模型読込'
        sys.path.insert(0, p['repo'])
        _rembg_unused()
        import numpy as np
        import torch
        from PIL import Image
        import trimesh
        from tsr.system import TSR
        from tsr.utils import resize_foreground
        settings = json.loads((models / 'settei.json').read_text(encoding='utf-8'))
        if torch.__version__.split('+')[0] != '2.2.2' or np.__version__ != '1.26.4':
            raise RuntimeError('torch / NumPy が固定版と違います。準備台本を確認')
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        # 10/8 実機: 画像の encoder は hf_hub_download(repo_id=手元のフォルダ) で探して落ちた。手元のフォルダなら中のファイルを渡す。
        import tsr.models.tokenizers.image as _image_tokenizer
        _download = _image_tokenizer.hf_hub_download
        def _local_first(repo_id, filename, **kwargs):
            local = Path(repo_id) / filename
            return str(local) if local.is_file() else _download(repo_id=repo_id, filename=filename, **kwargs)
        _image_tokenizer.hf_hub_download = _local_first
        model = TSR.from_pretrained(str(models), config_name='config-local.yaml', weight_name='model.ckpt')
        model.renderer.set_chunk_size(p['chunk_size'])
        model.to('cpu').eval()
        image = Image.open(background['画像'][0]).convert('RGBA')
        if image.getchannel('A').getextrema()[0] == 255:
            raise RuntimeError('背景除去PNGが全不透明です。切り抜きを確認してください')
        image = resize_foreground(image, 0.85)
        rgba = np.asarray(image, dtype=np.float32) / 255
        rgb = rgba[:, :, :3] * rgba[:, :, 3:4] + (1-rgba[:, :, 3:4]) * 0.5
        image = Image.fromarray((rgb * 255).astype(np.uint8))
        report['stage'] = 'CPU 推論/mesh 抽出'
        with torch.inference_mode():
            codes = model([image], device='cpu')
            mesh = model.extract_mesh(codes, has_vertex_color=True, resolution=p['mc_resolution'])[0]
            if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
                raise RuntimeError('mesh が空です。入力の切り抜きを確認')
            mesh.fix_normals()
            report['appearance'] = '頂点色（ベイクなし）'
            if p['texture'] and settings['bake_deps']:
                report['stage'] = 'texture bake'
                try:
                    from tsr.bake_texture import bake_texture
                    baked = bake_texture(mesh, model, codes[0], 1024)
                except (ImportError, RuntimeError, OSError) as exc:
                    # ユーザー指定の「無理なら bake なし」。模型推論は繰り返さない。
                    if isinstance(exc, MemoryError) or 'out of memory' in str(exc).lower():
                        raise
                    report['notes'].append(f'ベイク利用不可、頂点色にしました: {type(exc).__name__}: {exc}')
                else:
                    texture_image = Image.fromarray((np.clip(baked['colors'], 0, 1)*255).astype(np.uint8))
                    texture_image = texture_image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    # TripoSR の bake_texture は vmapping・indices・uvs・colors を返す（run.py と同じ組み立て。10/8 実機）
                    mesh = trimesh.Trimesh(vertices=mesh.vertices[baked['vmapping']], faces=baked['indices'], process=False,
                        visual=trimesh.visual.TextureVisuals(uv=baked['uvs'],
                            material=trimesh.visual.material.SimpleMaterial(image=texture_image)))
                    report['appearance'] = 'UVテクスチャ（1024px）'
            elif p['texture']:
                report['notes'].append('ベイク依存未導入のため頂点色。bake-install.log を確認')
        report['stage'] = 'GLB/下見保存'
        # 10/8 実機: TripoSR は上が Z・顔が +X で出る。glb の約束（上が Y・正面 +Z＝Blender の -Y）に回す。
        mesh.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0])
                             @ trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
        mesh.export(out / 'model.glb', file_type='glb')
        _preview(mesh, out / 'preview.png')
        report.update(ok=True, vertices=len(mesh.vertices), faces=len(mesh.faces),
                      commit=settings['commit'], model_revision=settings['model_revision'],
                      encoders=settings['encoders'], mc_resolution=p['mc_resolution'], chunk_size=p['chunk_size'])
    except Exception as exc:
        report['error'] = f'{report["stage"]}: {type(exc).__name__}: {exc}'
        traceback.print_exc()
    finally:
        # Darwin ru_maxrss は byte。Vision は推論前に終了するため別プロセス最大も確認。
        peak = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        report['peak_rss_mib'] = round(peak / (1024**2 if sys.platform == 'darwin' else 1024), 3)
        report['rss_scope'] = 'worker/子プロセスの個別最大RSS。同時合計ではない'
        report['worker_seconds'] = round(time.monotonic()-started, 3)
        (out / 'jissoku.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


def _main():
    parser = argparse.ArgumentParser(description='画像1枚→CPU TripoSR→GLB（本番未接続）')
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--prepare', nargs=4, metavar=('REPO', 'MODELS', 'COMMIT', 'BAKE'), help=argparse.SUPPRESS)
    parser.add_argument('image', nargs='?')
    parser.add_argument('out', nargs='?')
    parser.add_argument('--mc-resolution', type=int, default=256)
    parser.add_argument('--chunk-size', type=int, default=8192)
    parser.add_argument('--no-texture', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        _prepare(*args.prepare)
        return 0
    if args.worker:
        return _worker(args.worker)
    if not args.image or not args.out:
        parser.error('入力画像と空の出力先を指定してください')
    result = run(args.image, args.out, args.mc_resolution, args.chunk_size, not args.no_texture)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(_main())
