import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class NsdTests(unittest.TestCase):
    def test_retail_environment_and_unknown_command(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/ot0/runtime'),
                            str(ROOT / 'tests/hogwarts_nsd_probe.c'), '-o', str(exe)], check=True)
            self.assertEqual(subprocess.run([str(exe)]).returncode, 0)
            self.assertEqual(subprocess.run([str(exe), 'unknown']).returncode, 3)


if __name__ == '__main__':
    unittest.main()
