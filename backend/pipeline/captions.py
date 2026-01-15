from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from faster_whisper import WhisperModel


_MODEL: Optional[WhisperModel] = None


def _get_model(model_name: str, compute_type: str) -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = WhisperModel(model_name, device="cpu", compute_type=compute_type)
    return _MODEL


def _fmt_srt_time(seconds: float) -> str:
    # HH:MM:SS,mmm
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000.0))
    hh = ms // 3_600_000
    ms %= 3_600_000
    mm = ms // 60_000
    ms %= 60_000
    ss = ms // 1000
    ms %= 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _wrap_words(text: str, max_words: int = 7, max_chars: int = 42) -> list[str]:
    words = text.split()
    lines = []
    cur = []
    for w in words:
        test = (" ".join(cur + [w])).strip()
        if (len(cur) >= max_words) or (len(test) > max_chars):
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def write_srt(segments, srt_path: Path, max_words: int = 7, max_chars: int = 42) -> None:
    lines = []
    idx = 1
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue

        wrapped = _wrap_words(text, max_words=max_words, max_chars=max_chars)
        if not wrapped:
            continue

        start = _fmt_srt_time(float(seg.start))
        end = _fmt_srt_time(float(seg.end))

        # Put at most 2 lines on screen
        caption_text = "\n".join(wrapped[:2])

        lines.append(f"{idx}\n{start} --> {end}\n{caption_text}\n")
        idx += 1

    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(lines).strip() + ("\n" if lines else ""), encoding="utf-8")


def transcribe_to_srt(
    audio_wav_path: Path,
    srt_path: Path,
    *,
    model_name: str = "small",
    compute_type: str = "int8",
) -> None:
    model = _get_model(model_name, compute_type)
    segments, _info = model.transcribe(
        str(audio_wav_path),
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 200, "speech_pad_ms": 200},
        word_timestamps=True,
        language="en",
    )
    write_srt(segments, srt_path)

def transcribe_segments(
    audio_wav_path: Path,
    *,
    model_name: str = "small",
    compute_type: str = "int8",
):
    model = _get_model(model_name, compute_type)
    segments, info = model.transcribe(
        str(audio_wav_path),
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 200, "speech_pad_ms": 200},
        word_timestamps=True,
        language="en",
    )
    return list(segments), info

