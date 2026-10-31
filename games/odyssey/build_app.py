#!/usr/bin/env python3
"""Build the Odyssey 1.4.1 macOS app from game image(s) and prod.keys."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
VERSION = "v141"
LOCAL_SHARED_FONTS = HERE / "ODYSSEY_build/extracted/firmware/shared-fonts"


class BuildError(Exception):
    pass


def run(command: list[str | Path], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=True)
    except subprocess.CalledProcessError as error:
        raise BuildError(f"command failed with exit code {error.returncode}: {command[0]}") from None


def source_matches(manifest_path: Path, source: Path) -> bool:
    try:
        manifest = json.loads(manifest_path.read_text())
        stat = source.stat()
        return (manifest["source"] == str(source.resolve())
                and manifest["source_size"] == stat.st_size
                and manifest["source_mtime_ns"] == stat.st_mtime_ns)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def require_new_or_matching(output: Path, matches: bool, description: str) -> bool:
    if matches:
        return True
    if output.exists():
        raise BuildError(f"existing {description} does not match these inputs; choose a fresh --work folder: {output}")
    return False


def verify_shared_fonts(folder: Path) -> None:
    data = json.loads((folder / "manifest.json").read_text())
    fonts = data["fonts"]
    if data.get("status") != "pass" or len(fonts) != 6:
        raise ValueError("manifest does not contain six verified fonts")
    if sorted(entry["type"] for entry in fonts) != list(range(6)):
        raise ValueError("manifest font types are incomplete or duplicated")
    for entry in fonts:
        source = folder / f'{entry["type"]}-{entry["name"]}.bfttf'
        if (source.stat().st_size != entry["bfttf_bytes"]
                or hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]):
            raise ValueError(f"font verification failed: {source.name}")


def prepare_update(update: Path, keys: Path, work: Path, python: Path) -> Path:
    if update.suffix.lower() != ".nsz":
        return update
    cache = work / "extracted/containers"
    output = cache / f"{update.stem}.nsp"
    manifest = cache / f"{update.stem}.json"
    if source_matches(manifest, update) and output.is_file():
        return output
    if output.exists() or manifest.exists():
        raise BuildError(f"stale NSZ conversion exists; choose a fresh --work folder: {output}")
    cache.mkdir(parents=True, exist_ok=True)
    run([python.parent / "nsz", "-D", "--keys", keys, "-o", cache, update], cwd=work)
    generated = cache / f"{update.stem}.nsp"
    if not generated.is_file():
        raise BuildError(f"NSZ conversion did not produce {generated}")
    stat = update.stat()
    manifest.write_text(json.dumps({"source": str(update.resolve()), "source_size": stat.st_size,
                                    "source_mtime_ns": stat.st_mtime_ns}, indent=2) + "\n")
    return generated


def prepare_fonts(game: Path, work: Path, python: Path, keys: Path, firmware: Path | None,
                  font_xci: Path | None, shared_fonts: Path | None) -> None:
    output = work / "extracted/firmware/shared-fonts"
    manifest = output / "manifest.json"
    if manifest.is_file():
        try:
            verify_shared_fonts(output)
            return
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise BuildError(f"invalid shared-font cache {output}: {error}") from None
    if output.exists():
        raise BuildError(f"incomplete shared-font cache; choose a fresh --work folder: {output}")

    if shared_fonts:
        try:
            verify_shared_fonts(shared_fonts)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise BuildError(f"invalid shared-font source {shared_fonts}: {error}") from None
        shutil.copytree(shared_fonts, output)
        return

    if game.suffix.lower() == ".xci" or font_xci:
        source = game if game.suffix.lower() == ".xci" else font_xci
        if not source.is_file():
            raise BuildError(f"font XCI not found: {source}")
        source_args = ["--xci", source]
    else:
        firmware = firmware or Path.home() / "Library/Application Support/Ryujinx/bis/system/Contents/registered"
        if not firmware.is_dir():
            raise BuildError("NSP images do not contain system shared fonts; install Switch firmware in Ryujinx or pass --firmware")
        source_args = ["--firmware", firmware]
    run([python, HERE / "scripts/extract_shared_fonts.py", *source_args, "--keys", keys,
         "--output", output], cwd=work)


def build(args: argparse.Namespace) -> Path:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise BuildError("Odyssey app builds require macOS on Apple silicon")
    if shutil.which("xcrun") is None:
        raise BuildError("Xcode command line tools are required: xcode-select --install")
    for library in ("/opt/homebrew/opt/opus/lib/libopus.a", "/opt/homebrew/opt/libvpx/lib/libvpx.a"):
        if not Path(library).is_file():
            raise BuildError("missing Homebrew libraries; run: brew install opus libvpx")

    game = args.game.expanduser().resolve()
    update_source = args.update.expanduser().resolve() if args.update else game
    keys = args.keys.expanduser().resolve()
    if not game.is_file():
        raise BuildError(f"game image not found: {game}")
    if not update_source.is_file():
        raise BuildError(f"update image not found: {update_source}")
    if not keys.is_file():
        raise BuildError(f"prod.keys not found: {keys}")

    work = args.work.expanduser().resolve() if args.work else game.parent / "ODYSSEY_build"
    output = args.out.expanduser().resolve() if args.out else work / "build/Super Mario Odyssey.app"
    work.mkdir(parents=True, exist_ok=True)
    python = work / ".venv/bin/python"
    if not python.is_file():
        run([sys.executable, "-m", "venv", work / ".venv"], cwd=HERE)
    run([python, "-m", "pip", "install", "-r", HERE / "requirements.txt"], cwd=HERE)

    update = prepare_update(update_source, keys, work, python)
    firmware = args.firmware.expanduser().resolve() if args.firmware else None
    font_xci = args.font_xci.expanduser().resolve() if args.font_xci else None
    shared_fonts = (args.shared_fonts.expanduser().resolve() if args.shared_fonts else
                    LOCAL_SHARED_FONTS.resolve() if (LOCAL_SHARED_FONTS / "manifest.json").is_file() else None)
    if font_xci and not font_xci.is_file():
        raise BuildError(f"font XCI not found: {font_xci}")
    if shared_fonts and not shared_fonts.is_dir():
        raise BuildError(f"shared-font directory not found: {shared_fonts}")
    prepare_fonts(game, work, python, keys, firmware, font_xci, shared_fonts)

    version_dir = work / f"extracted/{VERSION}"
    exefs = version_dir / "exefs"
    code_manifest = version_dir / "extraction-manifest.json"
    if not require_new_or_matching(exefs, source_matches(code_manifest, update), "ExeFS extraction"):
        run([python, HERE / "scripts/extract_exefs.py", update, "--keys", keys,
             "--update", "--output", exefs], cwd=work)

    romfs = version_dir / "romfs"
    romfs_index = romfs / "index.json"
    romfs_matches = False
    try:
        record = json.loads(romfs_index.read_text())
        base = record["base"]
        patch = record["update"]
        romfs_matches = (base["source"] == str(game) and base["source_size"] == game.stat().st_size
                         and patch["source"] == str(update) and patch["source_size"] == update.stat().st_size)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if not require_new_or_matching(romfs, romfs_matches, "merged RomFS"):
        run([python, HERE / "scripts/merge_romfs.py", game, update, "--keys", keys, "--output", romfs], cwd=work)

    rewritten = work / f"rewritten/{VERSION}"
    rewritten.mkdir(parents=True, exist_ok=True)
    rewrite_env = dict(os.environ, DM_RULESET="native", DM_PRIVATE_GATES="0")
    for module in ("sdk", "subsdk0", "main"):
        run([python, HERE / "third_party/d2r/patch_nso.py", exefs / module, rewritten, module],
            cwd=work, env=rewrite_env)
    run([python, HERE / "scripts/prepare_runtime.py", "--work", work], cwd=work)

    run(["make", "-f", HERE / "Makefile", "app", f"WORK={work}", f"PY={python}",
         f"APP={output}", f"GAME={game}", f"KEYS={keys}"], cwd=HERE)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="base game image; may also contain the update Program NCA")
    parser.add_argument("-k", "--keys", type=Path, required=True, help="your prod.keys")
    parser.add_argument("--update", type=Path, help="separate 1.4.1 update NSP/NSZ; defaults to the game image")
    parser.add_argument("--firmware", type=Path, help="firmware NCA directory for NSP builds without cached fonts")
    parser.add_argument("--font-xci", type=Path, help="XCI to use for system fonts when the base image is an NSP")
    parser.add_argument("--shared-fonts", type=Path, help="directory with six verified .bfttf fonts and manifest.json")
    parser.add_argument("--work", type=Path, help="build/cache folder (default: ODYSSEY_build beside the game image)")
    parser.add_argument("-o", "--out", type=Path, help="output app bundle")
    args = parser.parse_args()
    try:
        output = build(args)
    except BuildError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1
    print(f"built app with game icon: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())