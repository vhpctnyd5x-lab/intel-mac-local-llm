# ubuntu-24.04-arm_m9q4_k_j_n_s_d11_f0  2026-09-29T13:13:23Z
```
llama.cpp b31b71f / koukai 92e1d2d / 問題 5961d8098783 / 頭脳 4bca6f18c73f
llama patch sha256 fc146c2e6569
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.54 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.39 ± 0.07 |

build: b31b71f3a (10872)

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35 9B Q4_K - Medium        |   5.43 GiB |     8.95 B | CPU        |       4 |           pp512 |         22.18 ± 0.02 |
| qwen35 9B Q4_K - Medium        |   5.43 GiB |     8.95 B | CPU        |       4 |           tg128 |          6.09 ± 0.10 |

build: b31b71f3a (10872)
基準比 pp512: 1.525（実験 / 基準）
基準比 tg128: 0.455（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.40.479.395 I Final estimate: PPL = 6.8231 +/- 0.25802
MiMo 9B: /apply-template の enable_thinking=false を確認
探り: 読み 10.0 t/s（11字）・書き 6.3 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 75.2,
  "平均秒": 24.9
 },
 "正解率": 75.2,
 "平均秒": 24.9,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 0
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_m9q4_k_j_n_s_d11_f0.json
```
所要 4336秒
