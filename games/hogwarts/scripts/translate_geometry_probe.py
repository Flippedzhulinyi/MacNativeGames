#!/usr/bin/env python3
"""Translate a private Hogwarts geometry capture for offline Metal compilation, not replay."""
import argparse
import hashlib
import json
import os
import plistlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRANSLATOR = ROOT / 'games/xc3/prebuilt/macos-arm64/totk_xlate'
PROBE = ROOT / 'tests/hogwarts_geometry_compile_probe.m'
TOPOLOGIES = {0: 'points', 1: 'lines', 3: 'lines', 4: 'triangles', 5: 'triangles', 6: 'triangles',
              10: 'lines_adj', 11: 'lines_adj', 12: 'triangles_adj', 13: 'triangles_adj'}


def decode_capture(capture):
    if not isinstance(capture, dict) or capture.get('version') != 1:
        raise ValueError('Unsupported geometry capture')
    primitive = capture.get('primitive')
    if type(primitive) is not int or primitive not in TOPOLOGIES:
        raise ValueError('Unsupported geometry input primitive')
    stages = capture.get('stages')
    if not isinstance(stages, list):
        raise ValueError('Missing shader stages')
    found = {}
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError('Invalid shader stage')
        number, code, offset = stage.get('stage'), stage.get('code'), stage.get('constant_offset')
        if (type(number) is not int or number < 0 or number > 5 or number in found or
                not isinstance(code, bytes) or len(code) > 16 * 1024 * 1024 or
                type(offset) is not int or offset > len(code) or offset < (0 if number == 5 else 0x30)):
            raise ValueError('Invalid shader stage data')
        found[number] = stage
    if 0 not in found or 2 not in found:
        raise ValueError('Capture requires vertex and geometry stages')
    return TOPOLOGIES[primitive], found[0], found[2]


def check_strip_layout(capture, geometry, reflections, work):
    vertices, instances = capture.get('count'), capture.get('instances')
    if (capture.get('primitive') != 5 or capture.get('indexed') is not False or
            type(vertices) is not int or not 3 <= vertices <= 0xffffffff or
            type(instances) is not int or not 1 <= instances <= 0xffffffff or
            len(geometry['code']) < 0x44):
        raise ValueError('Layout check requires a bounded non-indexed triangle-strip capture')
    invocations = (struct.unpack_from('<I', geometry['code'], 0x38)[0] >> 24) or 1
    max_output = struct.unpack_from('<I', geometry['code'], 0x40)[0] & 0xfff
    values = [vertices, vertices - 2, instances, invocations, max_output,
              reflections[0]['out_words'], reflections[1]['out_words']]
    executable = work / 'geometry-layout-probe'
    subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-I', str(ROOT / 'games/hogwarts/runtime'),
                    str(ROOT / 'tests/hogwarts_geometry_layout_probe.c'), '-o', str(executable)], check=True)
    result = subprocess.run([str(executable), *map(str, values)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f'Geometry layout rejected: {result.stderr.strip()}')
    sizes = [int(value) for value in result.stdout.split()]
    if len(sizes) != 3:
        raise ValueError('Geometry layout probe returned an invalid result')
    executable.unlink()
    (work / 'geometry_layout.json').write_text(json.dumps({
        'vertex_bytes': sizes[0], 'geometry_bytes': sizes[1], 'index_bytes': sizes[2],
        'vertices': vertices, 'primitives': vertices - 2, 'instances': instances,
        'invocations': invocations, 'max_output': max_output,
        'vertex_words': values[5], 'geometry_words': values[6],
        'diagnostic_only': True,
    }, indent=2) + '\n')


def translate(capture_path, output, spirv_cross, check_layout=False):
    capture_path = capture_path.resolve(strict=True)
    if capture_path.is_relative_to(ROOT):
        raise ValueError('Capture must be outside the repository')
    output = output.absolute()
    if output.resolve().is_relative_to(ROOT):
        raise ValueError('Output must be outside the repository')
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Output already exists: {output}')
    if not output.parent.is_dir():
        raise ValueError('Output parent must already exist')
    with capture_path.open('rb') as f:
        capture = plistlib.load(f)
    topology, vs, gs = decode_capture(capture)
    expected = TRANSLATOR.with_suffix('.sha256').read_text().split()[0]
    with TRANSLATOR.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != expected:
            raise ValueError('Geometry translator SHA-256 mismatch')
    if not os.access(TRANSLATOR, os.X_OK) or not os.access(spirv_cross, os.X_OK):
        raise ValueError('Translator or SPIRV-Cross is not executable')

    with tempfile.TemporaryDirectory(prefix='.hogwarts-geometry-', dir=output.parent) as temp:
        work = Path(temp)
        vertex_path, geometry_path = work / 'stage0.code', work / 'stage2.code'
        vertex_path.write_bytes(vs['code'][0x30:])
        geometry_path.write_bytes(gs['code'][0x30:])
        jobs = []
        for part in ('vsc', 'gsc', 'vpt'):
            stage = vs if part == 'vsc' else gs
            job = {'variant': f'geometry_{part}', 'stage': part,
                   'code': str(vertex_path if part == 'vsc' else geometry_path),
                   'c1': stage['code'][stage['constant_offset']:].hex(), 'topology': topology,
                   'tex': {}, 'img': {}, 'attr': {}, 'fout': {}}
            if part != 'vsc':
                job.update(vs_code=str(vertex_path), vs_c1=vs['code'][vs['constant_offset']:].hex())
            jobs.append(job)
        service = subprocess.run(
            [str(TRANSLATOR), '--service', '--spirv-cross', str(spirv_cross),
             '--out', str(work), '--chain', 'hogwarts-geometry-probe'],
            input=''.join(json.dumps(job) + '\n' for job in jobs),
            capture_output=True, text=True, timeout=120)
        if service.returncode:
            raise ValueError(f'Geometry translator exited {service.returncode}: '
                             f'{service.stderr.strip()} {service.stdout.strip()}')
        replies = [json.loads(line) for line in service.stdout.splitlines()]
        if len(replies) != len(jobs) or any(reply.get('ok') is not True for reply in replies):
            raise ValueError(f'Geometry translation failed: {service.stdout.strip()} {service.stderr.strip()}')
        reflections = []
        sources = []
        for part, kind in (('vsc', 'kernel'), ('gsc', 'kernel'), ('vpt', 'vertex')):
            reflection = json.loads((work / f'geometry_{part}_b.json').read_text())
            if (reflection.get('msl_entry_kind') != kind or reflection.get('drv_unfillable') or
                    type(reflection.get('out_words')) is not int or reflection['out_words'] <= 0):
                raise ValueError(f'Invalid geometry reflection for {part}')
            reflections.append(reflection)
            sources.append(work / f'geometry_{part}_b.metal')
        if (reflections[0]['out_words'] != reflections[1]['in_words'] or
                reflections[1]['out_words'] != reflections[2]['out_words']):
            raise ValueError('Geometry stage output layouts disagree')
        if check_layout:
            check_strip_layout(capture, gs, reflections, work)
        probe = work / 'geometry-compile-probe'
        subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror', str(PROBE),
                        '-framework', 'Foundation', '-framework', 'Metal', '-o', str(probe)], check=True)
        env = dict(os.environ, MTL_DEBUG_LAYER='1', MTL_SHADER_VALIDATION='1')
        subprocess.run([str(probe), *map(str, sources)], env=env, check=True)
        probe.unlink()
        output.mkdir(mode=0o700)
        try:
            for path in work.iterdir():
                os.rename(path, output / path.name)
        except OSError as error:
            raise OSError(f'Publishing failed; output may be incomplete at {output}: {error}') from error
    print(f'Geometry translations compiled: {output}')
    print('No game GPU work was submitted; runtime replay and actual attribute bindings remain unverified.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True, help='private capture plist outside the repository')
    parser.add_argument('--output', type=Path, required=True, help='new private output directory')
    parser.add_argument('--spirv-cross', type=Path, required=True, help='local SPIRV-Cross executable')
    parser.add_argument('--check-strip-layout', action='store_true',
                        help='check bounds for a non-indexed strip with one geometry invocation')
    args = parser.parse_args()
    try:
        translate(args.capture, args.output, args.spirv_cross, args.check_strip_layout)
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException,
            subprocess.SubprocessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
