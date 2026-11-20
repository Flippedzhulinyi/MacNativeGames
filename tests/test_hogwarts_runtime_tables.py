"""Tests for private, hash-checked loader table staging."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hogwarts_runtime_tables', ROOT / 'games/hogwarts/scripts/prepare_runtime.py')
tables = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tables)


class TableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name) / 'work'
        (self.work / 'rewritten/verified').mkdir(parents=True)
        romfs = self.work / 'extracted/merged-romfs'
        romfs.mkdir(parents=True)
        (romfs / 'romfs.bin').write_bytes(b'data')
        self.expected = Path(self.tmp.name) / 'expected.json'
        self.expected.write_text(json.dumps({
            'files': {'main': {'sha256': 'x'}},
            'rewritten_sha256': {'main.patched.bin': 'y'},
            'romfs': {'size': 4, 'sha256': hashlib.sha256(b'data').hexdigest()},
        }))

    def run_generate(self, failure=False):
        def runtime_tables(work, version, out, pinned):
            if failure:
                raise ValueError('bad loader')
            (out / 'runtime_tables.h').write_text('fixture')
            return {'modules': 3}

        with patch.object(tables.prepare, 'EXPECTED', self.expected), \
             patch.object(tables.prepare, 'verify_exefs'), \
             patch.object(tables.merge.merger, 'index_romfs', return_value=[]), \
             patch.object(tables.runtime, 'runtime_tables', side_effect=runtime_tables), \
             patch.object(tables.runtime, 'romfs_config'), \
             patch.object(tables.runtime, 'shared_fonts_config'):
            tables.generate(self.work)

    def test_publishes_generated_tables(self):
        self.run_generate()
        output = self.work / 'runtime/verified-tables'
        self.assertEqual((output / 'build/hogwarts/runtime_tables.h').read_text(), 'fixture')
        self.assertTrue((output / 'extracted/hogwarts/romfs/romfs.bin').is_file())
        self.assertEqual([p.name for p in output.parent.iterdir()], ['verified-tables'])

    def test_failed_generation_does_not_publish(self):
        with self.assertRaisesRegex(ValueError, 'bad loader'):
            self.run_generate(failure=True)
        self.assertEqual(list((self.work / 'runtime').iterdir()), [])

    def test_bad_romfs_is_rejected(self):
        (self.work / 'extracted/merged-romfs/romfs.bin').write_bytes(b'bad!')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.run_generate()
        self.assertFalse((self.work / 'runtime').exists())

    def test_existing_result_is_not_overwritten(self):
        (self.work / 'runtime/verified-tables').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'Output already exists'):
            self.run_generate()


if __name__ == '__main__':
    unittest.main()
