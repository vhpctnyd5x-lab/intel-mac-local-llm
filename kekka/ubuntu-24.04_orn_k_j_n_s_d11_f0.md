# ubuntu-24.04_orn_k_j_n_s_d11_f0  2026-09-30T07:38:35Z
```
llama.cpp b31b71f / koukai 7a9aa0c / 問題 5961d8098783 / 頭脳 be92ed1eb2da
llama patch sha256 1ff93abaabe7
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
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.50 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.80 ± 0.04 |

build: b31b71f3a (10872)
MODEL_ARCH=qwen35moe
MODEL_EXPERTS=256
MODEL_EXPERTS_USED=8
MODEL_SHARED_FF=512
MODEL_HAS_SHARED=1

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35moe 35B.A3B IQ2_M - 2.7 bpw |  11.67 GiB |    35.51 B | CPU        |       4 |           pp512 |         24.26 ± 0.08 |
| qwen35moe 35B.A3B IQ2_M - 2.7 bpw |  11.67 GiB |    35.51 B | CPU        |       4 |           tg128 |          8.71 ± 0.07 |

build: b31b71f3a (10872)
基準比 pp512: 1.244（実験 / 基準）
基準比 tg128: 0.589（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.26.618.382 I Final estimate: PPL = 8.1288 +/- 0.32954
MiMo 9B: /apply-template の enable_thinking=false を確認
探り: 読み 11.6 t/s（11字）・書き 8.6 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 86.4,
  "平均秒": 27.5
 },
 "正解率": 86.4,
 "平均秒": 27.5,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 1
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_orn_k_j_n_s_d11_f0.json
```
所要 4847秒
