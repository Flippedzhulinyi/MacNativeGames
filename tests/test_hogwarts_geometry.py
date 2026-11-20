"""Optional local-only check of translated game geometry stages."""
import json
import importlib.util
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'hogwarts_geometry_probe', ROOT / 'games/hogwarts/scripts/translate_geometry_probe.py')
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)


class GeometryCaptureTests(unittest.TestCase):
    def test_capture_validation_and_topology(self):
        vs = {'stage': 0, 'code': bytes(64), 'constant_offset': 48}
        gs = {'stage': 2, 'code': bytes(80), 'constant_offset': 64}
        capture = {'version': 1, 'primitive': 5, 'stages': [vs, gs]}
        self.assertEqual(geometry.decode_capture(capture), ('triangles', vs, gs))
        invalid = [
            {}, {**capture, 'primitive': 7}, {**capture, 'primitive': True},
            {**capture, 'stages': [vs]}, {**capture, 'stages': [vs, gs, gs]},
            {**capture, 'stages': [vs, {**gs, 'constant_offset': 81}]},
            {**capture, 'stages': [vs, {**gs, 'constant_offset': -1}]},
            {**capture, 'stages': [vs, {**gs, 'code': 'not bytes'}]},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                geometry.decode_capture(value)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            capture = root / 'capture.plist'
            capture.write_bytes(b'not parsed')
            output = root / 'output'
            output.mkdir()
            keep = output / 'keep'
            keep.write_text('unchanged')
            with self.assertRaises(FileExistsError):
                geometry.translate(capture, output, root / 'missing')
            self.assertEqual(keep.read_text(), 'unchanged')

    def test_strip_layout_rejects_unsupported_draws(self):
        reflections = [{'out_words': 13}, {'out_words': 14}]
        gs = {'code': bytes(0x44)}
        for capture in ({'primitive': 5, 'indexed': True, 'count': 3, 'instances': 32},
                        {'primitive': 4, 'indexed': False, 'count': 3, 'instances': 32},
                        {'primitive': 5, 'indexed': False, 'count': True, 'instances': 32},
                        {'primitive': 5, 'indexed': False, 'count': 3, 'instances': 0}):
            with self.subTest(capture=capture), self.assertRaises(ValueError):
                geometry.check_strip_layout(capture, gs, reflections, Path('/nonexistent'))


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun'), 'macOS required')
class GeometryTranslationTests(unittest.TestCase):
    def test_translate_private_capture(self):
        capture = os.environ.get('HOGWARTS_LOCAL_GEOMETRY_CAPTURE')
        spirv_cross = os.environ.get('HOGWARTS_LOCAL_SPIRV_CROSS')
        if not capture and not spirv_cross:
            self.skipTest('set HOGWARTS_LOCAL_GEOMETRY_CAPTURE and HOGWARTS_LOCAL_SPIRV_CROSS')
        if not capture or not spirv_cross:
            self.fail('both HOGWARTS_LOCAL_GEOMETRY_CAPTURE and HOGWARTS_LOCAL_SPIRV_CROSS are required')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'translated'
            subprocess.run([sys.executable, str(ROOT / 'games/hogwarts/scripts/translate_geometry_probe.py'),
                            '--capture', capture, '--output', str(output),
                            '--spirv-cross', spirv_cross, '--check-strip-layout'], check=True)
            for stage in ('vsc', 'gsc', 'vpt'):
                self.assertTrue((output / f'geometry_{stage}_b.metal').is_file())
                self.assertTrue((output / f'geometry_{stage}_b.json').is_file())
            layout = json.loads((output / 'geometry_layout.json').read_text())
            self.assertTrue(layout['diagnostic_only'])
            self.assertEqual(layout['invocations'], 1)
            self.assertGreater(layout['geometry_bytes'], 0)
            with open(capture, 'rb') as f:
                data = plistlib.load(f)
            gs = next(stage for stage in data['stages'] if stage['stage'] == 2)
            code = bytearray(gs['code'])
            value = struct.unpack_from('<I', code, 0x38)[0]
            struct.pack_into('<I', code, 0x38, (value & 0x00ffffff) | (2 << 24))
            gs['code'] = bytes(code)
            invalid_capture = Path(temp) / 'multiple-invocations.plist'
            invalid_capture.write_bytes(plistlib.dumps(data))
            invalid_output = Path(temp) / 'rejected'
            result = subprocess.run([sys.executable, str(ROOT / 'games/hogwarts/scripts/translate_geometry_probe.py'),
                                     '--capture', str(invalid_capture), '--output', str(invalid_output),
                                     '--spirv-cross', spirv_cross, '--check-strip-layout'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Geometry layout rejected:', result.stderr)
            self.assertFalse(invalid_output.exists())

    def test_local_geometry_sources_compile(self):
        directory = os.environ.get('HOGWARTS_LOCAL_GEOMETRY_TRANSLATION')
        if not directory:
            self.skipTest('set HOGWARTS_LOCAL_GEOMETRY_TRANSLATION to the private translation directory')
        directory = Path(directory)
        paths = []
        reflections = []
        for stage, kind in (('vsc', 'kernel'), ('gsc', 'kernel'), ('vpt', 'vertex')):
            reflection = json.loads((directory / f'geometry_{stage}_b.json').read_text())
            self.assertEqual(reflection['msl_entry_kind'], kind)
            self.assertFalse(reflection['drv_unfillable'])
            self.assertGreater(reflection['out_words'], 0)
            reflections.append(reflection)
            paths.append(directory / f'geometry_{stage}_b.metal')
        self.assertEqual(reflections[0]['out_words'], reflections[1]['in_words'])
        self.assertEqual(reflections[1]['out_words'], reflections[2]['out_words'])
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / 'probe'
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'tests/hogwarts_geometry_compile_probe.m'),
                            '-framework', 'Foundation', '-framework', 'Metal', '-o', str(exe)], check=True)
            env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1')
            subprocess.run([str(exe), *map(str, paths)], env=env, check=True)
            invalid = Path(temp) / 'invalid.metal'
            invalid.write_text('this is not valid Metal source')
            result = subprocess.run([str(exe), str(invalid), *map(str, paths[1:])],
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('geometry stage 1 compile:', result.stderr)


if __name__ == '__main__':
    unittest.main()
