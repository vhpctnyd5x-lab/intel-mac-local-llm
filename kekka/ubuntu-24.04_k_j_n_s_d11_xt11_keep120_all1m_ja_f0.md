# ubuntu-24.04_k_j_n_s_d11_xt11_keep120_all1m_ja_f0  2026-09-28T08:14:18Z
```
llama.cpp b31b71f / koukai fff2a6f / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t11_keep120_all1m_ja.env
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.36 ± 0.03 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.44 ± 0.04 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
16.20.191.266 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
16.20.191.267 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (86.72%)
16.20.191.268 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.16%)
16.20.191.270 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.06%)
16.20.191.271 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
16.20.191.274 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
16.20.191.275 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
16.20.191.276 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (88.28%)
16.20.191.277 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (88.28%)
16.20.191.278 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.06%)


較正 imatrix: 2eb5aa7c1922effc2068f555dcf83bb398b3b8a6afa74297f9a97092da3344e5  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 6.7G / 所要 7741秒
専門家を 120 個に手術: 6.3G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   6.24 GiB |    28.72 B | CPU        |       4 |           pp512 |         23.90 ± 0.04 |
| qwen3moe 30B.A3B Q2_K - Medium |   6.24 GiB |    28.72 B | CPU        |       4 |           tg128 |          8.87 ± 0.01 |

build: b31b71f3a (10872)
基準比 pp512: 1.235（実験 / 基準）
基準比 tg128: 0.614（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.41.484.882 I Final estimate: PPL = 9.1319 +/- 0.37238
探り: 読み 12.2 t/s（16字）・書き 6.2 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 60.0,
  "平均秒": 33.0
 },
 "正解率": 60.0,
 "平均秒": 33.0,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 10
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xt11_keep120_all1m_ja_f0.json
```
所要 14275秒
