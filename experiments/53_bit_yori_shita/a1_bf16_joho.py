#!/usr/bin/env python3
"""A1: 量子化する前の重み（BF16）は、どこに情報が詰まっているか（docs/kenkyuu/bit_yori_shita.md §4 A1）。

BF16 = 符号1・指数8・仮数7 ビット。テンソルごとに、記号の出方の偏りから「1個あたり本当に要るビット数」
（0次のエントロピー＝前後のつながりを使わない、1つずつ独立の値）を測る。

  H_sign / H_exp / H_mant     各部分だけのエントロピー
  H_mant|exp                  指数を知った上での仮数（＝仮数を指数ごとに別の符号表で書く場合）
  H_16                        16ビットの値まるごと（＝可逆・0次で到達できる下限）
  huff_exp                    指数だけハフマン符号、符号と仮数は生のまま（DFloat11 の形）の実長
  H_exp|prev                  1つ前（同じ行の左隣）の指数を知った上での指数（A3「隣から予測」の目安）

F32 の重みは BF16 に丸めて（最近接偶数）、F16 は F32 を経て BF16 に直して測る（元の配布が BF16 なら同じ）。

  python3 a1_bf16_joho.py MODEL_DIR_or_FILE [...] [--out kekka.json] [--max-elems 0]
  python3 a1_bf16_joho.py --tameshi            # 正規乱数で道具の確かめ（模型なし）

入力: *.safetensors（フォルダならその中の全部）、または *.gguf（F32/F16/BF16 のテンソルだけ）。
"""
import argparse
import heapq
import json
import math
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np


# ---------- 読み込み ----------

def f32_to_bf16(u32):
    """F32 のビット列（uint32）を BF16（uint16）へ、最近接偶数で丸める。NaN はそのまま上位を取る。"""
    u32 = u32.astype(np.uint32, copy=False)
    nan = (u32 & 0x7F800000) == 0x7F800000
    r = (u32 + np.uint32(0x7FFF) + ((u32 >> 16) & np.uint32(1))) >> 16
    r = np.where(nan & ((u32 & 0x007FFFFF) != 0), u32 >> 16, r)
    return r.astype(np.uint16)


def safetensors_tensors(path):
    """(名前, 形, BF16 の uint16 配列を返す関数) を順に返す。"""
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        head = json.loads(f.read(n))
    base = 8 + n
    mm = np.memmap(path, dtype=np.uint8, mode="r")
    for name, info in head.items():
        if name == "__metadata__":
            continue
        dt = info["dtype"]
        a, b = info["data_offsets"]
        raw = mm[base + a: base + b]
        shape = tuple(info["shape"])
        if dt == "BF16":
            yield name, shape, (lambda raw=raw: raw.view(np.uint16))
        elif dt == "F32":
            yield name, shape, (lambda raw=raw: f32_to_bf16(raw.view(np.uint32)))
        elif dt == "F16":
            yield name, shape, (lambda raw=raw: f32_to_bf16(raw.view(np.float16).astype(np.float32).view(np.uint32)))
        # 整数や FP8 は対象外


def gguf_tensors(path):
    try:
        import gguf  # llama.cpp の gguf-py
    except ImportError:
        sys.exit("gguf を読むには llama.cpp の gguf-py を PYTHONPATH に入れてください")
    r = gguf.GGUFReader(path)
    T = gguf.GGMLQuantizationType
    for t in r.tensors:
        shape = tuple(int(x) for x in reversed(t.shape.tolist()))
        raw = np.asarray(t.data).reshape(-1).view(np.uint8)
        if t.tensor_type == T.BF16:
            yield t.name, shape, (lambda raw=raw: raw.view(np.uint16))
        elif t.tensor_type == T.F32:
            yield t.name, shape, (lambda raw=raw: f32_to_bf16(raw.view(np.uint32)))
        elif t.tensor_type == T.F16:
            yield t.name, shape, (lambda raw=raw: f32_to_bf16(raw.view(np.float16).astype(np.float32).view(np.uint32)))


def all_tensors(paths):
    for p in paths:
        p = Path(p)
        files = sorted(p.glob("*.safetensors")) if p.is_dir() else [p]
        for f in files:
            src = gguf_tensors(str(f)) if f.suffix == ".gguf" else safetensors_tensors(str(f))
            for item in src:
                yield item


# ---------- 情報量 ----------

def entropy(counts):
    c = counts[counts > 0].astype(np.float64)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def cond_entropy(joint):
    """joint[a, b] の度数から H(b | a)。"""
    return entropy(joint.reshape(-1)) - entropy(joint.sum(axis=1))


def huffman_mean_len(counts):
    """度数からハフマン符号を作ったときの平均の長さ（ビット/記号）。記号が1種なら1ビットと数える。"""
    c = [int(x) for x in counts if x > 0]
    if len(c) <= 1:
        return 1.0
    heap = [(x, i) for i, x in enumerate(c)]
    heapq.heapify(heap)
    total, nxt = 0, len(c)
    while len(heap) > 1:
        a, _ = heapq.heappop(heap)
        b, _ = heapq.heappop(heap)
        total += a + b            # 合わせるたびに、その下の全記号が1ビット長くなる
        heapq.heappush(heap, (a + b, nxt))
        nxt += 1
    return total / sum(c)


class Kazoe:
    """度数を足し込む器。テンソル単位にも、全体・種類別の合計にも使う。"""

    def __init__(self):
        self.h16 = np.zeros(1 << 16, np.int64)
        self.prev = np.zeros((256, 256), np.int64)
        self.n = 0

    def add(self, u16, row_len, step=1 << 24):
        """行の切れ目で区切って少しずつ数える（大きい埋め込みでもメモリを食わないように）。"""
        rows = max(1, step // max(row_len, 1))
        for a in range(0, u16.size, rows * row_len):
            part = u16[a: a + rows * row_len]
            self.h16 += np.bincount(part, minlength=1 << 16)
            self.n += part.size
            if row_len > 1 and part.size % row_len == 0:
                e = ((part >> 7) & 0xFF).reshape(-1, row_len)
                pair = (e[:, :-1].astype(np.int32) << 8) | e[:, 1:]
                self.prev += np.bincount(pair.reshape(-1), minlength=1 << 16).reshape(256, 256)

    def merge(self, o):
        self.h16 += o.h16
        self.prev += o.prev
        self.n += o.n

    def report(self):
        h = self.h16.reshape(2, 256, 128)           # [符号, 指数, 仮数]
        exp = h.sum(axis=(0, 2))
        em = h.sum(axis=0)                          # [指数, 仮数]
        r = {
            "n": int(self.n),
            "H_sign": entropy(h.sum(axis=(1, 2))),
            "H_exp": entropy(exp),
            "H_mant": entropy(h.sum(axis=(0, 1))),
            "H_mant|exp": cond_entropy(em),
            "H_16": entropy(self.h16),
            "huff_exp": huffman_mean_len(exp),
            "exp_used": int((exp > 0).sum()),
        }
        r["dfloat_bits"] = 8 + r["huff_exp"]        # 符号1＋仮数7 は生、指数だけハフマン
        r["dfloat_ratio"] = r["dfloat_bits"] / 16
        r["H16_ratio"] = r["H_16"] / 16
        if self.prev.sum() > 0:
            r["H_exp|prev"] = cond_entropy(self.prev)
        return r


def shurui(name):
    """テンソル名から大まかな種類。HF と GGUF の両方の名前に合わせる。"""
    n = name.lower()
    if "norm" in n:
        return "norm"
    if "embed" in n or "token_embd" in n or n.startswith("output.") or "lm_head" in n:
        return "embed_out"
    if "router" in n or "gate_inp" in n or n.endswith("mlp.gate.weight"):
        return "router"
    if "shared" in n or "_shexp" in n:
        return "shared_expert"
    if "expert" in n or "_exps" in n:
        return "experts"
    if "attn" in n or "self_attn" in n or "q_proj" in n or "k_proj" in n or "v_proj" in n or "o_proj" in n:
        return "attention"
    if "mlp" in n or "ffn" in n:
        return "mlp"
    return "other"


def hakaru(items, max_elems=0, verbose=True):
    zentai, betsu, per = Kazoe(), defaultdict(Kazoe), []
    t0 = time.time()
    for name, shape, get in items:
        u16 = np.ascontiguousarray(get()).reshape(-1)
        if max_elems and u16.size > max_elems:     # 大きいテンソルは先頭の行から間引かずに切り取る
            row = shape[-1] if shape else 1
            u16 = u16[: max(row, (max_elems // row) * row)]
        k = Kazoe()
        k.add(u16, shape[-1] if len(shape) >= 2 else 1)
        r = k.report()
        r.update(name=name, shape=list(shape), kind=shurui(name))
        per.append(r)
        zentai.merge(k)
        betsu[r["kind"]].merge(k)
        if verbose:
            print(f"{name:60s} n={r['n']:>11,d} H_exp={r['H_exp']:.3f} H16={r['H_16']:.3f} "
                  f"dfloat={r['dfloat_bits']:.3f}", file=sys.stderr)
    return {
        "zentai": zentai.report(),
        "shurui": {k: v.report() for k, v in sorted(betsu.items())},
        "tensors": per,
        "byou": round(time.time() - t0, 1),
    }


def hyou(res):
    rows = [("全体", res["zentai"])] + list(res["shurui"].items())
    out = ["| 種類 | 重み数 | H_sign | H_exp | H_mant | H_mant\\|exp | H_16 | 指数ハフマン実長 | DFloat形 bit/重み (比) | 0次下限 (比) | H_exp\\|左隣 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, r in rows:
        out.append(f"| {k} | {r['n']:,} | {r['H_sign']:.3f} | {r['H_exp']:.3f} | {r['H_mant']:.3f} | "
                   f"{r['H_mant|exp']:.3f} | {r['H_16']:.3f} | {r['huff_exp']:.3f} | "
                   f"{r['dfloat_bits']:.2f} ({r['dfloat_ratio']:.1%}) | {r['H_16']:.2f} ({r['H16_ratio']:.1%}) | "
                   f"{r.get('H_exp|prev', float('nan')):.3f} |")
    return "\n".join(out)


def tameshi():
    """正規乱数で確かめる。N(0, σ²) の BF16 なら H_exp は約 2.6〜2.7、H_mant はほぼ 7、H_sign は 1。"""
    rng = np.random.default_rng(0)
    w = (rng.standard_normal((1024, 1024)) * 0.02).astype(np.float32)
    items = [("tameshi.normal.weight", w.shape, lambda: f32_to_bf16(w.view(np.uint32)))]
    r = hakaru(items, verbose=False)["zentai"]
    assert abs(r["H_sign"] - 1) < 1e-3, r
    assert 2.4 < r["H_exp"] < 2.9, r
    assert 6.9 < r["H_mant"] <= 7.0, r
    assert r["H_exp"] <= r["huff_exp"] < r["H_exp"] + 1, r
    assert abs(r["H_exp|prev"] - r["H_exp"]) < 0.02, r      # 独立に引いたので、左隣は役に立たない
    # 丸めの確かめ: 1.0 + 2^-8 ちょうど（真ん中）は偶数側の 1.0 に、少し上なら次へ
    x = np.array([1.0 + 2 ** -8, 1.0 + 2 ** -8 + 2 ** -20, 1.0 + 3 * 2 ** -8], np.float32)
    assert f32_to_bf16(x.view(np.uint32)).tolist() == [0x3F80, 0x3F81, 0x3F82]
    assert abs(huffman_mean_len(np.array([1, 1, 2])) - 1.5) < 1e-9
    print(hyou({"zentai": r, "shurui": {}}))
    print("ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--max-elems", type=int, default=0, help="1テンソルあたりの上限（0=全部）")
    ap.add_argument("--tameshi", action="store_true")
    a = ap.parse_args()
    if a.tameshi:
        return tameshi()
    if not a.paths:
        ap.error("模型のフォルダかファイルを指定")
    res = hakaru(all_tensors(a.paths), a.max_elems)
    res["paths"] = [str(p) for p in a.paths]
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(hyou(res))
    z = res["zentai"]
    print(f"\n全体: DFloat形 {z['dfloat_bits']:.2f} bit/重み（元の {z['dfloat_ratio']:.1%}）、"
          f"0次の下限 {z['H_16']:.2f} bit/重み（{z['H16_ratio']:.1%}）、{res['byou']} 秒")


if __name__ == "__main__":
    main()
