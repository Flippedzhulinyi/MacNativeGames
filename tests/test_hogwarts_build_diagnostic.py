"""Tests for the private diagnostic build orchestration."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'hogwarts_build_diagnostic', ROOT / 'games/hogwarts/scripts/build_diagnostic.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class DiagnosticBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base, self.update, self.keys = (self.root / name for name in ('base.nsp', 'update.nsp', 'keys'))
        for path in (self.base, self.update, self.keys):
            path.write_bytes(b'fixture')
        self.work = self.root / 'work'

    def test_existing_stages_are_checked_before_build(self):
        for path in ('extracted/update', 'extracted/merged-romfs', 'rewritten/verified',
                     'runtime/verified-tables'):
            (self.work / path).mkdir(parents=True)
        calls = []
        with patch.object(build.prepare.ex, 'load_keys', return_value={}), \
             patch.object(build.prepare, 'inspect', side_effect=lambda *a: calls.append('inspect')), \
             patch.object(build.prepare, 'verify_exefs', side_effect=lambda *a: calls.append('exefs')), \
             patch.object(build, 'check_romfs', side_effect=lambda *a: calls.append('romfs')), \
             patch.object(build, 'check_rewrites', side_effect=lambda *a: calls.append('rewrite')), \
             patch.object(build, 'check_tables', side_effect=lambda *a: calls.append('tables')), \
             patch.object(build.subprocess, 'run', side_effect=lambda *a, **k: calls.append('make')):
            build.build(self.base, self.update, self.keys, self.work, 2)
        self.assertEqual(calls, ['inspect', 'inspect', 'exefs', 'romfs', 'rewrite', 'tables', 'make'])

    def test_bad_existing_tables_stop_before_make(self):
        for path in ('extracted/update', 'extracted/merged-romfs', 'rewritten/verified',
                     'runtime/verified-tables'):
            (self.work / path).mkdir(parents=True)
        with patch.object(build.prepare.ex, 'load_keys', return_value={}), \
             patch.object(build.prepare, 'inspect'), patch.object(build.prepare, 'verify_exefs'), \
             patch.object(build, 'check_romfs'), patch.object(build, 'check_rewrites'), \
             patch.object(build, 'check_tables', side_effect=ValueError('bad tables')), \
             patch.object(build.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'bad tables'):
                build.build(self.base, self.update, self.keys, self.work, 2)
            run.assert_not_called()

    def test_fresh_stages_run_in_order(self):
        calls = []
        with patch.object(build.prepare.ex, 'load_keys', return_value={}), \
             patch.object(build.prepare, 'inspect'), \
             patch.object(build.prepare, 'prepare', side_effect=lambda *a: calls.append('prepare')), \
             patch.object(build.merge, 'merge', side_effect=lambda *a: calls.append('merge')), \
             patch.object(build, 'check_romfs', side_effect=lambda *a: calls.append('romfs')), \
             patch.object(build.rewrite, 'rewrite', side_effect=lambda *a: calls.append('rewrite')), \
             patch.object(build.tables, 'generate', side_effect=lambda *a: calls.append('tables')), \
             patch.object(build.subprocess, 'run', side_effect=lambda *a, **k: calls.append('make')):
            build.build(self.base, self.update, self.keys, self.work, 2)
        self.assertEqual(calls, ['prepare', 'merge', 'romfs', 'rewrite', 'tables', 'make'])

    def test_invalid_work_and_jobs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            build.build(self.base, self.update, self.keys, ROOT / 'work', 2)
        with self.assertRaisesRegex(ValueError, 'Jobs must be positive'):
            build.build(self.base, self.update, self.keys, self.work, 0)
        with self.assertRaisesRegex(ValueError, 'unsupported by make'):
            build.build(self.base, self.update, self.keys, self.root / 'bad work', 2)

    def test_existing_tables_reject_modified_files_and_links(self):
        source = self.work / 'extracted/update/exefs'
        source.mkdir(parents=True)
        romfs = self.work / 'extracted/merged-romfs'
        romfs.mkdir(parents=True)
        (romfs / 'romfs.bin').write_bytes(b'image')
        rewritten = self.work / 'rewritten/verified'
        rewritten.mkdir(parents=True)

        def make_tables(work):
            output = work / 'runtime/verified-tables'
            headers = output / 'build/hogwarts'
            headers.mkdir(parents=True)
            for name in ('runtime_tables.h', 'romfs_config.h', 'shared_fonts_config.h'):
                (headers / name).write_bytes(b'header')
            extracted = output / 'extracted/hogwarts'
            (extracted / 'romfs').mkdir(parents=True)
            (extracted / 'romfs/index.json').write_bytes(b'index')
            (extracted / 'romfs/runtime-index.bin').write_bytes(b'runtime-index')
            (extracted / 'exefs').symlink_to(source, target_is_directory=True)
            (extracted / 'romfs/romfs.bin').symlink_to(romfs / 'romfs.bin')
            (output / 'rewritten').mkdir()
            (output / 'rewritten/hogwarts').symlink_to(rewritten, target_is_directory=True)

        make_tables(self.work)
        with patch.object(build.tables, 'generate', side_effect=make_tables):
            build.check_tables(self.work)
            header = self.work / 'runtime/verified-tables/build/hogwarts/runtime_tables.h'
            header.write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError, 'loader tables mismatch'):
                build.check_tables(self.work)
            header.write_bytes(b'header')
            link = self.work / 'runtime/verified-tables/rewritten/hogwarts'
            link.unlink()
            link.symlink_to(source, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'loader input link mismatch'):
                build.check_tables(self.work)


if __name__ == '__main__':
    unittest.main()
