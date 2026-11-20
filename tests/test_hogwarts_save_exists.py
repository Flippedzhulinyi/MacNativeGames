import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc') and os.uname().sysname == 'Darwin', 'macOS C compiler required')
class SaveExistsTests(unittest.TestCase):
    def test_local_user_and_application(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=gnu11', '-DHOGWARTS_EXPERIMENTAL', '-ffunction-sections',
                            '-I', str(ROOT / 'games/ot0/runtime'),
                            str(ROOT / 'tests/hogwarts_save_exists_probe.c'),
                            '-Wl,-dead_strip', '-o', str(exe)], check=True)
            env = dict(os.environ, TOTK_PROFILE_DIR=str(Path(temp) / 'profile'))
            subprocess.run([str(exe)], env=env, capture_output=True, check=True)


if __name__ == '__main__':
    unittest.main()
