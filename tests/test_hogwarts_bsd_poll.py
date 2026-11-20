import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class BsdPollTests(unittest.TestCase):
    def test_offline_poll(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/ot0/runtime'),
                            str(ROOT / 'games/hogwarts/runtime/bsd_poll.c'),
                            str(ROOT / 'tests/hogwarts_bsd_poll_probe.c'), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
            self.assertEqual(subprocess.run([str(exe), 'short'], capture_output=True).returncode, 2)
            start = time.monotonic()
            subprocess.run([str(exe), 'wait'], check=True)
            self.assertGreaterEqual(time.monotonic() - start, 0.06)


if __name__ == '__main__':
    unittest.main()
