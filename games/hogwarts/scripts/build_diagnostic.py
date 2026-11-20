#!/usr/bin/env python3
"""Prepare and build the experimental Hogwarts diagnostic host, not a playable app."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('hogwarts_build_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load('prepare')
merge = load('merge_romfs')
rewrite = load('rewrite')
tables = load('prepare_runtime')


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def check_romfs(work):
    image = work / 'extracted/merged-romfs/romfs.bin'
    pinned = json.loads(prepare.EXPECTED.read_text())['romfs']
    prepare.ex.require(image.is_file() and image.stat().st_size == pinned['size'],
                       'Existing merged RomFS is missing or has the wrong size')
    prepare.ex.require(digest(image) == pinned['sha256'], 'Existing merged RomFS hash mismatch')


def check_rewrites(work, jobs):
    exefs = work / 'extracted/update/exefs'
    output = work / 'rewritten/verified'
    pins = json.loads(prepare.EXPECTED.read_text())['rewritten_sha256']
    env = dict(os.environ, DM_RULESET='native', DM_PRIVATE_GATES='0', DM_ROOT=str(work),
               DM_HOST_REGISTRY=str(prepare.ROOT / 'games/ot0/runtime/hle.h'))
    for module in rewrite.MODULES:
        image = output / f'{module}.patched.bin'
        prepare.ex.require(image.is_file() and digest(image) == pins[image.name],
                           f'Existing rewritten image hash mismatch: {module}')
        print(f'Checking existing rewrite: {module}', flush=True)
        subprocess.run([sys.executable, str(rewrite.TOOLS / 'structck.py'), str(output), module,
                        str(exefs / module)], env=env, check=True)
        subprocess.run([sys.executable, str(rewrite.TOOLS / 'equiv.py'), str(output), module,
                        str(exefs / module), '--jobs', str(jobs)], env=env, check=True)


def check_tables(work):
    existing = work / 'runtime/verified-tables'
    with tempfile.TemporaryDirectory(prefix='.hogwarts-check-', dir=work) as directory:
        staged = Path(directory)
        (staged / 'extracted').symlink_to(work / 'extracted', target_is_directory=True)
        (staged / 'rewritten').symlink_to(work / 'rewritten', target_is_directory=True)
        tables.generate(staged)
        reference = staged / 'runtime/verified-tables'
        paths = ('build/hogwarts/runtime_tables.h', 'build/hogwarts/romfs_config.h',
                 'build/hogwarts/shared_fonts_config.h', 'extracted/hogwarts/romfs/index.json',
                 'extracted/hogwarts/romfs/runtime-index.bin')
        for path in paths:
            prepare.ex.require((existing / path).is_file() and
                               (existing / path).read_bytes() == (reference / path).read_bytes(),
                               f'Existing loader tables mismatch: {path}')
        for path, target in (
            ('extracted/hogwarts/exefs', work / 'extracted/update/exefs'),
            ('extracted/hogwarts/romfs/romfs.bin', work / 'extracted/merged-romfs/romfs.bin'),
            ('rewritten/hogwarts', work / 'rewritten/verified'),
        ):
            link = existing / path
            prepare.ex.require(link.is_symlink() and link.resolve(strict=True) == target.resolve(strict=True),
                               f'Existing loader input link mismatch: {path}')


def build(base, update, keys_path, work, jobs):
    work = work.resolve()
    prepare.ex.require(not work.is_relative_to(prepare.ROOT.resolve()),
                       'Work folder must be outside the repository because it contains game data')
    prepare.ex.require(jobs > 0, 'Jobs must be positive')
    prepare.ex.require(re.fullmatch(r'[A-Za-z0-9_./-]+', str(work)) is not None,
                       'Work folder path contains characters unsupported by make; choose a different --work')
    for path in (base, update, keys_path):
        prepare.ex.require(path.is_file(), f'Input file missing: {path}')
    print('1/4 Verifying game inputs and update code', flush=True)
    keys = prepare.ex.load_keys(keys_path)
    prepare.inspect(base, keys, False)
    prepare.inspect(update, keys, True)
    exefs = work / 'extracted/update'
    if exefs.exists():
        prepare.verify_exefs(exefs / 'exefs')
    else:
        prepare.prepare(base, update, keys_path, work)
    print('2/4 Preparing and checking merged game data', flush=True)
    if (work / 'extracted/merged-romfs').exists():
        check_romfs(work)
    else:
        merge.merge(base, update, keys_path, work)
        check_romfs(work)
    print('3/4 Rewriting and validating native code', flush=True)
    if (work / 'rewritten/verified').exists():
        check_rewrites(work, jobs)
    else:
        rewrite.rewrite(work, jobs)
    print('4/4 Generating loader tables and building diagnostic host', flush=True)
    if (work / 'runtime/verified-tables').exists():
        check_tables(work)
    else:
        tables.generate(work)
    subprocess.run(['make', '-C', str(prepare.ROOT / 'games/ot0'), '-f', '../hogwarts/Makefile',
                    f'WORK={work / "runtime/verified-tables"}', 'runtime'], check=True)
    print(f'Diagnostic host: {work / "runtime/verified-tables/build/hogwarts-native-diagnostic"}', flush=True)
    print('Not a playable application. GPU submission and indirect draws remain blocked.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path, help='your base game NSP')
    parser.add_argument('--update', type=Path, required=True, help='your update NSP')
    parser.add_argument('-k', '--keys', type=Path, required=True, help='prod.keys from your own Switch')
    parser.add_argument('--work', type=Path, required=True, help='private work folder outside the repository')
    parser.add_argument('--jobs', type=int, default=2, help='equivalence-test workers (default: 2)')
    args = parser.parse_args()
    try:
        build(args.base, args.update, args.keys, args.work, args.jobs)
    except (OSError, ValueError, AssertionError, KeyError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
