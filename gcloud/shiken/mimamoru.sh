#!/bin/bash
# 起動後の状態を確認する。引数: PROJECT ZONE INSTANCE BUCKET RUN_ID SA ROLE CONDITION [分=250]
set -uo pipefail   # 10/4: gcloud の一時的な失敗で黙って抜けていた
PROJECT=${1:?}; ZONE=${2:?}; NAME=${3:?}; BUCKET=${4:?}; RUN=${5:?}; SA=${6:?}; ROLE=${7:?}; CONDITION=${8:?}; LIMIT=${9:-250}
PREFIX="gs://$BUCKET/shiken/$RUN"; START=$(date +%s); TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cleanup(){
  local end=$(( $(date +%s)+600 ));
  while [ -n "$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)' 2>/dev/null)" ] && (( $(date +%s)<end )); do sleep 10; done
  if [ -n "$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)' 2>/dev/null)" ]; then echo "VMが残存。IAMは残し安全側で停止: $NAME"; return 1; fi
  gcloud projects remove-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="projects/$PROJECT/roles/$ROLE" --condition="$CONDITION" --quiet >/dev/null 2>&1 || true
  gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin --quiet >/dev/null 2>&1 || true
  gcloud iam service-accounts delete "$SA" --project="$PROJECT" --quiet >/dev/null 2>&1 || true
}
while (( $(date +%s)-START < LIMIT*60 )); do
  state= note=
  if gcloud storage cat "$PREFIX/status.json" >"$TMP/status.json" 2>/dev/null; then
    state=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["state"])' "$TMP/status.json" 2>/dev/null || true)
    note=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["note"])' "$TMP/status.json" 2>/dev/null || true)
  fi
  if [ -n "$state" ]; then echo "$(date '+%H:%M:%S') $state $note"; fi
  if [ "$state" = complete ]; then gcloud storage cat "$PREFIX/result.json"; echo; echo "完了: $PREFIX/result.json"; cleanup; exit 0; fi
  if [ "$state" = failed ]; then echo "失敗: $PREFIX/startup.log"; gcloud storage cat "$PREFIX/startup.log" 2>/dev/null | tail -20; cleanup; exit 1; fi
  if (( $(date +%s)%600 < 60 )); then gcloud storage cat "$PREFIX/startup.log" 2>/dev/null | tail -5; fi
  if [ -z "$(gcloud compute instances list --project="$PROJECT" --filter="name=$NAME" --format='value(name)' 2>/dev/null)" ]; then echo 'VMが消失（Spot中断または時間上限）'; exit 1; fi
  sleep 60
done
echo '見張り上限。VMの最大実行時間は別途4時間以内に設定済み。'; exit 1
