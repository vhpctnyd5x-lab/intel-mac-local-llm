#!/usr/bin/env python3
"""Cloud試験の引数・結果形式だけを一時領域で確認（Cloud・問題ファイル不使用）。"""
import argparse
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

DEFAULT_ARGS = "KOUKAI_VOCAB_KEEP=vocab_keep_9999_q36_ids.txt --spec-type none -cram 512"


def parse_config(opts, args, env_items):
    parsed_opts = json.loads(opts)
    if not isinstance(parsed_opts, dict):
        raise ValueError("--opts はJSON object")
    env = {}
    for item in env_items:
        key, sep, value = item.partition("=")
        if not sep or not (key.startswith("KERNEL_") or key.startswith("KOUKAI_")) or not key.replace("_", "").isalnum():
            raise ValueError("環境変数は KERNEL_* または KOUKAI_* の形式")
        env[key] = value
    return {"opts": parsed_opts, "args": shlex.split(args), "env": env}


def summarize(rows):
    clean = [{"id": str(row["id"]), "status": row["status"], "seconds": round(float(row["seconds"]), 3)} for row in rows]
    if any(row["status"] not in ("PASS", "FAIL", "SKIP") for row in clean):
        raise ValueError("不正な判定")
    return {"pass": sum(r["status"] == "PASS" for r in clean), "total": len(clean), "results": clean}


def selftest():
    here = Path(__file__).resolve().parent
    for name in ("hajimeru.sh", "mimamoru.sh", "vm_startup.sh"):
        subprocess.run(["bash", "-n", str(here / name)], check=True)
    startup = (here / "vm_startup.sh").read_text(encoding="utf-8")
    embedded = startup.split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    compile(embedded, "vm_startup.sh embedded runner", "exec")
    config = parse_config('{"raw_template":true}', DEFAULT_ARGS, ["KERNEL_JIYUU_OPTS={}", "KERNEL_TEST=2"])
    assert config["opts"] == {"raw_template": True}
    assert config["args"] == ["KOUKAI_VOCAB_KEEP=vocab_keep_9999_q36_ids.txt", "--spec-type", "none", "-cram", "512"]
    assert config["env"]["KERNEL_TEST"] == "2"
    result = summarize([{"id": "J01", "status": "PASS", "seconds": 1.23456}, {"id": "J02", "status": "FAIL", "seconds": 2}])
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "result.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        got = json.loads(path.read_text(encoding="utf-8"))
        assert got["pass"] == 1 and got["total"] == 2 and got["results"][0] == {"id": "J01", "status": "PASS", "seconds": 1.235}
    print("確認OK: 引数分解・環境変数・PASS/可否/秒JSON / Cloud操作0 / 問題ファイル0")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--opts", default='{"raw_template": true}')
    validate.add_argument("--args", default=DEFAULT_ARGS)
    validate.add_argument("--env", default="[]")
    sub.add_parser("test")
    args = parser.parse_args()
    if args.cmd == "test":
        selftest()
    else:
        env = json.loads(args.env)
        parse_config(args.opts, args.args, env)


if __name__ == "__main__":
    main()
