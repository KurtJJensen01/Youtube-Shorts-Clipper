from __future__ import annotations

import subprocess
from pathlib import Path
import numpy as np
import wave

from .render import FFMPEG  # uses your absolute FFMPEG path


def extract_wav_mono_16k(video_path: Path, wav_path: Path) -> None:
    """Extract mono 16kHz WAV once. Skips if already exists."""
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    if wav_path.exists() and wav_path.stat().st_size > 0:
        return

    cmd = [
        FFMPEG,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(wav_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "ffmpeg audio extract failed")


def wav_rms_per_second(wav_path: Path, sample_rate: int = 16000) -> np.ndarray:
    """Return RMS per second."""
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sr = wf.getframerate()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()

        if n_channels != 1 or sr != sample_rate or sampwidth != 2:
            raise RuntimeError("Unexpected WAV format. Expected mono 16kHz 16-bit PCM.")

        raw = wf.readframes(n_frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    samples_per_sec = sample_rate
    total_secs = int(np.ceil(len(audio) / samples_per_sec))
    rms = np.zeros(total_secs, dtype=np.float32)

    for t in range(total_secs):
        start = t * samples_per_sec
        end = min((t + 1) * samples_per_sec, len(audio))
        chunk = audio[start:end]
        rms[t] = float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0

    return rms


def _smooth(x: np.ndarray, k: int = 5) -> np.ndarray:
    if len(x) < k:
        return x.copy()
    kernel = np.ones(k, dtype=np.float32) / float(k)
    return np.convolve(x, kernel, mode="same")


def candidate_peaks_by_energy(rms: np.ndarray) -> list[int]:
    """Return candidate seconds ordered by 'energy' (descending) using smoothed RMS."""
    smooth = _smooth(rms, k=5)
    return [int(i) for i in np.argsort(smooth)[::-1]]


def rms_threshold(rms: np.ndarray, percentile: float) -> float:
    """Adaptive threshold for 'quiet' vs 'active'."""
    if len(rms) == 0:
        return 0.0
    # Guard against pathological cases
    p = float(np.clip(percentile, 0.0, 100.0))
    return float(np.percentile(rms, p))

def _normalize01(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return x
    lo = float(np.percentile(x, 10))
    hi = float(np.percentile(x, 99))
    if hi <= lo:
        return np.zeros_like(x, dtype=np.float32)
    y = (x - lo) / (hi - lo)
    return np.clip(y, 0.0, 1.0).astype(np.float32)


def candidate_peaks_by_audio_and_motion(rms: np.ndarray, motion: np.ndarray, motion_weight: float) -> list[int]:
    # Smooth audio (you already do similar)
    audio = _smooth(rms, k=5).astype(np.float32)
    motion = motion.astype(np.float32)

    # Align lengths
    n = max(len(audio), len(motion))
    if len(audio) < n:
        audio = np.pad(audio, (0, n - len(audio)), mode="edge")
    if len(motion) < n:
        motion = np.pad(motion, (0, n - len(motion)), mode="edge")

    a = _normalize01(audio)
    m = _normalize01(motion)

    score = a + float(motion_weight) * m
    return [int(i) for i in np.argsort(score)[::-1]]


def refine_clip_window(
    rms: np.ndarray,
    peak_sec: int,
    *,
    pre_search_sec: int,
    min_leadin_sec: int,
    min_dur_sec: int,
    max_dur_sec: int,
    thr: float,
    end_silence_run_sec: int,
) -> tuple[int, int] | None:
    """
    Find better [start,end] around a peak.
    - Start: earliest 'active ramp' in [peak-pre_search, peak-min_leadin]
    - End: after min duration, stop when we see end_silence_run consecutive quiet seconds, or cap at max_dur
    """
    n = len(rms)
    if n == 0:
        return None

    peak = int(np.clip(peak_sec, 0, n - 1))

    start_lo = max(0, peak - int(pre_search_sec))
    start_hi = max(0, peak - int(min_leadin_sec))

    if start_hi <= start_lo:
        return None

    # Start selection: find the earliest second in [start_lo, start_hi] that looks like a ramp into activity.
    # Criteria: rms[t] >= thr AND (rms[t] >= rms[t-1]) AND (rms[t+1] >= thr)
    start = None
    for t in range(start_lo, start_hi):
        prev_ok = (t == 0) or (rms[t] >= rms[t - 1])
        next_ok = (t + 1 < n) and (rms[t + 1] >= thr)
        if rms[t] >= thr and prev_ok and next_ok:
            start = t
            break

    # Fallback: if we don't find a ramp, start a bit before peak
    if start is None:
        start = max(0, peak - 8)

    # End selection
    min_end = start + int(min_dur_sec)
    hard_end = min(n - 1, start + int(max_dur_sec))

    if min_end >= n:
        return None

    # After min duration, stop when we see consecutive quiet seconds
    quiet_run = 0
    end = hard_end
    for t in range(min_end, hard_end + 1):
        if rms[t] < thr:
            quiet_run += 1
            if quiet_run >= int(end_silence_run_sec):
                end = t - int(end_silence_run_sec) + 1  # end at the start of quiet run
                break
        else:
            quiet_run = 0

    if end <= start:
        return None

    return start, end


def silence_fraction(rms: np.ndarray, start: int, end: int, thr: float) -> float:
    """Fraction of seconds in [start,end] below threshold."""
    seg = rms[start : end + 1]
    if len(seg) == 0:
        return 1.0
    return float(np.mean(seg < thr))


def select_highlight_starts(
    rms: np.ndarray,
    *,
    desired_count: int,
    min_gap_sec: int,
    min_dur_sec: int,
    max_dur_sec: int,
    pre_search_sec: int,
    min_leadin_sec: int,
    silence_percentile: float,
    max_silence_frac: float,
    end_silence_run_sec: int,
    motion: np.ndarray | None = None,
    motion_weight: float = 0.0,
) -> list[tuple[int, int]]:
    """
    Returns list of (start_sec, end_sec) windows for best clips.
    Enforces min-gap between selected peaks.
    """
    thr = rms_threshold(rms, silence_percentile)
    if motion is not None and motion_weight > 0:
        candidates = candidate_peaks_by_audio_and_motion(rms, motion, motion_weight)
    else:
        candidates = candidate_peaks_by_energy(rms)

    chosen: list[tuple[int, int]] = []
    chosen_centers: list[int] = []

    for peak in candidates:
        if len(chosen) >= desired_count:
            break

        # enforce diversity / spacing around peaks
        if any(abs(peak - c) < int(min_gap_sec) for c in chosen_centers):
            continue

        win = refine_clip_window(
            rms,
            peak_sec=peak,
            pre_search_sec=int(pre_search_sec),
            min_leadin_sec=int(min_leadin_sec),
            min_dur_sec=int(min_dur_sec),
            max_dur_sec=int(max_dur_sec),
            thr=thr,
            end_silence_run_sec=int(end_silence_run_sec),
        )
        if win is None:
            continue

        s, e = win
        frac = silence_fraction(rms, s, e, thr)
        if frac > float(max_silence_frac):
            continue

        chosen.append((s, e))
        chosen_centers.append(peak)

    chosen.sort(key=lambda x: x[0])
    return chosen
