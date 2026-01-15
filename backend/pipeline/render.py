from __future__ import annotations

import subprocess
from pathlib import Path

FFMPEG = r"C:\Users\hocke\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
FFPROBE = r"C:\Users\hocke\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffprobe.exe"


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\n\nSTDERR:\n"
            + (proc.stderr or "")
        )


def has_audio_stream(in_path: Path) -> bool:
    cmd = [
        FFPROBE, "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=nw=1:nk=1",
        str(in_path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode == 0 and p.stdout.strip() != ""


def render_vertical_short(
    in_path: Path,
    out_path: Path,
    start_sec: float,
    dur_sec: float,
    *,
    gameplay_height: int,
    facecam_height: int,
    face_w_ratio: float,
    face_h_ratio: float,
    fps: int,
    crf: int,
    preset: str,
    sharpen: bool,
    sharpen_preset: str,
    face_x_offset_px: int,
    face_y_offset_px: int,
    game_top_crop_px: int,
    game_bottom_crop_px: int,
    story_hook_enabled: bool,
    hook_sec: float,
    hook_start_offset_sec: float = 0.0,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    input_has_audio = has_audio_stream(in_path)

    hook_sec = float(hook_sec)
    dur_sec = float(dur_sec)

    # Clamp teaser start using hook_start_offset_sec (relative to THIS CLIP, not the full source video)
    max_tease_start = max(0.0, dur_sec - hook_sec)
    tease_start = float(hook_start_offset_sec)
    tease_start = max(0.0, min(tease_start, max_tease_start))

    pre_dur = max(0.0, tease_start)
    post_start = max(0.0, tease_start + hook_sec)
    post_dur = max(0.0, dur_sec - post_start)

    # Only do 3-part splice if it makes sense (otherwise just output whole clip)
    do_hook = bool(story_hook_enabled) and hook_sec > 0.0 and (pre_dur > 0.0 or post_dur > 0.0)

    # -----------------------
    # VIDEO graph -> [v]
    # -----------------------
    filter_complex = (
        "[0:v]split=2[vmain][vfc];"
        f"[vfc]crop=w=iw*{face_w_ratio}:h=ih*{face_h_ratio}:"
        f"x=iw-(iw*{face_w_ratio})-{face_x_offset_px}:"
        f"y=ih-(ih*{face_h_ratio})-{face_y_offset_px},"
        f"scale=1080:{facecam_height}:force_original_aspect_ratio=increase,"
        f"crop=1080:{facecam_height}[face];"
        f"[vmain]crop=w=iw:h=ih-{game_top_crop_px}-{game_bottom_crop_px}:x=0:y={game_top_crop_px},"
        f"scale=1080:{gameplay_height}:force_original_aspect_ratio=increase,"
        f"crop=1080:{gameplay_height}[game];"
        f"[game][face]vstack=inputs=2[stack];"
        f"[stack]fps={fps},setsar=1,format=yuv420p[basev]"
    )

    if do_hook:
        # LOOP HOOK: output = [hook][body], where body ends right before hook starts
        filter_complex += (
            f";[basev]split=2[vhook_src][vbody_src]"
            f";[vhook_src]trim=start={tease_start}:duration={hook_sec},setpts=PTS-STARTPTS[vhook]"
            f";[vbody_src]trim=start=0:duration={tease_start},setpts=PTS-STARTPTS[vbody]"
            f";[vhook][vbody]concat=n=2:v=1:a=0,fps={fps},setpts=N/({fps}*TB)[v]"
        )
    else:
        filter_complex += f";[basev]copy[v]"

    if sharpen:
        if sharpen_preset == "strong":
            unsharp = "unsharp=5:5:1.0:5:5:0.0"
        elif sharpen_preset == "medium":
            unsharp = "unsharp=5:5:0.8:5:5:0.0"
        else:
            unsharp = "unsharp=5:5:0.6:5:5:0.0"
        filter_complex += f";[v]{unsharp}[v]"

    # -----------------------
    # AUDIO graph -> [a] (only if audio exists)
    # -----------------------
    if input_has_audio:
        if do_hook:
            filter_complex += (
                f";[0:a]asplit=2[ahook_src][abody_src]"
                f";[ahook_src]atrim=start={tease_start}:duration={hook_sec},asetpts=PTS-STARTPTS[ahook]"
                f";[abody_src]atrim=start=0:duration={tease_start},asetpts=PTS-STARTPTS[abody]"
                f";[ahook][abody]concat=n=2:v=0:a=1[a0]"
                f";[a0]aresample=async=1:first_pts=0,"
                f"loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.98[a]"
            )
        else:
            filter_complex += (
                f";[0:a]aresample=async=1:first_pts=0,"
                f"loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.98[a]"
            )

    # -----------------------
    # Command (NO -af anywhere)
    # -----------------------
    cmd = [
        FFMPEG,
        "-y",
        "-ss", str(start_sec),
        "-t", str(dur_sec),
        "-i", str(in_path),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]

    if input_has_audio:
        cmd += [
            "-map", "[a]",
            "-c:a", "aac",
            "-b:a", "160k",
            "-ar", "48000",
            "-ac", "2",
        ]

    cmd += ["-shortest", str(out_path)]

    _run(cmd)


def probe_duration_seconds(in_path: Path) -> float:
    cmd = [
        FFPROBE,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(in_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "ffprobe failed")
    return float(proc.stdout.strip())
