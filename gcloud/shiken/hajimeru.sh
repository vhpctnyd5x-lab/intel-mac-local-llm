#!/bin/bash
# 概算（us-central1、Spot、2026-10-04計画値。作成前に公式料金表で要再確認）:
#   c3-standard-8: 約 $0.20〜0.35/時、n2-standard-8: 約 $0.10〜0.18/時（Spot・変動）。
#   pd-standard 100GB 約 $0.0055/時、外部IPv4 約 $0.005/時。4時間上限でVM等 $0.45〜1.45。
#   GCSの模型・ソース・問題・結果保管料と転送費は別（同リージョン配置推奨）。Spot中断で再試行しない。
# 作るだけでは実行されない。使い方: bash gcloud/shiken/hajimeru.sh --mondai PATH [--opts JSON] [--args '...'] [--env KEY=VALUE]
# 環境: MACHINE_TYPE=c3-standard-8|n2-standard-8 ZONE=us-central1-a MAX_HOURS=4 BUCKET=...
set -Eeuo pipefail
umask 077
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$HERE/../.." && pwd)
LLAMA_SRC=${LLAMA_SRC:-$HOME/LocalAI_mirror/llama-koukai/src}
VOCAB="$ROOT/dougu/jikken/vocab_keep_9999_q36_ids.txt"
MODEL_NAME=Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf
MACHINE_TYPE=${MACHINE_TYPE:-c3-standard-8}
ZONE=${ZONE:-us-central1-a}; REGION=${ZONE%-*}; MAX_HOURS=${MAX_HOURS:-4}
[[ $MACHINE_TYPE == c3-standard-8 || $MACHINE_TYPE == n2-standard-8 ]] || { echo 'MACHINE_TYPEはc3-standard-8またはn2-standard-8'; exit 2; }
[[ $MAX_HOURS =~ ^[1-4]$ ]] || { echo 'MAX_HOURSは1〜4'; exit 2; }
MONDAI= OPTS='{"raw_template": true}' ARGS='KOUKAI_VOCAB_KEEP=vocab_keep_9999_q36_ids.txt --spec-type none -cram 512' RUN_ID="shiken-$(date -u +%Y%m%d-%H%M%S)-$RANDOM"
ENVS=()
while (($#)); do
  case "$1" in
    --mondai) MONDAI=${2:?}; shift 2;; --opts) OPTS=${2:?}; shift 2;; --args) ARGS=${2:?}; shift 2;;
    --env) ENVS+=("${2:?}"); shift 2;; *) echo "不明な引数: $1" >&2; exit 2;;
  esac
done
[ -n "$MONDAI" ] && [ -f "$MONDAI" ] || { echo '--mondai の問題ファイルが必要です'; exit 2; }
[[ "$MONDAI" = /* ]] || MONDAI="$MONDAI"
[ -d "$LLAMA_SRC" ] && [ -f "$VOCAB" ] || { echo 'llama src または語彙ファイルが見つかりません'; exit 2; }
python3 "$HERE/tamesu.py" validate --opts "$OPTS" --args "$ARGS" --env "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1:]))' ${ENVS[@]+"${ENVS[@]}"})"
command -v gcloud >/dev/null || { echo 'gcloud がありません'; exit 1; }
PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] && [ "$PROJECT" != '(unset)' ] || { echo 'gcloudの既定プロジェクトが未設定'; exit 1; }
BUCKET=${BUCKET:-${PROJECT}-chishiki}; PREFIX="gs://$BUCKET/shiken/$RUN_ID"; NAME=${RUN_ID//_/-}; SA_ID="shiken-$RANDOM"; SA="$SA_ID@$PROJECT.iam.gserviceaccount.com"; ROLE=shikenVmDelete; CONDITION="title=shiken-$RUN_ID,expression=request.time < timestamp('$(python3 -c 'import datetime as d;print((d.datetime.now(d.timezone.utc)+d.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"))')'),description=期限付き試験VM"
TMP_WORK=$(mktemp -d); CREATED=0; BOUND=0; BUCKET_BOUND=0; SA_CREATED=0
cleanup(){ local rc=$?; trap - EXIT; set +e; if ((CREATED == 0)); then if ((BOUND)); then gcloud projects remove-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="projects/$PROJECT/roles/$ROLE" --condition="$CONDITION" --quiet >/dev/null 2>&1; fi; if ((BUCKET_BOUND)); then gcloud storage buckets remove-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin --quiet >/dev/null 2>&1; fi; if ((SA_CREATED)); then gcloud iam service-accounts delete "$SA" --project="$PROJECT" --quiet >/dev/null 2>&1; fi; fi; rm -rf "$TMP_WORK"; exit "$rc"; }
retry(){ local i; for i in 1 2 3 4 5 6; do "$@" && return 0; sleep 10; done; return 1; }   # 作ったSAが行き渡るまで待つ
trap cleanup EXIT; trap 'exit 130' INT; trap 'exit 143' TERM
python3 - "$TMP_WORK/config.json" "$OPTS" "$ARGS" "$MONDAI" ${ENVS[@]+"${ENVS[@]}"} <<'PY'
import json,sys
out,opts,args,mondai,*env=sys.argv[1:]
values={}
for item in env:
 k,sep,v=item.partition('=')
 if not sep or not (k.startswith('KERNEL_') or k.startswith('KOUKAI_')) or not k.replace('_','').isalnum(): raise SystemExit('環境変数はKERNEL_* または KOUKAI_*')
 values[k]=v
json.dump({'opts':json.loads(opts),'args':args,'env':values,'mondai_name':mondai.rsplit('/',1)[-1]},open(out,'w'))
PY
gcloud services enable compute.googleapis.com storage.googleapis.com iam.googleapis.com --project="$PROJECT" --quiet
if ! gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then gcloud storage buckets create "gs://$BUCKET" --project="$PROJECT" --location="$REGION" --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention --quiet; fi
gcloud storage buckets describe "gs://$BUCKET" --format=json >"$TMP_WORK/bucket.json"
gcloud storage buckets get-iam-policy "gs://$BUCKET" --format=json >"$TMP_WORK/policy.json"
python3 - "$TMP_WORK/bucket.json" "$TMP_WORK/policy.json" "$REGION" <<'PY'
import json,sys
b=json.load(open(sys.argv[1])); p=json.load(open(sys.argv[2])); cfg=b.get('iamConfiguration',{})
if b.get('location','').lower()!=sys.argv[3].lower(): raise SystemExit('BUCKETとVMのリージョンが違います')
ubla=b.get('uniform_bucket_level_access', cfg.get('uniformBucketLevelAccess',{}).get('enabled')); pap=b.get('public_access_prevention', cfg.get('publicAccessPrevention'))
if not ubla or pap not in ('enforced','inherited'): raise SystemExit('非公開を保証できない既存BUCKETです。設定を変えず停止')
if any(m in ('allUsers','allAuthenticatedUsers') for bind in p.get('bindings',[]) for m in bind.get('members',[])): raise SystemExit('公開IAM bindingがあるため停止')
PY
gcloud iam service-accounts create "$SA_ID" --project="$PROJECT" --display-name="試験 $RUN_ID" --quiet; SA_CREATED=1
if ! gcloud iam roles describe "$ROLE" --project="$PROJECT" >/dev/null 2>&1; then gcloud iam roles create "$ROLE" --project="$PROJECT" --title='試験VM自己削除' --permissions=compute.instances.delete --stage=GA --quiet; fi
gcloud iam roles describe "$ROLE" --project="$PROJECT" --format=json >"$TMP_WORK/role.json"
python3 - "$TMP_WORK/role.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]));
if d.get('deleted') or set(d.get('includedPermissions',[])) != {'compute.instances.delete'}: raise SystemExit('自己削除role権限不一致')
PY
retry gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="projects/$PROJECT/roles/$ROLE" --condition="$CONDITION" --quiet >/dev/null; BOUND=1
retry gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin --quiet >/dev/null; BUCKET_BOUND=1
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$TMP_WORK/llama-src.tar.gz" --exclude=build --exclude=.git -C "$(dirname "$LLAMA_SRC")" "$(basename "$LLAMA_SRC")"
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$TMP_WORK/code.tar.gz" --exclude='dougu/kekka' --exclude='dougu/jikken' --exclude='dougu/*.jsonl' -C "$ROOT" $(cd "$ROOT" && ls dougu/*.py) monosashi
gcloud storage cp --quiet "$TMP_WORK/llama-src.tar.gz" "$PREFIX/llama-src.tar.gz"
gcloud storage cp --quiet "$TMP_WORK/code.tar.gz" "$PREFIX/code.tar.gz"
gcloud storage cp --quiet "$VOCAB" "$PREFIX/vocab_keep_9999_q36_ids.txt"
gcloud storage cp --quiet "$MONDAI" "$PREFIX/problem.jsonl"
gcloud storage cp --quiet "$TMP_WORK/config.json" "$PREFIX/config.json"
gcloud compute instances create "$NAME" --project="$PROJECT" --zone="$ZONE" --machine-type="$MACHINE_TYPE" --provisioning-model=SPOT --maintenance-policy=TERMINATE --instance-termination-action=DELETE --max-run-duration="${MAX_HOURS}h" --no-restart-on-failure --image-family=debian-12 --image-project=debian-cloud --boot-disk-size=50GB --boot-disk-type=pd-balanced --boot-disk-auto-delete --service-account="$SA" --scopes=cloud-platform --metadata="shiken-bucket=$BUCKET,shiken-run=$RUN_ID,shiken-project=$PROJECT,shiken-zone=$ZONE,shiken-instance=$NAME,shiken-prefix=shiken/$RUN_ID" --metadata-from-file="startup-script=$HERE/vm_startup.sh" --quiet
CREATED=1
echo "起動要求済み: $RUN_ID / $MACHINE_TYPE Spot / 最大${MAX_HOURS}時間 / $PREFIX"
echo "見張り: bash $HERE/mimamoru.sh $PROJECT $ZONE $NAME $BUCKET $RUN_ID $SA $ROLE \"$CONDITION\""
