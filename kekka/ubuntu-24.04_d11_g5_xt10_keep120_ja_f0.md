# ubuntu-24.04_d11_g5_xt10_keep120_ja_f0  2026-09-28T20:24:21Z
```
llama.cpp b31b71f / koukai 0376f11 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t10_keep120_ja.env
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         29.02 ± 9.87 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         21.30 ± 0.44 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
8.46.416.029 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
8.46.416.030 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (85.94%)
8.46.416.031 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.94%)
8.46.416.032 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
8.46.416.033 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
8.46.416.035 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
8.46.416.036 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
8.46.416.037 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (85.94%)
8.46.416.037 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (85.94%)
8.46.416.038 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 0517237453cee6085453ee29e88eb3c20e0841bea375262b2b2c4c00951696d5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 2876秒
専門家を 120 個に手術: 7.3G

## disk（page cache を捨ててから読む）
続けて読む 0.43 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 399 MB/s（3046 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |           pp512 |         37.99 ± 1.21 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |           tg128 |         10.10 ± 1.39 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 133799
基準比 pp512: 1.309（実験 / 基準）
基準比 tg128: 0.474（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 149126
4.31.166.789 I Final estimate: PPL = 8.0657 +/- 0.32243

## 起動指定の比べ（7段 深さ0 16問ずつ、同じ問題）
| 名前 | 指定 | 正解率 | 平均秒 |
|---|---|---|---|
探り: 読み 2.6 t/s（16字）・書き 8.5 t/s（128字）
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 2335699
| moto | `--spec-type ngram-simple --spec-ngram-simple-size-m 16` | 100.0 | 55.3 |
探り: 読み 3.1 t/s（16字）・書き 8.3 t/s（128字）
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 1187389
| kvk8v4 | `--spec-type ngram-simple --spec-ngram-simple-size-m 16 -fa on -ctk q8_0 -ctv q4_0` | 100.0 | 34.9 |
探り: 読み 3.0 t/s（16字）・書き 8.7 t/s（128字）
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 999064
| c4096_kvk8v4 | `--spec-type ngram-simple --spec-ngram-simple-size-m 16 -c 4096 -fa on -ctk q8_0 -ctv q4_0` | 100.0 | 32.0 |
所要 6748秒
