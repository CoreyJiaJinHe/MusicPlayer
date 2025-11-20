# MusicPlayer (Python)

A desktop music player that can search and play local files and stream online tracks (YouTube/SoundCloud) without storing them locally. YouTube/SoundCloud are played via official embedded players; local files via VLC.

## Requirements
- Python 3.11+ (3.13 supported)
- VLC installed (for local playback, required by `python-vlc`)

## Setup
```cmd
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```
## 1.0.0 Release Build Instructions (Windows)

1. Create and activate a virtual environment (recommended):
```
python -m venv .venv
call .venv\Scripts\activate
```
2. Upgrade pip and install dependencies:
```
python -m pip install --upgrade pip
pip install -r requirements.txt
```
3. Build the executable using the spec file:
```
build_windows.bat
```
4. The resulting executable will be at:
```
dist\MusicPlayer\MusicPlayer.exe
```
5. Test run:
```
dist\MusicPlayer\MusicPlayer.exe
```

## Distribution
Distribute the single directory `dist\MusicPlayer` or wrap with an installer.

## Version
Current version: 1.0.0 (see `musicplayer/version.py`).

Secrets go in `.env` (not in `config.json`):
```env
YOUTUBE_API_KEY=your_youtube_data_api_v3_key
SOUNDCLOUD_CLIENT_ID=optional_soundcloud_client_id
```
`config.json` stores only non-secret settings (e.g., `music_root`, optional `webengine_flags`). It is created on first run.

## Run
```cmd
.venv\Scripts\python main.py
```

## Notes
- YouTube search uses the Data API; store the key in `.env`.
- SoundCloud search is a placeholder (paste track URLs to play).
- Online playback is done via official embeds; the app does not download audio.
- Playlists persist to `playlists.json` in the project directory.
 - If you hit a Windows WebEngine error, adjust Settings → WebEngine Flags to toggle `--disable-direct-composition` and/or `--disable-gpu` (restart required).
