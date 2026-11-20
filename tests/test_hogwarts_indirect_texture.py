import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NVN = ROOT / 'games/ot0/third_party/d2r_gfx/gfx/nvn'


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class IndirectTextureTests(unittest.TestCase):
    def test_decoding_and_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(NVN), str(ROOT / 'tests/hogwarts_indirect_texture_probe.c'),
                            '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
    def test_reflection_parses_array_and_rejects_invalid_layouts(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            for define in ([], ['-DHOGWARTS_EXPERIMENTAL']):
                subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                                *define, '-I', str(NVN), str(NVN / 'nvn_refl.m'),
                                str(ROOT / 'tests/hogwarts_indirect_reflection_probe.m'),
                                '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
                subprocess.run([str(exe)], check=True)
                local_2d = os.environ.get('HOGWARTS_LOCAL_2D_REFLECTION')
                if define and local_2d:
                    env = dict(os.environ, HOGWARTS_EXPECT_UNSUPPORTED_2D='1')
                    subprocess.run([str(exe), local_2d], env=env, check=True)
                local_cube = os.environ.get('HOGWARTS_LOCAL_CUBE_REFLECTION')
                if define and local_cube:
                    env = dict(os.environ, HOGWARTS_EXPECT_DIAGNOSTIC_CUBE='1')
                    env.pop('HOGWARTS_EXPECT_UNSUPPORTED_2D', None)
                    subprocess.run([str(exe), local_cube], env=env, check=True)
                local_array_2d = os.environ.get('HOGWARTS_LOCAL_2D_ARRAY_REFLECTION')
                if define and local_array_2d:
                    env = dict(os.environ, HOGWARTS_EXPECT_DIAGNOSTIC_2D_ARRAY='1')
                    subprocess.run([str(exe), local_array_2d], env=env, check=True)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
    def test_dynamic_metal_texture_array(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            '-I', str(NVN),
                            str(ROOT / 'tests/hogwarts_indirect_metal_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
            env = os.environ.copy()
            env['HOGWARTS_PROBE_SWAP_TYPED_BUFFERS'] = '1'
            negative = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn('pass 0: got', negative.stderr)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
    def test_multiple_scalar_metal_bindings(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            '-I', str(NVN), str(ROOT / 'tests/hogwarts_indirect_scalar_metal_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1')
            env.pop('HOGWARTS_SCALAR_PROBE_BAD_EXPECTED', None)
            subprocess.run([str(exe)], env=env, check=True)
            env['HOGWARTS_SCALAR_PROBE_BAD_EXPECTED'] = '1'
            negative = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn('scalar GPU result mismatch', negative.stderr)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
    def test_dynamic_metal_cube_array(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            '-I', str(NVN), str(ROOT / 'tests/hogwarts_indirect_cube_metal_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1')
            env.pop('HOGWARTS_CUBE_PROBE_BAD_EXPECTED', None)
            env.pop('HOGWARTS_2D_ARRAY_PROBE_BAD_EXPECTED', None)
            env.pop('HOGWARTS_PROBE_2D_ARRAY', None)
            subprocess.run([str(exe)], env=env, check=True)
            env['HOGWARTS_CUBE_PROBE_BAD_EXPECTED'] = '1'
            negative = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn('array GPU result mismatch', negative.stderr)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
    def test_dynamic_metal_2d_array(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            '-I', str(NVN), str(ROOT / 'tests/hogwarts_indirect_cube_metal_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1', HOGWARTS_PROBE_2D_ARRAY='1')
            env.pop('HOGWARTS_CUBE_PROBE_BAD_EXPECTED', None)
            env.pop('HOGWARTS_2D_ARRAY_PROBE_BAD_EXPECTED', None)
            subprocess.run([str(exe)], env=env, check=True)
            env['HOGWARTS_2D_ARRAY_PROBE_BAD_EXPECTED'] = '1'
            negative = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn('array GPU result mismatch', negative.stderr)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
    def test_pinned_local_fragment_with_synthetic_resources(self):
        shader = os.environ.get('HOGWARTS_LOCAL_SHADER')
        reflection = os.environ.get('HOGWARTS_LOCAL_REFLECTION')
        if not shader and not reflection:
            self.skipTest('set HOGWARTS_LOCAL_SHADER and HOGWARTS_LOCAL_REFLECTION to test the private shader')
        if not shader or not reflection:
            self.fail('both HOGWARTS_LOCAL_SHADER and HOGWARTS_LOCAL_REFLECTION are required')
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            '-I', str(NVN), str(ROOT / 'tests/hogwarts_indirect_metal_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1',
                       HOGWARTS_PROBE_RUN_LOCAL_FRAGMENT='1')
            command = [str(exe), shader, reflection]
            subprocess.run(command, env=env, check=True)
            env['HOGWARTS_PROBE_BAD_FRAGMENT_EXPECTED'] = '1'
            negative = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn('local fragment pixel:', negative.stderr)
            env.pop('HOGWARTS_PROBE_BAD_FRAGMENT_EXPECTED')
            env['HOGWARTS_PROBE_BAD_FRAGMENT_TEXTURE'] = '1'
            negative = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn('expected 8.000 0 0 1', negative.stderr)
            env.pop('HOGWARTS_PROBE_BAD_FRAGMENT_TEXTURE')
            altered = Path(temp) / 'unrecognized.metal'
            altered.write_bytes(Path(shader).read_bytes() + b'\n')
            negative = subprocess.run([str(exe), str(altered), reflection], env=env, capture_output=True, text=True)
            self.assertNotEqual(negative.returncode, 0)
            self.assertIn('requires the pinned observed shader', negative.stderr)


if __name__ == '__main__':
    unittest.main()
