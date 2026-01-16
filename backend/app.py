import argparse
from pathlib import Path
import yaml
import math

from backend.pipeline.render import render_vertical_short, probe_duration_seconds
from send2trash import send2trash
from backend.pipeline.analyze_audio import extract_wav_mono_16k, wav_rms_per_second, select_highlight_starts
from backend.pipeline.boring_detect import detect_freezes, detect_scene_changes, overlap_seconds, count_events_in_window
from backend.pipeline.captions import transcribe_to_srt, transcribe_segments
from backend.pipeline.burn_subs import burn_in_subtitles
from backend.pipeline.karaoke_ass import write_karaoke_ass
from backend.pipeline.face_motion import compute_facecam_motion_per_second
from typing import Optional

def _normalize(arr: list[float]) -> list[float]:
    if not arr:
        return arr
    mn = min(arr)
    mx = max(arr)
    if mx - mn < 1e-9:
        return [0.0 for _ in arr]
    return [(x - mn) / (mx - mn) for x in arr]


def _scene_counts_per_second(scene_events: list[float], start_sec: float, dur_sec: float) -> list[float]:
    # counts events per second inside [start_sec, start_sec+dur_sec)
    n = max(1, int(math.ceil(dur_sec)))
    out = [0.0] * n
    end = start_sec + dur_sec
    for t in scene_events:
        if start_sec <= t < end:
            idx = int(t - start_sec)
            if 0 <= idx < n:
                out[idx] += 1.0
    return out


def choose_hook_offset_sec(
    *,
    clip_start_sec: float,
    clip_dur_sec: float,
    hook_sec: float,
    rms_per_sec: list[float],
    motion_per_sec: Optional[list[float]],
    scene_events: Optional[list[float]],
    sh_cfg: dict,
) -> float:
    """
    Returns hook start offset (seconds) RELATIVE to the clip start (0..clip_dur-hook_sec).
    Uses global per-second arrays and clamps safely.
    """
    hook_sec = float(hook_sec)
    if hook_sec <= 0:
        return 0.0

    max_offset = max(0.0, float(clip_dur_sec) - hook_sec)
    if max_offset <= 0.0001:
        return 0.0

    # Convert global arrays to clip-local per-second slices
    g0 = int(math.floor(clip_start_sec))
    g1 = int(math.ceil(clip_start_sec + clip_dur_sec))
    g0 = max(0, g0)
    g1 = min(len(rms_per_sec), g1)

    # Slice audio and force to plain list (handles numpy arrays)
    audio_slice = rms_per_sec[g0:g1]
    audio_slice = audio_slice.tolist() if hasattr(audio_slice, "tolist") else list(audio_slice)

    if len(audio_slice) == 0:
        return max(0.0, min(max_offset, float(clip_dur_sec) - hook_sec))

    # Clip-local length in seconds (aligned to slice)
    n = len(audio_slice)

    # Optional signals (force to plain lists)
    motion_slice: list[float] = []
    if motion_per_sec is not None and len(motion_per_sec) >= g1:
        ms = motion_per_sec[g0:g1]
        motion_slice = ms.tolist() if hasattr(ms, "tolist") else list(ms)

    scene_slice: list[float] = []
    if scene_events is not None:
        scene_slice = _scene_counts_per_second(scene_events, start_sec=float(g0), dur_sec=float(n))

    # Build score
    strategy = str(sh_cfg.get("strategy", "combined")).lower()
    if strategy == "loudest":
        score = _normalize(audio_slice)
    elif strategy == "motion" and len(motion_slice) > 0:
        score = _normalize(motion_slice)
    else:
        aw = float(sh_cfg.get("audio_weight", 1.0))
        mw = float(sh_cfg.get("motion_weight", 0.0))
        sw = float(sh_cfg.get("scene_weight", 0.0))

        aN = _normalize(audio_slice)
        mN = _normalize(motion_slice) if len(motion_slice) > 0 else [0.0] * n
        sN = _normalize(scene_slice) if len(scene_slice) > 0 else [0.0] * n

        score = [(aw * aN[i] + mw * mN[i] + sw * sN[i]) for i in range(n)]

    # Sliding window selection
    win = max(1, int(round(hook_sec)))  # per-second windows
    if n <= win:
        return 0.0

    tail = float(sh_cfg.get("search_tail_sec", 20))
    tail_len = min(n, max(win + 1, int(round(tail))))
    start_k = max(0, n - tail_len)
    end_k = n - win

    # Choose best window by average score, but avoid silent hooks
    min_rms = float(sh_cfg.get("min_rms", 0.0))

    best_k = start_k
    best_val = -1e9

    # First pass: require min RMS
    for k in range(start_k, end_k + 1):
        avg_score = sum(score[k:k + win]) / win
        avg_rms = sum(audio_slice[k:k + win]) / win
        if avg_rms < min_rms:
            continue
        if avg_score > best_val:
            best_val = avg_score
            best_k = k

    # Fallback pass: allow anything if all were silent
    if best_val < -1e8:
        best_k = start_k
        best_val = -1e9
        for k in range(start_k, end_k + 1):
            avg_score = sum(score[k:k + win]) / win
            if avg_score > best_val:
                best_val = avg_score
                best_k = k

    # Convert best_k (slice index) to offset relative to actual clip start
    best_global_start = float(g0 + best_k)
    offset = best_global_start - float(clip_start_sec)
    offset = max(0.0, min(max_offset, offset))
    return offset


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "default.yaml"

def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _generate_clip_starts(duration: float, count: int, start_offset: float, spacing: float, clip_dur: float) -> list[float]:
    starts = []
    t = start_offset
    for _ in range(count):
        if t + clip_dur >= duration:
            break
        starts.append(t)
        t += spacing
    return starts

def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(float(x) for x in values)
    if p <= 0:
        return xs[0]
    if p >= 100:
        return xs[-1]
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if c == f:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def silence_fraction_adaptive(
    start_sec: float,
    end_sec: float,
    rms_per_sec: list[float],
    silence_percentile: float,
) -> float:
    import math
    if end_sec <= start_sec:
        return 1.0
    g0 = max(0, int(math.floor(start_sec)))
    g1 = min(len(rms_per_sec), int(math.ceil(end_sec)))
    if g1 <= g0:
        return 1.0

    xs = rms_per_sec[g0:g1]
    xs = xs.tolist() if hasattr(xs, "tolist") else list(xs)

    thr = _percentile(xs, float(silence_percentile))
    silent = sum(1 for v in xs if float(v) <= thr)
    return silent / max(1, len(xs))


def choose_loop_duration_sec(
    *,
    window_start: float,
    climax_t: float,
    hook_sec: float,
    min_dur_sec: float,
    max_dur_sec: float,
    rms_per_sec: list[float],
    silence_percentile: float,
    max_silence_frac: float,
) -> float:
    import math

    hook_sec = float(hook_sec)
    min_d = float(min_dur_sec)
    max_d = float(max_dur_sec)

    feasible_max = min(max_d, hook_sec + max(0.0, float(climax_t) - float(window_start)))
    feasible_max = max(hook_sec, feasible_max)

    d = float(math.floor(feasible_max))
    if d < min_d:
        return max(min_d, feasible_max)

    while d >= min_d:
        body_len = max(0.0, d - hook_sec)
        body_start = float(climax_t) - body_len
        frac = silence_fraction_adaptive(body_start, float(climax_t), rms_per_sec, silence_percentile)
        if frac <= float(max_silence_frac):
            return float(d)
        d -= 1.0

    return float(min_d)


def process_video(video_path: Path, cfg: dict, delete_original: bool) -> None:
    out_dir = Path(cfg["output"]["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nProcessing: {video_path}")
    duration = probe_duration_seconds(video_path)
    print(f"Duration: {duration:.1f}s")

    clips_cfg = cfg["clips"]
    temp_dir = Path(cfg["output"]["temp_dir"])
    temp_dir.mkdir(parents=True, exist_ok=True)

    # define these EARLY (fixes your crash)
    layout = cfg["layout"]
    face = cfg["facecam_crop"]

    wav_path = temp_dir / f"{video_path.stem}_audio.wav"
    extract_wav_mono_16k(video_path, wav_path)
    rms = wav_rms_per_second(wav_path)

    # face motion (now face exists)
    fm = cfg.get("face_motion", {})
    motion = None
    motion_weight = 0.0
    if fm.get("enabled", False):
        motion = compute_facecam_motion_per_second(
            video_path,
            w_ratio=float(face["w_ratio"]),
            h_ratio=float(face["h_ratio"]),
            sample_fps=int(fm.get("sample_fps", 3)),
            smooth_sec=int(fm.get("smooth_sec", 5)),
        )
        motion_weight = float(fm.get("weight", 0.8))

    wins = select_highlight_starts(
        rms,
        desired_count=int(clips_cfg["count"]),
        min_gap_sec=int(clips_cfg["min_gap_sec"]),
        min_dur_sec=int(clips_cfg["min_dur_sec"]),
        max_dur_sec=int(clips_cfg["max_dur_sec"]),
        pre_search_sec=int(clips_cfg["pre_search_sec"]),
        min_leadin_sec=int(clips_cfg["min_leadin_sec"]),
        silence_percentile=float(clips_cfg["silence_percentile"]),
        max_silence_frac=float(clips_cfg["max_silence_frac"]),
        end_silence_run_sec=int(clips_cfg["end_silence_run_sec"]),
        motion=motion,
        motion_weight=motion_weight,
    )

    # build starts/durs from wins FIRST
    starts, durs = [], []
    for s, e in wins:
        if s < 0:
            continue
        d = (e - s)
        if s + d < duration:
            starts.append(float(s))
            durs.append(float(d))

    # apply boring filter AFTER starts/durs exist
    bf = cfg.get("boring_filter", {})
    gsc = cfg.get("gameplay_source_crop") or {}
    if starts and (bf.get("detect_freeze", True) or bf.get("detect_scene", True)):
        filtered_starts, filtered_durs = [], []

        cache_dir = temp_dir / "analysis_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        freeze_intervals = []
        scene_events = []

        if bf.get("detect_freeze", True):
            freeze_cache = cache_dir / f"{video_path.stem}_freezedetect.log"
            freeze_intervals = detect_freezes(
                video_path,
                fps=int(bf.get("freeze_fps", 2)),
                noise=float(bf.get("freeze_noise", 0.003)),
                min_dur_sec=float(bf.get("freeze_min_dur_sec", 2.0)),
                cache_path=freeze_cache,
            )

        if bf.get("detect_scene", True):
            scene_cache = cache_dir / f"{video_path.stem}_scene.log"
            scene_events = detect_scene_changes(
                video_path,
                fps=int(bf.get("scene_fps", 2)),
                threshold=float(bf.get("scene_threshold", 0.35)),
                cache_path=scene_cache,
            )

        max_freeze = float(bf.get("max_freeze_overlap_sec", 4.0))
        min_scene = int(bf.get("min_scene_changes", 1))

        for s, d in zip(starts, durs):
            e = s + d
            if freeze_intervals and overlap_seconds(freeze_intervals, s, e) > max_freeze:
                continue
            if scene_events and count_events_in_window(scene_events, s, e) < min_scene:
                continue
            filtered_starts.append(s)
            filtered_durs.append(d)

        starts, durs = filtered_starts, filtered_durs

    if not starts:
        print("No clips generated. Video too short or settings too aggressive.")
        return

    out_base = out_dir / video_path.stem
    out_base.mkdir(parents=True, exist_ok=True)
    sh = cfg.get("story_hook") or {}

    for i, (s, d) in enumerate(zip(starts, durs), start=1):
        out_path = out_base / f"short_{i:02d}.mp4"
        print(f"  Clip {i:02d}: start={s:.1f}s dur={d:.0f}s")
        hook_sec = float(sh.get("hook_sec", 2.0))
        hook_offset = 0.0
        if bool(sh.get("enabled", False)):
            hook_offset = choose_hook_offset_sec(
                clip_start_sec=float(s),
                clip_dur_sec=float(d),
                hook_sec=hook_sec,
                rms_per_sec=rms,
                motion_per_sec=motion,
                scene_events=scene_events,
                sh_cfg=sh,
            )

        climax_t = float(s) + float(hook_offset)

        # Choose final duration using silence constraint
        final_d = choose_loop_duration_sec(
            window_start=float(s),
            climax_t=climax_t,
            hook_sec=hook_sec,
            min_dur_sec=float(clips_cfg["min_dur_sec"]),
            max_dur_sec=float(clips_cfg["max_dur_sec"]),
            rms_per_sec=rms,
            silence_percentile=float(clips_cfg["silence_percentile"]),
            max_silence_frac=float(clips_cfg["max_silence_frac"]),
        )

        # Compute final start so the hook lands at the END of the extracted clip
        # tease_start within clip = final_d - hook_sec
        final_start = climax_t - (final_d - hook_sec)
        final_start = max(0.0, float(final_start))
        hook_start_offset_sec = final_d - hook_sec

        render_vertical_short(
            in_path=video_path,
            out_path=out_path,
            start_sec=float(final_start),
            dur_sec=float(final_d),
            gameplay_height=int(layout["gameplay_height"]),
            facecam_height=int(layout["facecam_height"]),
            face_w_ratio=float(face["w_ratio"]),
            face_h_ratio=float(face["h_ratio"]),
            fps=int(cfg["output"]["fps"]),
            crf=int(cfg["output"]["crf"]),
            preset=str(cfg["output"]["preset"]),
            sharpen=bool(cfg["output"].get("sharpen", False)),
            sharpen_preset=str(cfg["output"].get("sharpen_preset", "mild")),
            face_x_offset_px=int(face.get("x_offset_px", 0)),
            face_y_offset_px=int(face.get("y_offset_px", 0)),
            game_top_crop_px=int(gsc.get("top_px", 0)),
            game_bottom_crop_px=int(gsc.get("bottom_px", 0)),
            story_hook_enabled=bool(sh.get("enabled", False)),
            hook_sec=hook_sec,
            hook_start_offset_sec=float(hook_start_offset_sec),
        )


    if delete_original:
        print(f"Moving original to Recycle Bin: {video_path}")
        send2trash(str(video_path))

    print("Done.\n")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True, help="Path to video file (mp4/mov/mkv)")
    parser.add_argument("--delete", action="store_true", help="Move original to Recycle Bin after export")
    args = parser.parse_args()
    
    cfg = _load_config()
    
    # Clean up input path
    input_path = args.input.strip().strip('"').strip("'")
    video_path = Path(input_path).expanduser().resolve()
    
    # Check if file exists
    if not video_path.exists():
        print(f"\n[Error] Cannot find the video file.")
        print(f"Looking for: {video_path}")
        
        if video_path.parent.exists():
            print(f"\nFiles in {video_path.parent.name}:")
            for f in sorted(video_path.parent.iterdir()):
                if f.is_file():
                    print(f"  - {f.name}")
        
        raise FileNotFoundError(f"Input file not found: {video_path}")
    
    # Check if it's a supported video format
    supported_extensions = {'.mp4', '.mov', '.mkv', '.avi', '.MP4', '.MOV', '.MKV', '.AVI'}
    if video_path.suffix not in supported_extensions:
        print(f"\n[Warning] '{video_path.suffix}' may not be a supported video format.")
        print(f"Supported formats: {', '.join(sorted(supported_extensions))}")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return

    process_video(video_path, cfg, delete_original=args.delete)

if __name__ == "__main__":
    #try:
    main()
    #except FileNotFoundError:
        #print("\n[Error] The file path provided is incorrect. Please check the name and try again.")
    #except Exception as e:
        #print(f"\n[Unexpected Error] {e}")