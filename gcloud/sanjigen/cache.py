"""固定commit/revisionの環境・重みをGCSに保存。推論ではHFへ接続しない。"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
from progress import update

BASE = pathlib.Path('/opt/sanjigen')
CODE21 = '82920d643c0dc2f7bfd7255f45f62d386edfe60c'
CODE2 = 'f8db63096c8282cb27354314d896feba5ba6ff8a'
HF21 = '0b94677654c57bb9a6b6845cd7b704ccf551d327'
HFMV = '3a761b539b29fe4ff64714813aa9560fd66f5de0'
HFDINO = '611a9d42f2335e0f921f1e313ad3c1b7178d206d'
HFTEXT = '527cf2ecce7c04021975938f8b0e44e35d2b1ed9'
PY = str(BASE / 'venv/bin/python')


def run(*args, **kwargs):
    print("command:", " ".join(map(str, args)), flush=True)
    subprocess.run(args, check=True, **kwargs)


def bundle(label, paths, prepare, build):
    update("cache-" + label)
    # 環境キャッシュはDLVMの具体名・コード・torch・ビルド台本の内容で分離。
    spec = '\n'.join([os.environ['IMAGE'], CODE21, CODE2, 'py310-torch251-cu124-sm89-v1',
                      hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()])
    key = hashlib.sha256(spec.encode()).hexdigest()[:20]
    bucket = os.environ['PREFIX'].split('/sanjigen/')[0]
    prefix = f'{bucket}/cache/sanjigen/{key}/{label}'
    archive = BASE / f'{label}.tar'
    digest = BASE / f'{label}.sha256'
    # 既知オブジェクトを読むだけ。object list権限は不要。
    found = subprocess.run(['gcloud', 'storage', 'cp', prefix + '.sha256', str(digest)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if found:
        update("restore-" + label)
        run('gcloud', 'storage', 'cp', prefix + '.tar', str(archive))
        expected = digest.read_text().split()[0]
        with archive.open('rb') as f:
            actual = hashlib.file_digest(f, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hash_stream(f)
        if actual != expected:
            raise RuntimeError(f'破損キャッシュ: {prefix}。準備からやり直してください')
        run('tar', '-xf', str(archive), '-C', str(BASE))
        update('restore-' + label, 'completed')
    else:
        if not prepare:
            raise RuntimeError(f'キャッシュ未準備: {prefix}。--prepare-onlyを先に実行')
        build()
        update("save-" + label)
        run('tar', '-cf', str(archive), '-C', str(BASE), *paths)
        with archive.open('rb') as f:
            digest.write_text(hash_stream(f) + '\n')
        # SHAオブジェクトが完成印。中断された途中のarchiveを使わない。
        run('gcloud', 'storage', 'cp', str(archive), prefix + '.tar')
        run('gcloud', 'storage', 'cp', str(digest), prefix + '.sha256')
        update('save-' + label, 'completed')
    archive.unlink()
    digest.unlink()
    update("cache-" + label, "completed")


def hash_stream(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
        h.update(block)
    return h.hexdigest()


def environment():
    update("source")
    for directory, repo, revision in [('src21', 'Hunyuan3D-2.1', CODE21), ('src2', 'Hunyuan3D-2', CODE2)]:
        archive = BASE / (directory + '.tgz')
        urllib.request.urlretrieve(f'https://api.github.com/repos/Tencent-Hunyuan/{repo}/tarball/{revision}', archive)
        (BASE / directory).mkdir(exist_ok=True)
        run('tar', '-xzf', str(archive), '--strip-components=1', '-C', str(BASE / directory))
        archive.unlink()
    update("source", "completed")
    update("venv")
    run('python3.10', '-m', 'venv', str(BASE / 'venv'))
    run(PY, '-m', 'pip', 'install', 'pip==25.0.1', 'setuptools==75.8.2', 'wheel==0.45.1')
    update('venv', 'completed')
    update('torch')
    run(PY, '-m', 'pip', 'install', 'torch==2.5.1', 'torchvision==0.20.1', 'torchaudio==2.5.1',
        '--index-url', 'https://download.pytorch.org/whl/cu124')
    update('torch', 'completed')
    update('dependencies')
    # UI・訓練・deepspeedは不要。公式pinは保持し、未固定推論依存だけ明示。
    lines = (BASE / 'src21/requirements.txt').read_text().splitlines()
    skip = {'gradio', 'fastapi', 'uvicorn', 'configargparse', 'tb_nightly', 'deepspeed', 'pythreejs', 'timm', 'torchdiffeq', 'bpy'}  # bpy: PyPIにpy3.10 Linux版なし（GLBはtrimesh、下見はMacのBlender）
    keep = [x for x in lines if x.strip() and not x.startswith(('#', '--')) and x.split('==')[0] not in skip]
    keep += ['timm==1.0.15', 'torchdiffeq==0.2.5', 'pythreejs==2.4.2']
    (BASE / 'requirements-inference.txt').write_text('\n'.join(keep) + '\n')
    run(PY, '-m', 'pip', 'install', '-r', str(BASE / 'requirements-inference.txt'))
    # basicsr 1.4.2の古いtorchvision importを公式2.1の修正と同じ新APIへ。
    old = BASE / 'venv/lib/python3.10/site-packages/basicsr/data/degradations.py'
    old.write_text(old.read_text().replace('torchvision.transforms.functional_tensor', 'torchvision.transforms.functional'))
    update('dependencies', 'completed')
    paint = BASE / 'src21/hy3dpaint'
    update('custom-rasterizer')
    run(PY, '-m', 'pip', 'install', '--no-build-isolation', '-e', str(paint / 'custom_rasterizer'))
    update('custom-rasterizer', 'completed')
    update('mesh-painter')
    env = dict(os.environ, PATH=str(BASE / 'venv/bin') + ':' + os.environ['PATH'])
    run('bash', 'compile_mesh_painter.sh', cwd=paint / 'DifferentiableRenderer', env=env)
    update('mesh-painter', 'completed')
    update('environment-check')
    # pip check は ninja の wheel 名札だけで失敗する（10/10）。記録に残し、実際の読み込みは下で確かめる。
    subprocess.run([PY, '-m', 'pip', 'check'])
    frozen = subprocess.check_output([PY, '-m', 'pip', 'freeze'], text=True)
    (BASE / 'requirements.lock.txt').write_text(frozen)
    run(PY, '-c', 'import torch,pymeshlab,rembg,trimesh; import custom_rasterizer; assert torch.cuda.is_available()')
    # 重みを含まない環境完成印と、第三者ライセンスもソースごと保存。
    (BASE / 'env-manifest.json').write_text(json.dumps(dict(image=os.environ['IMAGE'], code21=CODE21,
        code2=CODE2, cuda=os.environ.get('CUDA_HOME'), architecture='sm89', built_at=time.time()), indent=2))
    update('environment-check', 'completed')


def snapshot(repo, revision, patterns):
    script = 'from huggingface_hub import snapshot_download; import json,sys; snapshot_download(repo_id=sys.argv[1],revision=sys.argv[2],allow_patterns=json.loads(sys.argv[3]))'
    run(PY, '-c', script, repo, revision, json.dumps(patterns))
    # paint/DINO/Textの公式APIはrevision=mainを読む。固定SHAのaliasを明示し、
    # offlineモードでもその実体だけを使わせる（HFにmainを照会しない）。
    refs = pathlib.Path(os.environ['HF_HOME']) / 'hub' / ('models--' + repo.replace('/', '--')) / 'refs'
    refs.mkdir(parents=True, exist_ok=True)
    (refs / 'main').write_text(revision)


def weights(label):
    if label == 'shape21':
        snapshot('tencent/Hunyuan3D-2.1', HF21, ['hunyuan3d-dit-v2-1/*', 'hunyuan3d-vae-v2-1/*', 'LICENSE', 'README.md'])
    elif label == 'mv':
        snapshot('tencent/Hunyuan3D-2mv', HFMV, ['hunyuan3d-dit-v2-mv/config.yaml', 'hunyuan3d-dit-v2-mv/model.fp16.safetensors', 'LICENSE', 'README.md'])
    elif label == 'paint21':
        snapshot('tencent/Hunyuan3D-2.1', HF21, ['hunyuan3d-paintpbr-v2-1/*', 'LICENSE'])
        snapshot('facebook/dinov2-giant', HFDINO, ['config.json', 'preprocessor_config.json', 'model.safetensors', 'LICENSE'])
        ckpt = BASE / 'src21/hy3dpaint/ckpt'
        ckpt.mkdir(exist_ok=True)
        urllib.request.urlretrieve('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth', ckpt / 'RealESRGAN_x4plus.pth')
    elif label == 'text':
        snapshot('Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers-Distilled', HFTEXT, ['*'])
    elif label == 'rembg':
        run(PY, '-c', 'from rembg import new_session; new_session("u2net")')


def main():
    c = json.loads(pathlib.Path(sys.argv[1]).read_text())
    start = time.monotonic()
    bundle('env', ['venv', 'src21', 'src2', 'requirements.lock.txt', 'env-manifest.json'],
           c['prepare'] in ('env', 'all'), environment)
    if c['prepare'] == 'env':
        selected = []
    else:
        selected = ['rembg', 'mv' if c['mode'] == 'mv' else 'shape21']
        if c['mode'] == 'text': selected.append('text')
        if c['texture'] == 'on': selected.append('paint21')
    for label in selected:
        # 各模型のHF cacheディレクトリは分ける。同じrepoの形/paintの上書きを避ける。
        store = BASE / 'stores' / label
        store.mkdir(parents=True, exist_ok=True)
        os.environ['HF_HOME'] = str(store)
        paths = ['stores/' + label]
        if label == 'rembg': paths.append('rembg')
        if label == 'paint21': paths.append('src21/hy3dpaint/ckpt')
        bundle(label, paths, bool(c['prepare']), lambda label=label: weights(label))
    (BASE / 'output/cache.json').write_text(json.dumps(dict(image=os.environ['IMAGE'], code21=CODE21,
        code2=CODE2, hf21=HF21, hfmv=HFMV, hfdino=HFDINO, hftext=HFTEXT,
        labels=selected, seconds=time.monotonic()-start), indent=2))
    if c['prepare']:
        update('prepare', 'prepared', c['prepare'])


if __name__ == '__main__':
    main()
