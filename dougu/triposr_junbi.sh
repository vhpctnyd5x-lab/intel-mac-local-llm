#!/bin/bash
# Claude が実行する準備台本。Codex は実行しない。版の自動変更・再試行はしない。
set -Eeuo pipefail
stage='事前確認'
trap 'code=$?; echo "失敗: ${stage}（終了 ${code}、行 ${LINENO}）。上のエラーを確認してください。版を変えて再試行していません。" >&2; exit "$code"' ERR
MIRROR="$HOME/LocalAI_mirror"
VENV="$MIRROR/seisei_venv"
UTA="$MIRROR/uta_venv/bin/python3.11"
REPO="$MIRROR/TripoSR"
MODELS="$MIRROR/models/triposr"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
COMMIT="${TRIPOSR_COMMIT:-}"
if [[ ! "$COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    echo '不足: TRIPOSR_COMMIT に確認済みの40桁 commit SHA を指定してください（main・タグ・短縮SHAは不可）。取得前に停止。' >&2
    exit 2
fi
[[ "$(uname -s)" == Darwin && "$(uname -m)" == x86_64 ]] || { echo 'macOS x86_64 専用です' >&2; exit 2; }
[[ -x "$UTA" ]] || { echo "不足: $UTA" >&2; exit 2; }
command -v git >/dev/null || { echo '不足: git（Command Line Tools）' >&2; exit 2; }
[[ ! -L "$VENV" && ! -L "$REPO" && ! -L "$MODELS" ]] || { echo '準備先のシンボリックリンクは使いません' >&2; exit 2; }
# 歌用 venv の site-packages はコピーしない。土台の実行ファイルだけを参照。
BASE="$("$UTA" -I -B -c 'import sys; assert sys.version_info[:2] == (3, 11); print(sys._base_executable)')"
stage='seisei_venv 作成'
if [[ ! -e "$VENV" ]]; then
    "$BASE" -I -m venv "$VENV"
fi
PY="$VENV/bin/python"
"$PY" -I -c 'import platform,sys; assert sys.version_info[:2]==(3,11) and platform.machine()=="x86_64"; assert sys.prefix!=sys.base_prefix'

stage='TripoSR の固定 commit 取得'
if [[ ! -e "$REPO" ]]; then
    git clone --no-checkout https://github.com/VAST-AI-Research/TripoSR.git "$REPO"
    git -C "$REPO" checkout --detach "$COMMIT"
fi
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$COMMIT" ]] || { echo '既存 TripoSR の HEAD が指定SHAと違います。変更せず停止。' >&2; exit 2; }
# 既存の変更は自分の marching-cubes パッチ以外、受け入れない。
changes="$(git -C "$REPO" status --porcelain --untracked-files=no)"
[[ -z "$changes" || "$changes" == ' M tsr/models/isosurface.py' ]] || { echo '既存 TripoSR に別の変更があります。変更せず停止。' >&2; exit 2; }

stage='依存導入（macOS の torch wheel は CPU 版）'
"$PY" -I -m pip install --disable-pip-version-check 'pip==24.0' 'setuptools==69.2.0' 'wheel==0.43.0'
REQ="$(mktemp -t triposr-requirements)"
trap 'rm -f -- "$REQ"' EXIT
cat > "$REQ" <<'REQS'
numpy==1.26.4
torch==2.2.2
torchvision==0.17.2
transformers==4.35.0
tokenizers==0.14.1
safetensors==0.4.2
einops==0.7.0
omegaconf==2.3.0
antlr4-python3-runtime==4.9.3
PyYAML==6.0.1
trimesh==4.0.5
huggingface_hub==0.16.4
imageio==2.33.1
Pillow==10.1.0
scipy==1.12.0
scikit-image==0.22.0
networkx==3.2.1
sympy==1.12
filelock==3.13.1
fsspec==2023.12.2
Jinja2==3.1.3
MarkupSafe==2.1.5
typing_extensions==4.10.0
packaging==23.2
requests==2.31.0
urllib3==2.2.1
certifi==2024.2.2
charset-normalizer==3.3.2
idna==3.6
tqdm==4.66.2
lazy_loader==0.3
tifffile==2023.12.9
mpmath==1.3.0
REQS
# antlr は純Pythonのためソース導入可。torch 等のネイティブ依存は wheel 必須。
"$PY" -I -m pip install --disable-pip-version-check --no-build-isolation \
    --only-binary=numpy,torch,torchvision,scipy,scikit-image,tokenizers,safetensors,Pillow \
    -r "$REQ"
stage='任意の texture bake 依存'
BAKE=0
mkdir -p "$MODELS"
if "$PY" -I -m pip install --disable-pip-version-check --only-binary=:all: \
    -c "$REQ" 'xatlas==0.0.9' 'moderngl==5.10.0' 'glcontext==2.5.0' > "$MODELS/bake-install.log" 2>&1; then
    BAKE=1
else
    echo "texture bake の固定版 wheel が導入できません。ベイクなし（頂点色GLB）: $MODELS/bake-install.log" >&2
    tail -n 12 "$MODELS/bake-install.log" >&2
fi
stage='CPU パッチ・模型取得・オフライン準備'
HF_HOME="$MODELS/hf" "$PY" -I -B "$HERE/sanjigen_gazou.py" --prepare "$REPO" "$MODELS" "$COMMIT" "$BAKE"
stage='整合確認'
"$PY" -I -m pip check
"$PY" -I -m pip freeze > "$MODELS/pip-freeze.txt"
echo "準備完了: $VENV / $REPO @ $COMMIT（本番への組込・推論は未実行）"
