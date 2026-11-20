#!/usr/bin/env python3
"""Generate experimental loader tables for verified Hogwarts Legacy inputs; does not compile a host."""
import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('hogwarts_merge', Path(__file__).with_name('merge_romfs.py'))
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)
prepare = merge.prepare

backend = prepare.ROOT / 'games/ot0/scripts'
original_path = sys.path[:]
sys.path.insert(0, str(backend))
try:
    spec = importlib.util.spec_from_file_location('hogwarts_ot0_runtime', backend / 'prepare_runtime.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
finally:
    sys.path[:] = original_path


def generate(work):
    prepare.ex.require(not work.resolve().is_relative_to(prepare.ROOT.resolve()),
                       'Work folder must be outside the repository because it contains game data')
    pins = json.loads(prepare.EXPECTED.read_text())
    exefs = work / 'extracted/update/exefs'
    prepare.verify_exefs(exefs)
    rewritten = work / 'rewritten/verified'
    prepare.ex.require(rewritten.is_dir(), 'Verified rewritten modules are missing; run rewrite.py first')
    image = work / 'extracted/merged-romfs/romfs.bin'
    prepare.ex.require(image.is_file() and image.stat().st_size == pins['romfs']['size'],
                       'Merged RomFS missing or size mismatch')
    with image.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    prepare.ex.require(digest == pins['romfs']['sha256'], 'Merged RomFS hash mismatch')
    files = merge.merger.index_romfs(image)
    destination = work / 'runtime/verified-tables'
    prepare.ex.require(not destination.exists(), f'Output already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    pinned = {'exefs_sha256': {name: info['sha256'] for name, info in pins['files'].items()},
              'rewritten_sha256': pins['rewritten_sha256'], 'romfs': pins['romfs']}
    with tempfile.TemporaryDirectory(prefix='.hogwarts-tables-', dir=destination.parent) as temp:
        result = Path(temp) / 'result'
        extracted = result / 'extracted/hogwarts'
        extracted.mkdir(parents=True)
        (extracted / 'exefs').symlink_to(exefs.resolve(), target_is_directory=True)
        romfs = extracted / 'romfs'
        romfs.mkdir()
        (romfs / 'romfs.bin').symlink_to(image.resolve())
        (romfs / 'index.json').write_text(json.dumps({
            'status': 'pass', 'romfs_sha256': digest, 'romfs_size': pins['romfs']['size'], 'files': files,
        }) + '\n')
        (result / 'rewritten').mkdir()
        (result / 'rewritten/hogwarts').symlink_to(rewritten.resolve(), target_is_directory=True)
        out = result / 'build/hogwarts'
        out.mkdir(parents=True)
        print('Generating module and relocation tables', flush=True)
        summary = runtime.runtime_tables(result, 'hogwarts', out, pinned)
        runtime.romfs_config(result, 'hogwarts', out, pinned)
        runtime.shared_fonts_config(result, out)
        result.rename(destination)
    print(f'Loader tables generated: {destination}; no host or app was built. {summary}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='private work folder outside the repository')
    args = parser.parse_args()
    try:
        generate(args.work)
    except (OSError, ValueError, AssertionError, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
