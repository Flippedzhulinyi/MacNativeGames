#!/usr/bin/env python3
"""Package a local Hogwarts diagnostic host as a non-playable macOS app."""
import argparse
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = ROOT / 'games/hogwarts/runtime/diagnostic_app.m'


def package(runtime, output):
    runtime = runtime.resolve(strict=True)
    if not runtime.is_dir() or runtime.is_relative_to(ROOT):
        raise ValueError('Runtime directory must be a private directory outside the repository')
    for relative in ('build/hogwarts-native-diagnostic', 'build/shader-service/totk_xlate',
                     'build/spirv-cross/spirv-cross'):
        path = runtime / relative
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f'Missing executable: {path}')
    for relative in ('rewritten/hogwarts', 'extracted/hogwarts/romfs/runtime-index.bin'):
        if not (runtime / relative).exists():
            raise ValueError(f'Missing diagnostic input: {runtime / relative}')
    output = output.absolute()
    if output.suffix != '.app':
        raise ValueError('Output must have an .app suffix')
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Output already exists: {output}')
    if not output.parent.is_dir():
        raise ValueError(f'Output parent directory does not exist: {output.parent}')
    with tempfile.TemporaryDirectory(prefix='.hogwarts-app-', dir=output.parent) as temp:
        bundle = Path(temp) / output.name
        contents = bundle / 'Contents'
        macos = contents / 'MacOS'
        resources = contents / 'Resources'
        macos.mkdir(parents=True)
        resources.mkdir()
        info = {
            'CFBundleName': 'Hogwarts Diagnostic - Not Playable',
            'CFBundleDisplayName': '霍格沃茨诊断测试（不可游玩）',
            'CFBundleIdentifier': 'org.macnativegames.hogwarts.diagnostic',
            'CFBundleVersion': '1',
            'CFBundleShortVersionString': '0.1',
            'CFBundlePackageType': 'APPL',
            'CFBundleExecutable': 'HogwartsDiagnostic',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '26.0',
        }
        (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
        (resources / 'DiagnosticConfig.plist').write_bytes(plistlib.dumps({'RuntimeDirectory': str(runtime)}))
        subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                        str(LAUNCHER), '-framework', 'Cocoa', '-o', str(macos / 'HogwartsDiagnostic')],
                       check=True)
        subprocess.run([str(macos / 'HogwartsDiagnostic'), '--verify'], check=True)
        output.mkdir()
        try:
            os.rename(contents, output / 'Contents')
        except OSError:
            output.rmdir()
            raise
    print(f'Diagnostic app: {output}\nNot playable; the private runtime directory must remain in place.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='private runtime/verified-tables directory')
    parser.add_argument('--output', type=Path, required=True, help='new .app path (must not exist)')
    args = parser.parse_args()
    try:
        package(args.runtime, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
