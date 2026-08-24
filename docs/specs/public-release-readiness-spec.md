# Public Release Readiness Spec

## Purpose

Make the YouTube downloader ready for a public GitHub release: installable by non-developer Windows users, reliable against common YouTube/yt-dlp breakage, clean enough to maintain, and clear about ownership/license.

## Assumptions

- First release is Windows-first.
- Current Python/Tkinter app stays unless UI cleanup proves insufficient.
- License: MIT.
- App should warn about dependency/update issues; auto-update buttons are optional unless approved later.

## Goals

- Fresh users can run the app without the creator's local Python/ffmpeg setup.
- EXE/release package includes or clearly resolves `yt-dlp`, `yt-dlp-ejs`/JS runtime, `ffmpeg`, and `ffprobe`.
- Startup health check reports app version, dependency versions, missing tools, outdated downloader support, and internet availability.
- Video and audio downloads work with real progress.
- Failed downloads expose useful errors and clean temporary files.
- Existing destination files never block repeat downloads.
- UI is cleaner, mode-aware, and removes test/debug controls.
- Public repo includes README, build/install docs, requirements/build metadata, license, release guidance, and clean ignore rules.

## Non-Goals

- No web app.
- No mobile support.
- No DRM/copyright bypassing.
- No playlist/batch mode for first release.
- No "stop merging" feature unless explicitly re-approved; otherwise remove that TODO.

## Required Behavior

- On launch, run dependency diagnostics for `yt-dlp`, JS runtime/EJS, `ffmpeg`, `ffprobe`, and network access.
- Show dependency warnings inside the UI, not only in console output.
- Resolve bundled binary paths correctly in PyInstaller builds, including `ffmpeg` and `ffprobe`.
- Download errors show the actual failure reason in the GUI.
- All Tkinter UI updates happen on the main thread.
- Resolution fetching is debounced and performed off the UI thread.
- Video resolution selection uses best available at or below the selected resolution when exact match is unavailable.
- Audio-only mode outputs exactly one final file with the selected extension.
- Audio-only mode reports progress instead of staying at "Connecting."
- Temp folders are cleaned after both success and failure when cleanup is enabled.
- Existing output filenames are handled with suffixes like `name (1).mp4`.
- Timestamp behavior is configurable: preserve upload date or use current download date.
- Remove unsafe/default `nocheckcertificate=True` unless a clearly labeled fallback setting exists.
- Paste works across keyboard layouts and a paste-from-clipboard button is available.
- Closing the app also stops/cleans any active worker process or background task safely.
- Production UI removes the old default-filled URL and visible `Default` button, while keeping any test-link helper explicit.
- App has a proper custom icon.

## Source Maintenance

- Existing TODO comments in `downloader.py` are part of the current issue inventory and should not be deleted just for cleanup.
- Remove a TODO only in the same commit that actually implements, supersedes, or explicitly de-scopes that TODO.
- If a TODO is not implemented for the public release, either keep it in source or move it to a tracked issue list with equivalent wording before removing it.
- Remove stale or misleading comments only when the related behavior has been corrected or the comment has been replaced by clearer documentation.

## Repo / Release Hygiene

- Add/verify `.gitignore` rules for generated EXEs, ZIPs, logs, PyInstaller output, specs, caches.
- Do not commit local build artifacts.
- Add `LICENSE`.
- Add real README: purpose, supported OS, install/run, build from source, troubleshooting, legal note.
- Add dependency/build metadata: `requirements.txt` or equivalent.
- Build script should not hard-code the creator's personal `C:\ffmpeg\...` path as the only path.

## Acceptance Criteria

- Given a fresh Windows machine, when the release EXE starts, then it opens and shows pass/warn/fail dependency status.
- Given missing `ffprobe` or JS runtime support, when the app starts, then the user sees a clear fix.
- Given a valid YouTube URL, when downloading video, then an MP4 saves successfully.
- Given audio-only MP3 mode, when downloading, then one `.mp3` file saves and progress updates.
- Given the same URL is downloaded twice, then both downloads succeed with unique filenames.
- Given a failed download, then temp files are cleaned and the GUI shows the real error.
- Given rapid typing/pasting in the URL field, then the UI stays responsive and only debounced resolution checks run.
- Given the public repo, then a visitor can install, build, understand the license, and avoid committing generated artifacts.
- Given a TODO is removed from `downloader.py`, then the same commit implements, supersedes, explicitly de-scopes, or preserves it elsewhere as a tracked issue.

## Suggested Commit Boundaries

- `[Fix : Packaging] Bundled runtime dependencies`
- `[Fix : Downloads] Handled audio, progress, cleanup, and file collisions`
- `[Add : Diagnostics] Added startup dependency health checks`
- `[Update : UI] Simplified downloader interface`
- `[Add : Docs] Prepared public repository docs`

## Open Decisions

- Confirm Windows-only first release.
- Confirm whether health checks only warn or also offer auto-update actions.
