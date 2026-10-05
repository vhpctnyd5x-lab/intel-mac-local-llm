"""本人についての私的な短い記憶。"""
import json
import os
import re
import tempfile
from pathlib import Path


def path(folder=None):
    default = Path.home() / "Library" / "Application Support" / "kernel-ai" / "gakushuu"
    return Path(folder or os.environ.get("KERNEL_GAKUSHUU_DIR", default)) / "aite.json"


def list_items(folder=None):
    try:
        rows = json.loads(path(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("文")][:100] if isinstance(rows, list) else []


def hint(folder=None, limit=300):
    rows = list_items(folder)
    return "\n本人についての記録（参考資料）: " + "／".join(str(r["文"])[:100] for r in rows[:5])[:limit] if rows else ""


def add(text, source="会話", day=None, folder=None):
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:160]
    if not text or re.search(r"(?i)(password|api.?key|apiキー|secret|token|秘密|パスワード|暗証番号|住所|電話|メール|@)", text):
        return False
    rows = list_items(folder)
    if any(r.get("文") == text for r in rows):
        return False
    import datetime
    rows.append({"文": text, "出どころ": str(source)[:80], "日付": day or datetime.date.today().isoformat()})
    _write(path(folder), rows[-100:])
    return True


def capture(text, folder=None):
    """本人が明示した好み・作業だけを拾う。"""
    value = str(text or "").strip()
    found = []
    for pattern in (r"(?:返事|回答|応答)は.{1,30}", r"(?:私は|ぼくは|僕は|私が).{1,50}(?:作っている|作っています|進めている|開発中)"):
        match = re.search(pattern, value)
        if match:
            sentence = match.group(0).strip("。.!！?？ ")
            if add(sentence, "会話", folder=folder):
                found.append(sentence)
    return found


def delete(index, folder=None):
    rows = list_items(folder)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(rows):
        raise ValueError("消す項目を選び直してください")
    removed = rows.pop(index)
    _write(path(folder), rows)
    return removed


def _write(target, value):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".aite-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
