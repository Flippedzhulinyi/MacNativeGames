#!/usr/bin/env python3
"""Verify Hogwarts Legacy NSP identities and prepare the observed update ExeFS.

This is an experimental preparation step, not an app builder.
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TITLE = '0100F7E00C70E000'
UPDATE_TITLE = '0100F7E00C70E800'
EXPECTED = Path(__file__).resolve().parents[1] / 'assets/expected-update.json'
EXTRACTOR = ROOT / 'games/by3/scripts/extract_code.py'
PARSER = ROOT / 'games/totk/scripts/extract_exefs.py'

spec = importlib.util.spec_from_file_location('hogwarts_container_parser', PARSER)
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)


def inspect(path, keys, update):
    with path.open('rb') as source:
        kind, entries = ex.container_entries(source, path.stat().st_size)
        ex.require(kind == 'nsp', f'{path}: expected an NSP')
        records = ex.nca_inventory(source, entries, keys)
        meta = [r for r, _ in records if r['content_type'] == 1]
        expected_meta = UPDATE_TITLE if update else TITLE
        ex.require(len(meta) == 1 and meta[0]['title_id'] == expected_meta,
                   f'{path}: expected {"update" if update else "base"} metadata for Hogwarts Legacy')
        ex.require(all(r['title_id'] in (TITLE, expected_meta) for r, _ in records),
                   f'{path}: contains another title')
        programs = [(r, h) for r, h in records if r['content_type'] == 0]
        ex.require(len(programs) == 1 and programs[0][0]['title_id'] == TITLE,
                   f'{path}: expected one Hogwarts Legacy Program NCA')
        header = programs[0][1]
        patch = any(header[0x400 + 512 * i + 4] == 4 for i in range(4))
        ex.require(patch == update, f'{path}: unexpected base/update Program NCA layout')
        ex.nca_ctr_key(header, keys, ex.common_tickets(source, entries))


def verify_exefs(directory):
    expected = json.loads(EXPECTED.read_text())['files']
    actual = {p.name for p in directory.iterdir()}
    ex.require(actual == set(expected), 'Unexpected update ExeFS file set')
    for name, info in expected.items():
        path = directory / name
        ex.require(path.is_file() and path.stat().st_size == info['size'],
                   f'Update ExeFS size mismatch: {name}')
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        ex.require(digest == info['sha256'], f'Update ExeFS hash mismatch: {name}')


def prepare(base, update, keys_path, work):
    ex.require(not work.resolve().is_relative_to(ROOT.resolve()),
               'Work folder must be outside the repository because it contains game data')
    keys = ex.load_keys(keys_path)
    inspect(base, keys, False)
    inspect(update, keys, True)
    destination = work / 'extracted/update'
    ex.require(not destination.exists(), f'Output already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.hogwarts-', dir=destination.parent) as temp:
        result = Path(temp) / 'result'
        subprocess.run([sys.executable, str(EXTRACTOR), str(update), '--keys', str(keys_path),
                        '--title', TITLE, '--output', str(result / 'exefs')], check=True)
        verify_exefs(result / 'exefs')
        result.rename(destination)
    print(f'Verified update ExeFS: {destination}', flush=True)
    print('No application was built: the Hogwarts Legacy runtime is not implemented.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path, help='your base game NSP')
    parser.add_argument('--update', type=Path, required=True, help='your update NSP')
    parser.add_argument('--keys', type=Path, required=True, help='prod.keys from your own Switch')
    parser.add_argument('--work', type=Path, required=True, help='private work folder outside the repository')
    args = parser.parse_args()
    try:
        prepare(args.base, args.update, args.keys, args.work)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
