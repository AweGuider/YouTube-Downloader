# YouTube Downloader

A small Windows-first desktop downloader for saving individual YouTube videos or audio files. It wraps `yt-dlp` in a Tkinter GUI, bundles runtime helpers for release builds, and shows startup diagnostics so users can see whether downloader dependencies are healthy.

## Features

- Download one video URL at a time as MP4.
- Download audio-only files as MP3, WAV, AAC, or FLAC.
- Preview the checked video's thumbnail, title, readable length, channel, and upload date before downloading.
- Choose best available quality or a quality at or below the selected resolution.
- Save repeated downloads with unique filenames.
- Show dependency diagnostics for `yt-dlp`, `yt-dlp-ejs`, JavaScript runtime support, `ffmpeg`, `ffprobe`, network access, and old PyInstaller temp folders.
- Save user settings such as output folder, cleanup behavior, timestamp behavior, mode, and format.

## Supported Platform

The first public release target is Windows. The source may run on other platforms with Python and compatible dependencies, but non-Windows use is not the release target yet.

## Install From Release

1. Download the latest release ZIP or EXE from the repository Releases page.
2. Extract the ZIP if needed.
3. Run `YouTubeDownloader_by_AweDev.exe`.
4. If Windows SmartScreen appears, review the publisher/file details and choose whether to run it.

The release EXE is intended to include the needed Python app package, thumbnail preview support, `ffmpeg`, `ffprobe`, and a JavaScript runtime used by `yt-dlp`.

## Run From Source

Requirements:

- Windows
- Python 3.13 or newer
- `ffmpeg` and `ffprobe` available on `PATH`
- Node or Deno available on `PATH`

Install Python dependencies:

```bat
python -m pip install -r requirements.txt
```

Run the app:

```bat
run_downloader.bat
```

Or run directly:

```bat
python downloader.py
```

## Build A Release EXE

Install build dependencies:

```bat
python -m pip install -r requirements-build.txt
```

Make sure these commands work before building:

```bat
ffmpeg -version
ffprobe -version
node --version
```

Then run:

```bat
build_exe_latest.bat
```

The build script asks for an EXE name, ZIP name, overwrite behavior, and whether to create a ZIP. Generated EXEs, ZIPs, logs, PyInstaller output, and `.spec` files are ignored by Git.

## Troubleshooting

- If diagnostics says `yt-dlp` is outdated, update the package in source builds or download a newer app release.
- If diagnostics says `ffmpeg` or `ffprobe` is missing, install FFmpeg and make sure both tools are on `PATH`, or use the packaged EXE.
- If diagnostics says JavaScript runtime support is missing, install Node or Deno, or use the packaged EXE.
- If a URL cannot be checked, try another video and confirm the video is public, available in your region, and reachable in a browser.
- If the app creates a PyInstaller temp folder while running, that is expected for one-file EXEs. Clean shutdown should remove it; diagnostics warns about older leftovers.

## Limitations

- One URL at a time.
- No playlist or batch downloads in the first release.
- No DRM or copyright bypassing.
- YouTube and `yt-dlp` behavior can change, so some failures may require dependency updates or a new app release.

## Legal Note

Use this tool only for content you have the right to download. This project does not bypass DRM and does not grant rights to third-party content. You are responsible for following YouTube's terms and applicable law.

Packaged releases may include third-party tools and packages such as `yt-dlp`, `yt-dlp-ejs`, `Pillow`, `ffmpeg`, `ffprobe`, and Node or Deno. Those components are governed by their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before publishing release binaries.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
