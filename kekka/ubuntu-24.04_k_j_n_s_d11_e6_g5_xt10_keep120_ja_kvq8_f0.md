# ubuntu-24.04_k_j_n_s_d11_e6_g5_xt10_keep120_ja_kvq8_f0  2026-09-29T09:48:20Z
```
llama.cpp b31b71f / koukai d724dfa / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t10_keep120_ja.env
専門家数 6
メモリ上限 5 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         18.40 ± 4.74 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.63 ± 1.22 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
13.08.294.229 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
13.08.294.229 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (85.94%)
13.08.294.230 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.94%)
13.08.294.231 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
13.08.294.232 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
13.08.294.233 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
13.08.294.234 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
13.08.294.235 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (85.94%)
13.08.294.235 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (85.94%)
13.08.294.236 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 0517237453cee6085453ee29e88eb3c20e0841bea375262b2b2c4c00951696d5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 4794秒
専門家を 120 個に手術: 7.3G

## disk（page cache を捨ててから読む）
続けて読む 0.35 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 372 MB/s（2836 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           pp512 |         19.41 ± 2.87 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           tg128 |          5.58 ± 1.48 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 125321
基準比 pp512: 1.055（実験 / 基準）
基準比 tg128: 0.357（実験 / 基準）
（上の llama-bench は 専門家 8人のまま。6 人の速さは 下の「探り」）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 174796
9.33.030.746 I Final estimate: PPL = 8.0470 +/- 0.32163
探り: 読み 3.1 t/s（16字）・書き 4.9 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 68.0,
  "平均秒": 80.9
 },
 "正解率": 68.0,
 "平均秒": 80.9,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 5
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_e6_g5_xt10_keep120_ja_kvq8_f0.json
```
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 12665683
所要 17671秒
