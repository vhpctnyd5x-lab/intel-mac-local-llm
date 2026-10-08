#!/usr/bin/env python3
"""B1: 使われ方で専門家ごとに精度を変える（docs/kenkyuu/bit_yori_shita.md §4 B1）。

よく呼ばれる専門家は「熱い」型（例 Q2_K）、めったに呼ばれない専門家は「冷たい」型（例 IQ1_M）にする。
GGUF は 1テンソル＝1つの型で、専門家は層ごとに1つの3次元テンソル（ffn_*_exps）に入っているため、
専門家ごとに型を混ぜる形式は llama.cpp に無い。そこでまず **賢さだけ** を安く確かめる:

  熱い型で量子化した模型 と 冷たい型で量子化した模型 を用意し、専門家ごとにどちらかの値を戻して（逆量子化）
  入れ物の型（Q8_0 か F16）に詰め直した GGUF を作る。中身の値は「混ぜた模型」と同じなので、困惑度・KLD はそのまま測れる。
  大きさは、本当に混ぜて保存した場合の数字を計算で出す（入れ物のファイルの大きさではない）。

効いたら、llama.cpp に「層ごとに熱い専門家のテンソルと冷たい専門家のテンソルを2つ持つ」形を足して、速さを測る（次の段）。

  # 使用数の偏りを見る（imatrix の <テンソル>.counts は、その専門家に回された字の数）
  python3 b1_mazeru.py shiyou IMATRIX.gguf

  # 混ぜた模型を作る（入れ物 Q8_0）。--frac は冷たくする専門家の割合
  python3 b1_mazeru.py tsukuru --hot Q2_K.gguf --cold IQ1_M.gguf --imatrix IMATRIX.gguf \
      --frac 0.5 --erabi shiyou --out mix.gguf

  --erabi  shiyou  層ごとに使用数の少ない順で frac を冷たく（本命）
           zentai  全層まとめて「層の中での使用の割合」が小さい順で frac を冷たく
           rand    層ごとに無作為で frac（対照: 使用数で選ぶ意味があるか）
           hanten  層ごとに使用数の多い順で frac（対照: 逆にすると悪くなるはず）

  python3 b1_mazeru.py ookisa MODEL.gguf   # 混ぜていない模型の大きさ（専門家の bit/重み）
  python3 b1_mazeru.py --tameshi     # 選び方と大きさの計算の確かめ（模型なし）

gguf-py（llama.cpp/gguf-py）を PYTHONPATH に入れて使う。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

EXPS = re.compile(r"^blk\.(\d+)\.ffn_(gate|up|down|gate_up)_exps\.weight$")


def _gguf():
    try:
        import gguf
    except ImportError:
        sys.exit("llama.cpp の gguf-py を PYTHONPATH に入れてください（例: PYTHONPATH=llama.cpp/gguf-py）")
    return gguf


# ---------- 使用数 ----------

def yomu_shiyou(imatrix_path):
    """imatrix から {層: 専門家ごとの使用数} を返す。gate（無ければ up / gate_up / down）の counts を使う。"""
    gguf = _gguf()
    r = gguf.GGUFReader(imatrix_path)
    per = {}
    for t in r.tensors:
        if not t.name.endswith(".counts"):
            continue
        m = EXPS.match(t.name[: -len(".counts")])
        if not m:
            continue
        layer, kind = int(m.group(1)), m.group(2)
        c = np.asarray(t.data, dtype=np.float64).reshape(-1)
        rank = {"gate": 0, "gate_up": 1, "up": 2, "down": 3}[kind]
        if layer not in per or rank < per[layer][0]:
            per[layer] = (rank, c)
    if not per:
        sys.exit("imatrix に専門家の counts がありません（MoE の模型で、新しい GGUF 形式の imatrix が要る）")
    return {k: v[1] for k, v in sorted(per.items())}


def matome_shiyou(per):
    """層ごとの偏り: 上位 x% の専門家が字の何割を受けたか、一度も呼ばれない専門家の数、ジニ係数。"""
    rows = []
    for layer, c in per.items():
        s = np.sort(c)[::-1]
        tot = s.sum()
        n = len(s)
        share = np.cumsum(s) / tot if tot else np.zeros(n)
        g = 1 - 2 * np.sum(np.cumsum(np.sort(c)) / tot) / n + 1 / n if tot else 0.0
        rows.append({
            "layer": layer, "n_expert": n, "tokens": float(tot),
            "top25": float(share[max(0, n // 4 - 1)]), "top50": float(share[max(0, n // 2 - 1)]),
            "zero": int((c == 0).sum()), "gini": float(g),
            "bottom50": float(1 - share[max(0, n // 2 - 1)]),
        })
    return rows


# ---------- 選び方 ----------

def erabu(per, frac, how, seed=0):
    """{層: 冷たくする専門家の番号の集合}。"""
    rng = np.random.default_rng(seed)
    cold = {}
    if how == "zentai":
        allx = []
        for layer, c in per.items():
            tot = c.sum() or 1.0
            allx += [(c[e] / tot, layer, e) for e in range(len(c))]
        allx.sort()
        k = int(round(frac * len(allx)))
        cold = {layer: set() for layer in per}
        for _, layer, e in allx[:k]:
            cold[layer].add(e)
        return cold
    for layer, c in per.items():
        n = len(c)
        k = int(round(frac * n))
        if how == "shiyou":
            order = np.argsort(c, kind="stable")
        elif how == "hanten":
            order = np.argsort(-c, kind="stable")
        elif how == "rand":
            order = rng.permutation(n)
        else:
            raise ValueError(how)
        cold[layer] = set(int(e) for e in order[:k])
    return cold


def tokuka(per, cold):
    """冷たい側に回る字の割合（層平均）。使用数で選べば小さく、無作為なら frac に近くなる。"""
    xs = []
    for layer, c in per.items():
        tot = c.sum()
        if tot:
            xs.append(sum(c[e] for e in cold.get(layer, ())) / tot)
    return float(np.mean(xs)) if xs else 0.0


# ---------- 大きさ ----------

def ookisa1(reader):
    """1つの GGUF の大きさと、専門家のテンソルの重み1個あたりのビット。"""
    total = n_w = exps_b = exps_n = 0
    for t in reader.tensors:
        n_el = int(np.prod([int(x) for x in t.shape]))
        total += int(t.n_bytes)
        n_w += n_el
        if EXPS.match(t.name):
            exps_b += int(t.n_bytes)
            exps_n += n_el
    return {"bytes": total, "GiB": total / 2 ** 30, "bpw_all": 8 * total / n_w,
            "bpw_exps": 8 * exps_b / exps_n if exps_n else 0.0}


def ookisa(hot_reader, cold_reader, cold):
    """混ぜて本当に保存した場合のバイト数と、重み1個あたりのビット。"""
    cold_t = {t.name: t for t in cold_reader.tensors}
    total = exps_total = 0
    n_w = exps_n = 0
    for t in hot_reader.tensors:
        n_el = int(np.prod([int(x) for x in t.shape]))
        n_w += n_el
        m = EXPS.match(t.name)
        if not m:
            total += int(t.n_bytes)
            continue
        layer = int(m.group(1))
        ct = cold_t[t.name]
        n_exp = int(t.shape[-1])
        k = len(cold.get(layer, ()))
        b = int(t.n_bytes) * (n_exp - k) // n_exp + int(ct.n_bytes) * k // n_exp
        total += b
        exps_total += b
        exps_n += n_el
    return {"bytes": total, "GiB": total / 2 ** 30, "bpw_all": 8 * total / n_w,
            "bpw_exps": 8 * exps_total / exps_n if exps_n else 0.0}


# ---------- 作る ----------

def tsukuru(hot_path, cold_path, imatrix, frac, how, out, ireru="q8_0", seed=0):
    gguf = _gguf()
    from gguf.quants import dequantize, quantize
    per = yomu_shiyou(imatrix)
    cold = erabu(per, frac, how, seed)
    hot_r, cold_r = gguf.GGUFReader(hot_path), gguf.GGUFReader(cold_path)
    cold_t = {t.name: t for t in cold_r.tensors}
    qt = {"q8_0": gguf.GGMLQuantizationType.Q8_0, "f16": gguf.GGMLQuantizationType.F16}[ireru]

    arch = hot_r.fields[gguf.Keys.General.ARCHITECTURE].contents()
    w = gguf.GGUFWriter(out, arch=arch, endianess=hot_r.endianess)
    for f in hot_r.fields.values():
        if f.name == gguf.Keys.General.ARCHITECTURE or f.name.startswith("GGUF."):
            continue
        vt = f.types[0]
        sub = f.types[-1] if vt == gguf.GGUFValueType.ARRAY else None
        w.add_key_value(f.name, f.contents(), vt, sub_type=sub)
    w.add_key_value("b1.frac", float(frac), gguf.GGUFValueType.FLOAT32)
    w.add_key_value("b1.erabi", how, gguf.GGUFValueType.STRING)

    def mixed(t):
        layer = int(EXPS.match(t.name).group(1))
        h = dequantize(np.asarray(t.data), t.tensor_type)
        ct = cold_t[t.name]
        if cold.get(layer):
            c = dequantize(np.asarray(ct.data), ct.tensor_type)
            idx = sorted(cold[layer])
            h[idx] = c[idx]                   # 先頭の次元が専門家の番号
        if qt == gguf.GGMLQuantizationType.F16:
            return h.astype(np.float16)
        return quantize(h.astype(np.float32), qt)

    plan = []
    for t in hot_r.tensors:
        if EXPS.match(t.name):
            if t.name not in cold_t:
                sys.exit(f"冷たい模型に {t.name} がありません")
            ne = [int(x) for x in t.shape]           # GGUF の順（行の長さが先）
            shape = list(reversed(ne))
            if qt == gguf.GGMLQuantizationType.F16:
                nbytes = int(np.prod(shape)) * 2
                w.add_tensor_info(t.name, shape, np.dtype(np.float16), nbytes, qt)
            else:
                bs, ts = gguf.GGML_QUANT_SIZES[qt]
                bshape = shape[:-1] + [shape[-1] // bs * ts]
                w.add_tensor_info(t.name, bshape, np.dtype(np.uint8), int(np.prod(bshape)), qt)
            plan.append((t, True))
        else:
            w.add_tensor_info(t.name, t.data.shape, t.data.dtype, t.data.nbytes, t.tensor_type)
            plan.append((t, False))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_ti_data_to_file()
    for t, mix in plan:
        w.write_tensor_data(mixed(t) if mix else t.data, tensor_endianess=hot_r.endianess)
        print(f"  {t.name}{' (混ぜた)' if mix else ''}", file=sys.stderr)
    w.close()

    info = {"frac": frac, "erabi": how, "seed": seed, "ireru": ireru,
            "cold_token_share": tokuka(per, cold), **ookisa(hot_r, cold_r, cold),
            "cold": {str(k): sorted(v) for k, v in cold.items()}}
    Path(str(out) + ".json").write_text(json.dumps(info, ensure_ascii=False, indent=1))
    return info


# ---------- 確かめ ----------

def tameshi():
    rng = np.random.default_rng(1)
    # 32人の層を3つ。使用数は偏りあり（ジップ風）、ゼロも混ぜる
    per = {}
    for layer in range(3):
        c = (1000.0 / (1 + np.arange(32)) ** 1.2)
        c[-3:] = 0
        per[layer] = rng.permutation(c)
    for how in ("shiyou", "hanten", "rand", "zentai"):
        cold = erabu(per, 0.5, how, seed=0)
        n = sum(len(v) for v in cold.values())
        assert n == 48, (how, n)
    s = tokuka(per, erabu(per, 0.5, "shiyou"))
    r = tokuka(per, erabu(per, 0.5, "rand"))
    h = tokuka(per, erabu(per, 0.5, "hanten"))
    assert s < r < h, (s, r, h)
    assert tokuka(per, erabu(per, 0.0, "shiyou")) == 0.0
    assert abs(tokuka(per, erabu(per, 1.0, "shiyou")) - 1.0) < 1e-12
    # 使用数ゼロの3人は必ず最初に冷たくなる
    c3 = erabu(per, 3 / 32, "shiyou")
    for layer, c in per.items():
        assert c3[layer] == set(np.where(c == 0)[0].tolist())
    rows = matome_shiyou(per)
    assert all(r["zero"] == 3 and 0 < r["gini"] < 1 for r in rows)
    print(f"冷たい側に回る字の割合（frac=0.5）: 使用数 {s:.3f} / 無作為 {r:.3f} / 逆 {h:.3f}")
    print("ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tameshi", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("shiyou")
    p.add_argument("imatrix")
    p.add_argument("--json")
    p = sub.add_parser("ookisa")
    p.add_argument("model")
    p = sub.add_parser("tsukuru")
    p.add_argument("--hot", required=True)
    p.add_argument("--cold", required=True)
    p.add_argument("--imatrix", required=True)
    p.add_argument("--frac", type=float, required=True)
    p.add_argument("--erabi", default="shiyou", choices=["shiyou", "zentai", "rand", "hanten"])
    p.add_argument("--ireru", default="q8_0", choices=["q8_0", "f16"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.tameshi:
        return tameshi()
    if a.cmd == "shiyou":
        rows = matome_shiyou(yomu_shiyou(a.imatrix))
        if a.json:
            Path(a.json).write_text(json.dumps(rows, indent=1))
        print("| 層 | 専門家 | 上位25%が受けた字 | 上位50% | 下位50% | 一度も呼ばれない | ジニ |")
        print("|---:|---:|---:|---:|---:|---:|---:|")
        for r in rows:
            print(f"| {r['layer']} | {r['n_expert']} | {r['top25']:.1%} | {r['top50']:.1%} | "
                  f"{r['bottom50']:.1%} | {r['zero']} | {r['gini']:.3f} |")
        print(f"\n層平均: 下位50%の専門家が受けた字 {np.mean([r['bottom50'] for r in rows]):.1%}、"
              f"ジニ {np.mean([r['gini'] for r in rows]):.3f}")
    elif a.cmd == "ookisa":
        print(json.dumps(ookisa1(_gguf().GGUFReader(a.model))))
    elif a.cmd == "tsukuru":
        info = tsukuru(a.hot, a.cold, a.imatrix, a.frac, a.erabi, a.out, a.ireru, a.seed)
        print(json.dumps({k: v for k, v in info.items() if k != "cold"}, ensure_ascii=False))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
