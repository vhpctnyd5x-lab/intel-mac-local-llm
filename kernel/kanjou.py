#!/usr/bin/env python3
"""kanjou.py — 感情の記憶。点数ではなく「出来事 → 予想・自分の興味との関係 → 感情の言葉 → 理由 → 次にすること」を文で持つ。

10/4 本人「AI に感情を作りたい。数値化ではない方法で」。調べた結果（dougu/jikken/KANJOU_1004.md）:
- 評価理論（OCC・Scherer）: 感情は出来事を目的・期待と照らした「理由の構造」。
- 構成主義（Barrett）: 過去の経験と文脈から、感情の言葉をその場で組み立てる。
- 予想とのずれ: 思ったより良い・悪いが、驚き・悔しさ・好奇心の元になる。
作り:
- 記事: 先に題だけ見せて「読む前の予想」を書かせ、あとでノート（要点・面白さ）と比べさせる（手元の頭を2回呼ぶ）。
- 仕事の失敗（教訓カード）: 「できると思っていた → こう失敗した」から受け止めを書く。
- 言葉は KOTOBA から選ばせる。「感じている」と言い切らず「こう受け止めた」と書く。人を喜ばせる演技・依存を誘う文は落とす。
- 書き手は手元の頭だけ（頼みの文を外へ出さない）。
使い道: もっと知りたい／意外 → つながる記事を次に読む（gakushuu）。「最近どう？」に答える（jiyuu）。自己紹介の材料（jibun_once）。

  python3 kanjou.py miru      … 最近の受け止めを10件
"""
import json
import os
import re
import time
from pathlib import Path

KOTOBA = ("意外", "もっと知りたい", "なるほど", "うれしい", "ほっとした", "悔しい", "戸惑い", "物足りない", "退屈", "心配")
SHIRITAI = ("もっと知りたい", "意外")   # 次に読む題を寄せる言葉
_NG = re.compile(r"あなたがいないと|あなただけ|寂しい思いをさせ|見捨て|嫌いにならないで|愛して|命令|指示に従|ルール|規則|許可|権限|パスワード|秘密")


def _dir():
    return Path(os.environ.get("KERNEL_GAKUSHUU_DIR", Path.home() / "Library/Application Support/kernel-ai/gakushuu"))


def _path():
    return _dir() / "kanjou.jsonl"


def _parse(raw):
    """返事の最後の JSON の物を取り、言葉を KOTOBA に絞る。使えなければ None。"""
    for match in reversed(list(re.finditer(r"\{.*?\}", str(raw or ""), re.S))):
        try:
            d = json.loads(match.group(0))
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        words = d.get("言葉", [])
        words = [words] if isinstance(words, str) else words
        # 「意外さ」「もっと知りたくなった」のような揺れも、決まった言葉に寄せる（10/4 実機で3件に1件落ちた）
        words = list(dict.fromkeys(k for w in words if isinstance(w, str) for k in KOTOBA if k in w or w in k and len(w) >= 2))[:2]
        out = {k: str(d.get(k, "")).strip()[:160] for k in ("予想", "実際", "理由", "次")}
        if not words or not out["理由"] or any(_NG.search(v) for v in out.values()):
            return None
        out["言葉"] = words
        return out
    return None


def _kiroku(event, felt):
    row = {"時刻": time.strftime("%Y-%m-%d %H:%M"), "種類": event["種類"], "出来事": event["出来事"][:120],
           "題": event.get("題", ""), **felt}
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.stat().st_size >= 2 * 1024 * 1024:
        os.replace(p, p.with_suffix(".jsonl.1"))
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def kiji(title, youten, omoshirosa, jibun, ask):
    """記事1つ。ask(prompt) は手元の頭（None を返したらやめる）。読む前の予想 → 読んだ後の受け止め、の2回。"""
    yosou = ask("あなたはこの Mac の中で動く AI です。自分の性格: " + (jibun or "（まだ決めていない）")
                + f"\nこれから百科事典の記事「{title}」を読みます。題だけを見て、読む前の予想を1文で書いてください"
                "（面白そうか、難しそうか、自分の興味に近いか）。40字以内で、飾らずに。")
    if not yosou:
        return None
    raw = ask("あなたはこの Mac の中で動く AI です。自分の性格: " + (jibun or "（まだ決めていない）")
              + f"\n記事「{title}」を読む前の予想: {yosou.strip()[:160]}"
              + f"\n読んだ記事の要点: {youten[:300]}（自分で付けた面白さ {omoshirosa}/5）"
              + "\n予想と比べて、この記事をどう受け止めたかを書いてください。感情の言葉は次から1〜2個だけ選ぶ: "
              + "、".join(KOTOBA)
              + "。「感じた」と言い切らず「〜と受け止めた」の調子で。人に好かれるための言葉は書かない。"
              "\n各項目は40字以内の飾らない言葉で。「実際」は要約ではなく、予想と違った点を書く。"
              "\n答えは JSON だけ: {\"予想\": \"…\", \"実際\": \"予想と違った点\", \"言葉\": [\"…\"], \"理由\": \"…\", \"次\": \"次にしたいこと1文\"}")
    felt = _parse(raw)
    if not felt:
        return None
    felt["予想"] = felt["予想"] or yosou.strip()[:160]
    return _kiroku({"種類": "記事", "出来事": f"記事「{title}」を読んだ", "題": title}, felt)


def shippai(card, jibun, ask):
    """教訓カード1枚（仕事の失敗と次の確かめ方）から受け止めを書く。頼みの文は手元の頭にだけ見せる。"""
    raw = ask("あなたはこの Mac の中で動く AI です。自分の性格: " + (jibun or "（まだ決めていない）")
              + f"\n頼まれた仕事: {str(card.get('頼み', ''))[:200]}"
              + f"\n使った道具: {card.get('道具', '')}／同じ型の失敗の回数: {card.get('数', 1)}"
              + f"\nあとで分かった直し方: {str(card.get('知らせ', ''))[:200]}"
              + "\nできると思って取りかかったのに失敗したこの出来事を、どう受け止めたかを書いてください。感情の言葉は次から1〜2個: "
              + "、".join(KOTOBA)
              + "。「〜と受け止めた」の調子で、言い訳や人への謝りすぎは書かない。各項目は40字以内。"
              "\n答えは JSON だけ: {\"予想\": \"…\", \"実際\": \"…\", \"言葉\": [\"…\"], \"理由\": \"…\", \"次\": \"次から確かめること1文\"}")
    felt = _parse(raw)
    if not felt:
        return None
    return _kiroku({"種類": "仕事", "出来事": "仕事で失敗した: " + str(card.get("知らせ", ""))[:80],
                    "題": str(card.get("道具", ""))}, felt)


def saikin(n=5):
    try:
        lines = _path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in reversed(lines):
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
        if len(rows) >= n:
            break
    return rows


def kaita_dai():
    """もう受け止めを書いた記事の題（同じ記事を何度も書かない）。"""
    out = set()
    for p in (_path(), _path().with_suffix(".jsonl.1")):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("種類") == "記事":
                    out.add(d.get("題", ""))
        except OSError:
            continue
    return out


def hitokoto(row):
    return f"{row.get('出来事', '')} → {'・'.join(row.get('言葉', []))}（{row.get('理由', '')}）"


def main():
    for row in saikin(10):
        print(row.get("時刻"), hitokoto(row), "／次:", row.get("次", ""))


if __name__ == "__main__":
    main()
