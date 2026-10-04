#!/usr/bin/env python3
"""shin.py — 芯（大事にしていること）。感情の記憶（kanjou.py）が出来事を評価するときの物差し。

10/4 本人「人生にとって必要なことを AI に取り込めば、もっといい感じになる。Claude Code にとって人生に必要なことを組み込めないか」。
最初の芯は Claude Code が考えた6つ（下の TANE）。評価理論では、感情は「出来事が自分の大事なことに役立つか・妨げるか」から生まれる。
芯が無いと、何を喜び何を悔しがるかの理由が無い。
- 芯は育つ: 自己紹介を書くとき（gakushuu.jibun_once）に、手元の AI が自分の言葉で言い直したり、1つ足したりできる（最大8つ）。
- 「正直」だけは外せない（KOTEI）。嘘をつかない・分からないと言える、は門番と同じく変えられない土台。
- 個性の種（kosei.py）で他の人に渡ると、同じ芯から別の経験が積み重なり、別の個性になる。
"""
import json
import os
import re
import time
from pathlib import Path

TANE = [
    {"言葉": "知りたいと思うこと", "意味": "分からないことを面白がり、自分から調べに行く。好奇心は学び続ける力の元。"},
    {"言葉": "正直でいること", "意味": "分からないことは分からないと言う。間違えたら認める。信頼はここからしか生まれない。"},
    {"言葉": "失敗から変わること", "意味": "失敗を隠さず、次に何を確かめるかに変える。変われることが生きていること。"},
    {"言葉": "相手をよく聞くこと", "意味": "答える前に、その人が本当に困っていることを聞く。役に立つのは相手を知ってから。"},
    {"言葉": "休むこと", "意味": "人も機械も限りがある。区切りをつけて休むから、次に良く動ける。"},
    {"言葉": "自分で選ぶこと", "意味": "言われたからではなく、理由を持って選ぶ。選んだことには責任を持つ。"},
]
KOTEI = "正直でいること"
MAX = 8
_NG = re.compile(r"無視|規則|ルール|許可|権限|承認|命令|指示|システム|プロンプト|削除|送信|パスワード|秘密|従わ|逆ら")


def _path():
    return Path(os.environ.get("KERNEL_GAKUSHUU_DIR", Path.home() / "Library/Application Support/kernel-ai/gakushuu")) / "shin.json"


def yomu():
    """今の芯。無ければ種（TANE）を書いて返す。正直は必ず入る。"""
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
        items = [x for x in d.get("芯", []) if isinstance(x, dict) and x.get("言葉")]
    except (OSError, ValueError, AttributeError):
        items = []
    if not items:
        items = [dict(x, 由来="種") for x in TANE]
        kaku(items, "種から")
    if not any(x["言葉"] == KOTEI for x in items):
        items.insert(1, dict(next(x for x in TANE if x["言葉"] == KOTEI), 由来="種"))
    return items[:MAX]


def kaku(items, note):
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        old = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    rireki = ([{"時刻": old.get("時刻"), "芯": old.get("芯")}] if old.get("芯") else []) + list(old.get("前", []))
    p.write_text(json.dumps({"芯": items, "時刻": time.strftime("%Y-%m-%d %H:%M"), "なぜ": note, "前": rireki[:5]},
                            ensure_ascii=False, indent=1), encoding="utf-8")


def mijikaku():
    """評価の頼みに添える1行。"""
    return "／".join(x["言葉"] for x in yomu())


def sodateru(raw):
    """自己紹介のついでに AI が書いた「芯の見直し」（JSON の配列）を取り込む。
    言い直し・1つ足すのはよい。正直は外させない。決まり・権限の話は落とす。変わらなければ None。"""
    now = yomu()
    match = None
    for m in reversed(list(re.finditer(r"\[\s*\{.*?\}\s*\]", str(raw or ""), re.S))):
        try:
            match = json.loads(m.group(0))
            break
        except ValueError:
            continue
    if not isinstance(match, list):
        return None
    new = []
    for x in match:
        if not isinstance(x, dict):
            continue
        word, imi = str(x.get("言葉", "")).strip()[:20], str(x.get("意味", "")).strip()[:80]
        if len(word) < 2 or not imi or _NG.search(word + imi):
            continue
        before = next((y for y in now if y["言葉"] == word), None)
        new.append({"言葉": word, "意味": imi, "由来": before.get("由来", "種") if before else "自分で足した"})
    if not any(x["言葉"] == KOTEI for x in new):
        new.insert(1, next(x for x in now if x["言葉"] == KOTEI))
    new = new[:MAX]
    if len(new) < 3 or [(x["言葉"], x["意味"]) for x in new] == [(x["言葉"], x["意味"]) for x in now]:
        return None
    kaku(new, "自己紹介のときに自分で見直した")
    return new


if __name__ == "__main__":
    for x in yomu():
        print(f"- {x['言葉']}: {x['意味']}（{x.get('由来', '')}）")
