"""標準ライブラリだけの契約試験。模型・pip・Blender・ネットを使わない。
実機は SEISEI_TRIPOSR=1 と SEISEI_TRIPOSR_IMAGE の両方を明示したときだけ。
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('sanjigen_gazou', Path(__file__).resolve().parents[1] / 'sanjigen_gazou.py')
sg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sg)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.image = self.root / 'input.png'
        self.image.write_bytes(b'input fixture')
        self.out = self.root / 'out'

    def ready(self):
        mirror = self.root / 'mirror'
        values = dict(MIRROR=mirror, PYTHON=mirror/'seisei_venv/bin/python', REPO=mirror/'TripoSR',
                      MODELS=mirror/'models/triposr', KERNEL=mirror/'kernel', SANDBOX=self.root/'sandbox-exec')
        for path in (values['PYTHON'], values['SANDBOX'], values['REPO']/'tsr/system.py',
                     values['MODELS']/'settei.json', values['MODELS']/'model.ckpt',
                     values['MODELS']/'config-local.yaml', values['KERNEL']/'seisei_hoka.py',
                     values['KERNEL']/'bin/haikei'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
            path.chmod(0o700)
        return patch.multiple(sg, **values)

    def test_nonempty_output_never_overwritten(self):
        self.out.mkdir()
        existing = self.out/'keep.txt'
        existing.write_text('keep')
        with patch.object(sg.subprocess, 'Popen') as popen:
            result = sg.run(self.image, self.out)
        self.assertFalse(result['ok'])
        self.assertIn('上書き禁止', result['結果'])
        self.assertEqual(existing.read_text(), 'keep')
        popen.assert_not_called()

    def test_invalid_options_do_not_spawn(self):
        for options in ({'mc_resolution': True}, {'chunk_size': 0}, {'texture': 'yes'}):
            with patch.object(sg.subprocess, 'Popen') as popen:
                self.assertFalse(sg.run(self.image, self.out, **options)['ok'])
                popen.assert_not_called()

    def test_missing_setup_does_not_create_output(self):
        with patch.object(sg, 'PYTHON', self.root/'absent'), patch.object(sg.subprocess, 'Popen') as popen:
            self.assertFalse(sg.run(self.image, self.out)['ok'])
            self.assertFalse(self.out.exists())
            popen.assert_not_called()

    def test_profile_scope_and_clean_environment(self):
        work = self.root/'一時'
        profile = sg._profile(self.out, work)
        self.assertIn('(deny network*)', profile)
        self.assertIn('(deny file-write*', profile)
        self.assertIn(str(work), profile)
        self.assertNotIn('(subpath "/private/var/folders")', profile)
        self.assertNotIn('(subpath "/dev")', profile)
        with patch.dict(os.environ, {'SECRET_TEST_TOKEN': 'do-not-inherit'}):
            env = sg._environment(work)
        self.assertNotIn('SECRET_TEST_TOKEN', env)
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')

    def fake_process(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        profile = Path(command[2]).read_text()
        self.assertIn('(deny network*)', profile)
        payload = json.loads(Path(command[-1]).read_text())
        out = Path(payload['out'])
        (out/'model.glb').write_bytes(b'glTF\x02\x00\x00\x00\x0c\x00\x00\x00')
        (out/'preview.png').write_bytes(b'\x89PNG\r\n\x1a\n')
        (out/'jissoku.json').write_text(json.dumps(dict(ok=True, peak_rss_mib=2048, appearance='頂点色')))
        class Process:
            pid = 12345
            def wait(self, timeout=None):
                return 0
            def poll(self):
                return 0
        return Process()

    def test_subprocess_contract_and_result(self):
        with self.ready(), patch.object(sg.sys, 'platform', 'darwin'), patch.object(sg.subprocess, 'Popen', self.fake_process):
            result = sg.run(self.image, self.out, 128, 2048, False)
        self.assertTrue(result['ok'], result)
        self.assertEqual(set(result), {'ok', '結果', '画像', '場所'})
        self.assertEqual(result['画像'], [str(self.out/'preview.png')])
        self.assertIn('2048 MiB', result['結果'])
        self.assertIn('-I', self.command)
        self.assertTrue(self.kwargs['start_new_session'])
        self.assertEqual(self.kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(self.kwargs['env']['TRANSFORMERS_OFFLINE'], '1')

    def test_timeout_kills_entire_process_group(self):
        class Process:
            pid = 12345
            stopped = False
            def wait(self, timeout=None):
                if timeout is not None:
                    raise subprocess.TimeoutExpired('fixture', timeout)
                self.stopped = True
                return -9
            def poll(self):
                return -9 if self.stopped else None
        process = Process()
        with self.ready(), patch.object(sg.sys, 'platform', 'darwin'), \
             patch.object(sg.subprocess, 'Popen', return_value=process), patch.object(sg.os, 'killpg') as kill:
            result = sg.run(self.image, self.out)
        self.assertFalse(result['ok'])
        self.assertIn('時間切れ', result['結果'])
        kill.assert_called_once_with(process.pid, sg.signal.SIGKILL)

    def test_cpu_patch_idempotence_and_tamper_refusal(self):
        source = self.root/'tsr/models/isosurface.py'
        source.parent.mkdir(parents=True)
        source.write_text('import torch\n' + sg.MC_IMPORT + '\n')
        sg._patch_isosurface(self.root)
        body = source.read_text()
        self.assertNotIn(sg.MC_IMPORT, body)
        self.assertIn('skimage.measure', body)
        sg._patch_isosurface(self.root)
        self.assertEqual(source.read_text(), body)
        source.write_text(body + '# edited\n')
        with self.assertRaisesRegex(RuntimeError, '上書きせず停止'):
            sg._patch_isosurface(self.root)


@unittest.skipUnless(os.environ.get('SEISEI_TRIPOSR') == '1', '実機は明示時だけ')
class MachineTests(unittest.TestCase):
    def test_real_cpu_glb(self):
        image = os.environ.get('SEISEI_TRIPOSR_IMAGE')
        self.assertTrue(image, 'SEISEI_TRIPOSR_IMAGE に実画像を指定してください')
        with tempfile.TemporaryDirectory(prefix='triposr-test-') as raw:
            out = Path(raw)/'out'
            result = sg.run(image, out, mc_resolution=128, chunk_size=2048, texture=False)
            self.assertTrue(result['ok'], result)
            report = json.loads((out/'jissoku.json').read_text())
            self.assertGreater(report['peak_rss_mib'], 0)
            self.assertGreater(report['faces'], 0)
            self.assertGreater((out/'model.glb').stat().st_size, 100)


if __name__ == '__main__':
    unittest.main()
