# ubuntu-24.04_k_j_n_s_d11_g5_xt10_keep120_ja_kvq8_f0  2026-09-29T04:16:52Z
```
llama.cpp b31b71f / koukai 1c72df8 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t10_keep120_ja.env
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.63 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.11 ± 0.07 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
16.02.022.721 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
16.02.022.723 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (86.72%)
16.02.022.724 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.16%)
16.02.022.725 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
16.02.022.726 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
16.02.022.729 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
16.02.022.730 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
16.02.022.731 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (88.28%)
16.02.022.732 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (88.28%)
16.02.022.733 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 2eb5aa7c1922effc2068f555dcf83bb398b3b8a6afa74297f9a97092da3344e5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 5240秒
専門家を 120 個に手術: 7.3G

## disk（page cache を捨ててから読む）
続けて読む 0.43 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 406 MB/s（3099 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           pp512 |         19.34 ± 0.14 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           tg128 |          7.10 ± 0.59 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 145474
基準比 pp512: 0.985（実験 / 基準）
基準比 tg128: 0.470（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 200736
9.28.783.918 I Final estimate: PPL = 7.9749 +/- 0.31805
探り: 読み 3.5 t/s（16字）・書き 6.1 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 77.6,
  "平均秒": 75.5
 },
 "正解率": 77.6,
 "平均秒": 75.5,
 "平均考えた字数": 0,
 "しくじり件数": 1,
 "形式違反(ゆるい採点)": 1
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_g5_xt10_keep120_ja_kvq8_f0.json
```
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 17682605
所要 17568秒
