# ubuntu-24.04_k_j_n_s_d11_g5_xt11_keep120_all1s_ja_f0  2026-09-28T14:31:32Z
```
llama.cpp b31b71f / koukai 27b8588 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t11_keep120_all1s_ja.env
メモリ上限 5 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V45 96-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          11           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         28.37 ± 9.36 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         21.45 ± 0.59 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
8.58.055.475 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
8.58.055.476 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (85.94%)
8.58.055.476 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.94%)
8.58.055.477 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
8.58.055.477 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
8.58.055.479 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
8.58.055.480 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
8.58.055.480 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (85.94%)
8.58.055.481 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (85.94%)
8.58.055.481 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 0517237453cee6085453ee29e88eb3c20e0841bea375262b2b2c4c00951696d5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 6.0G / 所要 1379秒
専門家を 120 個に手術: 5.7G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   5.65 GiB |    28.72 B | CPU        |       4 |           pp512 |         47.32 ± 1.61 |
| qwen3moe 30B.A3B Q2_K - Medium |   5.65 GiB |    28.72 B | CPU        |       4 |           tg128 |         13.99 ± 1.20 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 66338
基準比 pp512: 1.668（実験 / 基準）
基準比 tg128: 0.652（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 106094
3.57.823.119 I Final estimate: PPL = 9.8707 +/- 0.39941
探り: 読み 3.8 t/s（16字）・書き 9.8 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
