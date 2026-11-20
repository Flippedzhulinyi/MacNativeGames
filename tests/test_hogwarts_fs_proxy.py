"""Verify the FSP control plane does not accept invalid or unknown requests."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class FsProxyTests(unittest.TestCase):
    def test_control_plane(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/ot0/runtime'), str(ROOT / 'tests/hogwarts_fs_proxy_probe.c'),
                            '-o', str(binary)], check=True)
            for args, expected in [([], 0), (['bad-pid'], 2), (['before-init'], 2), (['unknown'], 3)]:
                result = subprocess.run([str(binary), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == '__main__':
    unittest.main()
