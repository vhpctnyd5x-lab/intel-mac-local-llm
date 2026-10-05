#!/usr/bin/env python3
"""A1/A3: 量子化前の BF16 重みの情報量と、可逆の可変長符号で縮む量を測る。

入力: safetensors（BF16）か GGUF（BF16 のテンソル）。1ファイルか、複数ファイル。
出力: テンソルごとの TSV と、全体のまとめ（標準出力）。

測る物（テンソルごと）:
  H_sign / H_exp / H_mant   0次の情報量（ビット/重み）
  H16                        16ビット全体を1記号とした0次の情報量
  H_exp|prev                 1つ前の重みの指数部を文脈にした条件つき情報量（A3）
  huff                       指数部を正準ハフマン + 符号と仮数部はそのまま8ビット（DFloat11 と同じ形）
  huff_ctx                   指数部を「1つ前の指数部」ごとの表でハフマン（A3）
  zstd / zstd_plane          生の2バイト列 / 上位バイトと下位バイトを分けた列を zstd -9
符号表の大きさ（表1つ 256 バイト）も含める。huff と huff_ctx は実際に復号して元と一致するか確かめる。

使い方:
  gcc -O2 -shared -fPIC -o huff.so huff.c
  python3 a1_jouhouryou.py model.safetensors [--out a1.tsv] [--so ./huff.so]
"""
import argparse
import ctypes
import heapq
import json
import os
import struct
import sys
import time

import numpy as np
import zstandard

MAXLEN = 30


def read_safetensors(path):
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        head = json.loads(f.read(n))
    mm = np.memmap(path, dtype=np.uint8, mode="r", offset=8 + n)
    for name, v in head.items():
        if name == "__metadata__":
            continue
        if v["dtype"] != "BF16":
            print(f"# 飛ばす {name} {v['dtype']}", file=sys.stderr)
            continue
        a, b = v["data_offsets"]
        yield name, np.frombuffer(mm[a:b], dtype=np.uint16)


def read_gguf(path):
    from gguf import GGUFReader, GGMLQuantizationType
    r = GGUFReader(path)
    for t in r.tensors:
        if t.tensor_type != GGMLQuantizationType.BF16:
            print(f"# 飛ばす {t.name} {t.tensor_type.name}", file=sys.stderr)
            continue
        yield t.name, np.asarray(t.data).view(np.uint16).reshape(-1)


def entropy(counts):
    c = counts[counts > 0].astype(np.float64)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def huff_lens(counts):
    """度数から符号長（最大 MAXLEN）。長すぎたら度数を半分にして作り直す。"""
    counts = counts.astype(np.int64).copy()
    while True:
        idx = np.nonzero(counts)[0]
        lens = np.zeros(256, np.uint8)
        if len(idx) == 1:
            lens[idx[0]] = 1
            return lens
        heap = [(int(counts[s]), i, [int(s)]) for i, s in enumerate(idx)]
        heapq.heapify(heap)
        k = len(heap)
        depth = np.zeros(256, np.int64)
        while len(heap) > 1:
            c1, _, s1 = heapq.heappop(heap)
            c2, _, s2 = heapq.heappop(heap)
            for s in s1 + s2:
                depth[s] += 1
            heapq.heappush(heap, (c1 + c2, k, s1 + s2))
            k += 1
        if depth.max() <= MAXLEN:
            lens[:] = depth
            return lens
        counts = np.where(counts > 0, np.maximum(counts // 2, 1), 0)


class Huff:
    def __init__(self, so):
        self.lib = ctypes.CDLL(so)
        P = ctypes.c_void_p
        self.lib.encode.argtypes = [P, ctypes.c_int64, P, ctypes.c_int, P]
        self.lib.encode.restype = ctypes.c_int64
        self.lib.decode.argtypes = [P, ctypes.c_int64, P, ctypes.c_int, P]
        self.lib.decode.restype = ctypes.c_int64

    def roundtrip(self, sym, lens, nctx):
        """符号化して復号し、一致を確かめる。返り値: 符号のビット数。"""
        sym = np.ascontiguousarray(sym, np.uint8)
        lens = np.ascontiguousarray(lens, np.uint8)
        out = np.zeros(len(sym) * MAXLEN // 8 + 16, np.uint8)
        bits = self.lib.encode(sym.ctypes.data, len(sym), lens.ctypes.data, nctx, out.ctypes.data)
        if bits < 0:
            raise RuntimeError("encode failed")
        back = np.empty_like(sym)
        r = self.lib.decode(out.ctypes.data, len(sym), lens.ctypes.data, nctx, back.ctypes.data)
        if r != bits or not np.array_equal(back, sym):
            raise RuntimeError("復号が一致しない")
        return bits


def measure(name, u, hf, zc):
    n = len(u)
    sign = (u >> 15).astype(np.uint8)
    exp = ((u >> 7) & 0xFF).astype(np.uint8)
    mant = (u & 0x7F).astype(np.uint8)
    ce = np.bincount(exp, minlength=256)
    r = dict(name=name, n=n)
    r["H_sign"] = entropy(np.bincount(sign, minlength=2))
    r["H_exp"] = entropy(ce)
    r["H_mant"] = entropy(np.bincount(mant, minlength=128))
    r["H16"] = entropy(np.bincount(u, minlength=65536))
    prev = np.concatenate([[0], exp[:-1]]).astype(np.int64)
    joint = np.bincount(prev * 256 + exp, minlength=65536).reshape(256, 256)
    r["H_exp|prev"] = entropy(joint.reshape(-1)) - entropy(joint.sum(1))
    # DFloat11 形: 指数部ハフマン + 符号・仮数部 8 ビット生
    lens = huff_lens(ce)
    bits = hf.roundtrip(exp, lens, 1) + 256 * 8 + 8 * n
    r["huff"] = bits / n
    # A3: 1つ前の指数部ごとの表
    lens_c = np.zeros((256, 256), np.uint8)
    used = 0
    for c in range(256):
        if joint[c].sum():
            lens_c[c] = huff_lens(joint[c])
            used += 1
    bits_c = hf.roundtrip(exp, lens_c, 256) + used * 256 * 8 + 8 * n
    r["huff_ctx"] = bits_c / n
    raw = u.tobytes()
    r["zstd"] = 8 * len(zc.compress(raw)) / n
    hi = (u >> 8).astype(np.uint8).tobytes()
    lo = (u & 0xFF).astype(np.uint8).tobytes()
    r["zstd_plane"] = 8 * (len(zc.compress(hi)) + len(zc.compress(lo))) / n
    return r


COLS = ["H_sign", "H_exp", "H_mant", "H16", "H_exp|prev", "huff", "huff_ctx", "zstd", "zstd_plane"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="a1.tsv")
    ap.add_argument("--so", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "huff.so"))
    ap.add_argument("--zstd-level", type=int, default=9)
    a = ap.parse_args()
    hf = Huff(a.so)
    zc = zstandard.ZstdCompressor(level=a.zstd_level)
    rows = []
    t0 = time.time()
    for path in a.files:
        it = read_gguf(path) if path.endswith(".gguf") else read_safetensors(path)
        for name, u in it:
            rows.append(measure(name, u, hf, zc))
            print(f"# {name} n={len(u)} huff={rows[-1]['huff']:.3f} ({time.time() - t0:.0f}s)", file=sys.stderr)
    with open(a.out, "w") as f:
        f.write("name\tn\t" + "\t".join(COLS) + "\n")
        for r in rows:
            f.write(f"{r['name']}\t{r['n']}\t" + "\t".join(f"{r[c]:.4f}" for c in COLS) + "\n")
    N = sum(r["n"] for r in rows)
    print(f"テンソル {len(rows)} 個、重み {N} 個、全部で {time.time() - t0:.0f} 秒。復号はすべて一致。")
    print("| 項目 | ビット/重み（重みで加重平均） | 16ビットに対する大きさ |")
    print("|---|---|---|")
    for c in COLS:
        v = sum(r[c] * r["n"] for r in rows) / N
        print(f"| {c} | {v:.3f} | {v / 16 * 100:.1f}% |")


if __name__ == "__main__":
    main()
