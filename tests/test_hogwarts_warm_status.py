import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
class WarmStatusTests(unittest.TestCase):
    def test_completed_warmup_and_first_frame_status(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'warm-status'
            subprocess.run([
                'xcrun', 'clang', '-std=gnu11', '-fobjc-arc', '-Wno-deprecated-declarations',
                '-I', str(ROOT / 'games/ot0/third_party/d2r_gfx/gfx/nvn/include'),
                str(ROOT / 'tests/hogwarts_warm_status_probe.m'),
                '-framework', 'Cocoa', '-framework', 'Metal', '-framework', 'QuartzCore',
                '-framework', 'CoreVideo', '-Wl,-undefined,dynamic_lookup', '-o', str(exe)
            ], check=True)
            subprocess.run([str(exe)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
