#!/usr/bin/env python3
"""Hugging Face に 頭脳（k160 の GGUF）と仕組み（公開リポジトリの写し）を公開する（10/5 本人）。
鍵はキーチェーン（AIBridge:HF_API_KEY）から承認ダイアログを通して取り、この台本の中だけで使う。値は出さない。
  python3 dougu/hf_dasu.py            # 作って上げる（公開）
本名・メールが混ざっていたら上げずに止まる。"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

KOUKAI = Path(__file__).resolve().parents[1]
MODEL = Path.home() / "LocalAI_mirror/models/Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf"
NAME = "intel-mac-local-llm"
# 確かめる名前は git の外（dougu/kekka/ng_namae.txt、正規表現1行）に置く。公開する台本に本名を書かない。
NG_FILE = KOUKAI / "dougu/kekka/ng_namae.txt"
NG = re.compile(NG_FILE.read_text(encoding="utf-8").strip(), re.I) if NG_FILE.is_file() else None


def main():
    sys.path.insert(0, str(Path.home() / ".claude/skills/ai-keychain/scripts"))
    import access_broker
    from huggingface_hub import HfApi
    if NG is None:
        sys.exit("dougu/kekka/ng_namae.txt が無いので止めます（本名の確かめができない）")
    token = access_broker.request_secret("HF_API_KEY", requester="Claude",
                                         reason="Hugging Face に intel-mac-local-llm（重みとコード）を公開する")
    if not token:
        sys.exit("鍵を取り出せませんでした（拒否か未登録）")
    api = HfApi(token=token)
    user = api.whoami()["name"]
    if NG.search(user):
        sys.exit("Hugging Face の名前に本名が入っているので止めます")
    repo = f"{user}/{NAME}"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "source"
        src.mkdir()
        archive = subprocess.run(["git", "-C", str(KOUKAI), "archive", "HEAD"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(src)], input=archive, check=True)
        hits = subprocess.run(["grep", "-rIl", "-i", "-E", NG.pattern, str(src)], capture_output=True, text=True).stdout.split()
        if hits or NG.search((KOUKAI / "hf/README.md").read_text(encoding="utf-8")):
            sys.exit(f"本名・メールが {len(hits)} ファイルに残っているので止めます: " + ", ".join(Path(h).name for h in hits[:5]))
        api.create_repo(repo, repo_type="model", private=False, exist_ok=True)
        print("置き場:", f"https://huggingface.co/{repo}", flush=True)
        api.upload_file(path_or_fileobj=str(KOUKAI / "hf/README.md"), path_in_repo="README.md", repo_id=repo,
                        commit_message="Model card")
        print("説明書を上げた", flush=True)
        api.upload_folder(folder_path=str(src), path_in_repo="source", repo_id=repo,
                          commit_message="Source: kernel, desktop app, tools (snapshot of the GitHub repo)")
        print("コード一式を上げた", flush=True)
    api.upload_file(path_or_fileobj=str(MODEL), path_in_repo=MODEL.name, repo_id=repo,
                    commit_message="Qwen3.6-35B-A3B UD-Q2_K_XL pruned to 160 experts")
    print("重みを上げた。公開:", f"https://huggingface.co/{repo}", flush=True)


def omomi():
    """10/5: 8.3GB の重みが2時間で上がりきらなかった。途中から続けられる upload_large_folder で上げる。説明書も上げ直す。"""
    import os
    sys.path.insert(0, str(Path.home() / ".claude/skills/ai-keychain/scripts"))
    import access_broker
    from huggingface_hub import HfApi
    if NG is None:
        sys.exit("dougu/kekka/ng_namae.txt が無いので止めます")
    token = access_broker.request_secret("HF_API_KEY", requester="Claude",
                                         reason="Hugging Face の intel-mac-local-llm に重み（8.3GB）を上げる続き")
    if not token:
        sys.exit("鍵を取り出せませんでした（拒否か未登録）")
    api = HfApi(token=token)
    repo = f"{api.whoami()['name']}/{NAME}"
    if NG.search((KOUKAI / "hf/README.md").read_text(encoding="utf-8")):
        sys.exit("説明書に本名が入っているので止めます")
    api.upload_file(path_or_fileobj=str(KOUKAI / "hf/README.md"), path_in_repo="README.md", repo_id=repo,
                    commit_message="Model card: drop an unverified claim")
    print("説明書を上げ直した", flush=True)
    stage = MODEL.parent / "hf_ageru"   # 同じディスクに固いリンク（写さない）。途中の記録も ここの .cache に残る
    stage.mkdir(exist_ok=True)
    target = stage / MODEL.name
    if not target.exists():
        os.link(MODEL, target)
    api.upload_large_folder(repo_id=repo, folder_path=str(stage), repo_type="model")
    print("重みを上げた。公開:", f"https://huggingface.co/{repo}", flush=True)


if __name__ == "__main__":
    omomi() if sys.argv[1:] == ["omomi"] else main()
