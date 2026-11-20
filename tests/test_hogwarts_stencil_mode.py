import shutil
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NVN = ROOT / 'games/ot0/third_party/d2r_gfx/gfx/nvn'


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class StencilModeTests(unittest.TestCase):
    def test_texture_defaults_and_view_overrides(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(NVN), '-I', str(NVN / 'include'),
                            str(ROOT / 'tests/hogwarts_stencil_mode_probe.c'), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS Metal required')
    def test_metal_stencil_plane_samples_written_values(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'metal-probe'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'tests/hogwarts_stencil_metal_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
