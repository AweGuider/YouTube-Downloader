import os
import time
import platform
import ctypes
import sys
import yt_dlp
import tempfile
import functools
import importlib.metadata
import json
import queue
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageOps, ImageTk

### Command to create .exe out of .py
# python -m PyInstaller --onefile downloader.py

APP_NAME = "YouTube Downloader"
APP_ID = "AweDevYouTubeDownloader"
TEST_URL = "https://www.youtube.com/watch?v=QDia3e12czc"
DEFAULT_RESOLUTION = "1080p"
DEFAULT_AUDIO_FORMAT = "MP3"
RESOLUTION_OPTIONS = ("Highest Available", "1080p", "720p", "480p", "360p")
AUDIO_FORMATS = ("MP3", "WAV", "AAC", "FLAC")
PREVIEW_IMAGE_SIZE = (200, 112)
MAX_THUMBNAIL_BYTES = 4 * 1024 * 1024

# Default output directory (current folder)
# Set default output folder to "Downloads/YouTubeDownloads/"
default_output_folder = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloads")
# Ensure the folder exists
os.makedirs(default_output_folder, exist_ok=True)

def settings_path():
    settings_root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(settings_root, APP_ID, "settings.json")

def load_settings():
    try:
        with open(settings_path(), "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}

saved_settings = load_settings()

# Use this as the initial output directory
saved_output_directory = saved_settings.get("output_directory")
output_directory = saved_output_directory if isinstance(saved_output_directory, str) and saved_output_directory else default_output_folder
try:
    os.makedirs(output_directory, exist_ok=True)
except OSError:
    output_directory = default_output_folder
    os.makedirs(output_directory, exist_ok=True)

saved_resolution = saved_settings.get("selected_resolution")
selected_resolution = saved_resolution if isinstance(saved_resolution, str) and saved_resolution else DEFAULT_RESOLUTION

fetch_delay = None  # Global variable to track scheduled fetch calls
fetch_request_id = 0
url_ready_for_download = False
latest_media_info = None
download_thread = None
download_cancel_event = None
is_closing = False
ui_queue = queue.Queue()

# For future implementation of stable progress UI update
latest_progress = {"percent": "0%", "speed": "N/A", "eta": "Unknown"}

APP_VERSION = "1.1.0"
STALE_MEI_AGE_SECONDS = 24 * 60 * 60
JS_RUNTIME_CANDIDATES = (
    ("deno", "deno", (2, 3, 0), True),
    ("node", "node", (22, 0, 0), False),
    ("bun", "bun", (1, 2, 11), True),
    ("quickjs", "qjs", (2023, 12, 9), False),
)

def app_runtime_dir():
    """Returns the PyInstaller extraction folder when frozen, otherwise the source folder."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

def app_resource_path(*parts):
    return os.path.join(app_runtime_dir(), *parts)

def set_app_icon(window):
    icon_path = app_resource_path("assets", "app.ico")
    if not os.path.exists(icon_path):
        return

    try:
        window.iconbitmap(icon_path)
    except tk.TclError:
        pass

def save_settings():
    data = {
        "output_directory": output_directory,
        "selected_resolution": selected_resolution,
        "audio_only": audio_only.get(),
        "audio_format": selected_audio_format.get(),
        "delete_temp_files": delete_temp_files.get(),
        "preserve_upload_date": preserve_upload_date.get(),
    }

    try:
        path = settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as settings_file:
            json.dump(data, settings_file, indent=2)
    except OSError as e:
        print(f"Could not save settings: {e}")

def binary_name(name):
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name

def bundled_binary_path(name):
    executable = binary_name(name)
    bundled_path = os.path.join(app_runtime_dir(), executable)
    if os.path.exists(bundled_path):
        return bundled_path
    return None

def resolve_windows_command(executable):
    if os.name != "nt":
        return None

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$cmd = Get-Command -Name '{executable}' -ErrorAction SilentlyContinue; if ($cmd) {{ $cmd.Source }}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None

    candidate = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
    if candidate and os.path.exists(candidate):
        return candidate
    return None

@functools.lru_cache(maxsize=None)
def system_binary_path(name):
    executable = binary_name(name)
    return shutil.which(executable) or resolve_windows_command(executable)

def runtime_binary_path(name):
    return bundled_binary_path(name) or system_binary_path(name)

def runtime_binary_dir(*required_names):
    runtime_dir = app_runtime_dir()
    if all(os.path.exists(os.path.join(runtime_dir, binary_name(name))) for name in required_names):
        return runtime_dir

    resolved = [runtime_binary_path(name) for name in required_names]
    if all(resolved):
        directories = {os.path.dirname(path) for path in resolved}
        if len(directories) == 1:
            return directories.pop()

    return None

def prepend_runtime_tools_to_path():
    runtime_dir = app_runtime_dir()
    current_path = os.environ.get("PATH", "")
    if runtime_dir and runtime_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = runtime_dir + os.pathsep + current_path

def iter_js_runtime_candidates():
    for source, resolver in (("bundled", bundled_binary_path), ("system", system_binary_path)):
        for runtime_name, executable_name, min_version, needs_remote_components in JS_RUNTIME_CANDIDATES:
            runtime_path = resolver(executable_name)
            if runtime_path:
                yield {
                    "name": runtime_name,
                    "executable": executable_name,
                    "path": runtime_path,
                    "min_version": min_version,
                    "needs_remote_components": needs_remote_components,
                    "source": source,
                }

@functools.lru_cache(maxsize=1)
def selected_js_runtime():
    for runtime in iter_js_runtime_candidates():
        is_usable, version_line, _ = probe_js_runtime(runtime)
        if is_usable:
            runtime["version_line"] = version_line
            return runtime
    return None

def create_ytdlp_options(overrides=None):
    options = {"quiet": True}

    ffmpeg_dir = runtime_binary_dir("ffmpeg", "ffprobe")
    if ffmpeg_dir:
        options["ffmpeg_location"] = ffmpeg_dir

    runtime = selected_js_runtime()
    if runtime:
        options["js_runtimes"] = {runtime["name"]: {"path": runtime["path"]}}
        if runtime["needs_remote_components"]:
            options["remote_components"] = ["ejs:npm"]

    if overrides:
        options.update(overrides)

    return options

prepend_runtime_tools_to_path()

def diagnostic(status, label, detail):
    return {"status": status, "label": label, "detail": detail}

def package_version(package_name):
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None

def first_output_line(text):
    for line in text.splitlines():
        if line.strip():
            return clean_text(line.strip())
    return ""

def compact_version_line(line):
    words = line.split()
    if len(words) >= 3 and words[1].lower() == "version":
        return f"{words[0]} {words[2]}"
    return line[:120]

def js_runtime_version_arg(runtime_name):
    return "--help" if runtime_name == "quickjs" else "--version"

def run_command(args, timeout=5):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

def parse_version_tuple(text):
    numbers = re.findall(r"\d+", text)
    return tuple(int(number) for number in numbers[:3])

def compare_versions(left, right):
    left_parts = parse_version_tuple(left)
    right_parts = parse_version_tuple(right)
    length = max(len(left_parts), len(right_parts))
    left_parts += (0,) * (length - len(left_parts))
    right_parts += (0,) * (length - len(right_parts))
    return (left_parts > right_parts) - (left_parts < right_parts)

def probe_js_runtime(runtime):
    try:
        result = run_command([runtime["path"], js_runtime_version_arg(runtime["name"])])
    except Exception as e:
        return False, "", f"{runtime['name']} found but could not run: {e}"

    if result.returncode != 0 and runtime["name"] != "quickjs":
        return False, "", f"{runtime['name']} returned {result.returncode}"

    version_line = first_output_line(result.stdout or result.stderr) or runtime["name"]
    return True, version_line, None

def check_binary_version(name):
    binary_path = runtime_binary_path(name)
    if not binary_path:
        return diagnostic("fail", name, "missing")

    try:
        result = run_command([binary_path, "-version"])
    except Exception as e:
        return diagnostic("fail", name, f"found but could not run: {e}")

    if result.returncode != 0:
        return diagnostic("fail", name, f"found but returned {result.returncode}")

    version_line = compact_version_line(first_output_line(result.stdout or result.stderr))
    source = "bundled" if bundled_binary_path(name) else "system"
    return diagnostic("pass", name, f"{version_line} ({source})")

def check_js_runtime():
    runtime = selected_js_runtime()
    if not runtime:
        failures = []
        for candidate in iter_js_runtime_candidates():
            _, _, error = probe_js_runtime(candidate)
            if error:
                failures.append(error)

        if failures:
            return diagnostic("fail", "JS runtime", "; ".join(failures[:2]))
        return diagnostic("fail", "JS runtime", "missing Deno, Node, Bun, or QuickJS")

    version_line = runtime.get("version_line") or runtime["name"]
    version_text = " ".join(re.findall(r"\d+(?:\.\d+)*", version_line)[:1])
    if version_text and runtime["min_version"]:
        min_text = ".".join(str(part) for part in runtime["min_version"])
        if compare_versions(version_text, min_text) < 0:
            return diagnostic("warn", "JS runtime", f"{version_line}; recommended >= {min_text}")

    return diagnostic("pass", "JS runtime", f"{version_line} ({runtime['source']})")

def check_ytdlp_latest(local_version):
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return diagnostic("warn", "yt-dlp update", f"could not check latest version: {e}")

    latest_version = data.get("info", {}).get("version")
    if not latest_version:
        return diagnostic("warn", "yt-dlp update", "latest version unknown")

    if compare_versions(local_version, latest_version) < 0:
        return diagnostic("warn", "yt-dlp update", f"local {local_version}, latest {latest_version}")

    return diagnostic("pass", "yt-dlp update", f"local {local_version} is current")

def check_network():
    try:
        with urllib.request.urlopen("https://www.youtube.com/generate_204", timeout=5) as response:
            status_code = getattr(response, "status", response.getcode())
    except Exception as e:
        return diagnostic("warn", "Network", f"YouTube check failed: {e}")

    if 200 <= status_code < 400:
        return diagnostic("pass", "Network", "YouTube reachable")
    return diagnostic("warn", "Network", f"YouTube returned HTTP {status_code}")

def check_pyinstaller_temp_leftovers():
    temp_root = tempfile.gettempdir()
    current_runtime = os.path.realpath(app_runtime_dir())
    stale_count = 0

    try:
        entries = os.listdir(temp_root)
    except OSError as e:
        return diagnostic("warn", "Temp cleanup", f"could not inspect Temp: {e}")

    now = time.time()
    for entry in entries:
        if not entry.startswith("_MEI"):
            continue

        path = os.path.realpath(os.path.join(temp_root, entry))
        if path == current_runtime or not os.path.isdir(path):
            continue

        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue

        if age >= STALE_MEI_AGE_SECONDS:
            stale_count += 1

    if stale_count:
        return diagnostic("warn", "Temp cleanup", f"{stale_count} old PyInstaller temp folder(s) found")
    return diagnostic("pass", "Temp cleanup", "no old PyInstaller temp folders found")

def run_startup_diagnostics():
    results = [
        diagnostic("pass", "App", f"{APP_VERSION} ({'EXE' if getattr(sys, 'frozen', False) else 'source'})")
    ]

    ytdlp_version = getattr(yt_dlp.version, "__version__", None) or package_version("yt-dlp")
    if ytdlp_version:
        results.append(diagnostic("pass", "yt-dlp", ytdlp_version))
        results.append(check_ytdlp_latest(ytdlp_version))
    else:
        results.append(diagnostic("fail", "yt-dlp", "version unknown"))

    ejs_version = package_version("yt-dlp-ejs")
    if ejs_version:
        results.append(diagnostic("pass", "yt-dlp-ejs", ejs_version))
    else:
        results.append(diagnostic("fail", "yt-dlp-ejs", "missing"))

    results.append(check_binary_version("ffmpeg"))
    results.append(check_binary_version("ffprobe"))
    results.append(check_js_runtime())
    results.append(check_network())
    results.append(check_pyinstaller_temp_leftovers())
    return results

def format_diagnostics(results):
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for result in results:
        counts[result["status"]] += 1

    lines = [f"Diagnostics: {counts['pass']} OK, {counts['warn']} warning(s), {counts['fail']} failure(s)"]
    labels = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}
    for result in results:
        lines.append(f"[{labels[result['status']]}] {result['label']}: {result['detail']}")
    return "\n".join(lines)

def diagnostics_color(results):
    statuses = {result["status"] for result in results}
    if "fail" in statuses:
        return "#b00020"
    if "warn" in statuses:
        return "#8a5a00"
    return "#1b6b34"

def show_diagnostics():
    diagnostics_visible.set(True)
    diagnostics_panel.grid()
    diagnostics_button.config(text="Hide Diagnostics")

def hide_diagnostics():
    diagnostics_visible.set(False)
    diagnostics_panel.grid_remove()
    diagnostics_button.config(text="Show Diagnostics")

def toggle_diagnostics():
    if diagnostics_visible.get():
        hide_diagnostics()
    else:
        show_diagnostics()

def apply_startup_diagnostics(results):
    formatted = format_diagnostics(results)
    summary, _, details = formatted.partition("\n")
    color = diagnostics_color(results)
    diagnostics_summary_label.config(text=summary, foreground=color)
    diagnostics_text.config(state=tk.NORMAL)
    diagnostics_text.delete("1.0", tk.END)
    diagnostics_text.insert("1.0", details)
    diagnostics_text.config(state=tk.DISABLED)

    if any(result["status"] != "pass" for result in results):
        show_diagnostics()

def run_startup_diagnostics_async():
    diagnostics_summary_label.config(text="Diagnostics: checking...", foreground="#333333")
    diagnostics_text.config(state=tk.NORMAL)
    diagnostics_text.delete("1.0", tk.END)
    diagnostics_text.config(state=tk.DISABLED)

    def worker():
        results = run_startup_diagnostics()
        queue_ui("diagnostics", results)

    threading.Thread(target=worker, daemon=True).start()

class DownloadCancelled(Exception):
    pass

def queue_ui(action, *args):
    ui_queue.put((action, args))

def process_ui_queue():
    while True:
        try:
            action, args = ui_queue.get_nowait()
        except queue.Empty:
            break

        if action == "diagnostics":
            apply_startup_diagnostics(*args)
        elif action == "status":
            status_label.config(text=args[0])
        elif action == "media_info_results":
            apply_media_info_results(*args)
        elif action == "download_done":
            update_ui_after_download(*args)

    if not is_closing or download_is_active():
        root.after(100, process_ui_queue)

def queue_status(text):
    queue_ui("status", text)

def download_is_active():
    return download_thread is not None and download_thread.is_alive()

def set_download_button_enabled(enabled):
    if "download_button" in globals():
        if enabled:
            download_button.config(state=tk.NORMAL, bg="#1f8f4d", cursor="hand2")
        else:
            download_button.config(state=tk.DISABLED, bg="#8aa99a", cursor="")

def set_quality_state(enabled):
    if "resolution_dropdown" not in globals() or "audio_format_dropdown" not in globals():
        return

    if audio_only.get():
        audio_format_dropdown.config(state="readonly")
        resolution_dropdown.config(state="disabled")
    else:
        audio_format_dropdown.config(state="disabled")
        resolution_dropdown.config(state="readonly" if enabled else "disabled")

def set_link_ready(is_ready, status_text=None):
    global url_ready_for_download
    url_ready_for_download = is_ready
    set_download_button_enabled(is_ready and not download_is_active())
    set_quality_state(is_ready)

    if status_text is not None:
        status_label.config(text=status_text)

def output_template_path(temp_dir, media_title):
    safe_title = media_title.replace("%", "%%")
    return os.path.join(temp_dir, f"{safe_title}.%(ext)s")

def unique_destination_path(directory, filename):
    base_name, extension = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1

    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base_name} ({counter}){extension}")
        counter += 1

    return candidate

def find_downloaded_file(temp_dir, media_title, preferred_extension, alternate_extensions=()):
    extensions = [preferred_extension.lower()]
    extensions.extend(extension.lower() for extension in alternate_extensions)

    for extension in extensions:
        expected_path = os.path.join(temp_dir, f"{media_title}.{extension}")
        if os.path.exists(expected_path):
            return expected_path

    candidates = []
    for entry in os.listdir(temp_dir):
        path = os.path.join(temp_dir, entry)
        if not os.path.isfile(path):
            continue

        extension = os.path.splitext(entry)[1].lstrip(".").lower()
        if extension in extensions:
            candidates.append(path)

    if candidates:
        return max(candidates, key=os.path.getmtime)

    files = [os.path.join(temp_dir, entry) for entry in os.listdir(temp_dir)]
    files = [path for path in files if os.path.isfile(path)]
    if len(files) == 1:
        return files[0]

    raise FileNotFoundError(f"Could not find downloaded .{preferred_extension} file")

def ensure_extension(filepath, extension):
    if filepath.lower().endswith(f".{extension.lower()}"):
        return filepath

    directory = os.path.dirname(filepath)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    renamed_path = unique_destination_path(directory, f"{base_name}.{extension}")
    os.rename(filepath, renamed_path)
    return renamed_path

def cleanup_temp_dir(temp_dir, cleanup_enabled):
    if cleanup_enabled and temp_dir and os.path.isdir(temp_dir):
        print("Cleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)

def upload_date_to_timestamp(upload_date):
    if not upload_date:
        return None

    try:
        return datetime.strptime(upload_date, "%Y%m%d").timestamp()
    except ValueError:
        return None

def video_format_for_resolution(resolution):
    if resolution == "Highest Available":
        return "bestvideo*+bestaudio/best"

    match = re.search(r"(\d+)", resolution or "")
    if not match:
        return "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best[height<=1080]/best"

    height = int(match.group(1))
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best[height<={height}]/best"

def open_download_folder():
    """ Opens the download folder in File Explorer. """
    folder_path = output_directory  # Use the configured output directory

    try:
        if sys.platform == "win32":
            os.startfile(folder_path)  # ✅ Windows
        elif sys.platform == "darwin":  # macOS
            subprocess.call(["open", folder_path])
        else:  # Linux
            subprocess.call(["xdg-open", folder_path])
    except Exception as e:
        print(f"❌ Error opening folder: {e}")
        messagebox.showerror("Error", "Could not open the download folder.")

def select_output_folder():
    """ Opens a dialog for the user to select an output folder. """
    global output_directory
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        output_directory = folder_selected
        folder_label.config(text=f"Save to: {output_directory}")
        save_settings()

def set_resolution(value):
    """ Updates the selected resolution. """
    global selected_resolution
    selected_resolution = value
    if "resolution_menu" in globals():
        resolution_menu.set(value)
    save_settings()
    print(f"New Resolution: {selected_resolution}, Value: {value}")

def toggle_audio_mode():
    """ Enables or disables audio-only mode and format selection. """
    if audio_only.get():
        resolution_label.grid_remove()
        resolution_dropdown.grid_remove()
        audio_format_label.grid()
        audio_format_dropdown.grid()
    else:
        audio_format_label.grid_remove()
        audio_format_dropdown.grid_remove()
        resolution_label.grid()
        resolution_dropdown.grid()
    set_quality_state(url_ready_for_download)
    save_settings()

def clean_text(text):
    """ Removes unwanted ANSI escape codes from yt-dlp output. """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def format_duration(duration_seconds):
    if duration_seconds is None:
        return "Length: Unknown"

    try:
        total_seconds = int(duration_seconds)
    except (TypeError, ValueError):
        return "Length: Unknown"

    if total_seconds < 0:
        return "Length: Unknown"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        duration_parts = [f"{hours} hr"]
        if minutes or seconds:
            duration_parts.append(f"{minutes} min")
        if seconds:
            duration_parts.append(f"{seconds} sec")
    elif minutes:
        duration_parts = [f"{minutes} min"]
        if seconds:
            duration_parts.append(f"{seconds} sec")
    else:
        duration_parts = [f"{seconds} sec"]

    return f"Length: {' '.join(duration_parts)}"

def format_upload_date(upload_date):
    if not upload_date:
        return ""

    try:
        return datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""

def clean_metadata_value(value):
    if not value:
        return ""
    return clean_text(str(value)).strip()

def format_live_status(info_dict):
    if info_dict.get("is_live"):
        return "Status: Live"

    live_status = info_dict.get("live_status")
    status_labels = {
        "is_live": "Status: Live",
        "is_upcoming": "Status: Upcoming",
        "was_live": "Status: Past live stream",
    }
    return status_labels.get(live_status, "")

def format_preview_details(media_info):
    details = []

    channel = media_info.get("channel")
    if channel:
        details.append(f"Channel: {channel}")

    upload_date_text = media_info.get("upload_date_text")
    if upload_date_text:
        details.append(f"Uploaded: {upload_date_text}")

    status_text = media_info.get("status_text")
    if status_text:
        details.append(status_text)

    return " | ".join(details)

def thumbnail_sort_key(thumbnail):
    try:
        width = int(thumbnail.get("width") or 0)
        height = int(thumbnail.get("height") or 0)
    except (TypeError, ValueError):
        width = 0
        height = 0
    preference = 1 if width >= PREVIEW_IMAGE_SIZE[0] and height >= PREVIEW_IMAGE_SIZE[1] else 0
    return preference, width * height, width, height

def best_thumbnail_url(info_dict):
    thumbnails = info_dict.get("thumbnails")
    if isinstance(thumbnails, list):
        valid_thumbnails = [
            thumbnail
            for thumbnail in thumbnails
            if isinstance(thumbnail, dict) and thumbnail.get("url")
        ]
        if valid_thumbnails:
            return max(valid_thumbnails, key=thumbnail_sort_key)["url"]

    return info_dict.get("thumbnail")

def download_thumbnail_bytes(thumbnail_url):
    if not thumbnail_url:
        return None

    try:
        with urllib.request.urlopen(thumbnail_url, timeout=5) as response:
            thumbnail_bytes = response.read(MAX_THUMBNAIL_BYTES + 1)
    except Exception as e:
        print(f"Could not load preview thumbnail: {e}")
        return None

    if len(thumbnail_bytes) > MAX_THUMBNAIL_BYTES:
        print("Could not load preview thumbnail: image too large")
        return None

    return thumbnail_bytes

def extract_available_resolutions(info_dict):
    available_resolutions = set()

    for video_format in info_dict.get("formats") or []:
        try:
            height = int(video_format.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        if height > 0:
            available_resolutions.add(f"{height}p")

    return sorted(available_resolutions, key=lambda value: int(value.replace("p", "")), reverse=True)

def build_media_info(url, info_dict):
    title = clean_text(info_dict.get("title") or "Untitled video")
    thumbnail_url = best_thumbnail_url(info_dict)
    upload_date = info_dict.get("upload_date")

    return {
        "url": url,
        "title": title,
        "channel": clean_metadata_value(info_dict.get("channel") or info_dict.get("uploader")),
        "duration": info_dict.get("duration"),
        "duration_text": format_duration(info_dict.get("duration")),
        "thumbnail_url": thumbnail_url,
        "thumbnail_bytes": download_thumbnail_bytes(thumbnail_url),
        "resolutions": extract_available_resolutions(info_dict) or ["Highest Available"],
        "upload_date": upload_date,
        "upload_date_text": format_upload_date(upload_date),
        "status_text": format_live_status(info_dict),
    }

def create_preview_photo(image_bytes):
    source_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    source_image = ImageOps.contain(source_image, PREVIEW_IMAGE_SIZE, Image.Resampling.LANCZOS)

    preview_image = Image.new("RGB", PREVIEW_IMAGE_SIZE, "#f0f0f0")
    x = (PREVIEW_IMAGE_SIZE[0] - source_image.width) // 2
    y = (PREVIEW_IMAGE_SIZE[1] - source_image.height) // 2
    preview_image.paste(source_image, (x, y))
    return ImageTk.PhotoImage(preview_image)

def update_preview_wraplength(event=None):
    if "preview_frame" not in globals() or "preview_details_label" not in globals():
        return

    frame_width = preview_frame.winfo_width()
    if not frame_width:
        return

    if preview_image_label.winfo_ismapped():
        wraplength = max(260, frame_width - PREVIEW_IMAGE_SIZE[0] - 48)
    else:
        wraplength = max(260, frame_width - 24)

    preview_title_label.config(wraplength=wraplength)
    preview_duration_label.config(wraplength=wraplength)
    preview_details_label.config(wraplength=wraplength)

def set_preview_text(title_text, duration_text="", details_text=""):
    global preview_photo_image

    if "preview_image_label" not in globals():
        return

    preview_photo_image = None
    preview_image_label.config(image="", text="")
    preview_image_label.grid_remove()

    preview_title_label.grid_configure(row=0, column=0, columnspan=2, sticky="ew")
    preview_title_label.config(text=title_text)

    if duration_text:
        preview_duration_label.grid_configure(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        preview_duration_label.config(text=duration_text)
        preview_duration_label.grid()
    else:
        preview_duration_label.config(text="")
        preview_duration_label.grid_remove()

    if details_text:
        preview_details_label.grid_configure(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        preview_details_label.config(text=details_text)
        preview_details_label.grid()
    else:
        preview_details_label.config(text="")
        preview_details_label.grid_remove()

    update_preview_wraplength()

def set_preview_with_image(photo_image, title_text, duration_text, details_text):
    global preview_photo_image

    if "preview_image_label" not in globals():
        return

    preview_photo_image = photo_image
    preview_image_label.config(image=preview_photo_image, text="")
    preview_image_label.grid(row=0, column=0, rowspan=3, sticky="w", padx=(0, 12))

    preview_title_label.grid_configure(row=0, column=1, columnspan=1, sticky="new")
    preview_title_label.config(text=title_text)

    preview_duration_label.grid_configure(row=1, column=1, columnspan=1, sticky="new", pady=(6, 0))
    preview_duration_label.config(text=duration_text)
    preview_duration_label.grid()

    if details_text:
        preview_details_label.grid_configure(row=2, column=1, columnspan=1, sticky="new", pady=(4, 0))
        preview_details_label.config(text=details_text)
        preview_details_label.grid()
    else:
        preview_details_label.config(text="")
        preview_details_label.grid_remove()

    update_preview_wraplength()

def reset_media_preview():
    set_preview_text("Nothing to preview")

def show_preview_loading():
    set_preview_text("Checking source...")

def show_preview_error():
    set_preview_text("Preview unavailable", "Link check failed.")

def apply_media_preview(media_info):
    if "preview_image_label" not in globals():
        return

    title_text = media_info.get("title") or "Untitled video"
    duration_text = media_info.get("duration_text") or "Length: Unknown"
    details_text = format_preview_details(media_info)

    thumbnail_bytes = media_info.get("thumbnail_bytes")
    if thumbnail_bytes:
        try:
            set_preview_with_image(
                create_preview_photo(thumbnail_bytes),
                title_text,
                duration_text,
                details_text,
            )
            return
        except Exception as e:
            print(f"Could not render preview thumbnail: {e}")

    set_preview_text(title_text, duration_text, details_text)

def make_progress_hook(cancel_event):
    """Creates a yt-dlp hook that reports progress through the main UI queue."""
    def hook(d):
        if cancel_event.is_set():
            raise DownloadCancelled("Download cancelled")

        if d["status"] == "downloading":
            percent = clean_text(d.get("_percent_str", "0%"))
            speed = clean_text(d.get("_speed_str", "N/A"))
            eta = clean_text(d.get("_eta_str", "Unknown"))
            queue_status(f"Progress: {percent}\nSpeed: {speed}\nETA: {eta}")
        elif d["status"] == "finished":
            queue_status("Processing downloaded file...")
        else:
            queue_status("Working...")

    return hook

def download_video_gui():
    """
    Function triggered when the Download button is clicked.
    """
    global download_thread, download_cancel_event

    url = url_entry.get().strip()

    if not url:
        messagebox.showerror("Error", "Please enter a YouTube URL")
        return

    if not url_ready_for_download:
        messagebox.showwarning("Link Not Ready", "Please wait until the link has been checked.")
        return

    if download_is_active():
        messagebox.showwarning("Download In Progress", "Please wait for the current download to finish.")
        return

    media_info = latest_media_info if latest_media_info and latest_media_info.get("url") == url else None
    download_settings = {
        "url": url,
        "output_dir": output_directory,
        "resolution": selected_resolution,
        "is_audio_only": audio_only.get(),
        "audio_format": selected_audio_format.get().lower(),
        "cleanup_enabled": delete_temp_files.get(),
        "preserve_upload_date": preserve_upload_date.get(),
        "media_title": media_info.get("title") if media_info else None,
        "upload_date": media_info.get("upload_date") if media_info else None,
    }
    download_cancel_event = threading.Event()

    # Disable the button to prevent multiple clicks
    set_download_button_enabled(False)
    status_label.config(text="Connecting...")

    # Run the download in a separate thread
    download_thread = threading.Thread(
        target=download_video_thread,
        args=(download_settings, download_cancel_event),
    )
    download_thread.start()

def update_resolution_options(*args):
    """Debounces media metadata fetching while the URL is being edited."""
    global fetch_delay, fetch_request_id, latest_media_info
    url = url_entry.get().strip()

    if fetch_delay:
        root.after_cancel(fetch_delay)
        fetch_delay = None

    if not url:
        fetch_request_id += 1
        latest_media_info = None
        set_link_ready(False, "")
        reset_media_preview()
        if "resolution_menu" in globals():
            resolution_menu.set(selected_resolution)
        status_label.config(text="")
        return

    fetch_request_id += 1
    request_id = fetch_request_id
    latest_media_info = None
    set_link_ready(False, "Checking link...")
    show_preview_loading()
    if not audio_only.get():
        resolution_menu.set("Checking...")
    fetch_delay = root.after(500, lambda: start_media_info_fetch(request_id, url))

def start_media_info_fetch(request_id, url):
    global fetch_delay
    fetch_delay = None

    if request_id != fetch_request_id:
        return

    set_link_ready(False, "Checking link...")
    show_preview_loading()
    if not audio_only.get():
        resolution_menu.set("Checking...")

    threading.Thread(
        target=fetch_media_info_thread,
        args=(request_id, url),
        daemon=True,
    ).start()

def fetch_media_info_thread(request_id, url):
    media_info, error_message = fetch_media_info(url)
    queue_ui("media_info_results", request_id, url, media_info, error_message)

def apply_media_info_results(request_id, url, media_info, error_message=None):
    global latest_media_info

    if request_id != fetch_request_id or url != url_entry.get().strip():
        return

    if error_message:
        latest_media_info = None
        if not audio_only.get():
            resolution_menu.set("Unavailable")
        show_preview_error()
        set_link_ready(False, f"Link check failed\n{error_message}")
        return

    if not media_info:
        latest_media_info = None
        if not audio_only.get():
            resolution_menu.set("Unavailable")
        set_link_ready(False, "Link check failed\nNo video metadata returned.")
        show_preview_error()
        return

    latest_media_info = media_info
    resolutions = media_info.get("resolutions") if media_info else None
    if not resolutions:
        resolutions = ["Highest Available"]

    resolution_dropdown.config(values=resolutions)

    preferred_resolution = selected_resolution if selected_resolution in resolutions else resolutions[0]
    set_resolution(preferred_resolution)
    apply_media_preview(media_info)
    set_link_ready(True, "Ready to download.")

def fetch_media_info(url):
    """Fetches preview metadata and available video resolutions for a URL."""
    try:
        with yt_dlp.YoutubeDL(create_ytdlp_options()) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return build_media_info(url, info_dict), None
    except Exception as e:
        error_message = clean_text(str(e)) or e.__class__.__name__
        print(f"❌ Error fetching media info: {error_message}")
        return None, error_message

def download_video_thread(download_settings, cancel_event):
    """ Runs the video download process in a separate thread. """
    success, error_message, final_path = download_video(download_settings, cancel_event)
    queue_ui("download_done", success, error_message, final_path)

def update_ui_after_download(success, error_message=None, final_path=None):
    """ Updates the UI after the download is completed. """
    global download_thread, download_cancel_event

    download_thread = None
    download_cancel_event = None

    if is_closing:
        root.destroy()
        return

    if success:
        status_label.config(text="Download complete")
        messagebox.showinfo("Download Complete", f"File saved to:\n{final_path}")
        open_download_folder()
    else:
        details = error_message or "Unknown error"
        status_label.config(text=f"Download failed\n{details}")
        if details != "Download cancelled":
            messagebox.showerror("Download Failed", details)

    set_download_button_enabled(url_ready_for_download)

def download_video(download_settings, cancel_event):
    """ Downloads a YouTube video or extracts audio based on user selection. """
    url = download_settings["url"]
    output_dir = download_settings["output_dir"]
    resolution = download_settings["resolution"]
    is_audio_only = download_settings["is_audio_only"]
    audio_format = download_settings["audio_format"]
    cleanup_enabled = download_settings["cleanup_enabled"]
    preserve_upload_date_setting = download_settings["preserve_upload_date"]
    media_title = sanitize_filename(download_settings.get("media_title") or "")
    upload_date = download_settings.get("upload_date")

    print(f"🎥 Fetching media... Audio Only: {is_audio_only}")

    # Use a temporary directory for processing
    temp_dir = tempfile.mkdtemp()

    # If the user has not changed the output folder, use the default folder
    if output_dir == os.getcwd():
        output_dir = default_output_folder

    # Ensure the output folder exists
    os.makedirs(output_dir, exist_ok=True)

    try:
        if cancel_event.is_set():
            raise DownloadCancelled("Download cancelled")

        if not media_title or (preserve_upload_date_setting and not upload_date):
            with yt_dlp.YoutubeDL(create_ytdlp_options()) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                if not media_title:
                    media_title = sanitize_filename(info_dict.get("title", "output"))
                if not upload_date:
                    upload_date = info_dict.get("upload_date")

        if not media_title:
            media_title = "output"

        progress = make_progress_hook(cancel_event)
        output_template = output_template_path(temp_dir, media_title)

        if is_audio_only:
            ydl_opts = create_ytdlp_options({
                'format': 'bestaudio/best',  # Download best audio only
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_format,
                    'preferredquality': '192',
                }],
                'fragment_retries': 10,
                'concurrent_fragments': 5,
                'progress_hooks': [progress],
            })

        else:
            print("🛠️ VIDEO MODE DETECTED")
            selected_format = video_format_for_resolution(resolution)
            print(f"Resolution Selected: {resolution}, Format Selected: {selected_format}")

            ydl_opts = create_ytdlp_options({
                'format': selected_format,
                'merge_output_format': 'mp4',
                'outtmpl': output_template,
                'postprocessor_args': [
                    '-c:a', 'aac',  # Convert audio to AAC (Windows-compatible)
                    '-b:a', '192k',  # Set audio bitrate to 192kbps for good quality
                    '-c:v', 'copy'  # Keep video unchanged (no re-encoding)
                ],
                'fragment_retries': 10,
                'concurrent_fragments': 5,
                'progress_hooks': [progress],
            })

        print("⏬ Starting yt-dlp download...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print("✅ yt-dlp download finished")
        print(f"📂 Temp directory contents: {os.listdir(temp_dir)}")

        if is_audio_only:
            alternate_extensions = ("m4a",) if audio_format == "aac" else ()
            final_file = find_downloaded_file(temp_dir, media_title, audio_format, alternate_extensions)
            final_file = ensure_extension(final_file, audio_format)
        else:
            final_file = find_downloaded_file(temp_dir, media_title, "mp4")
            final_file = ensure_extension(final_file, "mp4")

        # Check file codecs after download
        probe_cmd = [
            runtime_binary_path("ffprobe") or "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,codec_name", "-of", "default=noprint_wrappers=1",
            final_file
        ]
        print("🔍 Running ffprobe to inspect output file:")
        try:
            result = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            print(result.stdout)
        except Exception as e:
            print(f"⚠️ ffprobe failed: {e}")

        final_path = unique_destination_path(output_dir, os.path.basename(final_file))
        shutil.move(final_file, final_path)

        print(f"✅ Download complete: {final_path}")

        finalize_download(final_path, upload_date, preserve_upload_date_setting)

        return True, None, final_path

    except DownloadCancelled as e:
        print(f"Download cancelled: {e}")
        return False, str(e), None
    except Exception as e:
        error_message = clean_text(str(e)) or e.__class__.__name__
        print(f"❌ Error downloading media: {error_message}")
        return False, error_message, None
    finally:
        cleanup_temp_dir(temp_dir, cleanup_enabled)

def preserve_date_created(filepath, created_time):
    """ Restores the original 'Date Created' timestamp on Windows. """
    if platform.system() == "Windows":
        try:
            # Windows API call to set file creation time
            ctime = ctypes.windll.kernel32.SetFileTime
            handle = ctypes.windll.kernel32.CreateFileW(
                filepath, 256, 0, None, 3, 128, None
            )
            if handle != -1:
                ctime(handle, ctypes.byref(ctypes.c_ulonglong(int(created_time * 10000000 + 116444736000000000))))
                ctypes.windll.kernel32.CloseHandle(handle)
                print(f"✅ Restored 'Date Created' on Windows: {time.ctime(created_time)}")
        except Exception as e:
            print(f"⚠️ Could not restore 'Date Created': {e}")

def finalize_download(final_path, upload_date, preserve_upload_date_setting):
    """Applies final filesystem metadata after a successful download."""
    if not preserve_upload_date_setting:
        return

    upload_timestamp = upload_date_to_timestamp(upload_date)
    if not upload_timestamp:
        return

    try:
        os.utime(final_path, (upload_timestamp, upload_timestamp))
        preserve_date_created(final_path, upload_timestamp)
        print(f"✅ File timestamps updated from upload date: {upload_date}")
    except Exception as e:
        print(f"❌ Error updating timestamps: {e}")

def sanitize_filename(filename):
    """ Removes or replaces invalid characters in filenames """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)  # Replaces invalid characters with "_"

# Function to clear the URL entry box
def clear_url():
    url_entry.delete(0, tk.END)
    update_resolution_options()

def insert_test_url():
    clear_url()
    url_entry.insert(0, TEST_URL)
    update_resolution_options()

def paste_url_from_clipboard():
    try:
        clipboard_text = root.clipboard_get().strip()
    except tk.TclError:
        messagebox.showwarning("Clipboard Empty", "No text found in the clipboard.")
        return

    if not clipboard_text:
        messagebox.showwarning("Clipboard Empty", "No text found in the clipboard.")
        return

    clear_url()
    url_entry.insert(0, clipboard_text)
    update_resolution_options()

def handle_paste_event(event=None):
    root.after(10, update_resolution_options)

def select_all_url(event=None):
    url_entry.select_range(0, tk.END)
    url_entry.icursor(tk.END)
    return "break"

def delete_previous_word(event=None):
    cursor_position = url_entry.index(tk.INSERT)
    text = url_entry.get()
    start = cursor_position

    while start > 0 and text[start - 1].isspace():
        start -= 1

    while start > 0 and not text[start - 1].isspace():
        start -= 1

    if start != cursor_position:
        url_entry.delete(start, cursor_position)
        update_resolution_options()

    return "break"

def handle_control_keypress(event):
    if not event.state & 0x4:
        return None

    if event.keycode == 65:
        return select_all_url(event)

    if event.keycode == 86:
        paste_url_from_clipboard()
        return "break"

    if event.keysym == "BackSpace" or event.keycode == 8:
        return delete_previous_word(event)

    return None

def reset_output_folder():
    global output_directory
    output_directory = default_output_folder
    os.makedirs(output_directory, exist_ok=True)
    folder_label.config(text=f"Save to: {output_directory}")
    save_settings()

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tip_window or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            padx=6,
            pady=4,
            wraplength=280,
        )
        label.pack()

    def hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

def on_close():
    global is_closing

    save_settings()

    if download_is_active():
        is_closing = True
        if download_cancel_event:
            download_cancel_event.set()
        status_label.config(text="Canceling active download and cleaning up...")
        download_button.config(state=tk.DISABLED)
        return

    root.destroy()

def update_page_scroll_region(event=None):
    if "page_canvas" in globals():
        page_canvas.configure(scrollregion=page_canvas.bbox("all"))

def update_page_width(event):
    if "page_window" in globals():
        page_canvas.itemconfigure(page_window, width=event.width)

def handle_page_mousewheel(event):
    if "page_canvas" not in globals():
        return None

    if getattr(event, "num", None) == 4:
        scroll_units = -3
    elif getattr(event, "num", None) == 5:
        scroll_units = 3
    elif getattr(event, "delta", 0):
        scroll_units = -3 if event.delta > 0 else 3
    else:
        return None

    page_canvas.yview_scroll(scroll_units, "units")
    return None

# GUI Setup
root = tk.Tk()
root.title(APP_NAME)
root.geometry("760x650")
root.minsize(700, 500)
set_app_icon(root)

try:
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    style.configure("TButton", padding=(8, 4))
except tk.TclError:
    pass

delete_temp_files = tk.BooleanVar(value=bool(saved_settings.get("delete_temp_files", True)))
preserve_upload_date = tk.BooleanVar(value=bool(saved_settings.get("preserve_upload_date", True)))
audio_only = tk.BooleanVar(value=bool(saved_settings.get("audio_only", False)))
saved_audio_format = saved_settings.get("audio_format")
selected_audio_format = tk.StringVar(value=saved_audio_format if saved_audio_format in AUDIO_FORMATS else DEFAULT_AUDIO_FORMAT)
diagnostics_visible = tk.BooleanVar(value=False)
preview_photo_image = None

page_container = ttk.Frame(root)
page_container.pack(fill=tk.BOTH, expand=True)
page_container.columnconfigure(0, weight=1)
page_container.rowconfigure(0, weight=1)

page_canvas = tk.Canvas(page_container, borderwidth=0, highlightthickness=0)
page_canvas.grid(row=0, column=0, sticky="nsew")

page_scrollbar = ttk.Scrollbar(page_container, orient=tk.VERTICAL, command=page_canvas.yview)
page_scrollbar.grid(row=0, column=1, sticky="ns")
page_canvas.configure(yscrollcommand=page_scrollbar.set)

main_frame = ttk.Frame(page_canvas, padding=14)
page_window = page_canvas.create_window((0, 0), window=main_frame, anchor="nw")
main_frame.bind("<Configure>", update_page_scroll_region)
page_canvas.bind("<Configure>", update_page_width)
root.bind_all("<MouseWheel>", handle_page_mousewheel, add="+")
root.bind_all("<Button-4>", handle_page_mousewheel, add="+")
root.bind_all("<Button-5>", handle_page_mousewheel, add="+")
main_frame.columnconfigure(0, weight=1)

source_frame = ttk.LabelFrame(main_frame, text="Source", padding=10)
source_frame.grid(row=0, column=0, sticky="ew")
source_frame.columnconfigure(0, weight=1)

url_frame = ttk.Frame(source_frame)
url_frame.grid(row=0, column=0, sticky="ew")
url_frame.columnconfigure(0, weight=1)

url_entry = ttk.Entry(url_frame)
url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
url_entry.bind("<KeyRelease>", update_resolution_options)
url_entry.bind("<<Paste>>", handle_paste_event, add="+")
url_entry.bind("<Control-KeyPress>", handle_control_keypress)
url_entry.bind("<Control-a>", select_all_url)
url_entry.bind("<Control-A>", select_all_url)
url_entry.bind("<Control-BackSpace>", delete_previous_word)

paste_button = ttk.Button(url_frame, text="Paste", command=paste_url_from_clipboard)
paste_button.grid(row=0, column=1, padx=(0, 6))

clear_button = ttk.Button(url_frame, text="Clear", command=clear_url)
clear_button.grid(row=0, column=2, padx=(0, 6))

test_link_button = ttk.Button(url_frame, text="Test", command=insert_test_url)
test_link_button.grid(row=0, column=3, padx=(0, 6))

fetch_resolution_button = ttk.Button(url_frame, text="Check", command=update_resolution_options)
fetch_resolution_button.grid(row=0, column=4)

preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding=10)
preview_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
preview_frame.columnconfigure(1, weight=1)
preview_frame.bind("<Configure>", update_preview_wraplength)

preview_image_label = tk.Label(
    preview_frame,
    bg="#f0f0f0",
    relief=tk.SOLID,
    borderwidth=1,
    width=PREVIEW_IMAGE_SIZE[0],
    height=PREVIEW_IMAGE_SIZE[1],
    anchor=tk.CENTER,
)

preview_title_label = ttk.Label(
    preview_frame,
    text="Nothing to preview",
    wraplength=470,
    justify=tk.LEFT,
    font=("Segoe UI", 10, "bold"),
)
preview_title_label.grid(row=0, column=1, sticky="new")

preview_duration_label = ttk.Label(preview_frame, text="", wraplength=470, justify=tk.LEFT)
preview_duration_label.grid(row=1, column=1, sticky="new", pady=(6, 0))

preview_details_label = ttk.Label(preview_frame, text="", wraplength=470, justify=tk.LEFT)
preview_details_label.grid(row=2, column=1, sticky="new", pady=(4, 0))

download_frame = ttk.LabelFrame(main_frame, text="Download", padding=10)
download_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
download_frame.columnconfigure(1, weight=1)

audio_checkbox = ttk.Checkbutton(download_frame, text="Audio only", variable=audio_only, command=toggle_audio_mode)
audio_checkbox.grid(row=0, column=0, sticky="w", columnspan=2)

quality_frame = ttk.Frame(download_frame)
quality_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
quality_frame.columnconfigure(1, weight=1)

resolution_options = list(RESOLUTION_OPTIONS)
if selected_resolution not in resolution_options:
    resolution_options.insert(1, selected_resolution)
resolution_menu = tk.StringVar(root, value=selected_resolution)
resolution_label = ttk.Label(quality_frame, text="Quality")
resolution_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
resolution_dropdown = ttk.Combobox(
    quality_frame,
    textvariable=resolution_menu,
    values=resolution_options,
    state="disabled",
    width=22,
)
resolution_dropdown.grid(row=0, column=1, sticky="w")
resolution_dropdown.bind("<<ComboboxSelected>>", lambda event: set_resolution(resolution_menu.get()))

audio_format_label = ttk.Label(quality_frame, text="Format")
audio_format_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
audio_format_dropdown = ttk.Combobox(
    quality_frame,
    textvariable=selected_audio_format,
    values=AUDIO_FORMATS,
    state="disabled",
    width=22,
)
audio_format_dropdown.grid(row=0, column=1, sticky="w")
audio_format_dropdown.bind("<<ComboboxSelected>>", lambda event: save_settings())

options_frame = ttk.Frame(download_frame)
options_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

cleanup_checkbox = ttk.Checkbutton(
    options_frame,
    text="Delete temp files after download",
    variable=delete_temp_files,
    command=save_settings,
)
cleanup_checkbox.grid(row=0, column=0, sticky="w", padx=(0, 18))

timestamp_checkbox = ttk.Checkbutton(
    options_frame,
    text="Preserve upload date",
    variable=preserve_upload_date,
    command=save_settings,
)
timestamp_checkbox.grid(row=0, column=1, sticky="w")
ToolTip(timestamp_checkbox, "When enabled, downloaded files use the video's upload date for file timestamps. Turn it off to keep today's download time.")
ToolTip(test_link_button, "Insert a tiny test video link.")

destination_frame = ttk.LabelFrame(main_frame, text="Destination", padding=10)
destination_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
destination_frame.columnconfigure(0, weight=1)

folder_label = ttk.Label(destination_frame, text=f"Save to: {output_directory}", wraplength=680)
folder_label.grid(row=0, column=0, columnspan=3, sticky="ew")

folder_button = ttk.Button(destination_frame, text="Choose Folder", command=select_output_folder)
folder_button.grid(row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 6))

default_folder_button = ttk.Button(destination_frame, text="Use Downloads", command=reset_output_folder)
default_folder_button.grid(row=1, column=1, sticky="w", pady=(8, 0), padx=(0, 6))

open_folder_button = ttk.Button(destination_frame, text="Open Folder", command=open_download_folder)
open_folder_button.grid(row=1, column=2, sticky="w", pady=(8, 0))

actions_frame = ttk.Frame(main_frame)
actions_frame.grid(row=4, column=0, sticky="ew", pady=(14, 0))
actions_frame.columnconfigure(0, weight=1)

download_button = tk.Button(
    actions_frame,
    text="Download",
    command=download_video_gui,
    bg="#1f8f4d",
    fg="white",
    activebackground="#18743f",
    activeforeground="white",
    disabledforeground="#d8e9df",
    padx=28,
    pady=6,
    relief=tk.RAISED,
    cursor="hand2",
)
download_button.grid(row=0, column=0)

status_frame = ttk.LabelFrame(main_frame, text="Status", padding=10)
status_frame.grid(row=5, column=0, sticky="nsew", pady=(12, 0))
status_frame.columnconfigure(0, weight=1)
status_frame.rowconfigure(2, weight=1)
main_frame.rowconfigure(5, weight=1)

status_label = ttk.Label(status_frame, text="", wraplength=680, justify=tk.LEFT)
status_label.grid(row=0, column=0, sticky="ew")

diagnostics_header = ttk.Frame(status_frame)
diagnostics_header.grid(row=1, column=0, sticky="ew", pady=(8, 0))
diagnostics_header.columnconfigure(1, weight=1)

diagnostics_button = ttk.Button(
    diagnostics_header,
    text="Show Diagnostics",
    command=toggle_diagnostics,
)
diagnostics_button.grid(row=0, column=0, sticky="w", padx=(0, 8))

diagnostics_summary_label = ttk.Label(diagnostics_header, text="Diagnostics: checking...")
diagnostics_summary_label.grid(row=0, column=1, sticky="w")

diagnostics_panel = ttk.Frame(status_frame)
diagnostics_panel.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
diagnostics_panel.columnconfigure(0, weight=1)
diagnostics_panel.rowconfigure(0, weight=1)

diagnostics_text = tk.Text(
    diagnostics_panel,
    height=6,
    wrap=tk.WORD,
    borderwidth=1,
    relief=tk.SOLID,
    font=("Consolas", 9),
)
diagnostics_text.grid(row=0, column=0, sticky="nsew")

diagnostics_scrollbar = ttk.Scrollbar(diagnostics_panel, orient=tk.VERTICAL, command=diagnostics_text.yview)
diagnostics_scrollbar.grid(row=0, column=1, sticky="ns")
diagnostics_text.configure(yscrollcommand=diagnostics_scrollbar.set, state=tk.DISABLED)
hide_diagnostics()

reset_media_preview()
toggle_audio_mode()
set_link_ready(False)
root.protocol("WM_DELETE_WINDOW", on_close)
process_ui_queue()
run_startup_diagnostics_async()

root.mainloop()
