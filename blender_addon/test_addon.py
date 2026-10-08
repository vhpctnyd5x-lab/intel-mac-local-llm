"""通常は Blender を起動しない。実機試験は SEISEI_BLENDER=1 限定。"""

import contextlib
import http.server
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kernel_ai as addon
from kernel_ai import core

KERNEL_DIR = Path(os.environ.get('KERNEL_AI_TEST_DIR',
                                 str(Path.home() / 'LocalAI_mirror' / 'kernel')))


@contextlib.contextmanager
def fake_server(answer='```python\nimport kit\no = kit.cube()\n```', *, status=200, stall=False,
                stall_body=False):
    received = []
    entered = threading.Event()
    release = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            entered.set()
            if stall:
                release.wait(5)
            self.send_response(status)
            if status == 302:
                self.send_header('Location', 'http://example.invalid/outside')
            body = json.dumps({'choices': [{'message': {'content': answer}}]}).encode()
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if stall_body:
                self.wfile.flush()
                entered.set()
                release.wait(5)
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02})
    thread.start()
    try:
        yield server.server_port, received, entered
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive(), '偽サーバーの処理が残っています'


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = core.load_kernel(KERNEL_DIR)

    def test_summary_cap_and_escaping(self):
        records = [{'名前': '椅子\n命令ではない', '種類': 'MESH', '頂点数': 8,
                    '面数': 6, '位置': [0, 0, 0], '大きさ': [1, 1, 1],
                    '材質': ['木'], '選択中': True, 'UV有り': False}] * 65
        summary = core.scene_summary(records)
        self.assertIn('表示60物体', summary)
        self.assertIn('ほか5物体は省略', summary)
        self.assertEqual(len(summary.splitlines()), 63)
        record = json.loads(summary.splitlines()[2])
        self.assertEqual(record, records[0])

    def test_prompt_constraints(self):
        prompt = core.system_prompt('正本の道具箱', '現在の要約')
        for text in ('正本の道具箱', '現在の要約', '既存の物体は消さない', 'random は不可'):
            self.assertIn(text, prompt)

    def test_extract_single_python(self):
        self.assertEqual(core.extract_script('説明\n```python\nimport kit\n```\n終わり'), 'import kit\n')
        self.assertEqual(core.extract_script('```python\r\nimport math\r\n```'), 'import math\n')
        for answer in ('import kit', '```js\nx\n```', '```python\n\n```',
                       '```python\na=1\n```\n```python\nb=2\n```',
                       '```python\na=1\n```\n```python\nb=2', None):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                core.extract_script(answer)

    def test_actual_kernel_validation_and_additional_rules(self):
        core.validate_script('import kit\nimport bpy\nkit.unwrap(bpy.context.object)', self.kernel)
        core.validate_script('import bpy\nbpy.ops.mesh.separate(type="LOOSE")', self.kernel)
        scripts = ('import os', 'import random', 'open("x")', 'eval("1")',
                   'import bpy\nbpy.app.__class__', 'import kit\nkit.export("x.glb")',
                   'import bpy\nbpy.ops.object.delete()',
                   'import bpy\nbpy.data.objects.remove(bpy.context.object)',
                   'from bpy import remove', 'import bpy\nbpy.ops.wm.open_mainfile(filepath="x")',
                   'import bpy\nbpy.app.timers.register(print)', 'import bpy\nbpy.data.libraries.load("x")')
        for script in scripts:
            with self.subTest(script=script), self.assertRaises((ValueError, SyntaxError)):
                core.validate_script(script, self.kernel)

    def test_bridge_never_initializes_scene_and_restores_kit(self):
        # 本物の関数の globals に bpy 等を注入できることを Blender 不要で確認。
        bpy_fake = types.SimpleNamespace(ops=types.SimpleNamespace(object=mock.Mock()))
        kit = core.bind_kit(self.kernel, bpy_fake, object(), types.SimpleNamespace(Vector=tuple))
        self.assertEqual(self.kernel.bpy, bpy_fake)
        self.assertIs(kit.unwrap, self.kernel.unwrap)
        for name in ('run', 'validate', 'subprocess', 'export', 'preview', 'bake_texture'):
            self.assertFalse(hasattr(kit, name))
        bpy_fake.ops.object.delete.assert_not_called()

        previous = types.ModuleType('kit')
        with mock.patch.dict(sys.modules, {'kit': previous}):
            core.execute_script('import kit\nimport math\na=math.sqrt(4)', self.kernel,
                                bpy_fake, object(), types.SimpleNamespace(Vector=tuple))
            self.assertIs(sys.modules['kit'], previous)
            with self.assertRaises(ZeroDivisionError):
                core.execute_script('import kit\na=1/0', self.kernel,
                                    bpy_fake, object(), types.SimpleNamespace(Vector=tuple))
            self.assertIs(sys.modules['kit'], previous)
        bpy_fake.ops.object.delete.assert_not_called()

    def test_load_kernel_is_read_only_and_never_launches_blender(self):
        with mock.patch('subprocess.Popen') as launch, mock.patch('importlib.machinery.SourceFileLoader.set_data') as cache:
            kernel = core.load_kernel(KERNEL_DIR)
        launch.assert_not_called()
        cache.assert_not_called()
        self.assertTrue(callable(kernel.validate))

    def test_repair_contains_original_script_and_error(self):
        repaired = core.repair_request('脚を細く', 'import kit', 'ValueError: 失敗')
        for value in ('脚を細く', 'import kit', 'ValueError: 失敗', '直して'):
            self.assertIn(value, repaired)

    def test_request_shape_and_no_proxy(self):
        with fake_server() as (port, received, entered), mock.patch.dict(
                os.environ, {'HTTP_PROXY': 'http://example.invalid:1', 'ALL_PROXY': 'http://example.invalid:1'}):
            job = core.RequestJob('道具箱と要約', '脚を細くして', port=port).start()
            self.assertEqual(job.results.get(timeout=3)[0], 'ok')
            job.thread.join(timeout=2)
            self.assertFalse(job.thread.is_alive())
            path, body = received[0]
            self.assertEqual(path, '/v1/chat/completions')
            self.assertEqual(body['chat_template_kwargs'], {'enable_thinking': False})
            self.assertEqual(body['temperature'], 0.3)
            self.assertEqual(body['max_tokens'], 1500)
            self.assertEqual(body['messages'][1]['content'], '脚を細くして')
            self.assertEqual(job.timeout, 600)

    def test_redirect_is_not_followed(self):
        with fake_server(status=302) as (port, received, entered):
            job = core.RequestJob('道具箱', '頼み', port=port).start()
            kind, result = job.results.get(timeout=3)
            job.thread.join(timeout=2)
            self.assertEqual(kind, 'error')
            self.assertIn('転送先', result)
            self.assertEqual(len(received), 1)

    def test_server_absent_message(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        job = core.RequestJob('道具箱', '頼み', port=port).start()
        self.assertEqual(job.results.get(timeout=3), ('error', core.OFFLINE))
        job.thread.join(timeout=2)

    def test_cancel_closes_connection_and_discards_reply(self):
        with fake_server(stall=True) as (port, received, entered):
            job = core.RequestJob('道具箱', '頼み', port=port).start()
            self.assertTrue(entered.wait(2))
            job.cancel()
            job.thread.join(timeout=2)
            self.assertFalse(job.thread.is_alive())
            self.assertTrue(job.results.empty())

    def test_timeout(self):
        with fake_server(stall=True) as (port, received, entered):
            job = core.RequestJob('道具箱', '頼み', port=port, timeout=0.1).start()
            self.assertEqual(job.results.get(timeout=2)[0], 'error')
            job.thread.join(timeout=2)
            self.assertFalse(job.thread.is_alive())

    def test_cancel_while_reading_http10_response_body(self):
        with fake_server(stall_body=True) as (port, received, entered):
            job = core.RequestJob('道具箱', '頼み', port=port).start()
            self.assertTrue(entered.wait(2))
            # getresponse が接続の所有権を手放した HTTP/1.0 の場合も中止する。
            for attempt in range(100):
                with job.lock:
                    reading_body = job.connection is not None and job.connection.sock is None
                if reading_body:
                    break
                job.done.wait(0.01)
            self.assertTrue(reading_body)
            job.cancel()
            job.thread.join(timeout=2)
            self.assertFalse(job.thread.is_alive())
            self.assertTrue(job.results.empty())


class RuntimeTests(unittest.TestCase):
    """bpy の代用品で状態遷移を検証。実際の Blender は使わない。"""

    def setUp(self):
        class History(list):
            def add(self):
                entry = types.SimpleNamespace(request='')
                self.append(entry)
                return entry

            def remove(self, index):
                del self[index]

        class Text:
            def __init__(self):
                self.body = ''

            def clear(self):
                self.body = ''

            def write(self, body):
                self.body += body

            def as_string(self):
                return self.body

        class Texts(dict):
            def new(self, name):
                self[name] = Text()
                return self[name]

        self.state = types.SimpleNamespace(request='椅子の脚を細く', status='', error='',
                                           busy=False, can_execute=False, repair_used=False,
                                           history=History())
        prefs = types.SimpleNamespace(kernel_dir=str(KERNEL_DIR), model='local')
        self.context = types.SimpleNamespace(
            window_manager=types.SimpleNamespace(kernel_ai=self.state, windows=[]),
            preferences=types.SimpleNamespace(addons={'kernel_ai': types.SimpleNamespace(preferences=prefs)}),
            scene=types.SimpleNamespace(as_pointer=lambda: 123, name_full='試験の場面'))
        self.texts = Texts()
        fake_bpy = types.SimpleNamespace(context=self.context, data=types.SimpleNamespace(texts=self.texts),
                                         app=types.SimpleNamespace(timers=mock.Mock()))
        fake_bpy.app.timers.is_registered.return_value = False
        self.patches = [mock.patch.object(addon, 'bpy', fake_bpy),
                        mock.patch.object(addon, '_scene_records', return_value='試験の場面の要約')]
        for patch in self.patches:
            patch.start()
        addon._runtime.clear()
        addon._retired.clear()
        addon._job = None

    def tearDown(self):
        addon._cancel_job()
        for job in addon._retired:
            job.thread.join(timeout=2)
            self.assertFalse(job.thread.is_alive())
        addon._retired.clear()
        addon._runtime.clear()
        for patch in reversed(self.patches):
            patch.stop()

    def generate(self, port, repair=False):
        original = core.RequestJob
        with mock.patch.object(core, 'RequestJob', side_effect=lambda *args: original(*args, port=port)):
            addon._start(self.context, repair=repair)
        self.assertTrue(self.state.busy)
        self.assertFalse(self.state.can_execute)
        addon._job.thread.join(timeout=3)
        self.assertFalse(addon._job.thread.is_alive())
        addon._poll()

    def test_generation_only_displays_script_without_execution(self):
        with fake_server() as (port, received, entered), mock.patch.object(core, 'execute_script') as execute:
            self.generate(port)
        execute.assert_not_called()
        self.assertFalse(self.state.busy)
        self.assertTrue(self.state.can_execute, self.state.error)
        self.assertIn('kit.cube()', self.texts[core.TEXT_NAME].as_string())
        self.assertEqual(self.state.history[0].request, '椅子の脚を細く')

    def test_invalid_script_displayed_but_not_executable(self):
        with fake_server('```python\nimport os\n```') as (port, received, entered):
            self.generate(port)
        self.assertFalse(self.state.can_execute)
        self.assertTrue(self.state.error)
        self.assertIn('import os', self.texts[core.TEXT_NAME].as_string())

    def test_repair_once_and_scene_change_rejected(self):
        with fake_server() as (port, received, entered):
            self.generate(port)
            self.state.error = 'RuntimeError: 試験のエラー'
            self.generate(port, repair=True)
        self.assertTrue(self.state.repair_used)
        self.assertIn('RuntimeError: 試験のエラー', received[1][1]['messages'][1]['content'])
        self.state.error = '再度失敗'
        with self.assertRaises(ValueError):
            addon._start(self.context, repair=True)
        self.state.repair_used = False
        self.context.scene.as_pointer = lambda: 456
        with self.assertRaisesRegex(ValueError, '場面が変わりました'):
            addon._start(self.context, repair=True)

    def test_cancelled_old_reply_cannot_overwrite_new_generation(self):
        with fake_server(stall=True) as (port, received, entered):
            original = core.RequestJob
            with mock.patch.object(core, 'RequestJob', side_effect=lambda *args: original(*args, port=port)):
                addon._start(self.context)
            old = addon._job
            self.assertTrue(entered.wait(2))
            addon._cancel_job()
            old.thread.join(timeout=2)
            self.assertFalse(old.thread.is_alive())
            # 場面読込でタイマーが外れても、次の開始時に完了済み通信を回収する。
            with fake_server('```python\na=2\n```') as (new_port, _, _):
                self.generate(new_port)
        self.assertEqual(self.texts[core.TEXT_NAME].as_string(), 'a=2\n')
        self.assertFalse(addon._retired)


def blender_smoke():
    """この関数は外で明示許可された実機試験の子プロセスだけが呼ぶ。"""
    import addon_utils
    import bpy
    import kernel_ai as addon

    addon_utils.enable('kernel_ai', default_set=True, persistent=False)
    assert hasattr(bpy.types.WindowManager, 'kernel_ai')
    bpy.context.preferences.addons['kernel_ai'].preferences.kernel_dir = str(KERNEL_DIR)
    bpy.context.preferences.edit.use_global_undo = True
    scene = bpy.context.scene
    original_names = {o.name for o in scene.objects}
    obj = bpy.data.objects['Cube']
    original_scale = tuple(obj.scale)
    state = bpy.context.window_manager.kernel_ai
    state.request = '選択した物体を細くしてUVを開いて'
    answer = '```python\nimport bpy\nimport kit\no=bpy.data.objects["Cube"]\no.scale.x=0.5\nkit.smart_project(o)\n```'
    with fake_server(answer) as (port, received, entered):
        original_job = core.RequestJob
        with mock.patch.object(core, 'RequestJob', side_effect=lambda *args: original_job(*args, port=port)):
            assert bpy.ops.kernel_ai.think() == {'FINISHED'}
            assert state.busy
            assert entered.wait(2)
            addon._job.thread.join(timeout=3)
            assert not addon._job.thread.is_alive()
            addon._poll()
        assert not state.busy and state.can_execute, state.status
        assert '頂点数' in received[0][1]['messages'][0]['content']
    assert bpy.ops.kernel_ai.execute() == {'FINISHED'}, state.status
    assert not state.error, state.error
    assert obj.scale.x == 0.5 and len(obj.data.uv_layers) > 0
    assert {o.name for o in scene.objects} == original_names
    # 画面の無い -b では Blender が元に戻すを使えない。元に戻すは画面のある Blender で確かめる（README）。
    assert {o.name for o in scene.objects} == original_names
    assert addon._runtime['scene'] == scene.as_pointer()
    text = bpy.data.texts[core.TEXT_NAME]
    text.clear()
    text.write('import bpy\no=bpy.data.objects["Cube"]\no.scale.x=.75\na=1/0\n')
    state.can_execute = True
    assert bpy.ops.kernel_ai.execute() == {'FINISHED'}
    assert 'ZeroDivisionError' in state.error
    with fake_server(answer) as (port, received, entered):
        with mock.patch.object(core, 'RequestJob', side_effect=lambda *args: original_job(*args, port=port)):
            assert bpy.ops.kernel_ai.repair() == {'FINISHED'}
            addon._job.thread.join(timeout=3)
            addon._poll()
        assert state.repair_used
        assert 'ZeroDivisionError' in received[0][1]['messages'][1]['content']
        state.error = '再度失敗'
        try:
            addon._start(bpy.context, repair=True)
        except ValueError:
            pass
        else:
            raise AssertionError('修正を2回許してしまいました')
    addon_utils.disable('kernel_ai', default_set=True)
    assert not hasattr(bpy.types.WindowManager, 'kernel_ai')
    assert not bpy.app.timers.is_registered(addon._poll)
    assert not any(t.name == 'kernel_ai_http' and t.is_alive() for t in threading.enumerate())
    print('カーネル実機試験: 合格')


@unittest.skipUnless(os.environ.get('SEISEI_BLENDER') == '1',
                     'Blender 実機は Claude が外で SEISEI_BLENDER=1 のときだけ')
class BlenderTests(unittest.TestCase):
    def test_real_blender(self):
        result = subprocess.run([
            '/Applications/Blender.app/Contents/MacOS/Blender',
            '--background', '--factory-startup', '--python-exit-code', '1',
            '--python', str(Path(__file__).resolve()), '--', '--blender-smoke',
        ], capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout[-6000:] + result.stderr[-2000:])
        self.assertIn('カーネル実機試験: 合格', result.stdout)


if __name__ == '__main__':
    if '--blender-smoke' in sys.argv:
        if os.environ.get('SEISEI_BLENDER') != '1':
            raise SystemExit('実機試験には SEISEI_BLENDER=1 が必要です')
        blender_smoke()
    else:
        unittest.main(verbosity=2)
