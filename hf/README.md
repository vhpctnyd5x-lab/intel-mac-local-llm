---
license: apache-2.0
base_model: Qwen/Qwen3.6-35B-A3B
language:
- ja
- en
tags:
- gguf
- llama.cpp
- moe
- expert-pruning
- intel-mac
- cpu
- local-agent
pipeline_tag: text-generation
---

# Intel Mac Local LLM — 古い Mac で動く「育つ AI」

**16GB・GPU なしの Intel Mac** で、手元の AI に Mac の仕事（ファイルの整理・読み書き・状態の確認・調べもの）をさせるための
**頭脳（重み）** と **仕組み（カーネル・デスクトップアプリ）** 一式です。合言葉は「早い・安い・賢い」。

- GitHub（同じ中身・最新）: https://github.com/vhpctnyd5x-lab/intel-mac-local-llm
- このページの `source/` は、その公開リポジトリの写しです。

*English summary: An expert-pruned GGUF of Qwen3.6-35B-A3B (256 → 160 experts per layer, 8.29 GB) that fits a 16 GB Intel Mac without GPU,
plus the agent kernel (sandboxed tools, approval gate, self-learning) and the macOS desktop app source. Measured on an i7-9750H / 16 GB.*

## 頭脳: `Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf`（8.29GB / 7.7GiB）

| | 元（256人） | この版（160人） |
|---|---|---|
| 大きさ | 12.57GB（11.7GiB） | **8.29GB（7.7GiB）** |
| 常駐メモリ（実測） | 9.6〜10.0GB | **8.0〜8.2GB** |
| 書く速さ（300字×3回） | 8.3〜8.6 字/秒 | 8.1〜9.1 字/秒（変わらない） |
| 知識の問い 25問 | 24/25 | 23/25 |
| PC 操作の回帰テスト 41問 | — | 36〜39/41（回ごとに±2問ぶれる） |

すべて Intel Core i7-9750H・16GB・GPU なしで測った数字です。1回の数字は1回の数字として見てください。

**作り方**: 元は [unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF) の UD-Q2_K_XL。
校正文で imatrix を取り、**層ごとに使われる順で専門家を160人だけ残し**、MTP 層も外しました（手順は `source/dougu/kezuru_tejun.py`）。
重みの値そのものは変えていません（量子化は元のまま）。

**動かし方**: 動作を確かめたのは、llama.cpp に `source/llama_patch/` を当てて建てた llama-server です
（語彙を 99.99% に絞る改造が入っています）。手順は `source/README.md`。素の llama.cpp で読み込めるかは確かめていません。

```sh
llama-server -m Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf -t 6 -ngl 0 -c 32768 -np 2 -kvu --no-cache-idle-slots \
  -cb -cram 512 --cache-reuse 16 -fa off --reasoning-format none
```

## 仕組み（`source/`）

- **カーネル**（`source/kernel/`）: 頭脳が呼ぶ道具と、危ない操作を止める門番。命令は macOS の `sandbox-exec`（Linux は bubblewrap）で隔離し、
  消す・送るなどは本人の承認が要ります。会話ごとに「触ってよいフォルダ」を選べます。
- **デスクトップアプリ**: `source/kernel/tools/kernel_window.swift`（窓）と `source/kernel/ui.html`（画面）。会話・動きの欄・文脈の量・/compact・/loop・/整理。
- **事前学習**: 空いた時間に Wikipedia・教科書・文学・法令・論文を読み、知識の箱と学習ノートに貯めて答えに使います。興味が出た事を重点的に読みます。
- **育つ AI**: 芯・感情の記憶・日記・相手の記憶・自作スキル（要る/要らないを自分で決める）。

## ライセンス

重みは元と同じ **Apache License 2.0**（Qwen3.6 の著作権表示は元の模型に従います。変更点は上の「作り方」）。
コード（`source/`）は **MIT License**（`source/LICENSE`）。
