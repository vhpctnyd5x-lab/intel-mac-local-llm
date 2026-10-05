#!/usr/bin/env bash
# B1: 一様な量子化と、imatrix の重要度で型を混ぜた量子化を、同じ平均ビットで困惑度で比べる。
#
# 要る物（環境変数）:
#   LLAMA   llama.cpp の build/bin（llama-imatrix・llama-quantize・llama-perplexity）
#   SRC     BF16 の GGUF（例: convert_hf_to_gguf.py Qwen3-0.6B --outtype bf16）
#   CALIB   校正文（例: wikitext-2-raw/wiki.train.raw）。回ごとに別の部分を使う
#   EVAL    評価文（例: wikitext-2-raw/wiki.test.raw）
#   OUT     出力の置き場（大きい。git に入れない）
# 任意: RUNS=2  CHUNKS=100（評価の 512 トークンの塊の数）  ICHUNKS=100（校正）  THREADS=4
#       PAIRS="2.5:IQ2_S 3.0625:IQ3_XXS"（目標ビット:同じビットの一様な型）
#       CANDS="IQ1_M IQ2_XXS IQ2_XS IQ2_S IQ3_XXS IQ3_S IQ4_XS Q5_K"（混ぜる候補）
# 埋め込みと出力はどの版も Q8_0 に固定し、平均ビットは blk.* の重みだけで数える。
# 結果: $OUT/b1.tsv（回・目標ビット・版・困惑度・ファイルの大きさ）
set -euo pipefail
: "${LLAMA:?}" "${SRC:?}" "${CALIB:?}" "${EVAL:?}" "${OUT:?}"
RUNS=${RUNS:-2}; CHUNKS=${CHUNKS:-100}; ICHUNKS=${ICHUNKS:-100}; THREADS=${THREADS:-4}
PAIRS=${PAIRS:-"2.5:IQ2_S 3.0625:IQ3_XXS"}
CANDS=${CANDS:-"IQ1_M IQ2_XXS IQ2_XS IQ2_S IQ3_XXS IQ3_S IQ4_XS Q5_K"}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
FIX=(--pure --token-embedding-type q8_0 --output-tensor-type q8_0)

ppl() {  # $1=gguf → 困惑度
  "$LLAMA/llama-perplexity" -m "$1" -f "$EVAL" -c 512 --chunks "$CHUNKS" -t "$THREADS" 2>&1 \
    | grep -o 'Final estimate: PPL = [0-9.]*' | awk '{print $NF}'
}

echo -e "run\tbpw\tarm\tppl\tbytes" > "$OUT/b1.tsv"
echo -e "0\t16\tbf16\t$(ppl "$SRC")\t$(wc -c < "$SRC" | tr -d " ")" >> "$OUT/b1.tsv"
N=$(wc -l < "$CALIB")
for r in $(seq 1 "$RUNS"); do
  # 校正文を RUNS 等分し、r 番目を使う（回ごとに別の文で imatrix を取る）
  sed -n "$(( (r-1)*N/RUNS + 1 )),$(( r*N/RUNS ))p" "$CALIB" > "$OUT/calib$r.txt"
  "$LLAMA/llama-imatrix" -m "$SRC" -f "$OUT/calib$r.txt" -o "$OUT/imx$r.gguf" -c 512 \
    --chunks "$ICHUNKS" -t "$THREADS" > "$OUT/imx$r.log" 2>&1
  cand=()
  for q in $CANDS; do
    f="$OUT/r$r-$q.gguf"
    [ -f "$f" ] || "$LLAMA/llama-quantize" "${FIX[@]}" --imatrix "$OUT/imx$r.gguf" "$SRC" "$f" "$q" "$THREADS" > "$f.log" 2>&1
    cand+=(--cand "$q=$f")
  done
  for p in $PAIRS; do
    b=${p%%:*}; u=${p##*:}
    python3 "$HERE/b1_haibun.py" --src "$SRC" --imatrix "$OUT/imx$r.gguf" "${cand[@]}" --bpw "$b" \
      --out "$OUT/types-r$r-$b.txt" --err-out "$OUT/err-r$r-$b.tsv" 2> /dev/null | tee "$OUT/haibun-r$r-$b.txt"
    mix="$OUT/r$r-mix$b.gguf"
    "$LLAMA/llama-quantize" "${FIX[@]}" --imatrix "$OUT/imx$r.gguf" --tensor-type-file "$OUT/types-r$r-$b.txt" \
      "$SRC" "$mix" "$u" "$THREADS" > "$mix.log" 2>&1
    uni="$OUT/r$r-$u.gguf"
    echo -e "$r\t$b\tuniform-$u\t$(ppl "$uni")\t$(wc -c < "$uni" | tr -d " ")" >> "$OUT/b1.tsv"
    echo -e "$r\t$b\tmixed\t$(ppl "$mix")\t$(wc -c < "$mix" | tr -d " ")" >> "$OUT/b1.tsv"
    tail -2 "$OUT/b1.tsv"
  done
done
column -t "$OUT/b1.tsv"
