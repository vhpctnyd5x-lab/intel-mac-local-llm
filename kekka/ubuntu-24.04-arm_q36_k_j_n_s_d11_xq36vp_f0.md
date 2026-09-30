# ubuntu-24.04-arm_q36_k_j_n_s_d11_xq36vp_f0  2026-09-30T09:12:16Z
```
llama.cpp b31b71f / koukai 1856dfb / 問題 5961d8098783 / 頭脳 ed7cda7e3898
llama patch sha256 1ff93abaabe7
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/q36vp.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_9999_q36_ids.txt
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
Vendor ID:                               ARM
Model name:                              Neoverse-N2
               total        used        free      shared  buff/cache   available
Mem:              15           1          13           0           1          14
/dev/root       145G   37G  108G  26% /
```
語彙の照合 OK: 248070 語
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         14.52 ± 0.01 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         13.50 ± 0.05 |

build: b31b71f3a (10872)
MODEL_ARCH=qwen35moe
MODEL_EXPERTS=256
MODEL_EXPERTS_USED=8
MODEL_SHARED_FF=512
MODEL_HAS_SHARED=1

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q2_K - Medium |  11.70 GiB |    35.51 B | CPU        |       4 |           pp512 |         20.82 ± 0.65 |
| qwen35moe 35B.A3B Q2_K - Medium |  11.70 GiB |    35.51 B | CPU        |       4 |           tg128 |         11.34 ± 0.04 |

build: b31b71f3a (10872)
基準比 pp512: 1.434（実験 / 基準）
基準比 tg128: 0.840（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
6.31.972.150 I Final estimate: PPL = 6.5295 +/- 0.24364
MiMo 9B: /apply-template の enable_thinking=false を確認
探り: 読み 16.8 t/s（11字）・書き 11.1 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 92.0,
  "平均秒": 32.0
 },
 "正解率": 92.0,
 "平均秒": 32.0,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 8
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04-arm_q36_k_j_n_s_d11_xq36vp_f0.json
```
所要 5182秒
