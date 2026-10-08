"""python3 -m unittest kernel/tests/test_sanjigen.py（実機は短い台本だけ）。"""

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from types import SimpleNamespace

import sanjigen


class ValidationTests(unittest.TestCase):
    def test_forbidden_scripts(self):
        scripts = ['import os', 'open("bad", "w")', '__import__("os")',
                   'import subprocess', 'from pathlib import Path',
                   'import math as os', 'import bpy; bpy.app.__class__',
                   'getattr(1, "__class__")', 'eval("1")', 'exec("1")',
                   'import socket', 'import shutil', 'import sys',
                   'import kit; kit.cube.__globals__', 'from math import *',
                   'from . import kit', 'import bpy; bpy.data.texts.new("x").as_module()',
                   'import bpy; bpy.ops.script.python_file_run(filepath="bad.py")',
                   'import bpy; bpy.app.driver_namespace']
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / 'out'
            with mock.patch.object(sanjigen.subprocess, 'Popen') as launch:
                for script in scripts:
                    with self.subTest(script=script):
                        result = sanjigen.run(script, out)
                        self.assertFalse(result['ok'])
                        self.assertTrue(result['error'])
                        self.assertFalse(out.exists(), '拒否した台本は起動・出力しない')
                launch.assert_not_called()

    def test_allowed_imports(self):
        sanjigen.validate('import bpy, bmesh, mathutils, math, random, kit\n'
                          'from kit import cube\no = cube()\n')

    def test_profile(self):
        profile = sanjigen._profile(Path('/private/tmp/out'), Path('/private/tmp/work'))
        self.assertIn('(deny network*)', profile)
        self.assertIn('(allow default)', profile)
        self.assertNotIn('(deny default)', profile)
        self.assertIn('(deny file-write* (require-not (require-any ', profile)
        self.assertIn('(subpath "/private/tmp/out")', profile)
        self.assertIn('(subpath "/private/tmp/work")', profile)
        self.assertIn('(subpath "/private/var/folders")', profile)
        self.assertIn('(subpath "/dev")', profile)
        self.assertNotIn('(subpath "/private/tmp")', profile)
        self.assertEqual(profile.count('('), profile.count(')'))

    def test_bad_timeout_does_not_launch(self):
        with mock.patch.object(sanjigen.subprocess, 'Popen') as launch:
            for timeout in (0, -1, float('inf'), float('nan'), '300'):
                with self.subTest(timeout=timeout):
                    result = sanjigen.run('import kit', Path('/unused'), timeout=timeout)
                    self.assertFalse(result['ok'])
                    self.assertIn('timeout', result['error'])
            launch.assert_not_called()


class HelpersTests(unittest.TestCase):
    """Blender を読み込まずに、出力の境界と UV の連続性を調べる。"""

    def test_output_paths(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            out = root / 'out'
            out.mkdir()
            (out / 'link').symlink_to(root, target_is_directory=True)
            with mock.patch.object(sanjigen, '_OUT', out, create=True):
                self.assertEqual(sanjigen._output('mesh/model.glb'), out / 'mesh/model.glb')
                for name in ('../escape.glb', str(root / 'escape.glb'), 'link/escape.glb'):
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        sanjigen._output(name)
            self.assertFalse((root / 'escape.glb').exists())

    def test_uv_islands(self):
        # 2枚の四角形は頂点1・2の辺を共有する。UV の片端が切れると2島。
        mesh = SimpleNamespace(
            polygons=[SimpleNamespace(index=0, loop_indices=range(4)),
                      SimpleNamespace(index=1, loop_indices=range(4, 8))],
            loops=[SimpleNamespace(vertex_index=v) for v in (0, 1, 2, 3, 1, 4, 5, 2)],
            uv_layers=SimpleNamespace(active=SimpleNamespace(data=[
                SimpleNamespace(uv=p) for p in
                ((0, 0), (1, 0), (1, 1), (0, 1), (1, 0), (2, 0), (2, 1), (1, 1))])))
        obj = SimpleNamespace(data=mesh)
        self.assertEqual(sanjigen.uv_islands(obj), 1)
        mesh.uv_layers.active.data[4].uv = (1.5, 0)
        self.assertEqual(sanjigen.uv_islands(obj), 2)
        mesh.uv_layers.active = None
        self.assertEqual(sanjigen.uv_islands(obj), 0)


@unittest.skipUnless(sanjigen.BLENDER.is_file(), 'Blender がありません')
class BlenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
            raise unittest.SkipTest('macOS の sandbox-exec が必要です')
        probe = subprocess.run(['/usr/bin/sandbox-exec', '-p',
                                '(version 1)(allow default)(deny network*)', '/usr/bin/true'],
                               capture_output=True, text=True, timeout=5)
        if probe.returncode:
            raise unittest.SkipTest('実機試験は未検証: sandbox-exec 起動不可: ' + probe.stderr.strip())

    def setUp(self):
        # /private/var/folders は描画用に許可されるので、外部書込試験は
        # リポジトリ内に置く。親はホストだけが作り、Blender は out だけ。
        self.temp = tempfile.TemporaryDirectory(prefix='sanjigen-test-',
                                                dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.out = self.root / 'out'

    def test_cube_glb_preview_under_30_seconds(self):
        started = time.monotonic()
        result = sanjigen.run('''import kit
o = kit.cube()
kit.bevel(o, width=.1, segments=2)
kit.smart_project(o)
kit.material(o, name="Blue", color=(.1,.3,.8,1), metallic=.2, roughness=.4)
kit.export("cube.glb")
kit.preview()
''', self.out, timeout=29)
        self.assertTrue(result['ok'], json.dumps(result, ensure_ascii=False))
        self.assertLess(time.monotonic() - started, 30)
        glb, png = self.out / 'cube.glb', self.out / 'preview.png'
        self.assertEqual(glb.read_bytes()[:4], b'glTF')
        image = png.read_bytes()
        self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', image[16:24]), (512, 512))
        self.assertEqual(set(result['files']), {str(glb), str(png)})
        self.assertEqual(result['preview'], str(png))
        mesh = result['stats'][0]
        self.assertGreater(mesh['vertices'], 8)
        self.assertGreater(mesh['triangles'], 12)
        self.assertTrue(mesh['uv'])
        self.assertGreater(mesh['uv_islands'], 0)
        self.assertEqual(mesh['materials'], ['Blue'])
        self.assertLessEqual(len(result['log'].splitlines()), 40)

    def test_kit_rejects_escape(self):
        result = sanjigen.run('import kit\nkit.cube()\nkit.export("../escape.glb")', self.out, timeout=20)
        self.assertFalse(result['ok'])
        self.assertIn('出力先の外', result['error'])
        self.assertFalse((self.root / 'escape.glb').exists())

    def test_sandbox_blocks_direct_bpy_escape(self):
        outside = self.root / 'escape.blend'
        script = 'import bpy\nbpy.ops.wm.save_as_mainfile(filepath=' + repr(str(outside)) + ')'
        result = sanjigen.run(script, self.out, timeout=20)
        self.assertFalse(result['ok'], result)
        self.assertFalse(outside.exists(), result)

    def test_sandbox_blocks_symlink_escape(self):
        self.out.mkdir()
        outside = self.root / 'elsewhere'
        outside.mkdir()
        (self.out / 'link').symlink_to(outside, target_is_directory=True)
        dest = self.out / 'link' / 'escape.blend'
        script = 'import bpy\nbpy.ops.wm.save_as_mainfile(filepath=' + repr(str(dest)) + ')'
        result = sanjigen.run(script, self.out, timeout=20)
        self.assertFalse(result['ok'], result)
        self.assertFalse((outside / 'escape.blend').exists(), result)


if __name__ == '__main__':
    unittest.main()
