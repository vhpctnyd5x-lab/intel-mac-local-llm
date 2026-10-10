#!/bin/bash
set -Eeuo pipefail
umask 077
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
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
if ! gcloud storage rsync --recursive --exclude='^input/.*' "gs://$BUCKET/sanjigen/$RUN_ID/" "$OUT/"; then
  echo '回収失敗。手元にあるシリアル・ログから分かったことを表示します' >&2
fi
echo "取り戻し: $OUT"
BLENDER=/Applications/Blender.app/Contents/MacOS/Blender
if [[ -s $OUT/model.glb && ! -s $OUT/preview.png && -x $BLENDER ]]; then
  "$BLENDER" -b --factory-startup -P "$HERE/shitami.py" -- "$OUT/model.glb" "$OUT/preview.png" >"$OUT/shitami.log" 2>&1 || echo '下見の絵は作れませんでした（shitami.log）' >&2
fi
python3 "$HERE/report.py" "$OUT"
