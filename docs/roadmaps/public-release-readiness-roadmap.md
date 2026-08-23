# Public Release Readiness Roadmap

## Purpose

Sequence the work from `docs/specs/public-release-readiness-spec.md` so the project can become a public GitHub repository with a Windows-first release that non-developer users can install and run.

## Confirmed Facts

- The app is currently a small Python/Tkinter YouTube downloader.
- The public-release spec is the source of truth for required behavior.
- First release is assumed Windows-first.
- Existing TODO comments in `downloader.py` should remain until their matching issue is implemented, superseded, explicitly de-scoped, or preserved elsewhere.

## Sequencing Logic

Fix distribution and diagnostics first, because public users need the app to start and explain missing/outdated dependencies before deeper download behavior can be trusted. Then stabilize download flows, simplify the UI around the corrected behavior, and finish with repository/release polish.

## Phase Progress

- 2026-08-24: Phase 1 passed. The build baseline now resolves and bundles `ffmpeg`, `ffprobe`, and a JavaScript runtime, includes dependency/build metadata, and produced an EXE that was confirmed to run on another Windows device. Remaining release risk: bundled binary licensing still needs documentation before public release.
- 2026-08-24: Phase 2 passed for source-run validation. Startup diagnostics report app/dependency/network/temp status in the GUI with `9 OK, 0 warning(s), 0 failure(s)`, and download failures now surface the real error. Remaining release risk: diagnostics need EXE validation after the local Tcl/Tk build environment is repaired.

## Phase 1: Reproducible Packaging Baseline

### Outcome

A fresh Windows user can run the built app without depending on the creator's local Python and `C:\ffmpeg` setup.

### Why This Comes Now

Packaging is the known public-release blocker. If the EXE cannot run elsewhere, later download and UI fixes are hard to validate honestly.

### Included Work

- Replace personal-path-only build assumptions with reproducible dependency resolution.
- Ensure `ffmpeg` and `ffprobe` are both available to the packaged app.
- Verify PyInstaller handling for `yt-dlp` and `yt-dlp-ejs` resources.
- Add or update dependency/build metadata needed by contributors.
- Keep generated EXEs, ZIPs, logs, build output, and caches out of source control.

### Excluded Work

- UI redesign.
- Auto-update flows.
- Playlist or batch download support.

### Dependencies / Blockers

- Confirm whether bundled `ffmpeg`/`ffprobe` is acceptable for the release license/distribution story.
- Confirm Windows-only first release.

### Risks

- PyInstaller may miss dynamic `yt-dlp` resources unless explicitly configured.
- Bundling external binaries can create license/distribution obligations.

### Validation Gate

Build a release artifact and run it in a clean Windows environment or VM where Python, `ffmpeg`, and `ffprobe` are not preinstalled.

## Phase 2: Runtime Diagnostics And Error Visibility

### Outcome

The app clearly reports dependency health and actionable failure reasons from inside the GUI.

### Why This Comes Now

YouTube/yt-dlp breakage is expected over time. Users need to know whether the app, dependency versions, JS runtime, network, or URL caused a failure.

### Included Work

- Add startup checks for app version, `yt-dlp`, JS runtime/EJS support, `ffmpeg`, `ffprobe`, and network access.
- Surface pass/warn/fail status in the UI.
- Show actual download errors in the GUI instead of only printing them.
- Decide whether health checks only warn or also offer update actions.

### Excluded Work

- Full automated self-updater unless explicitly approved.
- Telemetry or remote error reporting.

### Dependencies / Blockers

- Packaging baseline should define where bundled tools live.
- Update-action behavior needs a product decision.

### Risks

- Version checks can become brittle if they depend on parsing command output too narrowly.
- Online checks must not make the app feel broken when the user is offline.

### Validation Gate

Run the app with missing or intentionally renamed dependencies and confirm it opens, identifies the issue, and gives a useful next step.

## Phase 3: Download Flow Reliability

### Outcome

Video and audio downloads work predictably, recover cleanly from failure, and do not leave users stuck.

### Why This Comes Now

Once startup and diagnostics are reliable, the core download paths can be fixed against the current TODO inventory and user-facing failures.

### Included Work

- Fix audio-only progress and double-extension output behavior.
- Clean temp folders after success and failure when cleanup is enabled.
- Handle existing destination files with unique suffixes.
- Debounce and background resolution fetching.
- Keep all Tkinter UI updates on the main thread.
- Use best available video format at or below the selected resolution.
- Add configurable timestamp behavior: upload date or current download date.
- Remove unsafe/default `nocheckcertificate=True` unless it becomes a clearly labeled fallback setting.
- Ensure app close stops or cleans active workers safely.

### Excluded Work

- Batch downloads.
- Resume manager or download queue UI.
- Advanced format picker beyond the current release target.

### Dependencies / Blockers

- Diagnostics should already expose useful errors.
- The TODO-retention rule controls which source TODOs can be removed during this phase.

### Risks

- YouTube extractor behavior may change while implementation is in progress.
- Threading fixes can expose hidden UI assumptions in the current script.

### Validation Gate

Manually verify video download, audio-only MP3, repeated same-URL download, failure cleanup, rapid URL typing/pasting, and closing the app during/around background work.

## Phase 4: Public UI Cleanup

### Outcome

The first screen feels like a simple public downloader instead of a local test tool.

### Why This Comes Now

UI cleanup should follow corrected behavior so the interface reflects the real workflows and diagnostics.

### Included Work

- Remove the default test URL and visible `Default` button from production UI.
- Add a paste-from-clipboard button and reliable paste behavior across keyboard layouts.
- Group controls by workflow: URL, mode, quality/format, destination, status/actions.
- Hide or disable irrelevant fields based on video/audio mode.
- Add a proper app icon.
- Keep the UI clear enough for non-developer users.

### Excluded Work

- Full framework rewrite.
- Branding/marketing site.
- Advanced theming system.

### Dependencies / Blockers

- A screenshot or visual review pass may be needed before final UI decisions.
- Final diagnostics surface from Phase 2 should already exist.

### Risks

- Tkinter limits how polished the UI can feel without increasing implementation cost.

### Validation Gate

Open the app at normal Windows desktop scale and confirm the main workflow is understandable without reading source code or console output.

## Phase 5: Public Repository And Release Prep

### Outcome

The GitHub repository is understandable, legally clear, and ready for a first public release.

### Why This Comes Now

Docs and release polish should describe the actual finished behavior, packaging model, limitations, and troubleshooting steps.

### Included Work

- Add `LICENSE`.
- Expand README with purpose, supported OS, install/run, build from source, troubleshooting, legal note, and known limitations.
- Document release packaging and dependency expectations.
- Confirm `.gitignore` covers generated artifacts.
- Remove or move TODOs only when allowed by the source-maintenance rule.
- Prepare release notes for the first public version.

### Excluded Work

- GitHub Actions automation unless explicitly approved.
- Multi-platform installers.
- Support/community process beyond basic README guidance.

### Dependencies / Blockers

- License choice must be confirmed.
- Earlier validation gates should pass before release docs are finalized.

### Risks

- Public downloader repos can attract support requests around YouTube breakage and legal usage; README needs clear boundaries.

### Validation Gate

Review the repo as a new visitor: clone/build instructions work, generated artifacts are absent from source control, license is present, and release download guidance is clear.

## Feature / Spec Candidates

- Auto-update or one-click dependency repair for `yt-dlp`/EJS/runtime support may need a follow-up spec if approved.
- Larger UI rewrite may need a separate spec if Tkinter cleanup is not enough.
- GitHub Actions release automation may need a separate spec if added later.

## Recommended Next Step

Start with Phase 1 and make one focused commit for packaging/release hygiene before touching downloader behavior.
