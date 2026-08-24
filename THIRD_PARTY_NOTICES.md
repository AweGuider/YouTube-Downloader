# Third-Party Notices

This project can package third-party tools so the Windows EXE works without a local developer setup. This file is not legal advice; verify the exact bundled versions before publishing a release artifact.

## Python Packages

| Component | Current requirement | License / notice |
| --- | --- | --- |
| `yt-dlp` | `yt-dlp[default]>=2026.8.19` | Unlicense. Some upstream release formats can include differently licensed bundled code; this app packages the Python package, not the standalone upstream executable. |
| `yt-dlp-ejs` | `yt-dlp-ejs>=0.8.0` | Unlicense, with prebuilt wheel contents also including MIT and ISC licensed code. |
| `Pillow` | `Pillow>=11.0.0` | Historical Permission Notice and Disclaimer license. Used for thumbnail preview image decoding and resizing. |
| `PyInstaller` | `pyinstaller>=6.21.0` | GPLv2-or-later with PyInstaller's bootloader exception for distributing bundled applications. Build-time dependency. |

## Runtime Binaries

| Component | How it is used | License / notice |
| --- | --- | --- |
| `ffmpeg` / `ffprobe` | Bundled into the release EXE by `build_exe_latest.bat` when found on `PATH`. | FFmpeg is usually LGPL, but builds configured with GPL options are GPL. If using the Gyan.dev full build shown in local testing, treat the bundled FFmpeg binaries as GPL-covered and include the license files/notices from that exact distribution. |
| Deno | Preferred JavaScript runtime bundled by `build_exe_latest.bat` when available. | MIT license. Include Deno's license text or notice when bundling the binary. |
| Node.js | Fallback JavaScript runtime bundled by `build_exe_latest.bat` when Deno is unavailable. | MIT license for Node.js plus notices for included third-party dependencies. Include Node's license file/notices when bundling the binary. |

## Release Requirement

Before attaching a ZIP or EXE to a public GitHub release, include the third-party license files/notices that match the exact bundled binaries. This matters most for `ffmpeg`/`ffprobe`, because the license obligations depend on the build configuration.
