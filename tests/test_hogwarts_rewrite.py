"""Verify rewrite publication only happens after all checks pass."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hogwarts_rewrite', ROOT / 'games/hogwarts/scripts/rewrite.py')
rewrite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rewrite)


class RewriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.expected = self.root / 'expected.json'
        self.expected.write_text(json.dumps({'rewritten_sha256': {
            'main.patched.bin': hashlib.sha256(b'patched').hexdigest(),
        }}))

    def run_rewrite(self, fail_check=False, bad_hash=False):
        def run(command, **kwargs):
            tool = Path(command[1]).name
            if tool == 'patch_nso.py':
                (Path(command[3]) / 'main.patched.bin').write_bytes(b'wrong' if bad_hash else b'patched')
            elif fail_check:
                raise subprocess.CalledProcessError(1, command)

        with patch.object(rewrite, 'MODULES', ('main',)), \
             patch.object(rewrite.prepare, 'verify_exefs'), \
             patch.object(rewrite.prepare, 'EXPECTED', self.expected), \
             patch.object(rewrite.importlib.util, 'find_spec', return_value=object()), \
             patch.object(rewrite.subprocess, 'run', side_effect=run):
            rewrite.rewrite(self.root / 'work', 1)

    def test_publishes_only_after_checks(self):
        self.run_rewrite()
        dest = self.root / 'work/rewritten/verified'
        self.assertEqual((dest / 'main.patched.bin').read_bytes(), b'patched')
        self.assertEqual([p.name for p in dest.parent.iterdir()], ['verified'])

    def test_hash_failure_cleans_staging(self):
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.run_rewrite(bad_hash=True)
        self.assertEqual(list((self.root / 'work/rewritten').iterdir()), [])

    def test_check_failure_cleans_staging(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_rewrite(fail_check=True)
        self.assertEqual(list((self.root / 'work/rewritten').iterdir()), [])

    def test_existing_result_is_not_overwritten(self):
        dest = self.root / 'work/rewritten/verified'
        dest.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'Output already exists'):
            self.run_rewrite()

    def test_invalid_jobs_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Jobs must be positive'):
            rewrite.rewrite(self.root / 'work', 0)


if __name__ == '__main__':
    unittest.main()
