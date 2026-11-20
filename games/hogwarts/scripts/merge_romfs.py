#!/usr/bin/env python3
"""Merge the observed Hogwarts Legacy NSPs and verify their RomFS; does not build an app."""
import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('hogwarts_prepare', Path(__file__).with_name('prepare.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

backend = prepare.ROOT / 'games/ot0/scripts'
original_path = sys.path[:]
sys.path.insert(0, str(backend))
try:
    spec = importlib.util.spec_from_file_location('hogwarts_ot0_merger', backend / 'merge_romfs.py')
    merger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merger)
finally:
    sys.path[:] = original_path


def merge(base_path, update_path, keys_path, work):
    prepare.ex.require(not work.resolve().is_relative_to(prepare.ROOT.resolve()),
                       'Work folder must be outside the repository because it contains game data')
    destination = work / 'extracted/merged-romfs'
    prepare.ex.require(not destination.exists(), f'Output already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.hogwarts-merge-', dir=destination.parent) as temp:
        temporary = Path(temp)
        prepare.prepare(base_path, update_path, keys_path, temporary / 'verification')
        keys = prepare.ex.load_keys(keys_path)
        bf, brec, bhdr, bctr = merger.open_program(base_path, keys, prepare.TITLE, False)
        with bf:
            uf, urec, uhdr, uctr = merger.open_program(update_path, keys, prepare.TITLE, True)
            with uf:
                base = merger.base_section(bctr, *merger.romfs_section(bhdr))
                start, end, fs = merger.romfs_section(uhdr)
                patched = merger.Patched(uctr, start, end, fs, base)
                result = temporary / 'result'
                result.mkdir()
                image = result / 'romfs.bin'
                counts, size, sha = merger.verify_ivfc(fs, patched.total, patched.read, image)
                files = merger.index_romfs(image)
                report = {
                    'status': 'pass',
                    'base': {'source': str(base_path.resolve()), 'program': brec},
                    'update': {'source': str(update_path.resolve()), 'program': urec},
                    'ivfc_blocks': counts, 'romfs_size': size, 'romfs_sha256': sha,
                    'bytes_from_base': patched.from_base, 'bytes_from_update': patched.from_update,
                    'files': files,
                    'integrity': 'FS headers and all six merged IVFC levels verified; RSA signatures not checked',
                }
                (result / 'index.json').write_text(json.dumps(report, indent=2) + '\n')
                result.rename(destination)
    print(f'Verified merged RomFS: {destination} ({size} bytes, {len(files)} files)', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path, help='your base game NSP')
    parser.add_argument('--update', type=Path, required=True, help='your update NSP')
    parser.add_argument('--keys', type=Path, required=True, help='prod.keys from your own Switch')
    parser.add_argument('--work', type=Path, required=True, help='private work folder outside the repository')
    args = parser.parse_args()
    try:
        merge(args.base, args.update, args.keys, args.work)
    except (OSError, ValueError, prepare.subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
