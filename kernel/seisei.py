"""10/8 本人「画像・動画・3D モデリングなど、さまざまな生成をカーネルのアプリでできるように」。
頭脳（手元の LLM）が呼ぶ「作る」道具の中身。作った物は ~/Documents/カーネルの作品/ の新しいフォルダにだけ書く（上書きしない）。
- 3d: Blender をヘッドレスで（sanjigen.py。台本は import kit）。
- gazou: stable-diffusion.cpp の sd-cli（模型と引数は models/gazou/settei.json）。外へは送らない。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(os.environ.get("KERNEL_SAKUHIN_DIR", Path.home() / "Documents" / "カーネルの作品"))
MIRROR = Path(os.environ.get("KERNEL_MIRROR", Path.home() / "LocalAI_mirror"))
SD_CLI = MIRROR / "sdcpp" / "build" / "bin" / "sd-cli"
GAZOU_SETTEI = MIRROR / "models" / "gazou" / "settei.json"


def new_folder(name: str = "") -> Path:
    slug = re.sub(r"[^\wぁ-んァ-ヶ一-龠ー-]", "_", str(name or "作品"))[:30].strip("_") or "作品"
    out = ROOT / f"{time.strftime('%m%d_%H%M%S')}_{slug}"
    i = 2
    while out.exists():
        out = out.with_name(f"{out.name}-{i}")
        i += 1
    out.mkdir(parents=True)
    return out


def sanjigen(script: str, name: str = "") -> dict:
    import sanjigen as s
    out = new_folder(name or "3D")
    result = s.run(script, out, timeout=300)
    stats = result.get("stats") or []
    parts = [f"{x.get('name')}: 頂点{x.get('vertices')}・面{x.get('faces')}・UV{'あり' if x.get('uv') else 'なし'}"
             + (f"（島{x.get('uv_islands')}）" if x.get('uv') else "") for x in stats[:12] if isinstance(x, dict)]
    files = [str(f) for f in result.get("files") or []]
    if not result.get("ok"):
        return {"ok": False, "結果": "Blender の台本が失敗しました: " + str(result.get("error") or "")[:300]
                + "\n" + "\n".join(str(result.get("log") or "").splitlines()[-8:]), "画像": []}
    preview = result.get("preview")
    return {"ok": True, "結果": f"作りました（{out}）\nファイル: " + "、".join(Path(f).name for f in files)
            + ("\n" + "\n".join(parts) if parts else ""), "画像": [str(preview)] if preview else [], "場所": str(out)}


def gazou_settei() -> dict | None:
    try:
        data = json.loads(GAZOU_SETTEI.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("args"), list) else None
    except (OSError, ValueError):
        return None


def gazou(prompt: str, name: str = "", size: int = 512) -> dict:
    settei = gazou_settei()
    if not settei or not SD_CLI.exists():
        return {"ok": False, "結果": "画像の模型がまだ入っていません", "画像": []}
    out = new_folder(name or "画像")
    target = out / "gazou.png"
    base = GAZOU_SETTEI.parent
    args = [str(SD_CLI)] + [str(a).replace("{dir}", str(base)) for a in settei["args"]]
    args += ["-p", str(prompt)[:1000] + str(settei.get("prompt_suffix", "")), "-o", str(target), "-W", str(size), "-H", str(size),
             "-t", str(settei.get("threads", 6)), "-s", "-1"]
    if settei.get("negative"):
        args += ["-n", settei["negative"]]
    started = time.time()
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=int(settei.get("timeout", 900)),
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"ok": False, "結果": "画像づくりが時間切れになりました", "画像": []}
    if done.returncode != 0 or not target.exists():
        tail = "\n".join((done.stderr or done.stdout or "").splitlines()[-6:])
        return {"ok": False, "結果": "画像づくりに失敗しました: " + tail[:400], "画像": []}
    (out / "prompt.txt").write_text(str(prompt), encoding="utf-8")
    return {"ok": True, "結果": f"描きました（{time.time() - started:.0f}秒、{settei.get('名前', '画像の模型')}）: {target}",
            "画像": [str(target)], "場所": str(out)}


def hint(request: str) -> str:
    """頼みが生成の話の時だけ、使い方を添える（いつも入れると文脈を食う）。"""
    text = str(request or "")
    if re.search(r"(?i)3d|３Ｄ|ポリゴン|モデリング|blender|ブレンダー|立体|glb|fbx|obj|UV|ローポリ|リグ", text):
        doc = Path(__file__).with_name("sanjigen.md")
        try:
            body = doc.read_text(encoding="utf-8")[:2600]
        except OSError:
            body = ""
        return ("\n（カーネルより: 3D は道具 tsukuru（kind=3d、script に Blender の台本）で作る。作品は ~/Documents/カーネルの作品 に入り、"
                "下見の画像は画面に出る。失敗したら台本を直してもう一度）\n" + body)
    if re.search(r"画像|絵|イラスト|写真を作|描いて|描く|生成", text):
        return ("\n（カーネルより: 絵は道具 tsukuru（kind=gazou、prompt は英語の短い説明。例 'a red fox in snow, watercolor'）で描く。"
                "作品は ~/Documents/カーネルの作品 に入り、画面に出る）")
    return ""
