#!/bin/bash
set -Eeuo pipefail
exec > >(tee -a /var/log/shiken-startup.log) 2>&1
BUCKET=$(curl -fsH 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/shiken-bucket)
RUN=$(curl -fsH 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/shiken-run)
PROJECT=$(curl -fsH 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/shiken-project)
ZONE=$(curl -fsH 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/shiken-zone)
INSTANCE=$(curl -fsH 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/shiken-instance)
PREFIX="gs://$BUCKET/shiken/$RUN"; WORK=/opt/shiken; export SHIKEN_PREFIX="$PREFIX"
STATE=running; NOTE=起動
write_status(){ python3 - "$WORK/status.json" "$STATE" "$NOTE" "$RUN" <<'PY'
import datetime,json,sys
json.dump({'run_id':sys.argv[4],'state':sys.argv[2],'note':sys.argv[3],'updated':datetime.datetime.now(datetime.timezone.utc).isoformat()},open(sys.argv[1],'w'),ensure_ascii=False)
PY
  gcloud storage cp --quiet "$WORK/status.json" "$PREFIX/status.json" >/dev/null 2>&1 || true
}
finish(){ local rc=$?; trap - EXIT; if [ "$rc" -eq 0 ]; then STATE=complete; NOTE=結果を保存; else STATE=failed; NOTE='試験に失敗（詳細はVM内。問題内容は記録しない）'; fi; write_status; gcloud storage cp --quiet /var/log/shiken-startup.log "$PREFIX/startup.log" >/dev/null 2>&1 || true; gcloud compute instances delete "$INSTANCE" --project="$PROJECT" --zone="$ZONE" --quiet >/dev/null 2>&1 || true; }
trap 'rc=$?; exit "$rc"' ERR
trap finish EXIT
mkdir -p "$WORK"; cd "$WORK"; write_status
# 10分ごとに一般的な進捗だけ写す。秘密問題の本文・tegoro詳細レポートは対象外。
(while sleep 600; do gcloud storage cp --quiet /var/log/shiken-startup.log "$PREFIX/startup.log" >/dev/null 2>&1 || true; done) &
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential cmake libcurl4-openssl-dev libssl-dev python3 python3-venv curl ca-certificates google-cloud-cli
gcloud storage cp --quiet "$PREFIX/llama-src.tar.gz" .
gcloud storage cp --quiet "$PREFIX/code.tar.gz" .
gcloud storage cp --quiet "$PREFIX/vocab_keep_9999_q36_ids.txt" .
gcloud storage cp --quiet "$PREFIX/problem.jsonl" ./problem.jsonl
gcloud storage cp --quiet "$PREFIX/config.json" ./config.json
tar -xzf llama-src.tar.gz; tar -xzf code.tar.gz; [ -d llama-src ] || mv src llama-src   # tar の中は src/
export KERNEL_KIROKU_DIR="$WORK/state/kiroku" KERNEL_HIKAE_DIR="$WORK/state/hikae" KERNEL_HIKAE_PATH="$WORK/state/hikae" KERNEL_TSUIKA_DIR="$WORK/state/tsuika" KERNEL_WAZA_DIR="$WORK/state/waza"
mkdir -p "$KERNEL_KIROKU_DIR" "$KERNEL_HIKAE_DIR" "$KERNEL_TSUIKA_DIR" "$KERNEL_WAZA_DIR"
NOTE="llama.cpp CPUビルド"; write_status
cmake -S llama-src -B llama-src/build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_METAL=OFF -DGGML_NATIVE=OFF -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_AVX512=OFF -DGGML_AMX_TILE=OFF -DGGML_AMX_INT8=OFF -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF
cmake --build llama-src/build --target llama-server -j 8
NOTE="模型取得"; write_status
gcloud storage cp --quiet "gs://$BUCKET/models/Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf" model.gguf
NOTE="試験実行"; write_status
python3 - <<'PY'
import json,shlex,subprocess,os,time,urllib.request
c=json.load(open('config.json')); env=os.environ.copy(); env.update(c['env']); env['KERNEL_LOCAL_URL']='http://127.0.0.1:8080'; env['KOUKAI_VOCAB_KEEP']='vocab_keep_9999_q36_ids.txt'
args=shlex.split(c['args']); rest=[]
for a in args:
 if a.startswith('KOUKAI_') and '=' in a:
  k,v=a.split('=',1); env[k]=v
 else: rest.append(a)
cmd=['llama-src/build/bin/llama-server','-m','model.gguf','--host','127.0.0.1','--port','8080','-t','8','-ngl','0','-c','8192','-np','1','-cb','-ub','256','--cache-reuse','16','-fa','off','--reasoning-format','none',*rest]
slog=open('server.log','w'); server=subprocess.Popen(cmd,stdout=slog,stderr=subprocess.STDOUT,env=env)   # 起動の失敗が見えるように
try:
 for _ in range(360):
  if server.poll() is not None:
   import sys; sys.stderr.write(''.join(open('server.log',errors='replace').readlines()[-25:])); sys.stderr.write(subprocess.run(['bash','-c','dmesg | tail -5; free -g; nproc; grep -o -m1 "avx512[a-z]*" /proc/cpuinfo'],capture_output=True,text=True).stdout); raise RuntimeError(f'server stopped rc={server.returncode}')
  try: urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2); break
  except Exception: time.sleep(5)
 else: raise RuntimeError('server startup timeout')
 os.environ.update(env)
 if 'KERNEL_JIYUU_OPTS' not in c['env']: os.environ['KERNEL_JIYUU_OPTS']=json.dumps(c['opts'],ensure_ascii=False,separators=(',',':'))
 # Markdownの詳細（問題文・回答）はVM内だけに保持し、GCSへは点・ID・秒だけ保存。
 r=subprocess.run(['python3','dougu/tegoro.py','--wa','jiyuu','--kata','輪','--mondai','problem.jsonl','--output','private-report.md'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=os.environ.copy())
 score_line=next((l for l in r.stdout.splitlines() if l.startswith('jiyuu: PASS')),'')   # 点の1行だけ（問題文は含まない）
 rows=[]
 for line in open('private-report.md',encoding='utf-8'):
  if not line.startswith('| '): continue
  cells=[x.strip().replace('\\|','|') for x in line.strip().strip('|').split('|')]
  if len(cells)>=3 and cells[1] in ('PASS','FAIL','SKIP'):   # jiyuu の表は「番号|可否|秒|答え」の4列（10/4）
   try: seconds=float(cells[2] if len(cells)<9 else cells[4])
   except ValueError: continue
   rows.append({'id':cells[0],'status':cells[1],'seconds':seconds})
 if not rows: raise RuntimeError('empty score')
 json.dump({'pass':sum(x['status']=='PASS' for x in rows),'total':len(rows),'score_line':score_line,'results':rows},open('result.json','w'),ensure_ascii=False,separators=(',',':'))
 subprocess.run(['gcloud','storage','cp','--quiet','result.json',os.environ['SHIKEN_PREFIX']+'/result.json'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if r.returncode: raise RuntimeError('checks failed')
finally:
 server.terminate()
 try: server.wait(timeout=30)
 except subprocess.TimeoutExpired: server.kill()
PY
