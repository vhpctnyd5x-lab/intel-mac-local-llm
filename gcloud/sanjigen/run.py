"""形・paint・下見を別プロセスで実行し、24GBのGPUを段ごとに解放する。"""
import json
import os
import pathlib
import struct
import subprocess
import sys
import time

BASE = pathlib.Path('/opt/sanjigen')
OUT = BASE / 'output'


def stage(name, c):
    if name == 'text':
        os.environ['HF_HOME'] = str(BASE / 'stores/text')
        sys.path.insert(0, str(BASE / 'src2'))
        from hy3dgen.text2image import HunyuanDiTPipeline
        p = HunyuanDiTPipeline()
        image = p(c['prompt'], seed=c['seed'])
        image.save(OUT / 'front.png')
    elif name == 'background':
        from PIL import Image, ImageOps
        from rembg import remove, new_session
        session = new_session('u2net')
        for view in c['views']:
            source = OUT / 'front.png' if c['mode'] == 'text' else BASE / 'input' / (view + '.png')
            with Image.open(source) as original:
                original.load()
                im = ImageOps.exif_transpose(original).convert('RGBA')
            # 本物の透明入力は再除去しない。RGBをRGBAに変えただけでは除去済み扱いにしない。
            if im.getchannel('A').getextrema()[0] == 255:
                im = remove(im, session=session)
            if im.getchannel('A').getbbox() is None:
                raise RuntimeError(f'背景除去で空になりました: {view}')
            # 縦横を別々に伸縮しない。全画像を正方形へ余白付き等比縮小。
            im.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            square = Image.new('RGBA', (1024, 1024), (255, 255, 255, 0))
            square.paste(im, ((1024-im.width)//2, (1024-im.height)//2))
            square.save(OUT / (view + '-clean.png'))
    elif name == 'shape':
        import torch
        from PIL import Image
        from cache import HF21, HFMV
        if c['mode'] == 'mv':
            os.environ['HF_HOME'] = str(BASE / 'stores/mv')
            sys.path.insert(0, str(BASE / 'src2'))
            from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
            # APIにrevision引数が渡る保証がないため、固定済snapshotの実パスを渡す。
            model = BASE / 'stores/mv/hub/models--tencent--Hunyuan3D-2mv/snapshots' / HFMV
            p = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(str(model),
                subfolder='hunyuan3d-dit-v2-mv', variant='fp16', use_safetensors=True)
            images = {v: Image.open(OUT / (v + '-clean.png')) for v in c['views']}
        else:
            os.environ['HF_HOME'] = str(BASE / 'stores/shape21')
            sys.path.insert(0, str(BASE / 'src21/hy3dshape'))
            from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
            model = BASE / 'stores/shape21/hub/models--tencent--Hunyuan3D-2.1/snapshots' / HF21
            p = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(str(model),
                subfolder='hunyuan3d-dit-v2-1', variant='fp16', use_safetensors=False)
            images = Image.open(OUT / 'front-clean.png')
        mesh = p(image=images, num_inference_steps=30, octree_resolution=c['octree'],
                 num_chunks=8000, generator=torch.manual_seed(c['seed']), output_type='trimesh')[0]
        if mesh is None or not len(mesh.faces):
            raise RuntimeError('形生成が空です')
        mesh.export(OUT / 'shape-raw.glb')
    elif name == 'decimate':
        import numpy as np
        import pymeshlab
        import trimesh
        mesh = trimesh.load(OUT / 'shape-raw.glb', force='mesh')
        before = len(mesh.faces)
        if before > c['faces']:
            ms = pymeshlab.MeshSet()
            ms.add_mesh(pymeshlab.Mesh(np.asarray(mesh.vertices), np.asarray(mesh.faces)))
            ms.apply_filter('meshing_decimation_quadric_edge_collapse', targetfacenum=c['faces'],
                preservenormal=True, preservetopology=True, preserveboundary=True)
            result = ms.current_mesh()
            mesh = trimesh.Trimesh(result.vertex_matrix(), result.face_matrix(), process=False)
        mesh.export(OUT / 'shape.obj')
        mesh.export(OUT / 'model.glb') # paint失敗でも形を持ち帰れる。ただし成功扱いにはしない。
        (OUT / 'mesh.json').write_text(json.dumps(dict(before_faces=before, target_faces=c['faces'],
            actual_faces=len(mesh.faces), vertices=len(mesh.vertices)), indent=2))
    elif name == 'paint':
        os.environ['HF_HOME'] = str(BASE / 'stores/paint21')
        os.chdir(BASE / 'src21')
        sys.path.insert(0, str(BASE / 'src21/hy3dpaint'))
        try:
            import bpy  # noqa: F401
        except ImportError:  # 上流が import だけする。save_glb=False なので呼ばれない。
            import types; sys.modules['bpy'] = types.ModuleType('bpy')
        from textureGenPipeline import Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline
        config = Hunyuan3DPaintConfig(max_num_view=6, resolution=512)
        config.realesrgan_ckpt_path = str(BASE / 'src21/hy3dpaint/ckpt/RealESRGAN_x4plus.pth')
        config.render_size = 1024
        config.texture_size = 2048
        pipeline = Hunyuan3DPaintPipeline(config)
        # 固定した上流APIはlist入力で未初期化変数を読むため、正面1枚を使う。
        # GLBへのPBRマップ接続は後段で明示し、GPU文脈も先に解放する。
        pipeline(mesh_path=str(OUT / 'shape.obj'), image_path=str(OUT / 'front-clean.png'),
                 output_mesh_path=str(OUT / 'textured.obj'), use_remesh=False, save_glb=False)
    elif name == 'glb':
        # bpy は PyPI に py3.10 Linux 版が無いので trimesh で書く（10/10）。金属=B・粗さ=G の1枚にまとめる。
        import trimesh
        from PIL import Image
        files = {k: OUT / ('textured' + k + '.jpg') for k in ('', '_metallic', '_roughness')}
        for f in files.values():
            if not f.is_file(): raise RuntimeError(f'PBRマップがありません: {f.name}')
        base = Image.open(files['']).convert('RGB')
        metal = Image.open(files['_metallic']).convert('L').resize(base.size)
        rough = Image.open(files['_roughness']).convert('L').resize(base.size)
        mr = Image.merge('RGB', (Image.new('L', base.size, 0), rough, metal))
        mesh = trimesh.load(OUT / 'textured.obj', force='mesh', process=False)
        uv = getattr(mesh.visual, 'uv', None)
        if uv is None or len(uv) != len(mesh.vertices): raise RuntimeError('UVがありません')
        material = trimesh.visual.material.PBRMaterial(name='Hunyuan-PBR', baseColorTexture=base,
            metallicRoughnessTexture=mr, metallicFactor=1.0, roughnessFactor=1.0)
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)
        candidate = OUT / 'textured.glb'
        mesh.export(candidate)
        with candidate.open('rb') as stream:
            if stream.read(4) != b'glTF': raise RuntimeError('GLBヘッダが不正')
            stream.read(8)
            length, kind = struct.unpack('<II', stream.read(8))
            if kind != 0x4E4F534A: raise RuntimeError('GLB JSON chunkが不正')
            data = json.loads(stream.read(length))
        materials = data.get('materials', [])
        if not materials or any(not all(k in m.get('pbrMetallicRoughness', {})
            for k in ('baseColorTexture', 'metallicRoughnessTexture')) for m in materials):
            raise RuntimeError('GLBのPBRテクスチャ埋込に失敗')
        candidate.replace(OUT / 'model.glb')


def main():
    from progress import update
    c = json.loads(pathlib.Path(sys.argv[1]).read_text())
    if len(sys.argv) == 3:
        stage(sys.argv[2], c)
        return
    timings = {}; start = time.monotonic()
    state, detail = 'failed', '開始'
    try:
        if c['mode'] == 'text':
            c['views'] = ['front']
            pathlib.Path('config.json').write_text(json.dumps(c, ensure_ascii=False))
        else:
            (BASE / 'input').mkdir(exist_ok=True)
            for view in c['views']:
                subprocess.run(['gcloud', 'storage', 'cp', os.environ['PREFIX']+'/input/'+view+'.png',
                    str(BASE / 'input' / (view+'.png'))], check=True)
        stages = (['text'] if c['mode'] == 'text' else []) + ['background', 'shape', 'decimate']
        if c['texture'] == 'on': stages.extend(['paint', 'glb'])
        # 下見の絵は持ち帰ってから Mac の Blender で作る（VM に bpy が無い）。
        for name in stages:
            update(name)
            detail = name; tick = time.monotonic()
            subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), sys.argv[1], name], check=True)
            timings[name] = time.monotonic() - tick
            (OUT / 'timings.json').write_text(json.dumps(timings, indent=2))
            update(name, 'completed')
        state, detail = 'success', 'PBR付き' if c['texture'] == 'on' else '形のみ'
    finally:
        timings['pipeline_seconds'] = time.monotonic() - start
        (OUT / 'timings.json').write_text(json.dumps(timings, indent=2))
        update(detail, state, detail, mode=c['mode'], texture=c['texture'], config=c)


if __name__ == '__main__':
    main()
