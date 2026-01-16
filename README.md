Here’s a ready-to-paste **README.md** with clean “new PC” setup instructions (Windows-first), including FFmpeg + venv + config + run commands.

````md
# yt-shorts-maker

Turns long gameplay recordings into vertical Shorts:
- Crops gameplay + facecam into a 1080x1920 stacked layout
- Picks highlight moments (audio-driven, optional motion/scene signals)
- Optionally moves a “climax”/hook segment to the start for looping-style Shorts
- Exports `.mp4` clips to `clips_out/<video_name>/`

---

## Requirements

### 1) Python
- **Python 3.11+** recommended  
  Check:
  ```bash
  python --version
````

### 2) FFmpeg (required)

This project needs `ffmpeg` + `ffprobe`.

#### Windows (recommended: winget)

```powershell
winget install Gyan.FFmpeg
```

Close and reopen your terminal, then verify:

```powershell
ffmpeg -version
ffprobe -version
```

#### If FFmpeg is NOT on PATH

You can still run by setting environment variables to your exe paths:

**PowerShell (temporary for this terminal):**

```powershell
$env:FFMPEG="C:\path\to\ffmpeg.exe"
$env:FFPROBE="C:\path\to\ffprobe.exe"
```

---

## Install (Fresh PC Setup)

From the repo root:

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Configure

Main config:

* `backend/config/default.yaml`

Common settings:

* `output.width` / `output.height` (default 1080x1920)
* `layout.gameplay_height` + `layout.facecam_height` should add up to `output.height`
* `facecam_crop` controls the facecam area
* `gameplay_source_crop.top_px/bottom_px` trims unwanted bars from the original gameplay capture
* `clips.*` controls min/max clip length + silence trimming
* `story_hook.*` controls the loop/hook behavior

**Note:** YAML should only define `story_hook` once. If you have duplicates, remove one.

---

## Run

### Basic usage

```powershell
python -m backend.app --input "C:\Users\YOU\Downloads\YourVideo.mp4"
```

### Delete original after export (moves to Recycle Bin)

```powershell
python -m backend.app --input "C:\Users\YOU\Downloads\YourVideo.mp4" --delete
```

Outputs go to:

```
clips_out/<VideoName>/short_01.mp4
clips_out/<VideoName>/short_02.mp4
...
```

Temporary files go to:

```
temp/
```

---

## Troubleshooting

### “ffmpeg not found” / “ffprobe not found”

* Make sure FFmpeg is installed and on PATH:

  ```powershell
  ffmpeg -version
  ffprobe -version
  ```
* Or set env vars:

  ```powershell
  $env:FFMPEG="C:\path\to\ffmpeg.exe"
  $env:FFPROBE="C:\path\to\ffprobe.exe"
  ```

### “Unplayable mp4” / broken output

* Ensure you are **not using `-af`** together with a complex audio filtergraph.
* This repo uses `-filter_complex` for audio when needed.
* Verify output:

  ```powershell
  ffprobe -v error -show_entries format=duration,size -show_streams "clips_out\...\short_01.mp4"
  ```

### Black bars

* If bars are from the source capture, use:

  ```yaml
  gameplay_source_crop:
    top_px: 0
    bottom_px: 100
  ```

  Adjust until bars are gone.

### Clips always hitting max duration

* Your `clips` config controls this:

  * `max_dur_sec` caps clip length
  * `end_silence_run_sec` trims after consecutive quiet seconds
  * `max_silence_frac` rejects clips that are too quiet overall
  * `silence_percentile` controls what counts as “quiet”