"""会話ごとの自由な仕事。本物の頭脳・本番データは使わない。"""
import contextlib
import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kernel"))
import chats
import conversation
import loop
import server

spec = importlib.util.spec_from_file_location("test_work_hako", ROOT / "dougu/hako.py")
hako = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hako)



def _dougu_jiyuu():
    """他の試験が本番 ~/LocalAI_mirror/kernel を sys.path に足すと、本番の jiyuu が読まれる。写しの dougu/jiyuu.py を必ず使う。"""
    want = str(ROOT / "dougu" / "jiyuu.py")
    mod = sys.modules.get("jiyuu")
    if mod is None or getattr(mod, "__file__", "") != want:
        sys.modules.pop("jiyuu", None)
        sys.path.insert(0, str(ROOT / "dougu"))
        try:
            import jiyuu as mod
        finally:
            sys.path.remove(str(ROOT / "dougu"))
    mod.gate.hako = mod._hako
    return mod

class ConversationWorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.old = chats.DIR, chats.DB, chats._READY
        chats.DIR, chats.DB, chats._READY = str(self.root / "legacy"), str(self.root / "chats.sqlite3"), False
        self.cid = chats.create()["id"]

    def tearDown(self):
        chats.DIR, chats.DB, chats._READY = self.old
        self.tmp.cleanup()

    def test_activity_isolated_bounded_and_reopened(self):
        other = chats.create()["id"]
        self.assertEqual(chats.load(other)["動き"], [])
        for i in range(207):
            chats.add_activity(self.cid, {"type": "note", "text": str(i)})
        chats.add_activity(other, {"text": "別の会話"})
        chats._READY = False
        activity = chats.load(self.cid)["動き"]
        self.assertEqual(len(activity), 200)
        self.assertEqual(activity[0]["text"], "7")
        self.assertEqual(chats.load(other)["動き"][0]["text"], "別の会話")
        chats.clear_activity(self.cid)
        self.assertEqual(chats.activities(self.cid), [])
        self.assertEqual(len(chats.activities(other)), 1)

    def fill(self, pairs=6):
        for i in range(pairs):
            chats.add_turn(self.cid, "user", f"頼み{i}")
            chats.add_turn(self.cid, "bot", f"答え{i}")

    def test_compact_replaces_previous_summary_and_keeps_recent_pairs(self):
        self.fill()
        chats.update_state(self.cid, summary="前回の要約", folders=[str(self.root)])
        summarize = mock.Mock(return_value="新しい要約")
        conversation.compact(chats, self.cid, summarize)
        c = chats.load(self.cid)
        self.assertEqual(c["要約"], "新しい要約")
        self.assertEqual([t["文"] for t in c["やりとり"]], [f"{role}{i}" for i in range(3, 6) for role in ("頼み", "答え")])
        self.assertEqual(summarize.call_args.args[1], "前回の要約")
        self.assertEqual(conversation.messages(c)[0]["role"], "system")
        self.assertIn("新しい要約", conversation.messages(c)[0]["content"])
        self.assertEqual(c["触ってよいフォルダ"], [str(self.root)])
        self.fill(2)
        conversation.compact(chats, self.cid, lambda old, previous: previous + "を更新")
        self.assertEqual(chats.load(self.cid)["要約"], "新しい要約を更新")

    def test_compact_failure_or_concurrent_message_does_not_discard_turns(self):
        self.fill()
        before = chats.load(self.cid)
        with self.assertRaises(ValueError):
            conversation.compact(chats, self.cid, lambda *_: "")
        self.assertEqual(chats.load(self.cid), before)
        def changed(*_):
            chats.add_turn(self.cid, "user", "追加")
            return "要約"
        with self.assertRaises(ValueError):
            conversation.compact(chats, self.cid, changed)
        self.assertEqual(len(chats.load(self.cid)["やりとり"]), 13)
        self.assertEqual(chats.load(self.cid)["要約"], "")

    def test_cancelled_compact_and_branch_preserve_context(self):
        self.fill()
        stop = threading.Event()
        stop.set()
        with self.assertRaises(ValueError):
            conversation.compact(chats, self.cid, lambda *_: "要約", stop=stop)
        self.assertEqual(len(chats.load(self.cid)["やりとり"]), 12)
        chats.update_state(self.cid, summary="決定", folders=[str(self.root)], loop={"running": True})
        branch = chats.fork(self.cid)
        self.assertEqual(branch["要約"], "決定")
        self.assertEqual(branch["触ってよいフォルダ"], [str(self.root)])
        self.assertEqual(branch["loop"], {})

    def test_stream_connects_mock_tools_to_the_correct_conversation(self):
        import queue
        sys.path.append(str(ROOT / "dougu"))
        jiyuu = _dougu_jiyuu()
        import kyoudou
        import teachers
        old_settings = server.CTX["設定"]
        server.CTX["設定"] = {"モード": "本番", "輪": "新"}
        chats.update_state(self.cid, summary="決定を引き継ぐ", folders=[str(self.root)])
        captured = {}
        def answer(text, on_event, **args):
            captured.update(args)
            on_event({"type": "tool_start", "id": "1", "name": "read", "label": "読む"})
            on_event({"type": "tool_end", "id": "1", "ok": True, "summary": "確認"})
            return "完了"
        try:
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(server, "_gakushuu_busy", side_effect=contextlib.nullcontext))
                stack.enter_context(mock.patch.object(server, "_temoto_tsukau", side_effect=contextlib.nullcontext))
                stack.enter_context(mock.patch.object(server, "moderu_youi", return_value=(True, "mock")))
                stack.enter_context(mock.patch.object(teachers, "mado_settei"))
                stack.enter_context(mock.patch.object(kyoudou, "is_shortcut", return_value=False))
                stack.enter_context(mock.patch.object(jiyuu, "kotaeru", side_effect=answer))
                result = server._run_request("読む", self.cid, queue.Queue(), threading.Event(), "kyoudou", [])
            self.assertTrue(result["出力"].endswith("完了"))
            self.assertEqual(captured["settei"]["要約"], "決定を引き継ぐ")
            self.assertEqual(captured["settei"]["触ってよいフォルダ"], [str(self.root)])
            self.assertEqual([e["type"] for e in chats.activities(self.cid)], ["tool_start", "tool_end"])
            self.assertEqual(chats.load(chats.create()["id"])["動き"], [])
        finally:
            server.CTX["設定"] = old_settings

    def test_token_meter_uses_props_tokenize_and_fallback(self):
        self.fill(1)
        def api(path, payload=None):
            return {"/props": {"default_generation_settings": {"n_ctx": 100}},
                    "/apply-template": {"prompt": "会話"}, "/tokenize": {"tokens": list(range(38))}}[path]
        meter = conversation.Meter(api)
        measured = meter.measure(chats.load(self.cid))
        self.assertEqual((measured["使った"], measured["上限"], measured["割合"]), (38, 100, 38))
        self.assertFalse(measured["推定"])
        missing = mock.Mock(side_effect=OSError("未提供"))
        result = conversation.Meter(missing).measure(chats.load(self.cid), {"コンテキスト上限": 1234})
        self.assertEqual(result["上限"], 1234)
        self.assertTrue(result["推定"])
        self.assertGreater(result["使った"], 0)

    def make_loop(self, runner, lesson=None):
        self.clock = [datetime.datetime(2026, 10, 4, 12).timestamp()]
        return loop.Manager(chats, runner, now=lambda: self.clock[0], lesson=lesson)

    def test_loop_rounds_learn_failures_interval_limit_and_restore(self):
        prompts = []
        def runner(cid, prompt, stop):
            prompts.append(prompt)
            if len(prompts) == 1:
                raise ValueError("試みAは失敗")
            return {"ok": True, "result": "方法Bを確認", "next": "方法C"}
        lessons = mock.Mock()
        manager = self.make_loop(runner, lessons)
        manager.start(self.cid, "技術を作る", 1800, maximum=3)
        manager.tick()
        manager.tick()
        self.assertEqual(len(prompts), 1)
        self.clock[0] += 1800
        restored = loop.Manager(chats, runner, now=lambda: self.clock[0], lesson=lessons)
        restored.tick()
        self.assertIn("試みAは失敗", prompts[1])
        self.clock[0] += 1800
        restored.tick()
        self.assertIn("方法C", prompts[2])
        state = chats.get_state(self.cid)["loop"]
        self.assertFalse(state["running"])
        self.assertEqual(state["round"], 3)
        self.assertEqual(lessons.call_count, 2)

    def test_loop_stop_during_round_and_night_pause(self):
        manager = None
        def runner(cid, prompt, stop):
            manager.stop(cid)
            self.assertTrue(stop.is_set())
            return {"ok": True, "result": "停止"}
        manager = self.make_loop(runner)
        manager.start(self.cid, "お題", 10)
        manager.tick()
        self.assertFalse(chats.get_state(self.cid)["loop"]["running"])
        manager.start(self.cid, "次のお題", 10)
        self.clock[0] = datetime.datetime(2026, 10, 5, 1).timestamp()
        manager.tick()
        state = chats.get_state(self.cid)["loop"]
        self.assertEqual(state["round"], 0)
        self.assertTrue(state["running"])
        self.assertEqual(datetime.datetime.fromtimestamp(state["next"]).hour, 7)

    def test_loop_inflight_restart_is_recorded_and_not_repeated(self):
        runner = mock.Mock(return_value={"ok": False, "result": "失敗"})
        manager = self.make_loop(runner)
        manager.start(self.cid, "お題")
        state = chats.get_state(self.cid)["loop"]
        state.update(inflight=True, round=1)
        chats.update_state(self.cid, loop=state)
        manager.tick()
        self.assertIn("再起動で中断", runner.call_args.args[1])
        self.assertEqual(chats.get_state(self.cid)["loop"]["round"], 2)

    def test_loop_command_parser(self):
        self.assertEqual(loop.parse("/loop 30m 新しい技術を作って")["interval"], 1800)
        self.assertEqual(loop.parse("/loop お題")["interval"], 600)
        self.assertTrue(loop.parse("/loop 止める")["stop"])
        for text in ("/loop", "/loop 0s お題", "/loop 30m"):
            with self.assertRaises(ValueError):
                loop.parse(text)

    def test_api_folders_and_activity_are_scoped_and_commands_listed(self):
        old_settings, old_id = server.CTX["設定"], server.CTX.get("会話id")
        server.CTX["設定"] = {"モード": "試験"}
        httpd = server.Server(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        def api(path, body=None):
            request = Request("http://127.0.0.1:%d%s" % (httpd.server_address[1], path),
                              data=None if body is None else json.dumps(body).encode(),
                              headers={"X-Token": server.TOKEN, "Content-Type": "application/json"})
            with urlopen(request) as response:
                return json.load(response)
        try:
            api("/chat/folders", {"id": self.cid, "folders": [str(self.root)]})
            chats.add_activity(self.cid, {"type": "note", "text": "本人の会話"})
            self.assertEqual(api("/ugoki")["動き"], [])
            self.assertEqual(api("/ugoki?cid=" + self.cid)["動き"][0]["text"], "本人の会話")
            with mock.patch.object(server._CONTEXT_METER, "measure", return_value={"使った": 1}):
                view = api("/chat/context?cid=" + self.cid)
            self.assertEqual(view["触ってよいフォルダ"], [str(self.root)])
            self.assertIn("/compact", [x["名"] for x in api("/commands")])
            self.assertIn("/loop", [x["名"] for x in api("/commands")])
            with mock.patch.object(server, "_LOOPS", self.make_loop(mock.Mock())):
                server._special_request("/loop お題", self.cid, threading.Event())
                api("/chat/loop/stop", {"id": self.cid})
            self.assertFalse(chats.get_state(self.cid)["loop"]["running"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(2)
            server.CTX["設定"], server.CTX["会話id"] = old_settings, old_id


class SandboxWorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve() / "home"
        self.work = self.home / "Documents"
        self.work.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parent_selection_never_allows_private_paths_or_symlinks(self):
        private = [".claude", ".codex", ".ssh", ".claude.json", ".groq.env", ".future.env",
                   "LocalAI_mirror/kernel", "LocalAI_mirror/koukai/dougu/hako.py", "LocalAI_mirror/koukai/kernel/kyoudou.py"]
        for path in private:
            for write in (False, True):
                self.assertFalse(hako.check_path(str(self.home / path), write=write, paths=[str(self.home)], home=str(self.home)), path)
        self.assertTrue(hako.check_path(str(self.work / "new"), True, [str(self.work)], str(self.home)))
        self.assertFalse(hako.check_path(str(self.home / "outside"), True, [str(self.work)], str(self.home)))
        self.assertFalse(hako.check_path(str(self.home / "Documents-other/new"), True, [str(self.work)], str(self.home)))
        (self.work / "escape").symlink_to(self.home / ".claude")
        self.assertFalse(hako.check_path(str(self.work / "escape/new"), True, [str(self.work)], str(self.home)))

    def test_mac_profile_limits_writes_and_denies_private_reads(self):
        profile = hako.build_profile("戻せる", home=str(self.home), allowed_roots=[str(self.work)])
        self.assertNotIn("(allow file-write*)", profile)
        self.assertIn(f'(subpath "{self.work}")', profile)
        for name in (".claude", ".codex", ".ssh", "LocalAI_mirror/kernel"):
            self.assertIn(f'(deny file-read* (subpath "{self.home / name}"))', profile)
            self.assertIn(f'(deny file-write* (subpath "{self.home / name}"))', profile)
        self.assertIn("(allow lsopen)", profile)   # 10/4: open -a・osascript（J08〜J10）は門番が危険度で扱う

    def test_linux_readonly_root_and_home_parent_exclusions(self):
        secret = self.home / ".nvidia.env"
        secret.write_text("fixture")
        (self.home / ".ssh").mkdir()
        with mock.patch.object(hako.shutil, "which", return_value="/usr/bin/bwrap"):
            argv = hako._bwrap_argv("true", risk="戻せる", env={"HOME": str(self.home)}, allowed_roots=[str(self.home)])
        triples = [argv[i:i+3] for i in range(len(argv)-2)]
        self.assertIn(["--ro-bind", "/", "/"], triples)
        self.assertIn(["--bind", str(self.work), str(self.work)], triples)
        self.assertNotIn(["--bind", str(self.home), str(self.home)], triples)
        self.assertIn(["--ro-bind", "/dev/null", str(secret)], triples)
        self.assertIn(["--tmpfs", str(self.home / ".ssh"), "--remount-ro"], triples)

    def test_jiyuu_uses_new_sandbox_and_guards_direct_write(self):
        sys.path.append(str(ROOT / "dougu"))
        jiyuu = _dougu_jiyuu()
        self.assertTrue(hasattr(jiyuu.gate.hako, "scope"))
        with jiyuu.gate.hako.scope([str(self.work)]):
            result = jiyuu._run("write", {"path": str(self.home / "outside"), "content": "禁止"}, "戻せる", "mock")
            self.assertFalse(result["ok"])
            result = jiyuu._run("write", {"path": str(self.work / "allowed"), "content": "許可"}, "戻せる", "mock")
            self.assertTrue(result["ok"])
            self.assertEqual((self.work / "allowed").read_text(), "許可")
            with mock.patch.object(jiyuu.gate.hako, "_sandbox_executable", return_value="sandbox-exec"):
                argv = jiyuu.gate.hako.command_argv("true", risk="戻せる")
            self.assertIn(f'(subpath "{self.work}")', argv[2])
            self.assertNotIn("(allow file-write*)", argv[2])

    def test_jiyuu_summary_is_first_and_full_history_is_preserved(self):
        sys.path.append(str(ROOT / "dougu"))
        jiyuu = _dougu_jiyuu()
        with contextlib.ExitStack() as stack:
            for name in ("_system", "_knowledge_hint", "_memory_hint", "_gakushuu_hint", "_kanjou_hint", "_skill_hint", "_user_context"):
                stack.enter_context(mock.patch.object(jiyuu, name, return_value=""))
            stack.enter_context(mock.patch.object(jiyuu, "_record"))
            ask = stack.enter_context(mock.patch.object(jiyuu, "_ask", return_value={"content": "答えです。"}))
            stack.enter_context(mock.patch.object(jiyuu.gate, "TOMERU", None))
            jiyuu.kotaeru("頼み", rireki=[{"role": "user", "text": "長"*1500}] * 8,
                           settei={"要約": "要約の決定", "触ってよいフォルダ": [str(self.work)]})
            messages = ask.call_args.args[0]
            self.assertEqual(messages[0]["content"], "")   # system は変えない（先頭の使い回し）
            self.assertIn("要約の決定", messages[1]["content"])
            self.assertEqual(sum(m.get("content") == "長"*1500 for m in messages), 8)

    def test_loop_cannot_leave_background_commands_running(self):
        sys.path.append(str(ROOT / "dougu"))
        jiyuu = _dougu_jiyuu()
        with mock.patch.object(jiyuu, "_job") as job:
            result = jiyuu._run("sh", {"command": "true", "background": True}, "戻せる", "mock", settei={"反復": True})
        self.assertFalse(result["ok"])
        job.assert_not_called()

    def test_shell_variable_expansion_cannot_bypass_write_scope(self):
        sys.path.append(str(ROOT / "dougu"))
        jiyuu = _dougu_jiyuu()
        with mock.patch.dict(os.environ, {"KOUKAI_TEST_OUTSIDE": str(self.work / "outside")}):
            with jiyuu.gate.hako.scope([str(Path.home())]):
                with mock.patch.object(jiyuu.gate, "_write_file") as write:
                    result = jiyuu._run("write", {"path": "$KOUKAI_TEST_OUTSIDE", "content": "禁止"}, "戻せる", "mock")
        self.assertFalse(result["ok"])
        write.assert_not_called()
