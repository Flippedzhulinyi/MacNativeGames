"""Verify merge staging and failure handling without game data."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hogwarts_merge', ROOT / 'games/hogwarts/scripts/merge_romfs.py')
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


class FakePatched:
    total = 4
    from_base = 2
    from_update = 2

    def __init__(self, *args):
        pass

    def read(self, offset, size):
        return b'data'[offset:offset + size]


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / 'base'
        self.update = self.root / 'update'
        self.keys = self.root / 'keys'
        self.base.write_bytes(b'base')
        self.update.write_bytes(b'update')
        self.keys.write_bytes(b'keys')

    def run_merge(self, error=None):
        def open_program(path, keys, title, update):
            return path.open('rb'), {'title': title}, None, None

        def verify(fs, size, read, image):
            image.write_bytes(read(0, size))
            if error:
                raise ValueError(error)
            return [1] * 6, size, 'test-digest'

        with patch.object(merge.prepare, 'prepare'), \
             patch.object(merge.prepare.ex, 'load_keys', return_value={}), \
             patch.object(merge.merger, 'open_program', side_effect=open_program), \
             patch.object(merge.merger, 'romfs_section', return_value=(0, 4, None)), \
             patch.object(merge.merger, 'base_section', return_value=None), \
             patch.object(merge.merger, 'Patched', FakePatched), \
             patch.object(merge.merger, 'verify_ivfc', side_effect=verify), \
             patch.object(merge.merger, 'index_romfs', return_value=[]):
            merge.merge(self.base, self.update, self.keys, self.root / 'work')

    def test_publishes_verified_image(self):
        self.run_merge()
        dest = self.root / 'work/extracted/merged-romfs'
        self.assertEqual((dest / 'romfs.bin').read_bytes(), b'data')
        self.assertTrue((dest / 'index.json').is_file())
        self.assertEqual([p.name for p in dest.parent.iterdir()], ['merged-romfs'])

    def test_failure_removes_staging_and_does_not_publish(self):
        with self.assertRaisesRegex(ValueError, 'bad IVFC'):
            self.run_merge('bad IVFC')
        self.assertEqual(list((self.root / 'work/extracted').iterdir()), [])

    def test_existing_result_is_not_overwritten(self):
        dest = self.root / 'work/extracted/merged-romfs'
        dest.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'Output already exists'):
            self.run_merge()


if __name__ == '__main__':
    unittest.main()
