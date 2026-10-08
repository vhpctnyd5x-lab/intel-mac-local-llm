#!/bin/bash
set -Eeuo pipefail
umask 077
RUN_ID=${1:?RUN_IDが必要}; shift
BUCKET=${BUCKET:-}; OUT="${HOME}/Documents/カーネルの作品/$RUN_ID"
while (($#)); do
  case "$1" in
    --bucket) BUCKET=${2:?}; shift 2;;
    --out) OUT=${2:?}; shift 2;;
    *) echo "不明な引数: $1" >&2; exit 2;;
  esac
done
[[ $RUN_ID =~ ^sanjigen-[0-9]{8}-[0-9]{6}-[0-9]+$ ]] || exit 2
[[ $BUCKET =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || { echo '--bucketが必要' >&2; exit 2; }
mkdir -p -- "$OUT"
gcloud storage rsync --recursive --exclude='^input/.*' "gs://$BUCKET/sanjigen/$RUN_ID/" "$OUT/"
echo "取り戻し: $OUT"
python3 - "$OUT" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); s=json.loads((p/'status.json').read_text())
print('結果:',s['state'],s.get('detail',''))
if s['state']=='success' and (p/'model.glb').stat().st_size>0 and (p/'preview.png').stat().st_size>0:
    print('model.glb・preview.pngを確認')
elif s['state']!='prepared':
    raise SystemExit('生成未完了。startup.logとtimings.jsonを確認してください')
PY
