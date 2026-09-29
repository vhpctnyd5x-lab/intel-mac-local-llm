# ubuntu-24.04_m9iq3_k_j_n_s_d11_g5_f0  2026-09-29T13:13:23Z
```
llama.cpp b31b71f / koukai 92e1d2d / 問題 5961d8098783 / 頭脳 e2638eb0a375
llama patch sha256 fc146c2e6569
メモリ上限 5 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.06 ± 0.08 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         12.52 ± 0.27 |

build: b31b71f3a (10872)

## disk（page cache を捨ててから読む）
続けて読む 0.44 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 323 MB/s（2466 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 9B IQ3_S mix - 3.66 bpw |   4.50 GiB |     8.95 B | CPU        |       4 |           pp512 |          9.51 ± 0.04 |
| qwen35 9B IQ3_S mix - 3.66 bpw |   4.50 GiB |     8.95 B | CPU        |       4 |           tg128 |          2.43 ± 0.04 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 177
基準比 pp512: 0.499（実験 / 基準）
基準比 tg128: 0.194（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 52849
16.32.883.344 I Final estimate: PPL = 7.0969 +/- 0.26974
MiMo 9B: /apply-template の enable_thinking=false を確認
探り: 読み 2.8 t/s（11字）・書き 2.5 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
