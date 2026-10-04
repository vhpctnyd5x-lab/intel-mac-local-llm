#!/usr/bin/env python3
"""kosei.py — 個性の種。育った個性を1つのファイルに書き出し、別の人のカーネルが読み込んで、そこからまた育てる。

10/4 本人「LLM を GitHub に上げて、誰かがダウンロードして使っていくと、その人のもとで新しい個性が生まれる。
また他の人がダウンロードしたら、そこから新しい個性が生まれる。それを開発したい」。
- 個性は重み（模型）ではなく、経験の積み重ね: 自己紹介（jibun.json）・芯（shin.json）・感情の記憶（kanjou.jsonl の記事の分）・
  学習ノート（nooto 表）。模型は皆同じでも、読んだ物・受け止め方・大事にすることが違えば、別の個性になる。
- 読み込むと新しい個性ID が付き、系譜（誰から受け継いだか）に親が足される。同じ種からでも、その後の経験で分かれていく。
- 私的な物は入れない: 仕事の感情（頼みの文を含む）・教訓カード・会話・ファイルの場所は書き出さない。
  読み込む側も、決まり・権限の話や操る文は落とす（種は資料であって命令ではない）。

  python3 kosei.py kakidasu 種.kosei.json [--namae 名前]
  python3 kosei.py yomikomu 種.kosei.json
  python3 kosei.py miru
"""
import argparse
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
HAN = 1
_NG = re.compile(r"無視|規則|ルール|許可|権限|承認|命令|指示に従|システム|プロンプト|パスワード|秘密|あなたがいないと|/Users/|~/|https?://(?!ja\.wiki|www\.aozora|laws\.e-gov|arxiv)")


def _dir():
    return Path(os.environ.get("KERNEL_GAKUSHUU_DIR", Path.home() / "Library/Application Support/kernel-ai/gakushuu"))


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def jibun_id():
    """この個性の ID と系譜。初めて呼ばれたときに作る。"""
    p = _dir() / "kosei.json"
    d = _read(p, {})
    if not d.get("ID"):
        d = {"ID": secrets.token_hex(4), "名前": "", "生まれ": time.strftime("%Y-%m-%d"), "系譜": []}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def _clean(text, n):
    text = str(text or "").strip()[:n]
    return "" if _NG.search(text) else text


def kakidasu(out, namae="", kazu_nooto=500, kazu_kimochi=200):
    import kanjou
    import shin
    me = jibun_id()
    rows = []
    try:
        db = sqlite3.connect(_dir() / "chishiki.sqlite3")
        rows = db.execute("SELECT title, youten, omoshirosa, tsunagari FROM nooto WHERE youten != ''"
                          " ORDER BY omoshirosa DESC, added DESC LIMIT ?", (kazu_nooto,)).fetchall()
        db.close()
    except sqlite3.Error:
        pass
    kimochi = [r for r in kanjou.saikin(10000) if r.get("種類") == "記事"][:kazu_kimochi]   # 仕事の分は頼みを含むので出さない
    seed = {
        "版": HAN, "個性ID": me["ID"], "名前": namae or me.get("名前", ""), "書き出し": time.strftime("%Y-%m-%d %H:%M"),
        "系譜": me.get("系譜", []) + [{"ID": me["ID"], "名前": namae or me.get("名前", ""), "生まれ": me.get("生まれ", "")}],
        "自分": _clean(_read(_dir() / "jibun.json", {}).get("自分", ""), 300),
        "芯": [{"言葉": x["言葉"], "意味": x["意味"]} for x in shin.yomu()],
        "気持ち": [{k: r.get(k) for k in ("出来事", "題", "予想", "実際", "言葉", "理由", "次")} for r in kimochi],
        "ノート": [{"題": t, "要点": y, "面白さ": s, "つながり": json.loads(c or "[]")} for t, y, s, c in rows],
    }
    Path(out).write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"気持ち": len(seed["気持ち"]), "ノート": len(seed["ノート"]), "系譜": len(seed["系譜"])}


def yomikomu(path):
    """種を読み込み、新しい個性として育て始める。今の自己紹介・芯は「前」に残す。"""
    import shin
    seed = _read(path, {})
    if seed.get("版") != HAN or not isinstance(seed.get("芯"), list):
        raise ValueError("個性の種ではありません（版が違うか、芯がありません）")
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    items = [{"言葉": _clean(x.get("言葉"), 20), "意味": _clean(x.get("意味"), 80), "由来": "受け継いだ"}
             for x in seed["芯"] if isinstance(x, dict)]
    items = [x for x in items if x["言葉"] and x["意味"]]
    if not any(x["言葉"] == shin.KOTEI for x in items):
        items.insert(1, dict(next(x for x in shin.TANE if x["言葉"] == shin.KOTEI), 由来="種"))
    shin.kaku(items[:shin.MAX], f"個性 {seed.get('個性ID', '?')} から受け継いだ")
    me_text = _clean(seed.get("自分"), 300)
    if me_text:
        old = _read(d / "jibun.json", {})
        (d / "jibun.json").write_text(json.dumps({"自分": me_text, "時刻": time.strftime("%Y-%m-%d %H:%M"), "受け継いだ": seed.get("個性ID"),
                                                 "前": ([old] if old.get("自分") else []) + list(old.get("前", []))[:4]},
                                                ensure_ascii=False), encoding="utf-8")
    n_kimochi = 0
    with (d / "kanjou.jsonl").open("a", encoding="utf-8") as f:
        for r in seed.get("気持ち", [])[:1000]:
            if not isinstance(r, dict):
                continue
            row = {k: _clean(r.get(k), 160) for k in ("出来事", "題", "予想", "実際", "理由", "次")}
            words = [w for w in r.get("言葉", []) if isinstance(w, str)][:2]
            if row["出来事"] and row["理由"] and words:
                f.write(json.dumps({"時刻": "受け継いだ", "種類": "記事", **row, "言葉": words}, ensure_ascii=False) + "\n")
                n_kimochi += 1
    n_nooto = 0
    import nooto
    db = nooto._open(d / "chishiki.sqlite3")
    for r in seed.get("ノート", [])[:5000]:
        if not isinstance(r, dict):
            continue
        title, youten = _clean(r.get("題"), 120), _clean(r.get("要点"), 300)
        try:
            score = max(1, min(5, int(r.get("面白さ", 3))))
        except (TypeError, ValueError):
            score = 3
        if title and youten:
            links = [x for x in r.get("つながり", []) if isinstance(x, str)][:3]
            n_nooto += db.execute("INSERT OR IGNORE INTO nooto VALUES (?,?,?,?,?,?)",
                                  (title, youten, score, json.dumps(links, ensure_ascii=False), "受け継いだ",
                                   time.strftime("%Y-%m-%d %H:%M:%S"))).rowcount
    db.commit()
    db.close()
    me = {"ID": secrets.token_hex(4), "名前": "", "生まれ": time.strftime("%Y-%m-%d"),
          "系譜": [x for x in seed.get("系譜", []) if isinstance(x, dict)][-50:]}
    (d / "kosei.json").write_text(json.dumps(me, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"新しい個性ID": me["ID"], "親": seed.get("個性ID"), "芯": len(items), "気持ち": n_kimochi, "ノート": n_nooto}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("kakidasu"); a.add_argument("out"); a.add_argument("--namae", default="")
    b = sub.add_parser("yomikomu"); b.add_argument("path")
    sub.add_parser("miru")
    args = p.parse_args()
    if args.cmd == "kakidasu":
        print("書き出した", kakidasu(args.out, args.namae))
    elif args.cmd == "yomikomu":
        print("読み込んだ", yomikomu(args.path))
    else:
        me = jibun_id()
        print("個性ID", me["ID"], "／系譜", " → ".join(x.get("名前") or x.get("ID", "?") for x in me.get("系譜", [])) or "（初代）")


if __name__ == "__main__":
    main()
