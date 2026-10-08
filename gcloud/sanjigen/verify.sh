#!/bin/bash
# クラウド・模型・GPUを使わない検査1本。
set -Eeuo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TMP_CHECK=$(mktemp -d)
trap 'rm -rf -- "$TMP_CHECK"' EXIT
for file in "$HERE"/*.sh; do bash -n "$file"; done
echo 'bash -n: OK'
if command -v shellcheck >/dev/null; then
  shellcheck "$HERE"/*.sh
  echo 'shellcheck: OK'
else
  echo 'shellcheck: 未導入のため省略'
fi
PYTHONPYCACHEPREFIX="$TMP_CHECK/pycache" python3 -m py_compile "$HERE"/*.py
python3 - "$HERE" "$TMP_CHECK" <<'PY'
import json,os,pathlib,py_compile,struct,subprocess,sys,zlib
here,tmp=map(pathlib.Path,sys.argv[1:]); folder=tmp/'images';folder.mkdir()
def chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,128,8,2,0,0,0))
png+=chunk(b'IDAT',zlib.compress((b'\0'+b'\xff'*192)*128))+chunk(b'IEND',b'')
(folder/'front.png').write_bytes(png)
fake=tmp/'bin';fake.mkdir(); cloud=fake/'gcloud'
cloud.write_text('#!/bin/bash\necho "禁止: gcloudを呼びました" >&2\nexit 99\n');cloud.chmod(0o700)
env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'])
launcher=['bash',str(here/'hajimeru.sh')]
checks=[([str(folder),'--mode','mv'],'single'),
        (['--prepare-only','env','--mode','mv'],'mv'),
        (['--mode','text','--prompt','艤装のあるアニメキャラ'],'text')]
for args,expected in checks:
    r=subprocess.run(launcher+args,env=env,capture_output=True,text=True,check=True)
    c,_=json.JSONDecoder().raw_decode(r.stdout);assert c['mode']==expected
(folder/'back.png').write_bytes(png)
r=subprocess.run(launcher+[str(folder),'--mode','mv'],env=env,capture_output=True,text=True,check=True)
c,_=json.JSONDecoder().raw_decode(r.stdout);assert c['mode']=='mv' and len(c['views'])==2
for args in [[str(folder),'--faces','0'],[str(folder),'--octree','1024'],['--mode','text'],
             [str(folder),'--provision','unknown']]:
    assert subprocess.run(launcher+args,env=env,capture_output=True).returncode!=0
# シェル内のPythonも構文検査。
for script in here.glob('*.sh'):
    text=script.read_text();lines=text.splitlines();i=0
    while i<len(lines):
        if "<<'PY'" in lines[i]:
            end=lines.index('PY',i+1);p=tmp/(script.stem+'-inline.py')
            p.write_text('\n'.join(lines[i+1:end])+'\n');py_compile.compile(str(p),doraise=True);i=end
        i+=1
print('py_compile（埋込含む）・入力検証8件・dry-runのクラウド非接続: OK')
PY
