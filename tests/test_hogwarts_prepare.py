"""Tests for Hogwarts Legacy preparation without game files or real keys."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hogwarts_prepare', ROOT / 'games/hogwarts/scripts/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / 'base.nsp'
        self.update = self.root / 'update.nsp'
        self.keys = self.root / 'prod.keys'
        for path in (self.base, self.update, self.keys):
            path.write_bytes(b'fixture')
        self.expected = self.root / 'expected.json'
        payload = b'synthetic program'
        self.expected.write_text(json.dumps({'files': {'main': {
            'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
        }}}))
        self.payload = payload

    def fake_extract(self, command, check):
        self.assertTrue(check)
        output = Path(command[command.index('--output') + 1])
        output.mkdir(parents=True)
        (output / 'main').write_bytes(self.payload)
        (output.parent / 'extraction-manifest.json').write_text('{}')

    def test_prepare_publishes_only_verified_files(self):
        with patch.object(prepare.ex, 'load_keys', return_value={}), \
             patch.object(prepare, 'inspect') as inspect, \
             patch.object(prepare, 'EXPECTED', self.expected), \
             patch.object(prepare.subprocess, 'run', side_effect=self.fake_extract):
            prepare.prepare(self.base, self.update, self.keys, self.root / 'work')
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual((self.root / 'work/extracted/update/exefs/main').read_bytes(), self.payload)
        self.assertTrue((self.root / 'work/extracted/update/extraction-manifest.json').is_file())
        self.assertEqual([p.name for p in (self.root / 'work/extracted').iterdir()], ['update'])

    def test_mismatch_does_not_publish_or_leave_staging(self):
        self.expected.write_text(json.dumps({'files': {'main': {
            'size': len(self.payload), 'sha256': '0' * 64,
        }}}))
        with patch.object(prepare.ex, 'load_keys', return_value={}), \
             patch.object(prepare, 'inspect'), \
             patch.object(prepare, 'EXPECTED', self.expected), \
             patch.object(prepare.subprocess, 'run', side_effect=self.fake_extract):
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                prepare.prepare(self.base, self.update, self.keys, self.root / 'work')
        self.assertEqual(list((self.root / 'work/extracted').iterdir()), [])

    def test_existing_output_is_not_overwritten(self):
        destination = self.root / 'work/extracted/update'
        destination.mkdir(parents=True)
        with patch.object(prepare.ex, 'load_keys', return_value={}), \
             patch.object(prepare, 'inspect'), \
             patch.object(prepare.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Output already exists'):
                prepare.prepare(self.base, self.update, self.keys, self.root / 'work')
        run.assert_not_called()

    def test_work_folder_inside_repository_is_rejected(self):
        with patch.object(prepare.ex, 'load_keys') as load:
            with self.assertRaisesRegex(ValueError, 'outside the repository'):
                prepare.prepare(self.base, self.update, self.keys, ROOT / 'games/hogwarts/work')
        load.assert_not_called()

    def test_extractor_failure_does_not_publish_or_leave_staging(self):
        with patch.object(prepare.ex, 'load_keys', return_value={}), \
             patch.object(prepare, 'inspect'), \
             patch.object(prepare.subprocess, 'run',
                          side_effect=prepare.subprocess.CalledProcessError(1, 'extract')):
            with self.assertRaises(prepare.subprocess.CalledProcessError):
                prepare.prepare(self.base, self.update, self.keys, self.root / 'work')
        self.assertEqual(list((self.root / 'work/extracted').iterdir()), [])

    def test_inspect_rejects_swapped_and_mixed_titles(self):
        header = bytearray(0xc00)
        header[0x404] = 4
        meta = {'content_type': 1, 'title_id': prepare.UPDATE_TITLE}
        program = {'content_type': 0, 'title_id': prepare.TITLE}
        with patch.object(prepare.ex, 'container_entries', return_value=('nsp', [])), \
             patch.object(prepare.ex, 'nca_inventory', return_value=[(meta, header), (program, header)]), \
             patch.object(prepare.ex, 'common_tickets', return_value={}), \
             patch.object(prepare.ex, 'nca_ctr_key'):
            prepare.inspect(self.update, {}, True)
            with self.assertRaisesRegex(ValueError, 'expected base metadata'):
                prepare.inspect(self.update, {}, False)
            meta['title_id'] = '0100000000000000'
            with self.assertRaisesRegex(ValueError, 'expected update metadata'):
                prepare.inspect(self.update, {}, True)


if __name__ == '__main__':
    unittest.main()
