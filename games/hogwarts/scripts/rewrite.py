#!/usr/bin/env python3
"""Rewrite and verify the observed Hogwarts Legacy update modules; does not build an app."""
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('hogwarts_prepare', Path(__file__).with_name('prepare.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

TOOLS = prepare.ROOT / 'games/ot0/third_party/d2r'
MODULES = ('main', 'sdk', 'subsdk0')


def rewrite(work, jobs):
    prepare.ex.require(not work.resolve().is_relative_to(prepare.ROOT.resolve()),
                       'Work folder must be outside the repository because it contains game data')
    prepare.ex.require(jobs > 0, 'Jobs must be positive')
    for package in ('lz4', 'capstone', 'unicorn'):
        prepare.ex.require(importlib.util.find_spec(package) is not None, f'Missing Python package: {package}')
    exefs = work / 'extracted/update/exefs'
    prepare.verify_exefs(exefs)
    expected = json.loads(prepare.EXPECTED.read_text())['rewritten_sha256']
    destination = work / 'rewritten/verified'
    prepare.ex.require(not destination.exists(), f'Output already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, DM_RULESET='native', DM_PRIVATE_GATES='0', DM_ROOT=str(work.resolve()),
               DM_HOST_REGISTRY=str(prepare.ROOT / 'games/ot0/runtime/hle.h'))
    with tempfile.TemporaryDirectory(prefix='.hogwarts-rewrite-', dir=destination.parent) as temp:
        result = Path(temp) / 'result'
        result.mkdir()
        for module in MODULES:
            original = exefs / module
            print(f'Rewriting and verifying {module}', flush=True)
            subprocess.run([sys.executable, str(TOOLS / 'patch_nso.py'), str(original), str(result), module],
                           env=env, check=True)
            rewritten = result / f'{module}.patched.bin'
            with rewritten.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            prepare.ex.require(digest == expected[rewritten.name], f'Rewritten hash mismatch: {module}')
            subprocess.run([sys.executable, str(TOOLS / 'structck.py'), str(result), module, str(original)],
                           env=env, check=True)
            subprocess.run([sys.executable, str(TOOLS / 'equiv.py'), str(result), module, str(original),
                            '--jobs', str(jobs)], env=env, check=True)
        result.rename(destination)
    print(f'Verified rewrites: {destination}; no application was built.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='private work folder outside the repository')
    parser.add_argument('--jobs', type=int, default=2, help='equivalence-test workers (default: 2)')
    args = parser.parse_args()
    try:
        rewrite(args.work, args.jobs)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
