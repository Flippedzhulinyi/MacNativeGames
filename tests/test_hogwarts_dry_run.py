"""Optional checks against a locally built diagnostic host."""
import os
import subprocess
import unittest


class DryRunGuardTests(unittest.TestCase):
    def test_refuses_without_explicit_no_commit(self):
        host = os.environ.get('HOGWARTS_DIAGNOSTIC_HOST')
        if not host:
            self.skipTest('set HOGWARTS_DIAGNOSTIC_HOST to the locally built diagnostic executable')
        for mode in ('HOGWARTS_SKIP_INDIRECT_DRY_RUN', 'HOGWARTS_SKIP_UNSUPPORTED_STAGES_DRY_RUN'):
            for value in (None, '0'):
                with self.subTest(mode=mode, no_commit=value):
                    env = dict(os.environ, TOTK_GPU_ALLOW_SUBMIT='1')
                    env.pop('HOGWARTS_SKIP_INDIRECT_DRY_RUN', None)
                    env.pop('HOGWARTS_SKIP_UNSUPPORTED_STAGES_DRY_RUN', None)
                    env.pop('HOGWARTS_GEOMETRY_CAPTURE', None)
                    env[mode] = '1'
                    if value is None:
                        env.pop('TOTK_GPU_NOCOMMIT', None)
                    else:
                        env['TOTK_GPU_NOCOMMIT'] = value
                    result = subprocess.run([host, '/nonexistent', 'boot'], env=env, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('dry run requires TOTK_GPU_NOCOMMIT=1', result.stderr)
                    self.assertNotIn('mapped main', result.stderr)

    def test_geometry_capture_requires_safe_explicit_dry_run(self):
        host = os.environ.get('HOGWARTS_DIAGNOSTIC_HOST')
        if not host:
            self.skipTest('set HOGWARTS_DIAGNOSTIC_HOST to the locally built diagnostic executable')
        for path, dry, no_commit in (('/tmp/capture.plist', None, '1'),
                                     ('relative.plist', '1', '1'),
                                     ('/tmp/capture.plist', '1', None)):
            with self.subTest(path=path, dry=dry, no_commit=no_commit):
                env = dict(os.environ, HOGWARTS_GEOMETRY_CAPTURE=path, TOTK_GPU_ALLOW_SUBMIT='1')
                env.pop('HOGWARTS_SKIP_INDIRECT_DRY_RUN', None)
                env.pop('HOGWARTS_SKIP_UNSUPPORTED_STAGES_DRY_RUN', None)
                env.pop('TOTK_GPU_NOCOMMIT', None)
                if dry is not None:
                    env['HOGWARTS_SKIP_UNSUPPORTED_STAGES_DRY_RUN'] = dry
                if no_commit is not None:
                    env['TOTK_GPU_NOCOMMIT'] = no_commit
                result = subprocess.run([host, '/nonexistent', 'boot'], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('geometry capture requires' if dry is None or not path.startswith('/')
                              else 'dry run requires TOTK_GPU_NOCOMMIT=1', result.stderr)
                self.assertNotIn('mapped main', result.stderr)


if __name__ == '__main__':
    unittest.main()
