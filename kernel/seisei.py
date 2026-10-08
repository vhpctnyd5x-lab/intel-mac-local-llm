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
    # 10/8: 頭脳は絵を見られないので、中心と大きさ（m）を返して、重なり・大きさの間違いに自分で気づけるようにする
    parts = [f"{x.get('name')}: 中心{x.get('center')}・大きさ{x.get('size')}・頂点{x.get('vertices')}・面{x.get('faces')}"
             f"・UV{'あり' if x.get('uv') else 'なし'}" for x in stats[:16] if isinstance(x, dict)]
    warn = _overlap_warning(stats)
    files = [str(f) for f in result.get("files") or []]
    if not result.get("ok"):
        try:
            if not any(out.iterdir()):
                out.rmdir()   # 失敗して空のままの作品フォルダは残さない（空のフォルダだけ）
        except OSError:
            pass
        return {"ok": False, "結果": "Blender の台本が失敗しました: " + str(result.get("error") or "")[:1500]
                + "\n" + "\n".join(str(result.get("log") or "").splitlines()[-8:]), "画像": []}
    preview = result.get("preview")
    return {"ok": True, "結果": f"作りました（{out}）\nファイル: " + "、".join(Path(f).name for f in files)
            + ("\n" + "\n".join(parts) if parts else "") + warn, "画像": [str(preview)] if preview else [], "場所": str(out)}


def _overlap_warning(stats) -> str:
    """中心がほぼ同じ物や、ほかの物の中に隠れた物を知らせる（雪だるまで球が全部同じ場所に重なった）。"""
    notes = []
    rows = [x for x in stats if isinstance(x, dict) and x.get("center") and x.get("size")]
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            gap = sum((p - q) ** 2 for p, q in zip(a["center"], b["center"])) ** 0.5
            scale = max(max(a["size"]), max(b["size"]), 1e-6)
            if gap < 0.05 * scale:
                notes.append(f"{a['name']} と {b['name']} がほぼ同じ場所にあります")
        if rows and max(a["size"]) < 0.02 * max(max(r["size"]) for r in rows):
            notes.append(f"{a['name']} は他に比べてとても小さい（見えない）")
    return ("\n確かめ: " + "。".join(notes[:6]) + "。意図と違えば台本を直してもう一度") if notes else ""


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


def gazou3d(path: str, name: str = "") -> dict:
    """10/8: 画像1枚から 3D（TripoSR、手元の CPU。背景は Apple Vision で切り抜く）。細かさ256・テクスチャ1024px で約2分。"""
    import sanjigen_gazou
    out = new_folder(name or "画像から3D")
    return sanjigen_gazou.run(path, out / "3d", mc_resolution=256, chunk_size=4096, texture=True)


def hoka(kind: str, args: dict) -> dict:
    """10/8: 読み上げ（koe）・背景除去（haikei）・動画（douga）。中身は seisei_hoka.py（Mac に最初からある物と Blender だけ）。"""
    import seisei_hoka as h
    out = new_folder(args.get("name") or {"koe": "読み上げ", "haikei": "切り抜き", "douga": "動画"}[kind])
    if kind == "koe":
        return h.koe(args["prompt"], voice=args.get("voice") or "Kyoko", out_dir=out / "koe")
    if kind == "haikei":
        return h.haikei(args["path"], out / "haikei")
    paths = args.get("paths") or ([args["path"]] if args.get("path") else [])
    if paths and str(paths[0]).lower().endswith(".glb"):
        return h.douga("3d", out / "douga", glb_path=paths[0])
    if len(paths) == 1 and not args.get("audio"):
        # 10/8: 絵1枚は奥行き（Depth Anything V2 Small）で 2.5D の動画にする（寄るだけより立体的）
        try:
            import douga25d
            result = douga25d.make(paths[0], out / "douga25d", seconds=5)
            if result.get("ok"):
                return result
        except Exception:
            pass
    return h.douga("gazou", out / "douga", images=paths, audio_path=args.get("audio") or None)


def hint(request: str) -> str:
    """頼みが生成の話の時だけ、使い方を添える（いつも入れると文脈を食う）。"""
    text = str(request or "")
    if re.search(r"(?i)3d|３Ｄ|ポリゴン|モデリング|blender|ブレンダー|立体|glb|fbx|obj|UV|ローポリ|リグ", text):
        doc = Path(__file__).with_name("sanjigen.md")
        try:
            body = doc.read_text(encoding="utf-8")[:2600]
        except OSError:
            body = ""
        if re.search(r"分け|分割|リメッシュ|リトポ|UV展開図|焼き|ベイク|リグ|アニメ|動かし|glbを|取り込|仕上げ|テクスチャ", text):
            try:
                body += "\n" + Path(__file__).with_name("sanjigen_shiage.md").read_text(encoding="utf-8")[:2200]
            except OSError:
                pass
        return ("\n（カーネルより: 画像があれば tsukuru（kind=3d、path に画像）で画像から 3D を作る（約2分）。"
                "画像が無ければ tsukuru（kind=3d、script に Blender の台本）で作る。作品は ~/Documents/カーネルの作品 に入り、"
                "下見の画像は画面に出る。結果の中心・大きさを見て、意図と違えば台本を直してもう一度）\n" + body)
    try:
        import seisei_hoka
        extra = seisei_hoka.hint(text) if re.search(r"読み上げ|音声|ナレーション|背景|切り抜|動画|映像|一周", text) else ""
    except ImportError:
        extra = ""
    if extra:
        return ("\n（カーネルより: 次の作る道具が使えます。作品は ~/Documents/カーネルの作品 に入ります。"
                "引数は tsukuru の kind・prompt（読み上げの文）・path / paths（手元の画像や glb）・audio・voice に置き換える）\n" + extra)
    if re.search(r"画像|絵|イラスト|写真を作|描いて|描く|生成", text):
        return ("\n（カーネルより: 絵は道具 tsukuru（kind=gazou、prompt は英語の短い説明。例 'a red fox in snow, watercolor'）で描く。"
                "作品は ~/Documents/カーネルの作品 に入り、画面に出る）")
    return ""
