# ubuntu-24.04_k_j_n_s_d11_g5_xt12_keep120_ja_edp70_kvq8_f0  2026-09-29T10:15:13Z
```
llama.cpp b31b71f / koukai 8628228 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t12_keep120_ja_edp70.env
メモリ上限 5 GB（swap なし、mmap ページキャッシュを含む）
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 7763 64-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           0          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.61 ± 0.02 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         15.14 ± 0.08 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
16.03.398.575 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
16.03.398.577 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (86.72%)
16.03.398.577 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.16%)
16.03.398.578 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
16.03.398.579 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
16.03.398.580 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
16.03.398.581 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
16.03.398.582 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (88.28%)
16.03.398.583 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (88.28%)
16.03.398.583 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 2eb5aa7c1922effc2068f555dcf83bb398b3b8a6afa74297f9a97092da3344e5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 5240秒
専門家を 120 個に手術: 7.3G

## disk（page cache を捨ててから読む）
続けて読む 0.44 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 341 MB/s（2603 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           pp512 |         18.63 ± 0.15 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           tg128 |          6.87 ± 0.91 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 146528
基準比 pp512: 0.950（実験 / 基準）
基準比 tg128: 0.454（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 203132
9.47.411.099 I Final estimate: PPL = 7.9591 +/- 0.31706
探り: 読み 3.2 t/s（16字）・書き 5.4 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 79.2,
  "平均秒": 77.9
 },
 "正解率": 79.2,
 "平均秒": 77.9,
 "平均考えた字数": 0,
 "しくじり件数": 1,
 "形式違反(ゆるい採点)": 1
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_g5_xt12_keep120_ja_edp70_kvq8_f0.json
```
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 17787207
所要 17811秒
