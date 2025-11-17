# MediaPlayer (Python)

A desktop media player that can search and play local files and stream online tracks (YouTube/SoundCloud) without storing them locally. YouTube/SoundCloud are played via official embedded players; local files via VLC.

## Requirements
- Python 3.11+ (3.13 supported)
- VLC installed (for local playback, required by `python-vlc`)

## Setup
```cmd
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

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
