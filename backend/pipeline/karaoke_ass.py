from __future__ import annotations
from pathlib import Path

def _ass_time(t: float) -> str:
    # h:mm:ss.cc
    if t < 0: t = 0.0
    h = int(t // 3600)
    t -= h * 3600
    m = int(t // 60)
    s = t - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"

def write_karaoke_ass(segments, ass_path: Path, *, font: str = "Arial", font_size: int = 44) -> None:
    # ASS uses script resolution; for vertical 1080x1920, use PlayResY=1920
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # PrimaryColour = normal text (white)
    # SecondaryColour = highlighted portion (yellow-ish)
    # Alignment=2 (bottom-center)

    lines = [header]

    for seg in segments:
        # faster-whisper word timestamps: seg.words may exist when word_timestamps=True
        words = getattr(seg, "words", None)
        if not words:
            continue

        start = float(seg.start)
        end = float(seg.end)
        if end <= start:
            continue

        # Build karaoke text: {\k<centiseconds>}word
        k_parts = []
        for w in words:
            w_text = (w.word or "").strip()
            if not w_text:
                continue
            w_start = float(w.start)
            w_end = float(w.end)
            dur_cs = max(1, int(round((w_end - w_start) * 100)))  # centiseconds
            k_parts.append(f"{{\\k{dur_cs}}}{w_text}")

        if not k_parts:
            continue

        text = " ".join(k_parts)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}\n"
        )

    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text("".join(lines), encoding="utf-8")
