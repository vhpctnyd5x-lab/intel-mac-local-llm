# ubuntu-24.04_q36_k_j_n_s_d11_xq36v_f0  2026-09-30T09:12:06Z
```
llama.cpp b31b71f / koukai 1856dfb / 問題 5961d8098783 / 頭脳 ed7cda7e3898
llama patch sha256 1ff93abaabe7
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/q36v.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_9999_q36_ids.txt
生成設定 temperature=0
runner "24.04.5 LTS (Noble Numbat)" gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cores 4
model name	: AMD EPYC 9V74 80-Core Processor
               total        used        free      shared  buff/cache   available
Mem:              15           1          12           0           2          14
/dev/root       145G   59G   86G  41% /
```
語彙の照合 OK: 248070 語
## 基準（同じ機械）pp512 / tg128
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           pp512 |         19.44 ± 0.00 |
| qwen3moe 30B.A3B Q2_K - Medium |  10.48 GiB |    30.53 B | CPU        |       4 |           tg128 |         14.70 ± 0.02 |

build: b31b71f3a (10872)
MODEL_ARCH=qwen35moe
MODEL_EXPERTS=256
MODEL_EXPERTS_USED=8
MODEL_SHARED_FF=512
MODEL_HAS_SHARED=1

## 速さ（llama-bench -t 4）
| model                          |       size |     params | backend    | threads |            test |                  t/s |
| ------------------------------ | ---------: | ---------: | ---------- | ------: | --------------: | -------------------: |
| qwen35moe 35B.A3B Q2_K - Medium |  11.70 GiB |    35.51 B | CPU        |       4 |           pp512 |         18.24 ± 0.27 |
| qwen35moe 35B.A3B Q2_K - Medium |  11.70 GiB |    35.51 B | CPU        |       4 |           tg128 |          9.12 ± 0.03 |

build: b31b71f3a (10872)
基準比 pp512: 0.938（実験 / 基準）
基準比 tg128: 0.620（実験 / 基準）

## PPL（llama-perplexity -c 512 --chunks 16）
8.28.393.929 I Final estimate: PPL = 6.5230 +/- 0.24322
MiMo 9B: /apply-template の enable_thinking=false を確認
探り: 読み 10.3 t/s（11字）・書き 8.9 t/s（128字）

## 7段 深さ0 0問（0=全部）
```
 "段11": {
  "件": 125,
  "正解率": 92.8,
  "平均秒": 40.3
 },
 "正解率": 92.8,
 "平均秒": 40.3,
 "平均考えた字数": 0,
 "しくじり件数": 0,
 "形式違反(ゆるい採点)": 8
}
→ /home/runner/work/localai-16gb/localai-16gb/kekka_actions/7dan_ubuntu-24.04_q36_k_j_n_s_d11_xq36v_f0.json
```
所要 6374秒
