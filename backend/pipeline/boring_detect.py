from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Tuple

from .render import FFMPEG  # your absolute ffmpeg.exe path


FREEZE_START_RE = re.compile(r"freeze_start:\s*(\d+(\.\d+)?)")
FREEZE_END_RE = re.compile(r"freeze_end:\s*(\d+(\.\d+)?)")
SHOWINFO_TIME_RE = re.compile(r"pts_time:\s*(\d+(\.\d+)?)")


def _run_ffmpeg_stderr(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # freezedetect/showinfo writes to stderr even on success
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "ffmpeg analysis failed")
    return proc.stderr or ""


def detect_freezes(
    video_path: Path,
    *,
    fps: int = 2,
    noise: float = 0.003,
    min_dur_sec: float = 2.0,
    cache_path: Path | None = None,
) -> List[Tuple[float, float]]:
    """
    Returns list of (start,end) freeze intervals in seconds.
    Uses low-fps sampling for speed.
    """
    if cache_path and cache_path.exists() and cache_path.stat().st_size > 0:
        txt = cache_path.read_text(encoding="utf-8", errors="ignore")
        return _parse_freeze_intervals(txt)

    vf = f"fps={fps},freezedetect=n={noise}:d={min_dur_sec}"
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-nostats",
        "-i",
        str(video_path),
        "-an",
        "-vf",
        vf,
        "-f",
        "null",
        "-",
    ]
    stderr = _run_ffmpeg_stderr(cmd)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(stderr, encoding="utf-8")

    return _parse_freeze_intervals(stderr)


def _parse_freeze_intervals(stderr: str) -> List[Tuple[float, float]]:
    starts: list[float] = []
    ends: list[float] = []

    for line in stderr.splitlines():
        ms = FREEZE_START_RE.search(line)
        if ms:
            starts.append(float(ms.group(1)))
        me = FREEZE_END_RE.search(line)
        if me:
            ends.append(float(me.group(1)))

    intervals: list[tuple[float, float]] = []
    # Pair them in order; if unmatched start exists, ignore it (rare)
    for s, e in zip(starts, ends):
        if e > s:
            intervals.append((s, e))

    return intervals


def detect_scene_changes(
    video_path: Path,
    *,
    fps: int = 2,
    threshold: float = 0.35,
    cache_path: Path | None = None,
) -> List[float]:
    """
    Returns list of timestamps (seconds) where scene score exceeds threshold.
    Uses low-fps sampling for speed.
    """
    if cache_path and cache_path.exists() and cache_path.stat().st_size > 0:
        txt = cache_path.read_text(encoding="utf-8", errors="ignore")
        return _parse_showinfo_times(txt)

    # Use low fps first, then detect scene events
    vf = f"fps={fps},select='gt(scene,{threshold})',showinfo"
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-nostats",
        "-i",
        str(video_path),
        "-an",
        "-vf",
        vf,
        "-f",
        "null",
        "-",
    ]
    stderr = _run_ffmpeg_stderr(cmd)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(stderr, encoding="utf-8")

    return _parse_showinfo_times(stderr)


def _parse_showinfo_times(stderr: str) -> List[float]:
    times: list[float] = []
    for line in stderr.splitlines():
        mt = SHOWINFO_TIME_RE.search(line)
        if mt:
            times.append(float(mt.group(1)))
    times.sort()
    return times


def overlap_seconds(intervals: List[Tuple[float, float]], start: float, end: float) -> float:
    """Total overlap between [start,end] and intervals."""
    total = 0.0
    for a, b in intervals:
        lo = max(start, a)
        hi = min(end, b)
        if hi > lo:
            total += (hi - lo)
    return total


def count_events_in_window(events: List[float], start: float, end: float) -> int:
    """Count timestamps within [start,end]."""
    return sum(1 for t in events if start <= t <= end)
