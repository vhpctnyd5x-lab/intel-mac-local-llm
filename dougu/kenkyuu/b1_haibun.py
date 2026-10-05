#!/usr/bin/env python3
"""B1: imatrix の重要度でテンソルごとに量子化の型を選ぶ（平均ビットは一様版と同じ以下）。

やり方:
  1. 候補の型ごとに「一様に量子化した GGUF」を用意する（llama-quantize --pure --imatrix）。
  2. テンソル t・型 q ごとに、重要度つきの誤差 E[t,q] = Σ_j a_j Σ_i (W_ij − Ŵ_ij)² を実測する。
     a_j は imatrix の入力の二乗平均（in_sum2 / counts）。W は元の BF16/F16、Ŵ は 1. の物をほどいた値。
  3. 全体のビット数 ≤ 目標ビット × 重みの数 の下で ΣE が最小になるよう、凸包に沿って貪欲に上げる。
  4. llama-quantize --tensor-type-file に渡す表を書く。

対象は blk.* の2次元の重みだけ（埋め込み・出力は両方の版で同じ型に固定する）。

使い方:
  python3 b1_haibun.py --src model-bf16.gguf --imatrix imatrix.gguf \
      --cand IQ1_M=q-iq1_m.gguf --cand IQ2_S=q-iq2_s.gguf ... --bpw 2.5 --out types.txt
"""
import argparse
import heapq
import re
import sys

import numpy as np
from gguf import GGUFReader, GGMLQuantizationType, GGML_QUANT_SIZES
from gguf.quants import dequantize

BLK = re.compile(r"^blk\.\d+\..*\.weight$")


def tensors(path):
    return {t.name: t for t in GGUFReader(path).tensors}


def as_f32(t):
    return dequantize(np.asarray(t.data), t.tensor_type).reshape(-1, int(t.shape[0])).astype(np.float32)


def bpw(qt):
    bs, ts = GGML_QUANT_SIZES[qt]
    return 8 * ts / bs


def hull(points):
    """(ビット, 誤差) の点を、ビットが増え誤差が減る下側の凸包にする。"""
    pts = sorted(points, key=lambda p: (p[0], p[1]))
    out = []
    for p in pts:
        if out and p[1] >= out[-1][1]:
            continue
        while len(out) >= 2:
            (x1, y1, _), (x2, y2, _) = out[-2], out[-1]
            if (y1 - y2) * (p[0] - x2) <= (y2 - p[1]) * (x2 - x1):
                out.pop()
            else:
                break
        out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--imatrix", required=True)
    ap.add_argument("--cand", action="append", required=True, help="TYPE=一様に量子化した.gguf")
    ap.add_argument("--bpw", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--err-out", help="テンソル×型の誤差表（TSV）")
    a = ap.parse_args()

    src = tensors(a.src)
    imx = tensors(a.imatrix)
    cands = []
    for c in a.cand:
        name, path = c.split("=", 1)
        cands.append((GGMLQuantizationType[name.upper()], tensors(path)))

    names = [n for n, t in src.items() if BLK.match(n) and len(t.shape) == 2]
    err, bits = {}, {}
    for n in names:
        w = as_f32(src[n])
        s2 = np.asarray(imx[n + ".in_sum2"].data, np.float64).reshape(-1)
        cnt = float(np.asarray(imx[n + ".counts"].data).reshape(-1)[0])
        act = s2 / max(cnt, 1.0)
        for qt, ts in cands:
            t = ts[n]
            if t.tensor_type != qt:
                sys.exit(f"{n}: {qt.name} の版なのに {t.tensor_type.name}（--pure で作ること）")
            d = w - as_f32(t)
            err[n, qt] = float(((d.astype(np.float64) ** 2).sum(0) * act).sum())
            bits[n, qt] = w.size * bpw(qt)
        print(f"# {n} " + " ".join(f"{qt.name}:{err[n, qt]:.3g}" for qt, _ in cands), file=sys.stderr)

    total_w = sum(src[n].n_elements for n in names)
    budget = a.bpw * total_w
    hulls = {n: hull([(bits[n, qt], err[n, qt], qt) for qt, _ in cands]) for n in names}
    pos = {n: 0 for n in names}
    used = sum(hulls[n][0][0] for n in names)
    heap = []

    def push(n):
        h, i = hulls[n], pos[n]
        if i + 1 < len(h):
            db = h[i + 1][0] - h[i][0]
            de = h[i][1] - h[i + 1][1]
            heapq.heappush(heap, (-de / db, n))

    for n in names:
        push(n)
    while heap:
        _, n = heapq.heappop(heap)
        h, i = hulls[n], pos[n]
        db = h[i + 1][0] - h[i][0]
        if used + db > budget:
            continue  # この上げは入らない。ほかの小さい上げは続けて試す
        used += db
        pos[n] = i + 1
        push(n)

    choice = {n: hulls[n][pos[n]][2] for n in names}
    with open(a.out, "w") as f:
        for n in names:
            f.write(f"^{re.escape(n)}$={choice[n].name.lower()}\n")
    if a.err_out:
        with open(a.err_out, "w") as f:
            f.write("name\tn\tchoice\t" + "\t".join(qt.name for qt, _ in cands) + "\n")
            for n in names:
                f.write(f"{n}\t{src[n].n_elements}\t{choice[n].name}\t" + "\t".join(f"{err[n, qt]:.6g}" for qt, _ in cands) + "\n")
    mix_err = sum(err[n, choice[n]] for n in names)
    print(f"平均 {used / total_w:.4f} ビット/重み（目標 {a.bpw}）、重要度つき誤差の合計 {mix_err:.6g}")
    for qt, _ in cands:
        k = sum(1 for n in names if choice[n] == qt)
        if k:
            print(f"  {qt.name}: {k} 個")
        if abs(bpw(qt) - a.bpw) < 1e-6:
            print(f"  （一様 {qt.name} の誤差の合計 {sum(err[n, qt] for n in names):.6g}）")


if __name__ == "__main__":
    main()
