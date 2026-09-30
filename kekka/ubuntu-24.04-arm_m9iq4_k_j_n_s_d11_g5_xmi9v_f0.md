# ubuntu-24.04-arm_m9iq4_k_j_n_s_d11_g5_xmi9v_f0  2026-09-30T07:38:37Z
```
llama.cpp b31b71f / koukai 7a9aa0c / 問題 5961d8098783 / 頭脳 eccfbc188e71
llama patch sha256 1ff93abaabe7
実験 /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/mi9v.env
vocab keep /home/runner/work/localai-16gb/localai-16gb/dougu/jikken/vocab_keep_9999_mimo9_ids.txt
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
語彙の照合失敗: 語彙数が違います: ファイル 248077 / GGUF 248320
失敗: exit=2 行=340 命令=python3 "$K/dougu/gguf_vocab.py" "$VOCAB_KEEP_PATH" "${ATAMA:-qwen3}" "$M" >> "$OUT" 2>&1
