from __future__ import annotations

import subprocess
from pathlib import Path

from .render import FFMPEG


def _ff_sub_path(p: Path) -> str:
    # ffmpeg subtitles filter treats ':' as separator; escape drive colon
    # Use forward slashes for safety
    s = p.resolve().as_posix()
    return s.replace(":", r"\:")


def burn_in_subtitles(
    in_mp4: Path,
    srt_path: Path,
    out_mp4: Path,
    *,
    crf: int,
    preset: str,
    style: str,
) -> None:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    sub = _ff_sub_path(srt_path)
    ext = srt_path.suffix.lower()
    if ext == ".ass":
        vf = f"subtitles='{sub}'"
    else:
        vf = f"subtitles='{sub}':force_style='{style}'"


    cmd = [
        FFMPEG,
        "-y",
        "-i", str(in_mp4),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-c:a", "copy",
        str(out_mp4),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "subtitle burn-in failed")
