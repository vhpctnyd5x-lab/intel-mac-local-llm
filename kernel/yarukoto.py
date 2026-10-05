"""興味が枯れた時に、保存済みの材料から小さな学習仕事を1つ選ぶ。"""
import json
import os
import time
from pathlib import Path


def _folder():
    default = Path.home() / "Library" / "Application Support" / "kernel-ai" / "gakushuu"
    return Path(os.environ.get("KERNEL_GAKUSHUU_DIR", default))


def choose(folder=None, now=None, use_conversations=True):
    base = Path(folder) if folder else _folder()
    now = time.time() if now is None else now
    log = base / "yarukoto.jsonl"
    try:
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()[-100:]]
    except (OSError, ValueError):
        rows = []
    if rows and now - float(rows[-1].get("時刻", 0) or 0) < 3600:
        return None
    state = {}
    try:
        state = json.loads((base / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    interests = [x for x in state.get("興味", []) if isinstance(x, dict) and x.get("テーマ")]
    if interests:
        seed = interests[len(rows) % len(interests)]
        kind = "問いに答える" if seed.get("問い") else "調べてまとめる"
        return {"種類": kind, "題": seed.get("題") or seed["テーマ"], "問い": seed.get("問い", ""),
                "テーマ": seed["テーマ"], "状態": "選定"}
    # 最近の会話で続いている仕事を候補にする。秘密・場所は記録しない。
    try:
        if not use_conversations:
            raise ImportError
        import chats
        for conv in chats.listing()[:12]:
            history = chats.load(conv["id"]).get("やりとり", [])
            turns = [str(x.get("文", "")) for x in history if x.get("役") == "user"]
            if turns:
                topic = _safe(turns[-1])
                if len(topic) >= 4 and not topic.startswith("/"):
                    return {"種類": "調べてまとめる", "題": topic[:100],
                            "問い": "次に進めるために必要な事実を調べて要点をまとめる", "状態": "選定"}
    except (ImportError, OSError, ValueError, KeyError):
        pass
    cards = []
    for name in ("kyoukun.json", "wasureta.jsonl"):
        try:
            p = base / name
            if name.endswith(".json"):
                cards.extend(json.loads(p.read_text(encoding="utf-8")))
            else:
                cards.extend(json.loads(x) for x in p.read_text(encoding="utf-8").splitlines())
        except (OSError, ValueError, TypeError):
            pass
    failed = next((x for x in cards if isinstance(x, dict) and ("失敗" in str(x) or x.get("種類") == "失敗")), None)
    if failed:
        return {"種類": "失敗の練習", "題": _safe(failed.get("題") or failed.get("知らせ") or "失敗した仕事")[:100],
                "問い": "一時フォルダで再現し、別の方法を試す", "状態": "選定"}
    try:
        discoveries = [json.loads(x) for x in (base / "hakken.jsonl").read_text(encoding="utf-8").splitlines()[-30:]]
    except (OSError, ValueError):
        discoveries = []
    if discoveries:
        row = discoveries[len(rows) % len(discoveries)]
        return {"種類": "自作スキルを作って練習", "題": str(row.get("題") or row.get("テーマ") or "発見を確かめる")[:100],
                "問い": str(row.get("問い", ""))[:300], "状態": "選定"}
    return None


def run_once(folder=None, now=None, ask=None):
    explicit_folder = folder is not None
    base = Path(folder) if explicit_folder else _folder()
    task = choose(base, now, use_conversations=not explicit_folder)
    if not task:
        return None
    # 手元の保存資料だけを使い、実行記録と次の提案を残す。外部送信はしない。
    result, ok = _execute(task, base, ask=ask)
    task.update({"時刻": time.time() if now is None else now, "結果": result,
                 "提案": "学習画面で確認して、必要なら本人が採用する"})
    base.mkdir(parents=True, exist_ok=True)
    with (base / "yarukoto.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(task, ensure_ascii=False) + "\n")
    _growth("やること", ok, base)
    return task


def _safe(value):
    text = " ".join(str(value or "").split())
    text = __import__("re").sub(r"(?:/Users/|~/|/private/)\S+", "[場所]", text)
    return text[:140]


def _materials(base, task, limit=4):
    """題・問いの語で知識の箱を引く（trigram・上限付き。35万記事でも全件は読まない）。"""
    import re
    import sqlite3
    words = re.findall(r"[A-Za-z0-9]{3,}|[一-龯々ァ-ヶー]{3,}|[ぁ-ん一-龯々ァ-ヶー]{2,}", " ".join(
        str(task.get(k, "")) for k in ("題", "テーマ", "問い")))[:6]
    found = []
    try:
        db = sqlite3.connect(f"file:{base / 'chishiki.sqlite3'}?mode=ro", uri=True, timeout=5)
        try:
            for word in words:
                if len(word) < 3:
                    continue
                q = '"' + word.replace('"', '""') + '"'
                for title, text in db.execute("SELECT title,substr(text,1,700) FROM chishiki_trigram WHERE chishiki_trigram MATCH ? LIMIT 2", (q,)):
                    if title not in {t for t, _ in found}:
                        found.append((title, text))
                if len(found) >= limit:
                    break
        finally:
            db.close()
    except sqlite3.Error:
        pass
    return found[:limit]


_PROMPTS = {
    "調べてまとめる": "次のテーマについて、資料をもとに要点をまとめてください。資料に無いことは「分からない」と書く。",
    "問いに答える": "次の問いに、資料をもとに答えてください。資料に無いことは「分からない」と書く。",
    "失敗の練習": "次の失敗について、考えられる原因を2つと、次に試す別のやり方を3つ書いてください。実行はしない。",
}


def _think(task, base, ask=None):
    """手元の LLM で実際に考えて書く（10/5 本人: 事前学習だけで、何をすればいいか分かっていない）。"""
    kind = task.get("種類")
    if kind == "自作スキルを作って練習":
        try:
            import kyoumi
            made = kyoumi.create_self_skill_once(every=0, ask=ask)
            return (f"自作スキルを作りました: {made}" if made else ""), bool(made)
        except Exception:
            return "", False
    lead = _PROMPTS.get(kind)
    if not lead:
        return "", False
    material = _materials(base, task)
    docs = "\n\n".join(f"【{t}】{x}" for t, x in material) or "（資料なし）"
    prompt = (f"{lead}\nテーマ: {task.get('題', '')}\n問い: {task.get('問い', '')}\n\n資料:\n{docs}\n\n"
              "日本語で、見出しなしの箇条書き5行以内。最後の行は「次に調べること: …」。")
    try:
        import kyoumi
        answer = kyoumi._ask(prompt, ask=ask, tokens=600)
    except Exception:
        answer = None
    answer = str(answer or "").strip()
    if not answer:
        return "", False
    import re
    notes = base / "yarukoto_notes"
    notes.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\wぁ-んァ-ヶ一-龠-]", "_", _safe(task.get("題")))[:50] or "学習"
    sources = "、".join(t for t, _ in material) or "なし"
    (notes / (time.strftime("%m%d_") + slug + ".md")).write_text(
        f"# {kind}: {_safe(task.get('題'))}\n\n{answer[:3000]}\n\n資料: {sources}\n", encoding="utf-8")
    return f"{kind}をしました（資料 {len(material)} 件）: {answer.splitlines()[0][:120]}", True


def _execute(task, base, ask=None):
    """まず手元の LLM で実際に考える。呼べない時（上限・停止中）だけ、保存済みの資料のノート化か提案の登録。"""
    thought, ok = _think(task, base, ask=ask)
    if ok:
        return thought, True
    title = _safe(task.get("題"))
    body = ""
    try:
        import nooto
        db = nooto._open(base / "chishiki.sqlite3")
        try:
            row = db.execute("SELECT youten FROM nooto WHERE title=?", (title,)).fetchone()
            if not row and title:
                row = db.execute("SELECT youten FROM nooto WHERE title LIKE ? ORDER BY omoshirosa DESC LIMIT 1",
                                 ("%" + title[:30] + "%",)).fetchone()
            body = row[0] if row else ""
        finally:
            db.close()
    except (ImportError, OSError, ValueError):
        body = ""
    if body:
        notes = base / "yarukoto_notes"
        notes.mkdir(parents=True, exist_ok=True)
        slug = __import__("re").sub(r"[^\wぁ-んァ-ヶ一-龠-]", "_", title)[:50] or "学習"
        (notes / (slug + ".md")).write_text("# " + title + "\n\n" + str(body)[:3000] + "\n", encoding="utf-8")
        return "保存済みの学習ノートを読み直し、要点をやることノートにまとめました", True
    try:
        import sqlite3
        card = {"目的": title, "適用条件": task.get("問い", ""), "手順": [
            "保存済みの関連資料を探す", "根拠を分けて要点をまとめる", "学習画面で提案を確認する"],
            "確かめ方": "根拠と要点が対応していること", "根拠": []}
        db = sqlite3.connect(base / "chishiki.sqlite3", timeout=5)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS teian (id INTEGER PRIMARY KEY, 題 TEXT NOT NULL, 中身 TEXT NOT NULL, 根拠の記事 TEXT NOT NULL DEFAULT '', 用件の識別 TEXT NOT NULL, 用件の題 TEXT NOT NULL DEFAULT '', 状態 TEXT NOT NULL DEFAULT '提案中', 不要の理由 TEXT NOT NULL DEFAULT '', 作った日時 TEXT NOT NULL, 選んだ日時 TEXT NOT NULL DEFAULT '')")
            exists = db.execute("SELECT 1 FROM teian WHERE 用件の識別=?", ("yarukoto:" + title,)).fetchone()
            if not exists:
                db.execute("INSERT INTO teian(題,中身,根拠の記事,用件の識別,用件の題,状態,作った日時) VALUES(?,?,?,?,?,'提案中',?)",
                           (title[:100], json.dumps(card, ensure_ascii=False), "", "yarukoto:" + title, title[:100],
                            time.strftime("%Y-%m-%dT%H:%M:%S%z")))
            db.commit()
        finally:
            db.close()
        return "提案を学習画面に登録しました（本人への送信はしていません）", True
    except (ImportError, OSError, ValueError, sqlite3.Error):
        return "保存資料が見つからず、学習画面に残す候補だけ選びました", False


def _growth(kind, ok, base):
    path = base / "seichou.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"仕事": {}, "週": {}}
    data.setdefault("仕事", {}).setdefault(kind, {"成功": 0, "失敗": 0})["成功" if ok else "失敗"] += 1
    week = time.strftime("%G-W%V")
    data.setdefault("週", {}).setdefault(week, {"成功": 0, "失敗": 0})["成功" if ok else "失敗"] += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
