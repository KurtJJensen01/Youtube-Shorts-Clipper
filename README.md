# YouTube Shorts Clipper

Automatically turns your long gaming videos into vertical YouTube Shorts! This tool finds the most exciting moments in your gameplay, crops and stacks your gameplay and facecam, and exports ready-to-upload Short clips.

-----

## What You’ll Need

- A Windows PC or Mac
- About 10-15 minutes for setup
- Your gameplay video file (mp4, mov, or mkv)

-----

## Installation Guide

Choose your operating system below and follow the steps carefully.

### 🪟 **Windows Installation**

#### Step 1: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
1. Click the yellow “Download Python” button
1. Run the installer
1. **⚠️ IMPORTANT:** Check the box that says **“Add Python to PATH”** at the bottom of the installer
1. Click “Install Now”
1. Wait for installation to complete, then click “Close”

**Verify it worked:**

- Press `Windows Key + R`
- Type `cmd` and press Enter
- Type `python --version` and press Enter
- You should see something like “Python 3.11.x”

#### Step 2: Install FFmpeg

1. Press `Windows Key + R`
1. Type `powershell` and press Enter
1. Copy and paste this command, then press Enter:
   
   ```
   winget install Gyan.FFmpeg
   ```
1. Wait for it to finish installing
1. **Close PowerShell completely and open a new one**

**Verify it worked:**

- Open PowerShell again
- Type `ffmpeg -version` and press Enter
- You should see version information

#### Step 3: Download This Project

1. Click the green “Code” button at the top of this page
1. Click “Download ZIP”
1. Find the ZIP file in your Downloads folder
1. Right-click it and choose “Extract All”
1. Remember where you extracted it!

#### Step 4: Set Up the Project

1. Open File Explorer and navigate to the extracted folder
1. Click in the address bar at the top and type `powershell`, then press Enter
1. Copy and paste these commands **one at a time**:

```powershell
python -m venv .venv
```

Wait for it to finish, then:

```powershell
.venv\Scripts\Activate.ps1
```

If you get an error about “scripts disabled”, do this:

- Right-click PowerShell in the Start menu
- Choose “Run as Administrator”
- Type this and press Enter:
  
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- Type `Y` and press Enter
- Close the admin PowerShell
- Go back to your regular PowerShell in the project folder and try again

After activation works (you’ll see `(.venv)` at the start of your command line), run:

```powershell
python -m pip install --upgrade pip
```

Then:

```powershell
pip install -r requirements.txt
```

This will take a few minutes. Wait until it’s completely done.

#### Step 5: Run the Program!

Make sure you’re still in the project folder with `(.venv)` showing. Then:

```powershell
python -m backend.app --input "C:\path\to\your\video.mp4"
```

Replace `C:\path\to\your\video.mp4` with the actual path to your video.

**Tip:** You can drag and drop your video file into PowerShell to automatically type the path!

-----

### 🍎 **Mac Installation**

#### Step 1: Install Homebrew

Homebrew is a tool that helps install software on Mac.

1. Open **Terminal** (press `Command + Space`, type “Terminal”, press Enter)
1. Copy and paste this entire line, then press Enter:
   
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
1. Enter your Mac password when asked (you won’t see it as you type - that’s normal)
1. Press Enter to continue when prompted
1. **Important:** After installation, it will show you 2-3 commands to run. Copy and paste those commands and run them!

#### Step 2: Install Python and FFmpeg

In Terminal, run these commands one at a time:

```bash
brew install python@3.11
```

Wait for it to finish, then:

```bash
brew install ffmpeg
```

**Verify it worked:**

```bash
python3.11 --version
ffmpeg -version
```

You should see version numbers for both.

#### Step 3: Download This Project

1. Click the green “Code” button at the top of this page
1. Click “Download ZIP”
1. Find the ZIP in your Downloads folder and double-click to extract it

#### Step 4: Set Up the Project

1. In Terminal, navigate to the project folder:
   
   ```bash
   cd ~/Downloads/Youtube-Shorts-Clipper
   ```
   
   (Adjust the path if you extracted it somewhere else)
1. Run these commands one at a time:
   
   ```bash
   python3.11 -m venv .venv
   ```
   
   Then:
   
   ```bash
   source .venv/bin/activate
   ```
   
   You should now see `(.venv)` at the start of your command line.
   
   Then:
   
   ```bash
   python -m pip install --upgrade pip
   ```
   
   Then:
   
   ```bash
   pip install -r requirements.txt
   ```

This will take a few minutes. Wait until it’s completely done.

#### Step 5: Run the Program!

Make sure you’re still in the project folder with `(.venv)` showing. Then:

```bash
python -m backend.app --input "~/Downloads/your-video.mp4"
```

Replace `~/Downloads/your-video.mp4` with the actual path to your video.

**Tip:** You can drag and drop your video file into Terminal to automatically type the path!

-----

## How to Use

### Basic Usage

```bash
python -m backend.app --input "/path/to/your/video.mp4"
```

The program will:

- Analyze your video for exciting moments
- Create multiple Short clips (typically 30-60 seconds each)
- Save them in a folder called `clips_out/YourVideoName/`

### Delete Original After Processing

If you want to automatically move the original video to the Recycle Bin/Trash after processing:

**Windows:**

```powershell
python -m backend.app --input "C:\path\to\video.mp4" --delete
```

**Mac:**

```bash
python -m backend.app --input "~/Downloads/video.mp4" --delete
```

### Running the Program Again Later

Every time you want to use the program, you need to:

**Windows:**

1. Open PowerShell in the project folder
1. Run: `.venv\Scripts\Activate.ps1`
1. Run your command: `python -m backend.app --input "..."`

**Mac:**

1. Open Terminal
1. Navigate to the project: `cd ~/Downloads/Youtube-Shorts-Clipper`
1. Activate: `source .venv/bin/activate`
1. Run your command: `python -m backend.app --input "..."`

-----

## Configuration

You can customize how the clips are created by editing `backend/config/default.yaml`. Some settings you might want to adjust:

- **Clip count**: How many clips to generate
- **Clip length**: Min/max duration for each clip
- **Video quality**: Output resolution and quality settings
- **Layout**: Gameplay and facecam sizes
- **Hook settings**: Whether to put a “climax” moment at the start

Open the file in any text editor and the comments explain what each setting does.

-----

## Troubleshooting

### “FFmpeg not found” or “FFprobe not found”

**Windows:**

- Make sure you closed and reopened PowerShell after installing FFmpeg
- Try running: `ffmpeg -version` to test if it’s installed
- If it still doesn’t work, you may need to manually add FFmpeg to your PATH

**Mac:**

- Make sure Homebrew installation completed successfully
- Try running: `which ffmpeg` to see if it’s found
- If not found, try reinstalling: `brew reinstall ffmpeg`

### “Python not found” or “Python not recognized”

**Windows:**

- You forgot to check “Add Python to PATH” during installation
- Uninstall Python and reinstall it, making sure to check that box

**Mac:**

- Try using `python3.11` instead of `python`
- Make sure you ran the Homebrew setup commands after installing it

### “Permission denied” or “Execution policy” errors (Windows)

Run PowerShell as Administrator and execute:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### The video file “cannot be found”

- Make sure you’re using the correct path to your video
- On Windows, use backslashes: `C:\Users\...` or forward slashes: `C:/Users/...`
- On Mac, use forward slashes: `/Users/...` or tilde: `~/Downloads/...`
- Put the path in quotes if it contains spaces
- Try dragging and dropping the file into your Terminal/PowerShell window

### Clips are all the same length or hitting the maximum

Adjust these settings in `backend/config/default.yaml`:

- `max_dur_sec`: Maximum clip length
- `silence_percentile`: How quiet is considered “silence”
- `max_silence_frac`: Maximum allowed silence in a clip

-----

## What the Output Looks Like

After processing, you’ll find your clips in:

```
clips_out/
  └── YourVideoName/
      ├── short_01.mp4
      ├── short_02.mp4
      ├── short_03.mp4
      └── ...
```

Each clip is formatted as a vertical video (1080x1920) ready to upload to YouTube Shorts, TikTok, or Instagram Reels!

-----

## Getting Help

If you run into issues:

1. Read the error message carefully - it usually tells you what’s wrong
1. Check the Troubleshooting section above
1. Make sure you followed every step in order
1. Try searching for the error message online
1. Open an issue on this GitHub repository with the full error message

-----

## Tips for Best Results

- Use videos that are at least 5-10 minutes long
- Make sure your facecam and gameplay are both visible in the source video
- The program works best with videos that have audio (it uses audio levels to find exciting moments)
- Adjust the config file to match your specific video layout and style

Happy creating! 🎮🎬