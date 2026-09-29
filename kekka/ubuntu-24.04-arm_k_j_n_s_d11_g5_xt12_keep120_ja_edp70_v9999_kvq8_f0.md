# ubuntu-24.04-arm_k_j_n_s_d11_g5_xt12_keep120_ja_edp70_v9999_kvq8_f0  2026-09-29T10:15:18Z
```
llama.cpp b31b71f / koukai 8628228 / 問題 5961d8098783 / 頭脳 a68fe7343b0c
llama patch sha256 fc146c2e6569
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/t12_keep120_ja_edp70_v9999.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_9999_ids.txt
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.61 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.80 ± 0.03 |

build: b31b71f3a (10872)
配布 imatrix: revision=d5b1d57bd0b504ac62ae6c725904e96ef228dc74 sha256=99727c239f7061af66902cb42e2e4612c554fc44d9cc21caee0fdfa767a341de
較正: ja / 配布Q2_K由来 / c512 chunks32 / bd9c0eedcad223180b1b9f1705ea9f9a72e7ce596c447d9356b2d624f1a4e780  /home/runner/work/_temp/hakaru/calib_ja.txt
19.43.150.675 W save_imatrix: entry '                blk.0.ffn_up_exps.weight' has partial data (83.59%)
19.43.150.676 W save_imatrix: entry '             blk.28.ffn_down_exps.weight' has partial data (85.94%)
19.43.150.677 W save_imatrix: entry '             blk.20.ffn_down_exps.weight' has partial data (84.38%)
19.43.150.678 W save_imatrix: entry '               blk.31.ffn_up_exps.weight' has partial data (86.72%)
19.43.150.679 W save_imatrix: entry '              blk.7.ffn_gate_exps.weight' has partial data (91.41%)
19.43.150.681 W save_imatrix: entry '             blk.46.ffn_gate_exps.weight' has partial data (67.97%)
19.43.150.681 W save_imatrix: entry '              blk.5.ffn_down_exps.weight' has partial data (85.94%)
19.43.150.683 W save_imatrix: entry '               blk.30.ffn_up_exps.weight' has partial data (88.28%)
19.43.150.683 W save_imatrix: entry '             blk.30.ffn_down_exps.weight' has partial data (88.28%)
19.43.150.684 W save_imatrix: entry '             blk.31.ffn_down_exps.weight' has partial data (86.72%)


較正 imatrix: f30ff566a36e3269580eb5c5a63a47fc1a6029bac2e9d1f50fc9518fe01f7641  /home/runner/work/_temp/hakaru/imatrix_ja.gguf
作り直し: Q2_K / 7.7G / 所要 2307秒
専門家を 120 個に手術: 7.3G

## disk（page cache を捨ててから読む）
続けて読む 0.44 GB/s（先頭 2048 MiB）・飛び飛びに 128KiB を 2000 回 415 MB/s（3167 回/秒）

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads | type_k | type_v |  fa |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | -----: | -----: | --: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           pp512 |         13.06 ± 0.09 |
| qwen3moe 30B.A3B Q2_K - Medium |   7.23 GiB |    28.72 B | CPU        |       4 |   q8_0 |   q8_0 |   1 |           tg128 |         10.38 ± 1.10 |

build: b31b71f3a (10872)
llama-bench cgroup memory.peak: 5368709120 bytes; pgmajfault: 113064
基準比 pp512: 0.894（実験 / 基準）
基準比 tg128: 0.752（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
llama-perplexity cgroup memory.peak: 5368709120 bytes; pgmajfault: 312633
11.00.290.306 I Final estimate: PPL = 8.0527 +/- 0.32065
探り: 読み 2.6 t/s（16字）・書き 9.2 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 76.8,
  "平均秒": 67.7
 },
 "正解率": 76.8,
 "平均秒": 67.7,
 "平均考えた字数": 0,
 "しくじり件数": 3,
 "形式違反(ゆるい採点)": 2
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_k_j_n_s_d11_g5_xt12_keep120_ja_edp70_v9999_kvq8_f0.json
```
llama-server cgroup memory.peak: 5368709120 bytes; pgmajfault: 15521650
所要 13941秒
