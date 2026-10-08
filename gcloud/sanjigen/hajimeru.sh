#!/bin/bash
# 既定は計画表示のみ。--execute は課金・アップロード・終了時の削除までの承認。
set -Eeuo pipefail
umask 077
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ZONE=${ZONE:-us-central1-a}; REGION=${ZONE%-*}
MAX_MINUTES=30
MODE=mv; TEXTURE=on; FACES=100000; PROVISION=auto; INPUT=; PROMPT=
PREPARE=; EXECUTE=0; LICENSE=0; OCTREE=384; SEED=12345
IMAGE_FAMILY=${IMAGE_FAMILY:-common-cu129-ubuntu-2204-nvidia-580}
RUN_ID="sanjigen-$(date -u +%Y%m%d-%H%M%S)-$RANDOM"
usage() {
  cat <<'HELP'
使い方: bash gcloud/sanjigen/hajimeru.sh 画像フォルダ [--mode mv|single|text]
  [--texture on|off] [--faces 100000] [--octree 384] [--seed 12345]
  [--provision auto|spot|standard] [--prompt '文章']
  [--prepare-only env|weights|all] [--accept-license] [--execute]
環境: PROJECT / BUCKET / ZONE / IMAGE_NAME / IMAGE_FAMILY。既定は実行せず計画表示。
HELP
}
while (($#)); do
  case "$1" in
    --mode) MODE=${2:?}; shift 2;;
    --texture) TEXTURE=${2:?}; shift 2;;
    --faces) FACES=${2:?}; shift 2;;
    --octree) OCTREE=${2:?}; shift 2;;
    --seed) SEED=${2:?}; shift 2;;
    --provision) PROVISION=${2:?}; shift 2;;
    --prompt) PROMPT=${2:?}; shift 2;;
    --prepare-only) PREPARE=${2:?}; shift 2;;
    --execute) EXECUTE=1; shift;;
    --accept-license) LICENSE=1; shift;;
    --help|-h) usage; exit 0;;
    --*) echo "不明な引数: $1" >&2; exit 2;;
    *) [[ -z $INPUT ]] || { usage; exit 2; }; INPUT=$1; shift;;
  esac
done
[[ $PROVISION == auto || $PROVISION == spot || $PROVISION == standard ]] || exit 2
[[ $ZONE =~ ^(us-central1|asia-northeast1)-[abc]$ ]] || { echo '許可地域外のZONEです' >&2; exit 2; }
TMP_WORK=$(mktemp -d)
SA_CREATED=0; DELETE_BOUND=0; STORAGE_BOUND=0; CREATED=0; FINISHED=0
cleanup() {
  local rc=$?
  trap - EXIT
  set +e
  if ((CREATED == 1 && FINISHED == 0)); then
    if gcloud compute instances list --project="$PROJECT" --zones="$ZONE" --filter="name=$RUN_ID" --format='value(name)' >"$TMP_WORK/cleanup-live" 2>/dev/null; then
      if [[ ! -s $TMP_WORK/cleanup-live ]]; then FINISHED=1; fi
    fi
  fi
  # 生存中・状態不明のVMから自己削除権限を奪わない。
  if ((CREATED == 0 || FINISHED == 1)); then
    if ((DELETE_BOUND)); then gcloud projects remove-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="projects/$PROJECT/roles/$ROLE" --condition="$DELETE_CONDITION" --quiet >/dev/null; fi
    if ((STORAGE_BOUND)); then gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin --condition="$STORAGE_CONDITION" --quiet >/dev/null; fi
    if ((SA_CREATED)); then gcloud iam service-accounts delete "$SA" --project="$PROJECT" --quiet >/dev/null; fi
  elif ((SA_CREATED)); then
    echo "VM状態未確定。30分のGCP側削除を確認後、$SA のIAMとSAを整理してください。" >&2
  fi
  rm -rf -- "$TMP_WORK"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 "$HERE/config.py" "$TMP_WORK/config.json" "$MODE" "$TEXTURE" "$FACES" "$OCTREE" "$SEED" "$PREPARE" "$INPUT" "$PROMPT"
if ((EXECUTE == 0)); then
  cat "$TMP_WORK/config.json"
  echo "計画のみ: $RUN_ID / $ZONE / g2-standard-8+L4×1 / $PROVISION / ${MAX_MINUTES}分で削除"
  echo '通常生成は準備済みキャッシュ必須。実行には --execute --accept-license。'
  exit 0
fi
((LICENSE)) || { echo 'docs/kenkyuu/sanjigen_gcp.md の条件を確認し --accept-license を指定してください' >&2; exit 2; }
command -v gcloud >/dev/null
PROJECT=${PROJECT:-$(gcloud config get-value project 2>/dev/null)}
[[ $PROJECT =~ ^[a-z][a-z0-9-]{4,61}[a-z0-9]$ ]] || { echo 'PROJECTが不正・未設定' >&2; exit 2; }
BUCKET=${BUCKET:-${PROJECT}-sanjigen-${REGION}}
[[ $BUCKET =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || exit 2
PREFIX="gs://$BUCKET/sanjigen/$RUN_ID"
SA_ID="sj-${RUN_ID#sanjigen-}"; SA="$SA_ID@$PROJECT.iam.gserviceaccount.com"
ROLE=sanjigenVmDelete
EXPIRES=$(python3 -c 'import datetime as d; print((d.datetime.now(d.timezone.utc)+d.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))')
DELETE_CONDITION="title=$RUN_ID,expression=request.time < timestamp('$EXPIRES') && resource.name.endsWith('/instances/$RUN_ID'),description=期限付き単一VM自己削除"
STORAGE_CONDITION="title=$RUN_ID,expression=request.time < timestamp('$EXPIRES') && (resource.name.startsWith('projects/_/buckets/$BUCKET/objects/sanjigen/$RUN_ID/') || resource.name.startsWith('projects/_/buckets/$BUCKET/objects/cache/sanjigen/')),description=期限付き成果物とキャッシュ"
retry() { local i; for i in 1 2 3 4 5 6; do "$@" && return 0; sleep 5; done; return 1; }
if ! gcloud storage buckets describe "gs://$BUCKET" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --project="$PROJECT" --location="$REGION" --uniform-bucket-level-access --public-access-prevention --quiet
fi
gcloud storage buckets describe "gs://$BUCKET" --format=json >"$TMP_WORK/bucket.json"
gcloud storage buckets get-iam-policy "gs://$BUCKET" --format=json >"$TMP_WORK/policy.json"
python3 "$HERE/config.py" bucket "$TMP_WORK/bucket.json" "$TMP_WORK/policy.json" "$REGION"
# 公式DLVMを具体的なイメージ名に固定（キャッシュ鍵にも使用）。
if [[ -n ${IMAGE_NAME:-} ]]; then
  IMAGE=$(gcloud compute images describe "$IMAGE_NAME" --project=deeplearning-platform-release --format='value(name)')
else
  IMAGE=$(gcloud compute images describe-from-family "$IMAGE_FAMILY" --project=deeplearning-platform-release --format='value(name)')
fi
[[ -n $IMAGE ]] || exit 1
gcloud iam service-accounts create "$SA_ID" --project="$PROJECT" --display-name="$RUN_ID" --quiet
SA_CREATED=1
if ! gcloud iam roles describe "$ROLE" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud iam roles create "$ROLE" --project="$PROJECT" --title='3D単一VM自己削除' --permissions=compute.instances.delete --stage=GA --quiet
fi
gcloud iam roles describe "$ROLE" --project="$PROJECT" --format=json >"$TMP_WORK/role.json"
python3 "$HERE/config.py" role "$TMP_WORK/role.json"
DELETE_BOUND=1
retry gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="projects/$PROJECT/roles/$ROLE" --condition="$DELETE_CONDITION" --quiet >/dev/null
STORAGE_BOUND=1
retry gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin --condition="$STORAGE_CONDITION" --quiet >/dev/null
tar -czf "$TMP_WORK/code.tar.gz" -C "$HERE" config.py cache.py run.py vm_startup.sh
gcloud storage cp "$TMP_WORK/config.json" "$TMP_WORK/code.tar.gz" "$PREFIX/input/"
if [[ -n $INPUT && $MODE != text && -z $PREPARE ]]; then
  # config.pyで検証済みの4方向PNGのみ。フォルダ内の無関係な資料は送らない。
  for view in front back left right; do
    if [[ $MODE == single && $view != front ]]; then continue; fi
    if [[ -f $INPUT/$view.png ]]; then gcloud storage cp "$INPUT/$view.png" "$PREFIX/input/$view.png"; fi
  done
fi
ARGS=("$RUN_ID" --project="$PROJECT" --zone="$ZONE" --machine-type=g2-standard-8
  --image-project=deeplearning-platform-release --image="$IMAGE"
  --boot-disk-size=200GB --boot-disk-type=pd-balanced --boot-disk-auto-delete
  --service-account="$SA" --scopes=cloud-platform --no-restart-on-failure
  --maintenance-policy=TERMINATE --max-run-duration="${MAX_MINUTES}m" --instance-termination-action=DELETE
  --labels=job=sanjigen --metadata="sanjigen-bucket=$BUCKET,sanjigen-run=$RUN_ID,sanjigen-image=$IMAGE,install-nvidia-driver=True"
  --metadata-from-file="startup-script=$HERE/vm_startup.sh" --quiet)
create_vm() {
  local provisioning=$1
  CREATED=1 # API応答が途切れても、実際には作成済みの可能性がある。
  gcloud compute instances create "${ARGS[@]}" --provisioning-model="$provisioning" 2>"$TMP_WORK/create.err"
}
if [[ $PROVISION == standard ]]; then
  create_vm STANDARD || { cat "$TMP_WORK/create.err" >&2; exit 1; }
elif ! create_vm SPOT; then
  cat "$TMP_WORK/create.err" >&2
  # IAM・画像・ディスク・quota等の失敗では通常VMに落とさない。
  if [[ $PROVISION != auto ]] || ! rg -q 'ZONE_RESOURCE_POOL_EXHAUSTED|RESOURCE_POOL_EXHAUSTED|does not have enough resources' "$TMP_WORK/create.err"; then exit 1; fi
  gcloud compute instances list --project="$PROJECT" --zones="$ZONE" --filter="name=$RUN_ID" --format='value(name)' >"$TMP_WORK/live"
  [[ ! -s $TMP_WORK/live ]] || { echo '同名VMがあるため再作成しません' >&2; exit 1; }
  create_vm STANDARD || { cat "$TMP_WORK/create.err" >&2; exit 1; }
fi
echo "起動: $RUN_ID。前で待ちます（再試行なし、30分で削除）。成果物: $PREFIX"
# dougu/matsu.sh gcpと同じ読み取り監視。ただし他のVMを待たず、この1台だけ。
WAIT_LIMIT=$((SECONDS + 35 * 60))
while ((SECONDS < WAIT_LIMIT)); do
  gcloud compute instances list --project="$PROJECT" --zones="$ZONE" --filter="name=$RUN_ID" --format='value(name)' >"$TMP_WORK/live"
  if [[ ! -s $TMP_WORK/live ]]; then FINISHED=1; break; fi
  sleep 20
done
((FINISHED)) || { echo '35分で監視終了。GCP側の削除状態を確認してください' >&2; exit 1; }
bash "$HERE/torimodosu.sh" "$RUN_ID" --bucket "$BUCKET"
echo 'VM削除を確認。期限付きIAMとSAを片付けます。'
