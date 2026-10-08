"""回収済みの証拠だけを表示。欠落を成功やSpot中断と決めつけない。"""
import json
import pathlib
import sys


def report(folder):
    p = pathlib.Path(folder)
    def read(name):
        try:
            value = json.loads((p / name).read_text())
            if not isinstance(value, dict):
                raise ValueError('JSON objectではない')
            return value
        except (OSError, ValueError) as exc:
            print(f'{name}: 未取得または不正 ({type(exc).__name__})')
            return {}
    s = read('status.json')
    print('結果:', s.get('state', '不明'), s.get('detail', ''))
    print('最終段:', s.get('stage', '不明'), '更新:', s.get('updated_at', '不明'))
    print('完了印:', ', '.join(s.get('completed_stages', {})) or 'なし')
    pre = read('preemption.json')
    print('Spot中断通知:', pre.get('preempted', '不明'), pre.get('observed_at', ''),
          '（FALSE/未取得でも、その後の中断は否定できない）')
    for name in ('startup.log', 'serial-port-1.txt', 'timings.json', 'vm-finished.json'):
        file = p / name
        print(f'{name}: {file.stat().st_size} bytes' if file.is_file() else f'{name}: 未取得')
    for name in ('startup.log', 'serial-port-1.txt'):
        file = p / name
        if file.is_file():
            print(f'── {name} 末尾')
            print('\n'.join(file.read_text(errors='replace').splitlines()[-8:]))
    if s.get('state') == 'success':
        if all((p / n).is_file() and (p / n).stat().st_size > 0 for n in ('model.glb', 'preview.png')):
            print('model.glb・preview.pngを確認')
        else:
            print('成功印はあるが成果物が欠落。生成完了とは判定しない')
    elif s.get('state') != 'prepared':
        print('生成/準備は未完了または不明。上記の証拠を確認してください')


if __name__ == '__main__':
    report(sys.argv[1])
