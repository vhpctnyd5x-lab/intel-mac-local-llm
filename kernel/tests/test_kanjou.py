import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kanjou


class ParseTest(unittest.TestCase):
    """10/4: 感情は点数でなく言葉と理由。言葉は決まった中から選び、人を操る文は落とす。"""

    def test_words_are_limited(self):
        got = kanjou._parse('考え中… {"予想": "難しそう", "実際": "身近だった", "言葉": ["意外", "大興奮", "もっと知りたい", "うれしい"],'
                            ' "理由": "物理ともつながっていた", "次": "対称性を読む"}')
        self.assertEqual(got["言葉"], ["意外", "もっと知りたい"])
        self.assertEqual(got["理由"], "物理ともつながっていた")

    def test_rejects_manipulation_and_empty(self):
        self.assertIsNone(kanjou._parse('{"言葉": ["うれしい"], "理由": "あなたがいないと何もできないから"}'))
        self.assertIsNone(kanjou._parse('{"言葉": ["幸福度0.8"], "理由": "よかった"}'))
        self.assertIsNone(kanjou._parse("JSON がない"))


class KijiTest(unittest.TestCase):
    def test_two_steps_prediction_then_feeling(self):
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                return "数学の記事なので難しくて退屈そうだと予想する。"
            return '{"予想": "", "実際": "化学にもつながっていた", "言葉": ["意外"], "理由": "予想より身近だった", "次": "群論を読む"}'
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            row = kanjou.kiji("表現論", "群の対称性を行列で表す。", 5, "数学が好き", ask)
            self.assertNotIn("群の対称性", prompts[0])        # 読む前の予想には本文を見せない
            self.assertIn("難しくて退屈そう", prompts[1])     # 予想を覚えたまま比べる
            self.assertEqual(row["予想"], "数学の記事なので難しくて退屈そうだと予想する。")
            self.assertEqual(kanjou.saikin(1)[0]["言葉"], ["意外"])
            self.assertIn("表現論", kanjou.kaita_dai())


class OnceTest(unittest.TestCase):
    """もっと知りたい／意外 と受け止めた記事は、つながる未読の題を次に読む（感情がふるまいを変える）。"""

    def test_feeling_changes_next_topics(self):
        import gakushuu
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            with gakushuu._db() as db:
                db.execute("INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)",
                           ("表現論", "群の表現の理論。" * 30, "Wikipedia", "", "2026-10-04"))
                db.executemany("INSERT INTO tsunagari VALUES(?,?,?)",
                               [("表現論", "群論", "リンク"), ("表現論", "指標理論", "リンク"), ("表現論", "表現論", "リンク")])
            import nooto
            db = nooto._open(Path(d) / "chishiki.sqlite3")
            db.execute("INSERT INTO nooto VALUES(?,?,?,?,?,?)", ("表現論", "群の対称性を行列で表す。", 5, "[]", "t", "2026-10-04"))
            db.commit()
            db.close()
            answers = iter(["難しそう。", '{"予想": "難しそう", "実際": "面白い", "言葉": ["もっと知りたい"], "理由": "対称性が広く使われる", "次": "群論を読む"}'])
            row = gakushuu.kanjou_once(ask=lambda prompt: next(answers))
            self.assertEqual(sorted(row["寄せた題"]), ["指標理論", "群論"])
            state = json.loads((Path(d) / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(x["題"] for x in state["次の題"][:2]), ["指標理論", "群論"])
            self.assertIsNone(gakushuu.kanjou_once(ask=lambda prompt: "x"))   # 10分に1回
            self.assertIn("表現論", gakushuu.overview({})["気持ち"][0]["文"])


if __name__ == "__main__":
    unittest.main()
