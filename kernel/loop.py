"""会話別の反復仕事。永続状態と1周の実行を分離する。"""
import datetime
import re
import threading
import time
import unicodedata
import uuid


GAP = 5            # 10/5 本人「時間指定は要らない。止めるまでずっと動き続ける」: 周と周の間は5秒だけ
BACKOFF = 300      # 3周続けて失敗したら（頭脳が止まっている等）5分休んでから続ける


def parse(text):
    text = unicodedata.normalize("NFKC", str(text or "")).strip()
    parts = text.split(maxsplit=1)
    if not parts or parts[0] != "/loop":
        return None
    rest = parts[1].strip() if len(parts) > 1 else ""
    if rest in {"止める", "stop"}:
        return {"stop": True}
    # 前の形（/loop 30 お題・/loop 30分 お題）の時間は読み飛ばす。
    rest = re.sub(r"^\d+\s*(?:秒|分|時間|s|m|h)?(?:\s+|$)", "", rest).strip()
    if not rest:
        raise ValueError("/loop お題 の形で入力してください（止めるまで続けます。止めるときは /loop 止める）")
    return {"topic": rest, "interval": GAP}


def start_message(topic, hour=None):
    """依頼をそのまま確認し、いつ始まるか・どう止めるかを伝える。"""
    when = "いまは夜なので、1周目は7時から始めます（夜の重い計算は Mac で回さない決まり）。" if hour is not None and hour < 7 else "1周目を今から始めます。"
    return f"わかりました。『{topic}』を、止めるまで続けて回します。{when}止めるときは /loop 止める か停止ボタン。"


class Manager:
    def __init__(self, chats, runner, now=time.time, localtime=None, lesson=None):
        self.chats, self.runner, self.now = chats, runner, now
        self.localtime = localtime or datetime.datetime.fromtimestamp
        self.lesson = lesson
        self.lock = threading.RLock()
        self.active = {}
        self.closing = threading.Event()
        self.thread = None

    def start(self, cid, topic, interval=GAP, maximum=None):
        with self.lock:
            if cid in self.active or self.chats.get_state(cid).get("loop", {}).get("running"):
                raise ValueError("この会話の /loop は動いています。先に止めてください")
            state = {"running": True, "topic": topic, "interval": interval, "maximum": maximum,
                     "round": 0, "next": self.now(), "records": [], "generation": uuid.uuid4().hex}
            if not self.chats.load(cid)["やりとり"]:
                self.chats.add_turn(cid, "user", "【反復】" + topic)
            self.chats.update_state(cid, loop=state)
            self.chats.add_activity(cid, {"type": "loop", "text": start_message(topic, self.localtime(self.now()).hour)})
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
                if state.get("maximum") and state.get("round", 0) >= state["maximum"]:
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
            self.chats.add_activity(cid, {"type": "loop", "text": f"{state['round']}周目を開始: {state['topic']}"})
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
                    recent = current["records"][-3:]
                    if len(recent) == 3 and not any(r.get("ok") for r in recent):
                        current["next"] = self.now() + max(state["interval"], BACKOFF)
                        self.chats.add_activity(cid, {"type": "loop", "text": "3周続けて失敗したので、5分休んでから続けます"})
                    paused = self.closing.is_set() or self.localtime(self.now()).hour < 7
                    current["running"] = bool(current.get("running")) and (not stop.is_set() or paused) and not (state.get("maximum") and state["round"] >= state["maximum"])
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
