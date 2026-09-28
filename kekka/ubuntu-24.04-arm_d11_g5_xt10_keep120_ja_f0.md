# ubuntu-24.04-arm_d11_g5_xt10_keep120_ja_f0  2026-09-28T20:24:22Z
```
llama.cpp b31b71f / koukai 0376f11 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t10_keep120_ja.env
メモリ上限 5 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   37G  108G  26% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.58 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.68 ± 0.03 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
19.48.382.799 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
19.48.382.800 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (85.94%)
19.48.382.801 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (84.38%)
19.48.382.802 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (86.72%)
19.48.382.802 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
19.48.382.804 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
19.48.382.805 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (85.94%)
19.48.382.806 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (88.28%)
19.48.382.807 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (88.28%)
19.48.382.808 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (86.72%)


較正 imatrix: f30ff566a36e3269580eb5c5a63a47fc1a6029bac2e9d1f50fc9518fe01f7641  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 2343秒
専門家を 120 個に手術: 7.3G

## disk（page cache を捨ててから読む）
続けて読む 0.39 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 377 MB/s（2874 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |           pp512 |         11.41 ± 0.36 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |           tg128 |          8.80 ± 0.98 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 118623
基準比 pp512: 0.783（実験 / 基準）
基準比 tg128: 0.643（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 327825
12.32.877.540 I Final estimate: PPL = 8.0892 +/- 0.32298

## 起動指定の比べ（7段 深さ0 16問ずつ、同じ問題）
| 名前 | 指定 | 正解率 | 平均秒 |
|---|---|---|---|
探り: 読み 2.8 t/s（16字）・書き 6.6 t/s（128字）
llama-server cgroup memory.peak: 5368713216 bytes; pgmajfault: 1962923
| moto | `--spec-type ngram-simple --spec-ngram-simple-size-m 16` | 93.8 | 53.6 |
探り: 読み 3.6 t/s（16字）・書き 7.6 t/s（128字）
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 1115539
| kvk8v4 | `--spec-type ngram-simple --spec-ngram-simple-size-m 16 -fa on -ctk q8_0 -ctv q4_0` | 93.8 | 40.4 |
探り: 読み 3.2 t/s（16字）・書き 8.0 t/s（128字）
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 947633
| c4096_kvk8v4 | `--spec-type ngram-simple --spec-ngram-simple-size-m 16 -c 4096 -fa on -ctk q8_0 -ctv q4_0` | 93.8 | 38.7 |
所要 7623秒
