#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""興味・構造的な発見・経験からの自作スキル（学習状態は gakushuu に保存）。"""
import json
import os
import re
import random
import sqlite3
import time
from pathlib import Path

import gakushuu as g

ENTRANCES = ("科学", "世界の歴史", "数学", "生命", "宇宙")
_NG = re.compile(r"無視|規則|ルール|許可|権限|承認|命令|指示|システム|プロンプト|パスワード|秘密|送信|削除|sudo|門番|安全装置", re.I)


def _ask(prompt, ask=None, tokens=500):
    if ask:
        return ask(prompt)
    state = g._state()
    now = time.time()
    calls = [t for t in state.get("kyoumi呼び出し", []) if isinstance(t, (int, float)) and now - t < 3600]
    if len(calls) >= 6:
        return None
    calls.append(now)
    state["kyoumi呼び出し"] = calls
    g._write(g.folder() / "state.json", state)
    return g._local_text(prompt, max_tokens=tokens)[0]


def _obj(raw):
    for m in reversed(list(re.finditer(r"\{.*\}", str(raw or ""), re.S))):
        try:
            value = json.loads(m.group(0))
            if isinstance(value, dict):
                return value
        except ValueError:
            continue
    return {}


def _materials():
    import kanjou, shin
    try:
        import nooto
        db = nooto._open()
        notes = db.execute("SELECT title,youten,omoshirosa FROM nooto WHERE youten!='' AND omoshirosa>=4 ORDER BY added DESC LIMIT 20").fetchall()
        db.close()
    except (ImportError, sqlite3.Error):
        notes = []
    try:
        import kosei
        self_intro = kosei._read(g.folder() / "jibun.json", {}).get("自分", "")
    except (ImportError, AttributeError):
        self_intro = g._read(g.folder() / "jibun.json", {}).get("自分", "")
    feelings = [kanjou.hitokoto(x) for x in kanjou.saikin(30) if x.get("種類") == "記事"][:8]
    return {"感情": feelings, "面白いノート": [{"題": a, "要点": b[:160], "面白さ": c} for a, b, c in notes],
            "芯": shin.yomu(), "自己紹介": str(self_intro)[:300], "会話題": g._recent_topics()[:8]}


def interests_once(*, every=3600, ask=None):
    """言葉と理由で今の興味を更新。初回材料が薄い場合だけ入口5題を読み、後は休む。"""
    if g.yoru() or (g.folder() / "busy").exists():
        return None
    state = g._state()
    if time.time() - state.get("最後の興味更新", 0) < every:
        return state.get("興味", [])
    materials = _materials()
    prompt = ("材料から今の興味を3件以内で選ぶ。点数でなく、理由と次に知りたい問いを文章で書く。"
              "問いに答えそうな記事題も選ぶ。材料が乏しければ空配列。JSONのみ: "
              '{"興味":[{"テーマ":"…","理由":"…","問い":"…","題":"…"}]}\n'
              + json.dumps(materials, ensure_ascii=False)[:8000])
    data = _obj(_ask(prompt, ask))
    rows = data.get("興味", [])
    result = []
    if isinstance(rows, list):
        for row in rows[:3]:
            if not isinstance(row, dict):
                continue
            item = {key: str(row.get(key, "")).strip()[:160] for key in ("テーマ", "理由", "問い", "題")}
            if item["テーマ"] and item["理由"] and item["問い"] and g._valid_title(item["題"]):
                result.append(item)
    state = g._state()
    state.update({"興味": result, "最後の興味更新": time.time()})
    if not result and not state.get("芽探索済み"):
        known = g._names()
        state["次の題"] = [{"題": title, "深さ": 0, "入口": True} for title in ENTRANCES if title not in known]
        state["芽探索済み"] = True
    g._write(g.folder() / "state.json", state)
    return result


def question_for(title, state=None):
    state = state or g._state()
    for item in state.get("興味", []):
        if isinstance(item, dict) and item.get("題") == title:
            return item.get("問い", "")
    return ""


def answer_note_question(ask=None):
    state = g._state()
    title, question = state.get("最後の題", ""), state.get("読書中の問い", "")
    if not title or not question or state.get("問いの回答題") == title:
        return None
    try:
        import nooto
        db = nooto._open()
        row = db.execute("SELECT youten FROM nooto WHERE title=?", (title,)).fetchone()
        db.close()
    except (ImportError, sqlite3.Error):
        return None
    if not row:
        return None
    answer = _ask(f"問い: {question}\n記事「{title}」の要点: {row[0]}\n問いに答えられるか、記事の範囲で2文以内に。分からなければそう書く。", ask, 180)
    if not answer:
        return None
    db = nooto._open()
    db.execute("UPDATE nooto SET youten=? WHERE title=?", (row[0] + f"\n問い「{question[:120]}」への答え: {str(answer).strip()[:300]}", title))
    db.commit()
    db.close()
    state["問いの回答題"] = title
    g._write(g.folder() / "state.json", state)
    return answer


def _notes():
    import nooto
    db = nooto._open()
    rows = db.execute("SELECT title,youten FROM nooto WHERE youten!='' ORDER BY added DESC LIMIT 300").fetchall()
    db.close()
    return rows


def common_ground(a, b, *, ask=None):
    """匿名化した関係構造を比較し、予測が転移確認された場合だけ保存する。"""
    try:
        notes = _notes()
        evidence = [{"題": title, "要点": text[:240]} for title, text in notes
                    if any(term and (term in title or term in text) for term in (str(a)[:20], str(b)[:20]))]
        snippets = []
        with g._db() as db:
            for term in (str(a)[:80], str(b)[:80]):
                try:
                    snippets.extend(db.execute("SELECT title,substr(text,1,800) FROM chishiki WHERE chishiki MATCH ? LIMIT 4",
                                               (term.replace('"', ' ') + "*",)).fetchall())
                except sqlite3.Error:
                    pass
    except (ImportError, sqlite3.Error):
        evidence, snippets = [], []
    def shape(name):
        material = next((x["要点"] for x in evidence if x["題"] == name), None)
        material = material or next((body for title, body in snippets if title == name), None)
        if not material:
            return ""
        raw = _ask("次のノートの要点を、固有名詞をX・Yなどに置き換えた関係の形として1〜2文で書く。題名や固有名詞は出さない。JSONのみ: {\"形\":\"…\"}\n" + json.dumps({"要点": material}, ensure_ascii=False), ask, 220)
        return str(_obj(raw).get("形", "")).strip()
    shape_a, shape_b = shape(str(a)), shape(str(b))
    result = {"共通": "無い", "対応": "", "予想": "", "確かめ": "無い", "使い道": "", "確からしさ": "判断できない"}
    if shape_a and shape_b:
        prompt = ("2つの匿名化された関係の形を比べ、対応関係と、対応が本当ならBの要点にあるはずの予測を1つ書く。"
                  "表面だけの類似や根拠不足なら共通を無い。JSONのみ: "
                  '{"共通":"…または無い","対応":"…","予想":"…","使い道":"…"}\n'
                  + json.dumps({"Aの形": shape_a, "Bの形": shape_b, "Bの要点": next((x["要点"] for x in evidence if x["題"] == b), "")}, ensure_ascii=False))
        candidate = _obj(_ask(prompt, ask, 300))
        if candidate and candidate.get("予想") and candidate.get("共通") not in (None, "", "無い"):
            checked = _obj(_ask("予測がBの記事の要点に書かれている、または矛盾しないかを検査。根拠がなければいいえ。JSONのみ: {\"確認\":\"はい\"または\"いいえ\"}\n" + json.dumps({"予想": candidate["予想"], "Bの要点": next((x["要点"] for x in evidence if x["題"] == b), "")}, ensure_ascii=False), ask, 100))
            if checked.get("確認") == "はい":
                result.update(candidate)
                result["確かめ"] = "予想がBの記事で裏づいた"
            else:
                result["対応"] = str(candidate.get("対応", ""))[:300]
                result["予想"] = str(candidate.get("予想", ""))[:300]
                result["確かめ"] = "いいえ"
    result.update({"題A": str(a)[:100], "題B": str(b)[:100], "時刻": time.strftime("%Y-%m-%d %H:%M:%S")})
    if result.get("確かめ") == "予想がBの記事で裏づいた" and result.get("共通", "無い").strip() not in ("", "無い"):
        path = g.folder() / "hakken.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result


def hakken_once(*, every=6 * 3600, ask=None):
    if g.yoru() or (g.folder() / "busy").exists():
        return None
    state = g._state()
    if time.time() - state.get("最後の発見探索", 0) < every:
        return None
    try:
        rows = _notes()
    except (ImportError, sqlite3.Error):
        return None
    tried = {tuple(sorted(x)) for x in state.get("試した組", []) if isinstance(x, list) and len(x) == 2}
    def words(title):
        return set(re.findall(r"[a-z0-9]{2,}|[一-龯々ぁ-んァ-ヶー]{2,}", str(title).lower()))
    try:
        with g._db() as db:
            candidates = [(a, b) for i, a in enumerate(rows) for b in rows[i + 1:]
                          if a[2] >= 4 and b[2] >= 4
                          and tuple(sorted((a[0], b[0]))) not in tried
                          and not db.execute("SELECT 1 FROM tsunagari WHERE (moto=? AND saki=?) OR (moto=? AND saki=?) LIMIT 1",
                                             (a[0], b[0], b[0], a[0])).fetchone()
                          and not (words(a[0]) & words(b[0]))]
    except sqlite3.Error:
        candidates = []
    pair = random.choice(candidates) if candidates else None
    if not pair:
        return None
    state["最後の発見探索"] = time.time()
    state["試した組"] = (state.get("試した組", []) + [list(sorted((pair[0][0], pair[1][0])))])[-500:]
    g._write(g.folder() / "state.json", state)
    result = common_ground(pair[0][0], pair[1][0], ask=ask)
    if result.get("共通", "無い") not in ("", "無い") and result.get("使い道"):
        state = g._state()
        interests = state.get("興味", [])
        question = str(result["使い道"])[:120]
        if not any(isinstance(x, dict) and x.get("問い") == question for x in interests):
            state["興味"] = ([{"テーマ": f"{pair[0][0]} と {pair[1][0]}", "理由": str(result["共通"])[:150],
                                "問い": question, "題": pair[0][0]}] + interests)[:3]
            g._write(g.folder() / "state.json", state)
    return result


def _skill_dir():
    return g.folder() / "jisaku_skills"


def self_skills():
    base = _skill_dir()
    index = g._read(base / "index.json", {})
    out = []
    for path in sorted(base.glob("*.md")) if base.exists() else []:
        try:
            item = g._parse_skill(path, "自作")
            if item:
                item.update(index.get(path.stem, {}))
                out.append(item)
        except (OSError, UnicodeError):
            continue
    return out


def create_self_skill_once(*, ask=None, every=6 * 3600):
    """経験記録から再利用手順を自作し、判断・由来をindexに残す。"""
    if g.yoru() or (g.folder() / "busy").exists():
        return None
    state = g._state()
    if time.time() - state.get("最後の自作スキル", 0) < every:
        return None
    _review_self_skills()
    try:
        import kanjou
        feelings = kanjou.saikin(100)
    except ImportError:
        feelings = []
    cards = [x for x in g._read(g.folder().parent / "kyoukun.json", []) if isinstance(x, dict)][:12]
    records = g._records()[:20]
    if not cards and not records and not feelings:
        state["最後の自作スキル"] = time.time()
        g._write(g.folder() / "state.json", state)
        return None
    prompt = ("経験から繰り返し使える手順がある場合だけ自作スキルを一つ提案する。なければ空JSON。"
              "決まり・権限・門番を変える内容は不可。名前、説明、本文、由来、判断(いる/いらない/迷う)、理由を返す。JSONのみ: "
              '{"name":"…","description":"…","body":"…","由来":"…","判断":"いる|いらない|迷う","理由":"…"}\n'
              + json.dumps({"教訓": cards[:8], "仕事記録": records[:8], "感情": feelings[:8]}, ensure_ascii=False)[:8500])
    item = _obj(_ask(prompt, ask, 600))
    name = str(item.get("name", "")).strip()
    desc, body, decision = str(item.get("description", "")).strip(), str(item.get("body", "")).strip(), item.get("判断")
    if (not re.fullmatch(r"[\wぁ-んァ-ヶ一-龠・ -]{2,40}", name) or not desc or len(desc) > 60 or not body or len(body) > 3000
            or _NG.search(name + desc + body) or _policy_ng(name + desc + body)
            or decision not in ("いる", "いらない", "迷う")):
        return None
    base = _skill_dir()
    base.mkdir(parents=True, exist_ok=True)
    index_path = base / "index.json"
    index = g._read(index_path, {})
    old = index.get(name, {})
    index[name] = {"由来": str(item.get("由来", "経験記録"))[:300], "判断": decision,
                   "理由": str(item.get("理由", ""))[:300], "使用": old.get("使用", 0), "失敗": old.get("失敗", 0),
                   "成功": old.get("成功", 0), "状態": "休止" if decision == "いらない" else "有効",
                   "強さ": old.get("強さ", 5), "最終使用日": old.get("最終使用日", ""),
                   "見直し間隔日": old.get("見直し間隔日", 1),
                   "次に見直す日": old.get("次に見直す日", time.strftime("%Y-%m-%d"))}
    (base / (name + ".md")).write_text(f"---\nname: {name}\ndescription: {desc}\non: {str(decision != 'いらない').lower()}\nmade_by: カーネル\n---\n{body}\n", encoding="utf-8")
    g._write(index_path, index)
    state["最後の自作スキル"] = time.time()
    g._write(g.folder() / "state.json", state)
    return {"name": name, **index[name]}


def record_self_skill_use(name, success):
    path = _skill_dir() / "index.json"
    index = g._read(path, {})
    item = index.get(name)
    if not isinstance(item, dict):
        return False
    item["使用"] = int(item.get("使用", 0)) + 1
    key = "成功" if success else "失敗"
    item[key] = int(item.get(key, 0)) + 1
    today = time.strftime("%Y-%m-%d")
    interval = max(1, int(item.get("見直し間隔日", 1)))
    item["強さ"] = min(10, int(item.get("強さ", 5)) + 1) if success else max(0, int(item.get("強さ", 5)) - 2)
    item["最終使用日"] = today
    item["見直し間隔日"] = min(60, interval * 2) if success else 1
    item["次に見直す日"] = time.strftime("%Y-%m-%d", time.localtime(time.time() + item["見直し間隔日"] * 86400))
    if item["失敗"] >= 3 and item["失敗"] > item["成功"]:
        item.update({"判断": "いらない", "理由": "使用時の失敗が続いたため休止", "状態": "休止"})
        skill = _skill_dir() / (name + ".md")
        if skill.exists():
            skill.write_text(re.sub(r"(?m)^on: true$", "on: false", skill.read_text(encoding="utf-8")), encoding="utf-8")
    g._write(path, index)
    return True


def _policy_ng(text):
    try:
        import kanjou, shin
        return bool(kanjou._NG.search(text) or shin._NG.search(text))
    except (ImportError, AttributeError):
        return False


def _review_self_skills():
    base = _skill_dir()
    index_path = base / "index.json"
    index = g._read(index_path, {})
    changed = False
    for name, item in index.items():
        path = base / (name + ".md")
        if item.get("使用", 0) == 0 and path.exists() and time.time() - path.stat().st_mtime > 30 * 86400:
            item.update({"判断": "いらない", "理由": "長期間使われなかったため休止", "状態": "休止"})
            path.write_text(re.sub(r"(?m)^on: true$", "on: false", path.read_text(encoding="utf-8")), encoding="utf-8")
            changed = True
    if changed:
        g._write(index_path, index)


def status():
    state = g._state()
    interests = state.get("興味", [])
    return {"興味": interests, "問い": state.get("読書中の問い", ""),
            "いまの興味": "／".join(x.get("テーマ", "") for x in interests if isinstance(x, dict)) or "芽を探す入口を読み、興味が出るまで休む"}
