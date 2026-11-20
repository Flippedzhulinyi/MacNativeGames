import os
import json
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
class GeometryStripTests(unittest.TestCase):
    def test_local_capture_layout(self):
        capture = os.environ.get('HOGWARTS_LOCAL_GEOMETRY_CAPTURE')
        translation = os.environ.get('HOGWARTS_LOCAL_GEOMETRY_TRANSLATION')
        if not capture and not translation:
            self.skipTest('set HOGWARTS_LOCAL_GEOMETRY_CAPTURE and HOGWARTS_LOCAL_GEOMETRY_TRANSLATION')
        if not capture or not translation:
            self.fail('both local geometry paths are required')
        with open(capture, 'rb') as f:
            data = plistlib.load(f)
        self.assertEqual((data['primitive'], data['indexed']), (5, False))
        vertices, instances = data['count'], data['instances']
        self.assertGreaterEqual(vertices, 3)
        stages = [stage for stage in data['stages'] if stage['stage'] == 2]
        self.assertEqual(len(stages), 1)
        code = stages[0]['code']
        self.assertGreaterEqual(len(code), 0x44)
        invocations = (struct.unpack_from('<I', code, 0x38)[0] >> 24) or 1
        max_output = struct.unpack_from('<I', code, 0x40)[0] & 0xfff
        with open(Path(translation) / 'geometry_vsc_b.json') as f:
            vs = json.load(f)
        with open(Path(translation) / 'geometry_gsc_b.json') as f:
            gs = json.load(f)
        self.assertEqual(vs['out_words'], gs['in_words'])
        args = [vertices, vertices - 2, instances, invocations, max_output,
                vs['out_words'], gs['out_words']]
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/hogwarts/runtime'),
                            str(ROOT / 'tests/hogwarts_geometry_layout_probe.c'), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe), *map(str, args)], check=True, capture_output=True, text=True)
            n = vertices * instances
            self.assertEqual(list(map(int, result.stdout.split())),
                             [n * vs['out_words'] * 4, n * max_output * gs['out_words'] * 4,
                              n * (max_output + 1) * 4])
            args[3] = 2
            result = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unsafe or unsupported geometry layout', result.stderr)

    def test_synthetic_vertex_geometry_pipeline(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-std=gnu11', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/hogwarts/runtime'),
                            str(ROOT / 'tests/hogwarts_geometry_pipeline_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1')
            env.pop('HOGWARTS_PIPELINE_PROBE_BAD_EXPECTED', None)
            subprocess.run([str(exe)], env=env, check=True, timeout=30)
            env['HOGWARTS_PIPELINE_PROBE_BAD_EXPECTED'] = '1'
            result = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('geometry readback mismatch instance=31 primitive=2 vertex=2 word=12', result.stderr)

    def test_strip_remap_and_metal_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-std=gnu11', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/hogwarts/runtime'),
                            str(ROOT / 'tests/hogwarts_geometry_strip_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1')
            env.pop('HOGWARTS_STRIP_PROBE_BAD_EXPECTED', None)
            subprocess.run([str(exe)], env=env, check=True, timeout=30)
            env['HOGWARTS_STRIP_PROBE_BAD_EXPECTED'] = '1'
            result = subprocess.run([str(exe)], env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('strip readback mismatch instance=31 element=8', result.stderr)


if __name__ == '__main__':
    unittest.main()
