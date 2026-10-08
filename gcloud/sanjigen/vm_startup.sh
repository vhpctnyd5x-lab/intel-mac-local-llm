#!/bin/bash
# 最初の実行命令からシリアルにも出す。宛先判明まではローカルに保持。
exec > >(tee -a /tmp/sanjigen-startup.log) 2>&1
set -Eeuo pipefail
umask 077
echo "$(date -u +%FT%TZ) stage=boot startup-script開始 pid=$$"
ROOT=/opt/sanjigen
PREFIX=; PUBLISH_PID=; STAGE=boot
MD=http://metadata.google.internal/computeMetadata/v1
meta() { curl --connect-timeout 2 --max-time 5 -fsH 'Metadata-Flavor: Google' "$MD/$1"; }
stage() {
  STAGE=$1
  echo "$(date -u +%FT%TZ) stage=$STAGE ${2:-running}"
  python3 "$ROOT/progress.py" "$STAGE" "${2:-running}"
}
publish() { bash "$ROOT/observe.sh" --once; }
finish() {
  local rc=$?
  trap - EXIT ERR TERM INT
  set +e
  if [[ -n $PUBLISH_PID ]]; then kill -- "-$PUBLISH_PID"; wait "$PUBLISH_PID"; fi
  if [[ -s $ROOT/progress.py ]]; then python3 "$ROOT/progress.py" "$STAGE" finalize "$rc"; fi
  echo "$(date -u +%FT%TZ) stage=finish rc=$rc"
  if [[ -n $PREFIX && -f $ROOT/observe.sh ]]; then
    publish
    timeout 90s gcloud storage cp --recursive "$ROOT"/output/* "$PREFIX/"
    local upload_rc=$?
    printf '{"exit_code":%s,"upload_exit_code":%s}\n' "$rc" "$upload_rc" >"$ROOT/output/vm-finished.json"
    timeout 15s gcloud storage cp "$ROOT/output/vm-finished.json" "$PREFIX/vm-finished.json"
    # 手元のシリアル保存印を最大60秒待つ。強制期限はGCP側で有効。
    for _ in {1..12}; do
      timeout 3s gcloud storage cp "$PREFIX/serial-collected.json" "$ROOT/serial-collected.json" >/dev/null 2>&1 && break
      sleep 2
    done
  fi
  if [[ -n ${NAME:-} && -n ${PROJECT:-} && -n ${ZONE:-} ]]; then
    timeout 30s gcloud compute instances delete "$NAME" --project="$PROJECT" --zone="$ZONE" --async --quiet
  fi
  exit "$rc"
}
trap finish EXIT
trap 'rc=$?; echo "$(date -u +%FT%TZ) ERROR stage=$STAGE rc=$rc line=$LINENO command=$BASH_COMMAND"' ERR
trap 'echo "$(date -u +%FT%TZ) signal=TERM stage=$STAGE"; exit 143' TERM
trap 'exit 130' INT
mkdir -p "$ROOT/output"
# 本体アーカイブ取得前から状態を書けるようmetadataでも渡す。
meta instance/attributes/sanjigen-progress >"$ROOT/progress.py"
stage metadata
BUCKET=$(meta instance/attributes/sanjigen-bucket); RUN=$(meta instance/attributes/sanjigen-run)
PREFIX="gs://$BUCKET/sanjigen/$RUN"; export PREFIX
printf '%s' "$PREFIX" >"$ROOT/prefix"
cat >"$ROOT/observe.sh" <<'OBSERVER'
#!/bin/bash
set -u
ROOT=/opt/sanjigen
PREFIX=$(cat "$ROOT/prefix")
snapshot() {
  echo "$(date -u +%FT%TZ) observer diagnostics"
  timeout 5s nvidia-smi || true
  timeout 3s df -h / /opt/sanjigen || true
}
preemption() {
  local value
  # 一度観測したTRUEを、終了時のFALSE/通信失敗で消さない。
  if [[ -f $ROOT/output/preemption.json ]] && grep -q '"preempted":"TRUE"' "$ROOT/output/preemption.json"; then return 0; fi
  value=$(curl --connect-timeout 1 --max-time 2 -fsH 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/instance/preempted 2>/dev/null) || value=UNKNOWN
  printf '{"preempted":"%s","observed_at":"%s"}\n' "$value" "$(date -u +%FT%TZ)" >"$ROOT/output/preemption.$$.tmp"
  mv "$ROOT/output/preemption.$$.tmp" "$ROOT/output/preemption.json"
  if [[ $value == TRUE ]]; then echo "$(date -u +%FT%TZ) Spot preempted=TRUE"; return 0; fi
  return 1
}
upload() {
  # statusがまだ無い場合もログを残す。送信失敗も次のログへ。
  cp /tmp/sanjigen-startup.log "$ROOT/output/startup.log"
  local files=("$ROOT/output/startup.log" "$ROOT/output/preemption.json")
  [[ ! -f $ROOT/output/status.json ]] || files+=("$ROOT/output/status.json")
  timeout 20s gcloud storage cp "${files[@]}" "$PREFIX/" || echo "$(date -u +%FT%TZ) observer upload失敗"
}
if [[ ${1:-} == --once ]]; then
  preemption || true
  snapshot; upload
  exit 0
fi
last=0
while :; do
  if preemption; then upload; exit 0; fi
  now=$(date +%s)
  if ((now - last >= 60)); then snapshot; upload; last=$now; fi
  sleep 5
done
OBSERVER
# まず同期送信、その後の送り役。Spot終了時もshutdown-scriptから呼ぶ。
publish
setsid bash "$ROOT/observe.sh" >>/tmp/sanjigen-startup.log 2>&1 &
PUBLISH_PID=$!
NAME=$(meta instance/name); ZONE=$(meta instance/zone); ZONE=${ZONE##*/}
PROJECT=$(meta project/project-id)
IMAGE=$(meta instance/attributes/sanjigen-image); export IMAGE
MAX_MINUTES=$(meta instance/attributes/sanjigen-max-minutes)
[[ $MAX_MINUTES =~ ^(30|[34][0-9]|50)$ ]] || exit 2
stage metadata completed
cd "$ROOT"
stage input
gcloud storage cp "$PREFIX/input/code.tar.gz" "$PREFIX/input/config.json" .
tar -xzf code.tar.gz
stage input completed
PREPARE=$(python3 -c 'import json;print(json.load(open("config.json"))["prepare"])')
if [[ -n $PREPARE ]]; then LIMIT=$((MAX_MINUTES * 60 - 300)); else LIMIT=1140; fi
LEFT=$(awk -v limit="$LIMIT" '{n=limit-int($1); print (n>0?n:0)}' /proc/uptime)
((LEFT > 0)) || exit 1
export ROOT
export -f stage
timeout --signal=TERM --kill-after=15s "${LEFT}s" /bin/bash -Eeuo pipefail <<'JOB'
trap 'rc=$?; echo "$(date -u +%FT%TZ) ERROR stage=$STAGE rc=$rc line=$LINENO command=$BASH_COMMAND"' ERR
export DEBIAN_FRONTEND=noninteractive
stage apt
apt-get update -qq
apt-get install -y -qq python3.10-venv python3.10-dev build-essential libgl1 libopengl0 libglib2.0-0 libegl1 libgomp1 libxrender1 libxi6 libxkbcommon0 libsm6
stage apt completed
stage gpu
nvidia-smi
stage gpu completed
export CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=8.9
export HF_HOME=/opt/sanjigen/hf U2NET_HOME=/opt/sanjigen/rembg PYTHONNOUSERSITE=1
python3.10 cache.py config.json
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DIFFUSERS_OFFLINE=1
if [[ -z $(/opt/sanjigen/venv/bin/python -c 'import json;print(json.load(open("config.json"))["prepare"])') ]]; then
  /opt/sanjigen/venv/bin/python run.py config.json
fi
JOB
