import importlib.util
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'hogwarts_package_app', ROOT / 'games/hogwarts/scripts/package_diagnostic_app.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
class DiagnosticAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / 'runtime'
        for name in ('build/hogwarts-native-diagnostic', 'build/shader-service/totk_xlate',
                     'build/spirv-cross/spirv-cross'):
            path = self.runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o700)
        (self.runtime / 'rewritten/hogwarts').mkdir(parents=True)
        index = self.runtime / 'extracted/hogwarts/romfs/runtime-index.bin'
        index.parent.mkdir(parents=True)
        index.write_bytes(b'index')
        self.output = self.root / 'Diagnostic.app'

    def test_bundle_and_private_reference(self):
        package.package(self.runtime, self.output)
        contents = self.output / 'Contents'
        info = plistlib.loads((contents / 'Info.plist').read_bytes())
        config = plistlib.loads((contents / 'Resources/DiagnosticConfig.plist').read_bytes())
        self.assertIn('Not Playable', info['CFBundleName'])
        self.assertEqual(info['LSMinimumSystemVersion'], '26.0')
        self.assertEqual(config['RuntimeDirectory'], str(self.runtime.resolve()))
        executable = contents / 'MacOS/HogwartsDiagnostic'
        self.assertTrue(os.access(executable, os.X_OK))
        result = subprocess.run([executable, '--verify'], capture_output=True, text=True, check=True)
        self.assertIn('GPU submission disabled', result.stdout)
        with self.assertRaises(FileExistsError):
            package.package(self.runtime, self.output)

    def test_invalid_inputs_do_not_create_output(self):
        (self.runtime / 'build/shader-service/totk_xlate').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing executable'):
            package.package(self.runtime, self.output)
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            package.package(ROOT, self.output)

    def test_smoke_launch_forces_safe_environment_and_isolated_profile(self):
        host = self.runtime / 'build/hogwarts-native-diagnostic'
        host.write_text('#!/bin/sh\n/usr/bin/env\nprintf "arguments: %s %s\\n" "$1" "$2"\n')
        host.chmod(0o700)
        package.package(self.runtime, self.output)
        env = dict(os.environ, TOTK_GPU_NOCOMMIT='0', TOTK_GPU_ALLOW_SUBMIT='1',
                   TOTK_PROFILE_DIR='/do-not-use', HOGWARTS_SKIP_INDIRECT_DRY_RUN='0',
                   DM_NVN_AB_NOREUSE='1')
        subprocess.run([self.output / 'Contents/MacOS/HogwartsDiagnostic', '--smoke-test'],
                       env=env, cwd=self.root, check=True)
        subprocess.run([self.output / 'Contents/MacOS/HogwartsDiagnostic', '--smoke-test'],
                       env=env, cwd=self.root, check=True)
        log = (self.runtime / 'hogwarts-diagnostic-app-data/diagnostic.log').read_text()
        self.assertEqual(log.count('[hogwarts-app] diagnostic launch; GPU submission disabled'), 2)
        self.assertIn('TOTK_GPU_NOCOMMIT=1', log)
        self.assertIn('HOGWARTS_SKIP_INDIRECT_DRY_RUN=1', log)
        self.assertIn('HOGWARTS_SKIP_UNSUPPORTED_STAGES_DRY_RUN=1', log)
        self.assertIn(f'TOTK_PROFILE_DIR={self.runtime.resolve()}/hogwarts-diagnostic-app-data', log)
        self.assertIn(f'arguments: {self.runtime.resolve()}/rewritten/hogwarts boot', log)
        self.assertNotIn('TOTK_GPU_ALLOW_SUBMIT=', log)
        self.assertNotIn('DM_NVN_AB_NOREUSE=', log)

    def test_smoke_launch_rejects_non_directory_and_symlink(self):
        package.package(self.runtime, self.output)
        data = self.runtime / 'hogwarts-diagnostic-app-data'
        executable = self.output / 'Contents/MacOS/HogwartsDiagnostic'
        for kind in ('file', 'symlink'):
            with self.subTest(kind=kind):
                if kind == 'file':
                    data.write_text('not a directory')
                else:
                    target = self.root / 'other'
                    target.mkdir()
                    data.symlink_to(target, target_is_directory=True)
                result = subprocess.run([executable, '--smoke-test'], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('诊断数据目录不是当前用户拥有的普通目录', result.stderr)
                data.unlink()
                if kind == 'symlink':
                    self.assertFalse((target / 'diagnostic.log').exists())


if __name__ == '__main__':
    unittest.main()
