# ubuntu-24.04_m9iq4_k_j_n_s_d11_g5_xmi9v_f0  2026-09-30T08:47:06Z
```
llama.cpp b31b71f / koukai 119863a / 問題 5961d8098783 / 頭脳 eccfbc188e71
llama patch sha256 1ff93abaabe7
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/mi9v.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_9999_mimo9_ids.txt
メモリ上限 5 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
語彙の照合 OK: 248077 語
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.46 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.76 ± 0.08 |

build: b31b71f3a (10872)
MODEL_ARCH=qwen35
MODEL_EXPERTS=0
MODEL_EXPERTS_USED=0
MODEL_SHARED_FF=0
MODEL_HAS_SHARED=0

## disk（page cache を捨ててから読む）
続けて読む 0.43 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 423 MB/s（3227 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 9B IQ4_XS - 4.25 bpw    |   4.86 GiB |     8.95 B | CPU        |       4 |           pp512 |         13.49 ± 0.04 |
| qwen35 9B IQ4_XS - 4.25 bpw    |   4.86 GiB |     8.95 B | CPU        |       4 |           tg128 |          5.20 ± 0.03 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 8446
基準比 pp512: 0.693（実験 / 基準）
基準比 tg128: 0.352（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 106012
11.28.632.546 I Final estimate: PPL = 6.8400 +/- 0.25854
MiMo 9B: /apply-template の enable_thinking=false を確認
探り: 読み 6.0 t/s（11字）・書き 5.2 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
  "件": 8,
  "正解率": 62.5,
  "平均秒": 131.7
 },
 "正解率": 62.5,
 "平均秒": 131.7,
 "平均考えた字数": 0,
 "打ち切り": "8/125問: 8問の平均 131.7 秒から全件が期限超過と見積もった",
 "しくじり件数": 3,
 "形式違反(ゆるい採点)": 0
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_m9iq4_k_j_n_s_d11_g5_xmi9v_f0.json
```
打ち切り: 8/125問: 8問の平均 131.7 秒から全件が期限超過と見積もった / 正解率 62.5% / 平均秒 131.7
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 3352906
所要 2544秒
