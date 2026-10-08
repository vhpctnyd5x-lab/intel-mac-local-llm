#!/bin/bash
set -Eeuo pipefail
umask 077
mkdir -p /opt/sanjigen/output
exec > >(tee -a /opt/sanjigen/output/startup.log) 2>&1
MD=http://metadata.google.internal/computeMetadata/v1
meta() { curl --connect-timeout 5 --max-time 15 --retry 3 -fsH 'Metadata-Flavor: Google' "$MD/$1"; }
# GCPのmax-run-duration=30m+DELETEは、この台本が動かなくても有効。
NAME=$(meta instance/name); ZONE=$(meta instance/zone); ZONE=${ZONE##*/}
PROJECT=$(meta project/project-id)
BUCKET=$(meta instance/attributes/sanjigen-bucket); RUN=$(meta instance/attributes/sanjigen-run)
IMAGE=$(meta instance/attributes/sanjigen-image)
PREFIX="gs://$BUCKET/sanjigen/$RUN"; export PREFIX IMAGE
delete_self() { timeout 45s gcloud compute instances delete "$NAME" --project="$PROJECT" --zone="$ZONE" --async --quiet; }
finish() {
  local rc=$?
  trap - EXIT
  set +e
  if [[ ! -f /opt/sanjigen/output/status.json ]]; then
    echo '{"state":"failed","detail":"startup失敗・期限切れ。ログ参照"}' >/opt/sanjigen/output/status.json
  fi
  sync
  timeout 75s gcloud storage cp --recursive /opt/sanjigen/output/* "$PREFIX/"
  systemctl stop sanjigen-log.timer >/dev/null 2>&1
  delete_self
  exit "$rc"
}
trap finish EXIT
trap 'exit 143' TERM
# VM内の第2の見張り。再起動で時間を延ばさないよう /proc/uptime から差し引く。
LEFT=$(awk '{n=1800-int($1)-90; print (n>1?n:1)}' /proc/uptime)
cat >/opt/sanjigen/expire.sh <<'SH'
#!/bin/bash
timeout 30s gcloud storage cp /opt/sanjigen/output/startup.log "$(cat /opt/sanjigen/prefix)/startup.log" || true
timeout 30s gcloud compute instances delete "$(cat /opt/sanjigen/name)" --project="$(cat /opt/sanjigen/project)" --zone="$(cat /opt/sanjigen/zone)" --async --quiet || true
SH
printf '%s' "$PREFIX" >/opt/sanjigen/prefix
printf '%s' "$NAME" >/opt/sanjigen/name
printf '%s' "$PROJECT" >/opt/sanjigen/project
printf '%s' "$ZONE" >/opt/sanjigen/zone
systemd-run --unit=sanjigen-expire --on-active="${LEFT}s" /bin/bash /opt/sanjigen/expire.sh
# Spot中断や強制期限でも、最長60秒前までのログを残す。
systemd-run --unit=sanjigen-log --on-active=60s --on-unit-active=60s \
  /usr/bin/timeout 30s gcloud storage cp /opt/sanjigen/output/startup.log "$PREFIX/startup.log"
cd /opt/sanjigen
gcloud storage cp "$PREFIX/input/code.tar.gz" "$PREFIX/input/config.json" .
tar -xzf code.tar.gz
PREPARE=$(python3 -c 'import json;print(json.load(open("config.json"))["prepare"])')
if [[ -n $PREPARE ]]; then LIMIT=1650; else LIMIT=1140; fi
LEFT=$(awk -v limit="$LIMIT" '{n=limit-int($1); print (n>0?n:0)}' /proc/uptime)
((LEFT > 0)) || exit 1
# 一連の処理を1個のforeground process groupで制限。終了後は保存・削除のみ。
timeout --signal=TERM --kill-after=15s "${LEFT}s" /bin/bash -Eeuo pipefail <<'JOB'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3.10-venv python3.10-dev build-essential libgl1 libopengl0 libglib2.0-0 libegl1 libgomp1 libxrender1 libxi6 libxkbcommon0 libsm6
nvidia-smi
export CUDA_HOME=/usr/local/cuda
export TORCH_CUDA_ARCH_LIST=8.9
export HF_HOME=/opt/sanjigen/hf
export U2NET_HOME=/opt/sanjigen/rembg
export PYTHONNOUSERSITE=1
python3.10 cache.py config.json
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 DIFFUSERS_OFFLINE=1
if [[ -z $(/opt/sanjigen/venv/bin/python -c 'import json;print(json.load(open("config.json"))["prepare"])') ]]; then
  /opt/sanjigen/venv/bin/python run.py config.json
fi
JOB
