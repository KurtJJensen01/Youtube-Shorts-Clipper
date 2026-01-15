import argparse
from pathlib import Path
import yaml

from backend.pipeline.render import render_vertical_short, probe_duration_seconds
from send2trash import send2trash
from backend.pipeline.analyze_audio import extract_wav_mono_16k, wav_rms_per_second, select_highlight_starts
from backend.pipeline.boring_detect import detect_freezes, detect_scene_changes, overlap_seconds, count_events_in_window
from backend.pipeline.captions import transcribe_to_srt, transcribe_segments
from backend.pipeline.burn_subs import burn_in_subtitles
from backend.pipeline.karaoke_ass import write_karaoke_ass
from backend.pipeline.face_motion import compute_facecam_motion_per_second




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
        d = (e - s + 1)
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
        render_vertical_short(
            in_path=video_path,
            out_path=out_path,
            start_sec=s,
            dur_sec=d,
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
            hook_sec=float(sh.get("hook_sec", 2.0)),
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
    video_path = Path(args.input).expanduser().resolve()

    if not video_path.exists():
        raise FileNotFoundError(f"Input file not found: {video_path}")

    process_video(video_path, cfg, delete_original=args.delete)

if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        print("\n[Error] The file path provided is incorrect. Please check the name and try again.")
    except Exception as e:
        print(f"\n[Unexpected Error] {e}")
