"""Depth Anything V2 Small をローカルキャッシュから CPU 推論する。"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


VENV_PYTHON = Path.home() / "LocalAI_mirror" / "okuyuki_venv" / "bin" / "python"   # 10/8: TripoSR の環境は transformers 4.35 で Depth Anything V2 を読めない
MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def depth(image_path, out_png):
    """画像から相対深度を16bit PNGにする。モデル未取得時は取得せず失敗する。"""
    source = Path(image_path).expanduser().resolve(strict=True)
    destination = Path(out_png).expanduser().resolve()
    if not source.is_file():
        raise ValueError("入力画像がファイルではありません")
    if source.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("入力画像は100MiB以内にしてください")
    if source == destination:
        raise ValueError("奥行き画像で入力画像を上書きできません")
    if not VENV_PYTHON.is_file():
        raise RuntimeError(f"seisei_venv の Python がありません: {VENV_PYTHON}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    # モデルの出力を入力画像寸法へ戻し、画像ごとに16bitの相対深度へ正規化。
    code = r'''import sys
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
src, dst, model_id = sys.argv[1:]
torch.set_num_threads(2)
processor = AutoImageProcessor.from_pretrained(model_id, local_files_only=True)
model = AutoModelForDepthEstimation.from_pretrained(model_id, local_files_only=True).to("cpu").eval()
image = Image.open(src).convert("RGB")
inputs = processor(images=image, return_tensors="pt")
with torch.inference_mode():
    prediction = model(**inputs).predicted_depth
    prediction = torch.nn.functional.interpolate(
        prediction.unsqueeze(1), size=(image.height, image.width),
        mode="bicubic", align_corners=False).squeeze()
depth = prediction.float().cpu().numpy()
lo, hi = np.nanpercentile(depth, (1, 99))
if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
    raise RuntimeError("有効な深度を推定できませんでした")
scaled = np.clip((depth - lo) / (hi - lo), 0, 1)
Image.fromarray(np.round(scaled * 65535).astype(np.uint16), mode="I;16").save(dst)
'''
    env = {
        "PATH": "/usr/bin:/bin", "HOME": tempfile.gettempdir(),
        "TMPDIR": tempfile.gettempdir(), "HF_HUB_OFFLINE": "1",
        "HF_HOME": str(Path.home() / ".cache" / "huggingface"),
        "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "OMP_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false",
    }
    try:
        completed = subprocess.run(
            [str(VENV_PYTHON), "-c", code, str(source), str(destination), MODEL],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=900, env=env, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("深度推定が900秒で時間切れになりました") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[-1800:]
        raise RuntimeError("深度推定に失敗しました（モデルは事前配置が必要です）: " + detail)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("深度推定は終了しましたが16bit PNGがありません")
    return str(destination)


def soften_edges(image_path, out_png):
    """画像外周だけをわずかにぼかし、メッシュ端の引き伸ばしを和らげる。"""
    source = Path(image_path).expanduser().resolve(strict=True)
    destination = Path(out_png).expanduser().resolve()
    code = r'''import sys
from PIL import Image, ImageFilter, ImageChops
src, dst = sys.argv[1:]
im = Image.open(src).convert("RGB")
w, h = im.size
radius = max(2, round(min(w, h) * 0.012))
blur = im.filter(ImageFilter.GaussianBlur(radius))
mask = Image.new("L", (w, h), 255)
px = mask.load()
band = max(2, round(min(w, h) * 0.045))
for y in range(h):
    for x in range(w):
        d = min(x, y, w-1-x, h-1-y)
        t = max(0.0, min(1.0, d / band))
        t = t*t*(3-2*t)
        px[x, y] = round(t*255)
im = Image.composite(im, blur, mask)
im.save(dst, format="PNG")
'''
    env = {"PATH": "/usr/bin:/bin", "HOME": tempfile.gettempdir(),
           "TMPDIR": tempfile.gettempdir(), "HF_HUB_DISABLE_TELEMETRY": "1"}
    completed = subprocess.run([str(VENV_PYTHON), "-c", code, str(source), str(destination)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=120, env=env, check=False)
    if completed.returncode or not destination.is_file():
        detail = (completed.stderr or completed.stdout).strip()[-1200:]
        raise RuntimeError("外周ぼかしに失敗しました: " + detail)
    return str(destination)
