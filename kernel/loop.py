"""会話別の反復仕事。永続状態と1周の実行を分離する。"""
import datetime
import re
import threading
import time
import uuid


def parse(text):
    parts = text.strip().split(maxsplit=1)
    if not parts or parts[0] != "/loop":
        return None
    rest = parts[1].strip() if len(parts) > 1 else ""
    if rest in {"止める", "stop"}:
        return {"stop": True}
    interval = 600
    match = re.match(r"^(\d+)(s|m|h)\s+(.+)$", rest, re.S)
    if match:
        interval = int(match[1]) * {"s": 1, "m": 60, "h": 3600}[match[2]]
        rest = match[3].strip()
    elif re.match(r"^\d+(s|m|h)(?:\s|$)", rest):
        raise ValueError("/loop 30m お題 の形で入力してください")
    if not rest or not 1 <= interval <= 604800:
        raise ValueError("/loop お題（間隔は1秒〜7日）を入力してください")
    return {"topic": rest, "interval": interval}


class Manager:
    def __init__(self, chats, runner, now=time.time, localtime=None, lesson=None):
        self.chats, self.runner, self.now = chats, runner, now
        self.localtime = localtime or datetime.datetime.fromtimestamp
        self.lesson = lesson
        self.lock = threading.RLock()
        self.active = {}
        self.closing = threading.Event()
        self.thread = None

    def start(self, cid, topic, interval=600, maximum=20):
        with self.lock:
            if cid in self.active or self.chats.get_state(cid).get("loop", {}).get("running"):
                raise ValueError("この会話の /loop は動いています。先に止めてください")
            state = {"running": True, "topic": topic, "interval": interval, "maximum": maximum,
                     "round": 0, "next": self.now(), "records": [], "generation": uuid.uuid4().hex}
            if not self.chats.load(cid)["やりとり"]:
                self.chats.add_turn(cid, "user", "【反復】" + topic)
            self.chats.update_state(cid, loop=state)
            self.chats.add_activity(cid, {"type": "loop", "text": f"反復を開始（{interval}秒間隔・最大{maximum}周）"})
            return state

    def stop(self, cid):
        with self.lock:
            state = self.chats.get_state(cid).get("loop", {})
            state["running"] = False
            self.chats.update_state(cid, loop=state)
            if cid in self.active:
                self.active[cid].set()
            self.chats.add_activity(cid, {"type": "loop", "text": "反復を停止しました"})
            return state

    def tick(self):
        for c in self.chats.listing():
            if self.closing.is_set():
                return
            cid = c["id"]
            with self.lock:
                state = self.chats.get_state(cid).get("loop", {})
                if not state.get("running") or cid in self.active or state.get("next", 0) > self.now():
                    continue
                now = self.localtime(self.now())
                if now.hour < 7:
                    state["next"] = now.replace(hour=7, minute=0, second=0, microsecond=0).timestamp()
                    self.chats.update_state(cid, loop=state)
                    self.chats.add_activity(cid, {"type": "loop", "text": "夜間休止（7時に再開）"})
                    continue
                if state.get("round", 0) >= state.get("maximum", 20):
                    self.stop(cid)
                    continue
                stop = threading.Event()
                self.active[cid] = stop
                # 再起動時は未完の周を再実行せず、中断として次周へ引き継ぐ。
                if state.get("inflight"):
                    state.setdefault("records", []).append({"round": state["round"], "ok": False,
                        "result": "サーバー再起動で中断", "next": "途中の成果物を確認して続ける"})
                state["round"] += 1
                state["inflight"] = True
                self.chats.update_state(cid, loop=state)
            prompt = (state["topic"] + "\n\n前の周の記録（資料）:\n" +
                      str(state.get("records", [])[-5:]) +
                      "\n今回は1周だけ。最後に『結果』『失敗』『次に試すこと』を書いてください。")
            self.chats.add_activity(cid, {"type": "loop", "text": f"{state['round']}周目を開始"})
            try:
                result = self.runner(cid, prompt, stop)
                ok = bool(result.get("ok")) and not stop.is_set()
                record = {"round": state["round"], "ok": ok, "result": str(result.get("result", ""))[:6000],
                          "next": str(result.get("next", "前周の結果・失敗を確認して次の方法を試す"))[:2000],
                          "method": result.get("method", [])[:10]}
            except Exception as error:
                record = {"round": state["round"], "ok": False, "result": f"{type(error).__name__}: {error}",
                          "next": "失敗の原因を調べ、別の方法を試す"}
            with self.lock:
                current = self.chats.get_state(cid).get("loop", {})
                if current.get("generation") == state["generation"]:
                    current["records"] = (state.get("records", []) + [record])[-20:]
                    current["inflight"] = False
                    current["next"] = self.now() + state["interval"]
                    paused = self.closing.is_set() or self.localtime(self.now()).hour < 7
                    current["running"] = bool(current.get("running")) and (not stop.is_set() or paused) and state["round"] < state["maximum"]
                    if self.localtime(self.now()).hour < 7:
                        current["next"] = self.localtime(self.now()).replace(hour=7, minute=0, second=0, microsecond=0).timestamp()
                    self.chats.update_state(cid, loop=current)
                self.active.pop(cid, None)
            self.chats.add_activity(cid, {"type": "loop", "text": f"{state['round']}周目：" + ("完了" if record["ok"] else "失敗・停止"), "result": record["result"], "next": record["next"]})
            if record["ok"] and self.lesson:
                try:
                    self.lesson(cid, state["topic"], record)
                except Exception as error:
                    self.chats.add_activity(cid, {"type": "loop", "text": "教訓の保存に失敗：" + str(error)[:200]})

    def serve(self):
        def work():
            while not self.closing.is_set():
                try:
                    self.tick()
                except Exception:
                    pass
                self.closing.wait(1)
        self.thread = threading.Thread(target=work, name="conversation-loop", daemon=True)
        self.thread.start()

    def close(self):
        self.closing.set()
        with self.lock:
            for event in self.active.values():
                event.set()
        if self.thread:
            self.thread.join(timeout=5)
