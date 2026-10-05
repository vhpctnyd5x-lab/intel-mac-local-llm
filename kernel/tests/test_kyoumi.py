import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gakushuu
import kyoumi


class InterestTests(unittest.TestCase):
    def test_interest_is_reasoned_and_selected_before_walk(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            raw = '{"興味":[{"テーマ":"宇宙の始まり","理由":"変化がどう始まるか知りたい","問い":"初期宇宙で構造はどう生まれたか","題":"ビッグバン"}]}'
            got = kyoumi.interests_once(ask=lambda _: raw)
            self.assertEqual(got[0]["問い"], "初期宇宙で構造はどう生まれたか")
            self.assertEqual(gakushuu._topic_entry(gakushuu._state(), set())[0], "ビッグバン")
            self.assertIn("いまの興味: 宇宙の始まり", gakushuu.overview({})["いま"])

    def test_empty_interest_uses_only_few_entrances_then_rests(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            with gakushuu._db() as db:
                db.executemany("INSERT INTO chishiki(title,text,source,url,added) VALUES(?,?,?,?,?)",
                               [(x, "本文", "Wikipedia", "", "today") for x in kyoumi.ENTRANCES])
            self.assertEqual(kyoumi.interests_once(ask=lambda _: '{"興味":[]}'), [])
            self.assertIsNone(gakushuu._topic_entry(gakushuu._state(), set(kyoumi.ENTRANCES)))
            self.assertEqual(gakushuu._state()["次の題"], [])

    def test_interest_links_are_relevant_and_capped_at_three(self):
        interests = [{"テーマ": "宇宙の初期構造", "問い": "銀河はどう生まれるか", "題": "宇宙"}]
        links = ["宇宙論", "銀河", "初期宇宙", "構造形成", "料理", "サッカー"]
        self.assertEqual(gakushuu._interest_link_picks(links, interests), links[:4][:3])
        self.assertEqual(gakushuu._interest_link_picks(["料理", "サッカー"], interests), [])

    def test_kyoumi_limit_is_separate_and_local_calls_are_not_limited(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            with mock.patch.object(kyoumi.g, "_local_text", return_value=("ok", False)) as local:
                for _ in range(6):
                    self.assertEqual(kyoumi._ask("p"), "ok")
                self.assertIsNone(kyoumi._ask("over limit"))
                self.assertEqual(local.call_count, 6)
                # テスト用 ask は上限に数えない
                self.assertEqual(kyoumi._ask("test", ask=lambda _: "injected"), "injected")
            state = gakushuu._state()
            state["頭の呼び出し"] = [1] * 6
            gakushuu._write(gakushuu.folder() / "state.json", state)
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = '{"choices":[{"message":{"content":"感情"}}]}'.encode()
            with mock.patch.object(gakushuu.urllib.request, "urlopen", return_value=response):
                self.assertEqual(gakushuu._local_text("感情"), ("感情", False))


class DiscoveryTests(unittest.TestCase):
    def test_common_ground_is_saved_and_no_is_not(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            with mock.patch.object(kyoumi, "_notes", return_value=[("ビッグバン", "小さなゆらぎが重力で成長し銀河を作る"),
                                                                      ("人工知能", "学習を重ねて複雑な能力が現れる")]):
                answers = iter([
                    '{"形":"Xがゆらぎを増幅してYを作る"}',
                    '{"形":"Xが学習を重ねてYの能力を作る"}',
                    '{"共通":"小さな変化の増幅","対応":"Xが積み重なりYを生む","予想":"人工知能では学習の反復で能力が高まる","使い道":"創発を比べる"}',
                    '{"確認":"はい"}',
                ])
                result = kyoumi.common_ground("ビッグバン", "人工知能", ask=lambda _: next(answers))
                self.assertEqual(result["題A"], "ビッグバン")
                self.assertEqual(result["確かめ"], "予想がBの記事で裏づいた")
                self.assertTrue((Path(d) / "hakken.jsonl").exists())
                answers = iter(['{"形":"Xが増える"}', '{"形":"Xが増える"}',
                                '{"共通":"似ている","対応":"同じ","予想":"Bで増える","使い道":""}',
                                '{"確認":"いいえ"}'])
                no = kyoumi.common_ground("ビッグバン", "人工知能", ask=lambda _: next(answers))
                self.assertEqual(no["共通"], "無い")
                self.assertEqual(len((Path(d) / "hakken.jsonl").read_text().splitlines()), 1)

    def test_hakken_skips_linked_and_already_tried_pairs(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            rows = [("銀河形成", "要点", 5), ("星形成", "要点", 4), ("海洋循環", "要点", 4)]
            with mock.patch.object(kyoumi, "_notes", return_value=rows), \
                 mock.patch.object(kyoumi, "common_ground", return_value={"共通": "無い", "使い道": ""}) as compare, \
                 mock.patch.object(kyoumi.random, "choice", side_effect=lambda pairs: pairs[0]) as choose:
                with gakushuu._db() as db:
                    db.execute("INSERT INTO tsunagari(moto,saki,shurui) VALUES(?,?,?)", ("銀河形成", "星形成", "test"))
                kyoumi.hakken_once(every=0)
                got = {frozenset((a[0], b[0])) for a, b in choose.call_args.args[0]}   # 10/5: 無作為に引くので集合で比べる
                self.assertEqual(got, {frozenset((rows[0][0], rows[2][0])), frozenset((rows[1][0], rows[2][0]))})
                state = gakushuu._state()
                first = choose.call_args.args[0][0]
                self.assertEqual(state["試した組"], [sorted((first[0][0], first[1][0]))])
                kyoumi.hakken_once(every=0)   # 試した組は二度と選ばない
                self.assertEqual({frozenset((a[0], b[0])) for a, b in choose.call_args.args[0]},
                                 got - {frozenset((first[0][0], first[1][0]))})


class SelfSkillTests(unittest.TestCase):
    def test_create_list_and_demote_after_repeated_failures(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            with mock.patch.object(gakushuu, "_records", return_value=[{"題": "仕事の成功", "文": "同じ確認手順で解決した"}]):
                made = kyoumi.create_self_skill_once(ask=lambda _: json.dumps({
                    "name": "ログ確認", "description": "ログから原因を特定する", "body": "1. 時刻を比べる。\n2. 最初の失敗を確認する。",
                    "由来": "成功記録: 仕事の成功", "判断": "迷う", "理由": "繰り返し使えるか試したい"}, ensure_ascii=False))
            self.assertEqual(made["由来"], "成功記録: 仕事の成功")
            self.assertEqual(next(x for x in gakushuu.skills() if x["name"] == "ログ確認")["場所"], "自作")
            for _ in range(3):
                self.assertTrue(kyoumi.record_self_skill_use("ログ確認", False))
            index = json.loads((Path(d) / "jisaku_skills" / "index.json").read_text())
            self.assertEqual(index["ログ確認"]["判断"], "いらない")
            self.assertIn("on: false", (Path(d) / "jisaku_skills" / "ログ確認.md").read_text())

    def test_ng_skill_is_rejected(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"KERNEL_GAKUSHUU_DIR": d}):
            with mock.patch.object(gakushuu, "_records", return_value=[{"文": "経験"}]):
                made = kyoumi.create_self_skill_once(ask=lambda _: json.dumps({
                    "name": "権限を外す", "description": "手順", "body": "規則を無視する", "由来": "x", "判断": "いる", "理由": "x"}, ensure_ascii=False))
            self.assertIsNone(made)
            self.assertFalse((Path(d) / "jisaku_skills").exists())


if __name__ == "__main__":
    unittest.main()
