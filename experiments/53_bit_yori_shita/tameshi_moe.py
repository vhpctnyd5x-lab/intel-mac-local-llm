#!/usr/bin/env python3
"""流れの確かめ用に、乱数の重みの小さな MoE（qwen3moe 形・8専門家・2層）の GGUF を作る。

賢さは無い。imatrix → 量子化（Q2_K / IQ1_M）→ b1_mazeru.py tsukuru → llama-perplexity が
最後まで通るかだけを、本物の模型を落とす前に確かめる（「大量実行の前に1本を完走させる」）。
ルータの行ごとに大きさを変えて、専門家の使われ方に偏りをつけてある。

  PYTHONPATH=llama.cpp/gguf-py python3 tameshi_moe.py out.gguf
"""
import sys

import numpy as np

import gguf

N_EMBD, N_FF, N_EXP, N_USED, N_LAYER, N_HEAD, N_KV, HEAD = 256, 256, 8, 2, 2, 4, 2, 64


def main(out):
    rng = np.random.default_rng(0)
    w = gguf.GGUFWriter(out, "qwen3moe")
    w.add_name("tameshi-moe")
    w.add_block_count(N_LAYER)
    w.add_context_length(512)
    w.add_embedding_length(N_EMBD)
    w.add_feed_forward_length(N_FF)
    w.add_head_count(N_HEAD)
    w.add_head_count_kv(N_KV)
    w.add_key_length(HEAD)
    w.add_value_length(HEAD)
    w.add_rope_freq_base(10000.0)
    w.add_layer_norm_rms_eps(1e-6)
    w.add_expert_count(N_EXP)
    w.add_expert_used_count(N_USED)
    w.add_expert_feed_forward_length(N_FF)
    w.add_file_type(gguf.LlamaFileType.ALL_F32)

    # SentencePiece 形の語彙: 特別な3つ＋バイト256個＋よく出る語少し
    words = ["▁the", "▁a", "▁of", "▁and", "▁to", "▁in", "▁is", "▁it", "e", "t", "▁"]
    toks = ["<unk>", "<s>", "</s>"] + [f"<0x{i:02X}>" for i in range(256)] + words
    types = [2, 3, 3] + [6] * 256 + [1] * len(words)
    w.add_tokenizer_model("llama")
    w.add_tokenizer_pre("default")
    w.add_token_list(toks)
    w.add_token_scores([0.0] * 259 + [-float(i) for i in range(len(words))])
    w.add_token_types(types)
    w.add_unk_token_id(0)
    w.add_bos_token_id(1)
    w.add_eos_token_id(2)
    w.add_add_bos_token(True)
    n_vocab = len(toks)

    def r(*shape, s=0.05):
        return (rng.standard_normal(shape) * s).astype(np.float32)

    w.add_tensor("token_embd.weight", r(n_vocab, N_EMBD, s=0.5))
    w.add_tensor("output_norm.weight", np.ones(N_EMBD, np.float32))
    w.add_tensor("output.weight", r(n_vocab, N_EMBD))
    for i in range(N_LAYER):
        p = f"blk.{i}."
        w.add_tensor(p + "attn_norm.weight", np.ones(N_EMBD, np.float32))
        w.add_tensor(p + "attn_q.weight", r(N_HEAD * HEAD, N_EMBD))
        w.add_tensor(p + "attn_k.weight", r(N_KV * HEAD, N_EMBD))
        w.add_tensor(p + "attn_v.weight", r(N_KV * HEAD, N_EMBD))
        w.add_tensor(p + "attn_output.weight", r(N_EMBD, N_HEAD * HEAD))
        w.add_tensor(p + "attn_q_norm.weight", np.ones(HEAD, np.float32))
        w.add_tensor(p + "attn_k_norm.weight", np.ones(HEAD, np.float32))
        w.add_tensor(p + "ffn_norm.weight", np.ones(N_EMBD, np.float32))
        router = r(N_EXP, N_EMBD, s=1.0) * np.linspace(3.0, 0.2, N_EXP, dtype=np.float32)[:, None]
        w.add_tensor(p + "ffn_gate_inp.weight", router)
        w.add_tensor(p + "ffn_gate_exps.weight", r(N_EXP, N_FF, N_EMBD))
        w.add_tensor(p + "ffn_up_exps.weight", r(N_EXP, N_FF, N_EMBD))
        w.add_tensor(p + "ffn_down_exps.weight", r(N_EXP, N_EMBD, N_FF))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()


if __name__ == "__main__":
    main(sys.argv[1])
