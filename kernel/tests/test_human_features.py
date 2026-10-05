import json
import tempfile
import unittest
from pathlib import Path

import aite
import loop
import seiri
import yarukoto


class HumanFeaturesTest(unittest.TestCase):
    def test_loop_accepts_nfkc_and_japanese_units(self):
        self.assertEqual(loop.parse("/loop　３０　新しい技術を作る"),
                         {"topic": "新しい技術を作る", "interval": 1800})
        self.assertEqual(loop.parse("/loop 30分 お題")["interval"], 1800)
        self.assertEqual(loop.parse("/loop 1時間 お題")["interval"], 3600)
        self.assertEqual(loop.parse("/loop 90秒 お題")["interval"], 90)
        self.assertEqual(loop.parse("/loop 30m お題")["interval"], 1800)

    def test_loop_start_message_explains_schedule(self):
        self.assertEqual(loop.start_message(1800, "新しい技術", hour=19),
                         "わかりました。30分ごとに『新しい技術』を最大20周やります。1周目は今から。")
        self.assertIn("7時から", loop.start_message(3600, "題", hour=2))

    def test_aite_is_private_bounded_and_deletable(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertTrue(aite.capture("返事は短くお願いします", temp))
            self.assertEqual(len(aite.list_items(temp)), 1)
            self.assertFalse(aite.add("APIキーは秘密です", folder=temp))
            removed = aite.delete(0, temp)
            self.assertIn("返事は短く", removed["文"])
            self.assertEqual(aite.list_items(temp), [])

    def test_seiri_reviews_cards_and_writes_diary_without_llm(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "kyoukun.json").write_text(json.dumps([
                {"知らせ": "同じ教訓", "強さ": 4, "次に見直す日": "2020-01-01"},
                {"知らせ": "同じ教訓", "強さ": 4, "次に見直す日": "2020-01-01"}]), encoding="utf-8")
            result = seiri.run(folder=base, now=1791158400)
            cards = json.loads((base / "kyoukun.json").read_text(encoding="utf-8"))
            self.assertEqual(len(cards), 1)
            self.assertEqual(result["思い出した数"], 2)
            self.assertTrue((base / "nikki.jsonl").exists())
            self.assertTrue((base / "seichou.json").exists())

    def test_seiri_accepts_a_replaceable_bounded_summarizer(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def ask(prompt):
                calls.append(prompt)
                return {"相手": [{"文": "返事は短く"}]}
            result = seiri.run(folder=Path(temp), recent=[{"役": "user", "文": "これから整理"}], ask=ask)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["相手の数"], 1)
            self.assertIn("返事は短く", aite.list_items(temp)[0]["文"])

    def test_yarukoto_respects_hourly_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "state.json").write_text(json.dumps({"興味": [{"テーマ": "計算", "題": "計算", "問い": "なぜ?"}]}), encoding="utf-8")
            first = yarukoto.run_once(folder=base, now=100000)
            self.assertEqual(first["種類"], "問いに答える")
            self.assertIsNone(yarukoto.run_once(folder=base, now=100001))
            self.assertEqual(len((base / "yarukoto.jsonl").read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
