"""段の開始・完了を原子的に保存。クラウド接続なし。"""
import datetime
import json
import os
import pathlib
import sys

STATUS = pathlib.Path('/opt/sanjigen/output/status.json')


def update(stage, action='running', detail='', **fields):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data = json.loads(STATUS.read_text()) if STATUS.exists() else {'state': 'running', 'completed_stages': {}}
    if action == 'finalize':
        if int(detail) != 0 or data.get('state') not in ('success', 'prepared'):
            data.update(state='failed', detail=f'終了コード {detail}。startup.log参照')
        data['exit_code'] = int(detail)
    else:
        data.update(stage=stage, state='running')
        if action == 'completed':
            data.setdefault('completed_stages', {})[stage] = now
        elif action in ('prepared', 'success', 'failed'):
            data.update(state=action, detail=detail)
    data.update(updated_at=now, **fields)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS.with_name(f'status.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(STATUS)
    print(f'{now} stage={stage} {action} {detail}', flush=True)


if __name__ == '__main__':
    update(*sys.argv[1:])
