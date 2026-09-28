# ubuntu-24.04_k_j_n_s_d11_xt11_keep120_mid32_1m_ja_f0  2026-09-28T08:14:15Z
```
llama.cpp b31b71f / koukai fff2a6f / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t11_keep120_mid32_1m_ja.env
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: INTEL(R) XEON(R) PLATINUM 8573C
               total        used        free      shared  buff/cache   available
Mem:              15           1          11           0           2          14
/dev/root       145G   59G   86G  41% /
```
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         23.49 ± 0.41 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         12.99 ± 0.16 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
12.34.781.931 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
12.34.781.932 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (84.38%)
12.34.781.933 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (85.94%)
12.34.781.934 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (89.84%)
12.34.781.934 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
12.34.781.936 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (65.62%)
12.34.781.937 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (86.72%)
12.34.781.938 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (87.50%)
12.34.781.938 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (87.50%)
12.34.781.939 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (89.84%)


較正 imatrix: ba7962d86a20dc7d219f3c53a94ac6b3ed56db07850399b28b9c8c96e390f24c  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.0G / 所要 6181秒
専門家を 120 個に手術: 6.6G

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   6.57 GiB |    28.72 B | CPU        |       4 |           pp512 |         37.47 ± 0.16 |
| qwen3moe 30B.A3B Q2_K - Medium |   6.57 GiB |    28.72 B | CPU        |       4 |           tg128 |          9.57 ± 0.13 |

build: b31b71f3a (10872)
基準比 pp512: 1.595（実験 / 基準）
基準比 tg128: 0.737（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
4.13.513.366 I Final estimate: PPL = 8.5733 +/- 0.34516
探り: 読み 15.6 t/s（16字）・書き 8.9 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 66.4,
  "平均秒": 29.5
 },
 "正解率": 66.4,
 "平均秒": 29.5,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 13
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_k_j_n_s_d11_xt11_keep120_mid32_1m_ja_f0.json
```
所要 11840秒
