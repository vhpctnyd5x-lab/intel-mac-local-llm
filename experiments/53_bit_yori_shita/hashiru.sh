#!/bin/bash
# A1・B1 を小さい模型で通しで回す（docs/kenkyuu/bit_yori_shita.md §5「まず A1 と B1 を小さい模型で」）。
#
#   LLAMA=~/llama.cpp  OUT=~/kekka_53 \
#   bash hashiru.sh MODEL_DIR KOUSEI.txt HYOUKA1.txt [HYOUKA2.txt]
#
# MODEL_DIR  HF の safetensors（MoE。例 ibm-granite/granite-3.1-1b-a400m-base、allenai/OLMoE-1B-7B-0125）
# KOUSEI     imatrix の較正文。HYOUKA*  KLD を測る文（較正文と重ねない。2つ渡すと両方で測る）
# 出来た物は作り直さないので、途中で止めても続きから流せる。表は $OUT/matome.md。
set -eu
MODEL_DIR=$1; KOUSEI=$2; shift 2; HYOUKA=("$@")
LLAMA=${LLAMA:?llama.cpp の場所（build/bin に llama-quantize 等）}
OUT=${OUT:-./kekka_53}; T=${THREADS:-4}; CTX=${CTX:-512}; CHUNKS=${CHUNKS:-80}
FRACS=${FRACS:-"0.25 0.5 0.75"}; ERABI=${ERABI:-"shiyou rand hanten"}
HOT=${HOT:-Q2_K}; COLD=${COLD:-iq1_m}
HERE=$(cd "$(dirname "$0")" && pwd); BIN=$LLAMA/build/bin
export PYTHONPATH=$LLAMA/gguf-py${PYTHONPATH:+:$PYTHONPATH}
mkdir -p "$OUT"; cd "$OUT"
log() { echo "[$(date +%H:%M:%S)] $*"; }

# A1: BF16 の情報量（変換前の safetensors をそのまま読む）
[ -s a1.json ] || { log A1; python3 "$HERE/a1_bf16_joho.py" "$MODEL_DIR" --out a1.json 2>a1.log > a1.md; }

# 土台: BF16 の GGUF → imatrix → 熱い型・冷たい型
[ -s base.gguf ] || { log 変換; python3 "$LLAMA/convert_hf_to_gguf.py" "$MODEL_DIR" --outtype bf16 --outfile base.gguf > conv.log 2>&1; }
[ -s imatrix.gguf ] || { log imatrix; "$BIN/llama-imatrix" -m base.gguf -f "$KOUSEI" -c "$CTX" -t "$T" -o imatrix.gguf > imat.log 2>&1; }
python3 "$HERE/b1_mazeru.py" shiyou imatrix.gguf --json shiyou.json > shiyou.md
[ -s hot.gguf ] || { log "熱い $HOT"; "$BIN/llama-quantize" --imatrix imatrix.gguf base.gguf hot.gguf "$HOT" "$T" > q_hot.log 2>&1; }
[ -s cold.gguf ] || { log "冷たい $COLD"; "$BIN/llama-quantize" --imatrix imatrix.gguf --tensor-type "ffn_.*_exps=$COLD" base.gguf cold.gguf "$HOT" "$T" > q_cold.log 2>&1; }
# 同じ大きさの比べ相手: 専門家を一律 IQ2_XXS（2.06 bit）
[ -s iq2xxs.gguf ] || { log "一律 iq2_xxs"; "$BIN/llama-quantize" --imatrix imatrix.gguf --tensor-type "ffn_.*_exps=iq2_xxs" base.gguf iq2xxs.gguf "$HOT" "$T" > q_iq2.log 2>&1; }

# 混ぜた模型（入れ物 Q8_0）。端の 0・1 は入れ物の誤差の確かめ（hot・cold と同じ KLD になるはず）
mk() { [ -s "$1.gguf" ] || python3 "$HERE/b1_mazeru.py" tsukuru --hot hot.gguf --cold cold.gguf --imatrix imatrix.gguf \
        --frac "$2" --erabi "$3" ${4:+--seed $4} --out "$1.gguf" > "$1.log" 2>&1; }
VARS="hot cold iq2xxs"
mk mix_0 0 shiyou; mk mix_1 1 shiyou; VARS="$VARS mix_0 mix_1"
for f in $FRACS; do for e in $ERABI; do mk "mix_${e}_$f" "$f" "$e"; VARS="$VARS mix_${e}_$f"; done
  case " $ERABI " in *" rand "*) mk "mix_rand_${f}_s1" "$f" rand 1; VARS="$VARS mix_rand_${f}_s1";; esac; done
for f in $FRACS; do mk "mix_zentai_$f" "$f" zentai; VARS="$VARS mix_zentai_$f"; done

# KLD（土台 BF16 との差）。文ごとに土台の答えを1回だけ取る
zumi() { [ -s "$1" ] && grep -q "Mean    KLD" "$1" && grep -q "Same top p:" "$1"; }
i=0
for H in "${HYOUKA[@]}"; do
  i=$((i+1))
  [ -s "base_$i.kld" ] || { log "土台の答え 文$i"; "$BIN/llama-perplexity" -m base.gguf -f "$H" -c "$CTX" --chunks "$CHUNKS" -t "$T" --kl-divergence-base "base_$i.kld" > "pb_$i.log" 2>&1; }
  for v in $VARS; do
    # llama.cpp の非同期ログは終了時に尾（KLD の集計）を落とすことがある（終了コードは0）。揃うまで最大3回
    for try in 1 2 3; do
      zumi "k_${v}_$i.log" && break
      log "KLD $v 文$i（$try 回目）"; "$BIN/llama-perplexity" -m "$v.gguf" --kl-divergence-base "base_$i.kld" --kl-divergence -t "$T" > "k_${v}_$i.log" 2>&1
    done
    zumi "k_${v}_$i.log" || log "注意: k_${v}_$i.log に集計がありません"
  done
done

B1="$HERE/b1_mazeru.py" python3 - "$VARS" "${#HYOUKA[@]}" > matome.md <<'EOF'
import json, re, sys, os
vars_, n = sys.argv[1].split(), int(sys.argv[2])
def pick(path, key):
    try:
        for line in open(path, errors="ignore"):
            if line.strip().startswith(key):
                return line.split(":", 1)[1].split()[0]
    except FileNotFoundError:
        pass
    return "-"
def size(v):
    j = v + ".gguf.json"
    if os.path.exists(j):
        d = json.load(open(j)); return d["bpw_exps"], d["GiB"], d["cold_token_share"]
    import subprocess
    d = json.loads(subprocess.run([sys.executable, os.environ["B1"], "ookisa", v + ".gguf"],
                                  capture_output=True, text=True, check=True).stdout)
    return d["bpw_exps"], d["GiB"], None
print("| 版 | 専門家 bit/重み | 大きさ GiB | 冷たい側に回る字 | " + " | ".join(f"KLD 文{i} | PPL 文{i} | 同じ top1 文{i}" for i in range(1, n+1)) + " |")
print("|---|---:|---:|---:|" + "---:|" * (3 * n))
for v in vars_:
    b, g, s = size(v)
    cells = []
    for i in range(1, n+1):
        L = f"k_{v}_{i}.log"
        cells += [pick(L, "Mean    KLD"), pick(L, "Mean PPL(Q)"), pick(L, "Same top p")]
    print(f"| {v} | {'-' if b is None else f'{b:.3f}'} | {g:.3f} | {'-' if s is None else f'{s:.1%}'} | " + " | ".join(cells) + " |")
EOF
log "済み: $OUT/matome.md"; cat matome.md
