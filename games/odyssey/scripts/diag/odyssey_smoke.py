#!/usr/bin/env python3
"""Run an isolated Odyssey GUI smoke/performance test from a copied profile."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


FRAME_RE = re.compile(r"帧时间 p50 ([\d.]+) / p95 ([\d.]+) / 最大 ([\d.]+) ms（(\d+) 帧）")
AUDIO_RE = re.compile(r"underruns (\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="ODYSSEY_build work directory")
    parser.add_argument("--profile", type=Path, required=True, help="source profile; it is copied before launch")
    parser.add_argument("--seconds", type=int, default=180, help="test duration (default: 180)")
    parser.add_argument("--frame-p95-ms", type=float, default=16.67, help="maximum passing p95 frame time")
    parser.add_argument("--output", type=Path, help="result directory (default: WORK/logs/auto-smoke-TIMESTAMP)")
    parser.add_argument("--input-script", default="10:38:1000,24:38:1000,38:38:1000,52:38:1000",
                        help="runtime key script in sec:keycode:ms entries")
    args = parser.parse_args()
    if args.seconds < 30:
        parser.error("--seconds must be at least 30")
    if args.frame_p95_ms <= 0:
        parser.error("--frame-p95-ms must be positive")
    return args


def append_command(path: Path, command: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(command + "\n")
        stream.flush()


def main() -> int:
    args = parse_args()
    work = args.work.resolve()
    source_profile = args.profile.resolve()
    runtime = work / "build/odyssey-native"
    if sys.platform != "darwin":
        raise SystemExit("Odyssey GUI smoke tests require macOS")
    if not runtime.is_file() or not os.access(runtime, os.X_OK):
        raise SystemExit(f"runtime is not executable: {runtime}")
    if not source_profile.is_dir():
        raise SystemExit(f"source profile does not exist: {source_profile}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = (args.output or work / "logs" / f"auto-smoke-{stamp}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    profile_copy = output / "profile-copy"
    shutil.copytree(source_profile, profile_copy, symlinks=True)
    slot = output / "game-slot"
    slot.mkdir()
    proof_dir = output / "romfs-proof"
    proof_dir.mkdir()
    anomaly_dir = output / "anomaly"
    anomaly_dir.mkdir()
    input_file = output / "input.txt"
    input_file.touch()
    log_path = output / "odyssey.log"
    startup_screenshot = output / "startup.png"
    screenshot = output / "gameplay.png"
    final_screenshot = output / "final.png"

    env = os.environ.copy()
    env.update({
        "TOTK_PROFILE_DIR": str(profile_copy),
        "TOTK_GAME_SLOT_DIR": str(slot),
        "TOTK_INPUT_FILE": str(input_file),
        "TOTK_ROMFS_PROOF_DIR": str(proof_dir),
        "TOTK_ANOMALY": str(anomaly_dir),
        "TOTK_GPU_ALLOW_SUBMIT": "1",
        "DM_PRESENT_LINK_FALLBACK": "1",
        "TOTK_ASSUME_FOCUS": "1",
        "TOTK_INPUT_LOG": "1",
        "TOTK_SLOT_OWNER": "automation",
        "TOTK_SLOT_PURPOSE": "smoke-test",
        "TOTK_INPUT_SCRIPT": args.input_script,
    })
    env.pop("TOTK_HEADLESS", None)

    frame_samples: list[dict[str, float | int]] = []
    underruns: list[int] = []
    fatal_lines: list[str] = []
    reached_gameplay = False
    gameplay_started_at: float | None = None
    probed = False
    startup_shot_sent = False
    final_shot_sent = False
    probe_release_at = 0.0
    launch_time = time.monotonic()
    log_offset = 0
    status: int | None = None

    with log_path.open("w", encoding="utf-8") as log_stream:
        process = subprocess.Popen(
            [str(runtime), "rewritten/v141", "boot"],
            cwd=work,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=log_stream,
        )
        try:
            while time.monotonic() - launch_time < args.seconds:
                time.sleep(1)
                log_stream.flush()
                try:
                    with log_path.open("r", encoding="utf-8", errors="replace") as reader:
                        reader.seek(log_offset)
                        lines = reader.readlines()
                        log_offset = reader.tell()
                except OSError:
                    lines = []
                for line in lines:
                    if "[movie] configured " in line and " AVC" in line:
                        reached_gameplay = True
                        if gameplay_started_at is None:
                            gameplay_started_at = time.monotonic() - launch_time
                    match = FRAME_RE.search(line)
                    if match and probed:
                        p50, p95, maximum, frames = match.groups()
                        frame_samples.append({"p50_ms": float(p50), "p95_ms": float(p95),
                                              "max_ms": float(maximum), "frames": int(frames)})
                    match = AUDIO_RE.search(line)
                    if match:
                        underruns.append(int(match.group(1)))
                    if re.search(r"\bFAIL:|runtime failed|\bfatal\b|Traceback", line, re.IGNORECASE):
                        fatal_lines.append(line.rstrip())

                elapsed = time.monotonic() - launch_time
                if not startup_shot_sent and elapsed >= 20:
                    append_command(input_file, f"wshot {startup_screenshot}")
                    startup_shot_sent = True
                if not final_shot_sent and elapsed >= args.seconds - 5:
                    append_command(input_file, f"wshot {final_screenshot}")
                    final_shot_sent = True
                if reached_gameplay and not probed and gameplay_started_at is not None and elapsed >= gameplay_started_at + 25:
                    append_command(input_file, f"shot {screenshot}")
                    append_command(input_file, "down 2")
                    probe_release_at = elapsed + 1.0
                    probed = True
                if probed and probe_release_at and elapsed >= probe_release_at:
                    append_command(input_file, "up 2")
                    append_command(input_file, "anomdump")
                    probe_release_at = 0.0
                status = process.poll()
                if status is not None:
                    break
        finally:
            if process.poll() is None:
                append_command(input_file, "close")
                try:
                    status = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        status = process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        status = process.wait()
            log_stream.flush()

    passed = (
        status == 0
        and reached_gameplay
        and probed
        and screenshot.is_file()
        and len(frame_samples) >= 3
        and max((sample["p95_ms"] for sample in frame_samples), default=float("inf")) <= args.frame_p95_ms
        and max(underruns, default=0) == 0
        and not fatal_lines
    )
    report = {
        "passed": passed,
        "exit_code": status,
        "source_profile": str(source_profile),
        "profile_was_copied": True,
        "reached_gameplay_video": reached_gameplay,
        "movement_probe_sent": probed,
        "startup_screenshot_exists": startup_screenshot.is_file(),
        "screenshot_exists": screenshot.is_file(),
        "final_screenshot_exists": final_screenshot.is_file(),
        "frame_p95_limit_ms": args.frame_p95_ms,
        "frame_samples": frame_samples,
        "audio_underruns_max": max(underruns, default=None),
        "fatal_lines": fatal_lines,
        "log": str(log_path),
        "output": str(output),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())