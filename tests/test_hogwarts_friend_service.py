import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class FriendServiceTests(unittest.TestCase):
    def test_create_and_reject_unimplemented(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/ot0/runtime'),
                            str(ROOT / 'tests/hogwarts_friend_service_probe.c'), '-o', str(exe)], check=True)
            for arg, expected in [([], 0), (['unknown-creator'], 3), (['unknown-service'], 3)]:
                self.assertEqual(subprocess.run([str(exe), *arg]).returncode, expected)


if __name__ == '__main__':
    unittest.main()
