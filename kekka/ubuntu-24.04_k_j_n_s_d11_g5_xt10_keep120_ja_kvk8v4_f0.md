# ubuntu-24.04_k_j_n_s_d11_g5_xt10_keep120_ja_kvk8v4_f0  2026-09-28T22:34:55Z
```
llama.cpp b31b71f / koukai 0376f11 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t10_keep120_ja.env
メモリ上限 5 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: Intel(R) Xeon(R) 6973P-C
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         17.44 ± 2.05 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |          9.02 ± 0.46 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
15.06.206.627 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
15.06.206.628 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (84.38%)
15.06.206.629 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.94%)
15.06.206.630 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.84%)
15.06.206.631 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
15.06.206.633 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (65.62%)
15.06.206.633 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
15.06.206.634 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (87.50%)
15.06.206.635 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (87.50%)
15.06.206.635 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.84%)


較正 imatrix: ba7962d86a20dc7d219f3c53a94ac6b3ed56db07850399b28b9c8c96e390f24c  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 4027秒
専門家を 120 個に手術: 7.3G

## disk（page cache を捨ててから読む）
続けて読む 0.12 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 90 MB/s（685 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           pp512 |          7.68 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q4_0 |   1 |           tg128 |          2.48 ± 0.51 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 103429
基準比 pp512: 0.440（実験 / 基準）
基準比 tg128: 0.275（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 195614
15.28.546.748 I Final estimate: PPL = 8.0354 +/- 0.32090
探り: 読み 1.4 t/s（16字）・書き 2.5 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
