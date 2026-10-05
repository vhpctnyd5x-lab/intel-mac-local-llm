#!/usr/bin/env python3
"""a1_jouhouryou.py の自己点検（模型なし）。合成の BF16 で、復号一致と情報量の計算が正しいかを見る。
数字は合成データの物で、模型の結果ではない。"""
import os
import sys

import numpy as np
import zstandard

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a1_jouhouryou as a1

so = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "huff.so")
hf = a1.Huff(so)
zc = zstandard.ZstdCompressor(level=3)
rng = np.random.default_rng(0)
f32 = (rng.standard_normal(1 << 20) * 0.02).astype(np.float32)
u = (f32.view(np.uint32) >> 16).astype(np.uint16)  # 切り捨てで BF16
r = a1.measure("gauss", u, hf, zc)
for k in a1.COLS:
    print(f"{k}\t{r[k]:.4f}")
assert r["H_sign"] > 0.999
assert r["H_exp"] < 3.5, "正規分布なら指数部は 3 ビット前後"
assert r["H_exp"] + 8 <= r["huff"] < r["H_exp"] + 8 + 0.1, "ハフマンは情報量から 0.1 ビット以内"
assert r["huff_ctx"] >= r["H_exp|prev"] + 8 - 1e-9
# 1つしか記号が無い・偏りが極端な場合も復号できるか
for sym in [np.zeros(1000, np.uint8), np.r_[np.zeros(100000, np.uint8), np.arange(256, dtype=np.uint8)]]:
    hf.roundtrip(sym, a1.huff_lens(np.bincount(sym, minlength=256)), 1)
print("ok")
