"""偽gcloudのみで、欠落回収・50分制限・削除前シリアル採取を検証。"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory() as name:
        tmp = pathlib.Path(name)
        spec = importlib.util.spec_from_file_location('progress', HERE / 'progress.py')
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        progress.STATUS = tmp / 'status.json'
        progress.update('torch')
        progress.update('torch', 'completed')
        progress.update('mesh-painter')
        progress.update('input', 'finalize', '124')
        status = json.loads(progress.STATUS.read_text())
        assert status['state'] == 'failed' and status['stage'] == 'mesh-painter'
        assert 'torch' in status['completed_stages'] and status['exit_code'] == 124
        progress.update('prepare', 'prepared', 'env')
        progress.update('input', 'finalize', '0')
        assert json.loads(progress.STATUS.read_text())['state'] == 'prepared'
        binary = tmp / 'bin'
        binary.mkdir()
        cloud = binary / 'gcloud'
        cloud.write_text('#!' + sys.executable + '\n' + r'''
import json,os,pathlib,sys
args=sys.argv[1:]; text=' '.join(args); base=pathlib.Path(os.environ['FAKE_ROOT'])
with (base/'calls').open('a') as f: f.write(json.dumps(args)+'\n')
scenario=os.environ.get('SCENARIO','complete')
if args[:3]==['storage','buckets','describe']:
 print(json.dumps(dict(location='US-CENTRAL1',uniform_bucket_level_access=True,public_access_prevention='enforced')))
elif args[:3]==['storage','buckets','get-iam-policy']: print('{"bindings":[]}')
elif args[:3]==['iam','roles','describe']: print('{"includedPermissions":["compute.instances.delete"]}')
elif args[:2]==['compute','images']: print('fake-dlvm')
elif args[:3]==['compute','instances','create']:
 assert '--max-run-duration=50m' in args
 assert '--provisioning-model=SPOT' in args
 metadata=next(x for x in args if x.startswith('--metadata-from-file='))
 for item in metadata.split('=',1)[1].split(','):
  _,filename=item.split('=',1);assert pathlib.Path(filename).is_file()
 (base/'vm').write_text(args[3])
elif args[:3]==['compute','instances','list']:
 if (base/'vm').exists() and not (base/'ack').exists():
  if scenario in ('missing','copyfail'):
   n=int((base/'poll').read_text()) if (base/'poll').exists() else 0
   (base/'poll').write_text(str(n+1))
   if n<1: print((base/'vm').read_text())
  else: print((base/'vm').read_text())
elif args[:3]==['compute','instances','get-serial-port-output']:
 print('startup-script開始\nERROR stage=torch rc=1 command=pip install')
elif args[:2]==['storage','cp']:
 if args[2].startswith('gs://'):
  dest=pathlib.Path(args[3]); filename=args[2].rsplit('/',1)[-1]
  if scenario=='missing':sys.exit(1)
  if filename=='startup.log':dest.write_text('stage=torch completed\n')
  elif filename=='vm-finished.json':dest.write_text('{"exit_code":0,"upload_exit_code":0}')
  else:sys.exit(1)
 elif args[-1].endswith('/serial-collected.json'):
  prior=[json.loads(x) for x in (base/'calls').read_text().splitlines()]
  assert any(x[:3]==['compute','instances','get-serial-port-output'] for x in prior)
  assert pathlib.Path(os.environ['FAKE_OUT'],'serial-port-1.txt').is_file()
  (base/'ack').write_text('saved')
elif args[:2]==['storage','rsync']:
 if scenario=='missing':sys.exit(1)
 dest=pathlib.Path(args[-1]);dest.mkdir(exist_ok=True)
 (dest/'status.json').write_text('{"state":"prepared","detail":"env","stage":"prepare","completed_stages":{"torch":"time"}}')
 (dest/'preemption.json').write_text('{"preempted":"FALSE"}')
''')
        cloud.chmod(0o700)
        sleep = binary / 'sleep'
        sleep.write_text('#!/bin/bash\nexit 0\n')
        sleep.chmod(0o700)
        copy = binary / 'cp'
        copy.write_text('#!/bin/bash\nif [[ ${SCENARIO:-} == copyfail && $2 == */serial-port-1.txt ]]; then exit 1; fi\nexec /bin/cp "$@"\n')
        copy.chmod(0o700)
        for scenario in ('complete', 'missing', 'copyfail'):
            base = tmp / scenario
            base.mkdir()
            out = base / 'out'
            env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                       PROJECT='fake-project', BUCKET='fake-bucket',
                       FAKE_ROOT=str(base), FAKE_OUT=str(out), SCENARIO=scenario,
                       ZONE='us-central1-a')
            result = subprocess.run(['bash', str(HERE / 'hajimeru.sh'), '--prepare-only', 'env',
                '--prepare-max-minutes', '50', '--provision', 'spot', '--execute',
                '--accept-license', '--out', str(out)], env=env, capture_output=True, text=True, errors="replace", timeout=15)
            assert result.returncode == 0, result.stdout + result.stderr
            assert (out / 'serial-port-1.txt').is_file() == (scenario != 'copyfail'), (scenario, result.stdout, result.stderr, (base / 'calls').read_text())
            calls = [json.loads(x) for x in (base / 'calls').read_text().splitlines()]
            assert any(x[:3] == ['iam', 'service-accounts', 'delete'] for x in calls)
            if scenario == 'complete':
                assert (base / 'ack').is_file() and 'prepared' in result.stdout
            elif scenario == 'copyfail':
                assert not (base / 'ack').exists()
                assert '保存に失敗' in result.stderr
            else:
                assert '結果: 不明' in result.stdout and '回収失敗' in result.stderr
                assert 'Traceback' not in result.stderr
            # torimodosu単独もstatus欠落・不正を例外にしない。
            bad = base / 'bad'
            bad.mkdir()
            (bad / 'status.json').write_text('{broken' if scenario == 'complete' else '[]')
            result = subprocess.run([sys.executable, str(HERE / 'report.py'), str(bad)], capture_output=True, text=True, check=True)
            assert '結果: 不明' in result.stdout
        # VM内の埋込shellにも構文検査（GPU/apt/クラウドは実行しない）。
        text = (HERE / 'vm_startup.sh').read_text()
        for tag in ('OBSERVER', 'JOB'):
            shell = text.split("<<'" + tag + "'\n", 1)[1].split('\n' + tag, 1)[0]
            subprocess.run(['bash', '-n'], input=shell, text=True, check=True)
        # shutdown送信役をローカルの置換ROOTで実行し、TRUEを保持する。
        observer = text.split("<<'OBSERVER'\n", 1)[1].split('\nOBSERVER', 1)[0]
        base = tmp / 'observer'
        (base / 'output').mkdir(parents=True)
        (base / 'prefix').write_text('gs://fake-bucket/sanjigen/fake')
        logfile = base / 'boot.log'
        logfile.write_text('最初の起動ログ\nERROR pip install\n')
        observer = observer.replace('/opt/sanjigen', str(base)).replace('/tmp/sanjigen-startup.log', str(logfile))
        for command, output in [('curl', 'TRUE'), ('nvidia-smi', 'GPU L4'), ('timeout', '')]:
            tool = binary / command
            tool.write_text('#!/bin/bash\n' + ('shift\nexec "$@"\n' if command == 'timeout' else f'echo {output}\n'))
            tool.chmod(0o700)
        env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'], FAKE_ROOT=str(base))
        result = subprocess.run(['bash', '-c', observer, '--', '--once'], env=env, capture_output=True, text=True, check=True)
        assert 'GPU L4' in result.stdout
        assert json.loads((base / 'output/preemption.json').read_text())['preempted'] == 'TRUE'
        (binary / 'curl').write_text('#!/bin/bash\necho FALSE\n')
        subprocess.run(['bash', '-c', observer, '--', '--once'], env=env, capture_output=True, text=True, check=True)
        assert json.loads((base / 'output/preemption.json').read_text())['preempted'] == 'TRUE'
        assert '最初の起動ログ' in (base / 'output/startup.log').read_text()
    print('診断回帰検査: 状態履歴・偽VM正常/欠落回収・シリアル保存印・Spot通知保持 OK（実gcloud未使用）')


if __name__ == '__main__':
    main()
