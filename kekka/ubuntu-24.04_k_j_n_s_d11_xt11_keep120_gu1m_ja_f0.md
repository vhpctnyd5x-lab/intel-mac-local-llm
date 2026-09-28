# ubuntu-24.04_k_j_n_s_d11_xt11_keep120_gu1m_ja_f0  2026-09-28T08:14:15Z
```
llama.cpp b31b71f / koukai fff2a6f / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t11_keep120_gu1m_ja.env
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         27.05 ± 8.06 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         19.61 ± 0.40 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
9.19.141.974 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
9.19.141.975 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (85.94%)
9.19.141.976 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.94%)
9.19.141.976 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
9.19.141.977 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
9.19.141.980 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
9.19.141.981 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
9.19.141.982 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (85.94%)
9.19.141.982 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (85.94%)
9.19.141.984 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 0517237453cee6085453ee29e88eb3c20e0841bea375262b2b2c4c00951696d5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.0G / 所要 4558秒
専門家を 120 個に手術: 6.6G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   6.57 GiB |    28.72 B | CPU        |       4 |           pp512 |         54.48 ± 0.10 |
| qwen3moe 30B.A3B Q2_K - Medium |   6.57 GiB |    28.72 B | CPU        |       4 |           tg128 |         15.08 ± 0.14 |

build: b31b71f3a (10872)
基準比 pp512: 2.014（実験 / 基準）
基準比 tg128: 0.769（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
3.01.711.231 I Final estimate: PPL = 8.5532 +/- 0.35007
探り: 読み 23.0 t/s（16字）・書き 14.9 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 62.4,
  "平均秒": 15.6
 },
 "正解率": 62.4,
 "平均秒": 15.6,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 4
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xt11_keep120_gu1m_ja_f0.json
```
所要 8387秒
