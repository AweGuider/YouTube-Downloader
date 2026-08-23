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
from tkinter import filedialog, messagebox
import threading
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime

### TODO:
# - Can't paste with a different keyboard layout like Russian for example
# - Add button to Paste link from clipboard (clear + insert from clipboard)
# - Change application Icon
# - Improve UI instead of everything being from top to bottom, make similar groups like for URL
# - Add a button to choose default Download Folder as the one in the Downloads/YouTubeDownloads
# - (Skip) Stop merging

### Command to create .exe out of .py
# python -m PyInstaller --onefile downloader.py

### For testing
# 1080p - https://www.youtube.com/watch?v=ps74zeevi-g
# 720p - https://www.youtube.com/watch?v=cUM8OCBy6Ls

# Auto-fill test URL (Replace with any default video link)
default_url = "https://www.youtube.com/watch?v=ps74zeevi-g"

# Default output directory (current folder)
# Set default output folder to "Downloads/YouTubeDownloads/"
default_output_folder = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloads")
# Ensure the folder exists
os.makedirs(default_output_folder, exist_ok=True)
# Use this as the initial output directory
output_directory = default_output_folder

selected_resolution = "1080p"  # Default resolution

fetch_delay = None  # Global variable to track scheduled fetch calls
fetch_request_id = 0
download_thread = None
download_cancel_event = None
is_closing = False
ui_queue = queue.Queue()

# For future implementation of stable progress UI update
latest_progress = {"percent": "0%", "speed": "N/A", "eta": "Unknown"}

APP_VERSION = "0.1.0-dev"
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

def apply_startup_diagnostics(results):
    diagnostics_label.config(text=format_diagnostics(results), fg=diagnostics_color(results))

def run_startup_diagnostics_async():
    diagnostics_label.config(text="Diagnostics: checking...", fg="#333333")

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
        elif action == "resolution_results":
            apply_resolution_results(*args)
        elif action == "download_done":
            update_ui_after_download(*args)

    if not is_closing or download_is_active():
        root.after(100, process_ui_queue)

def queue_status(text):
    queue_ui("status", text)

def download_is_active():
    return download_thread is not None and download_thread.is_alive()

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
        folder_label.config(text=f"📁 Save to: {output_directory}")

def set_resolution(value):
    """ Updates the selected resolution. """
    global selected_resolution
    selected_resolution = value
    print(f"New Resolution: {selected_resolution}, Value: {value}")

def toggle_audio_mode():
    """ Enables or disables audio-only mode and format selection. """
    if audio_only.get():
        resolution_dropdown.config(state=tk.DISABLED)  # Disable resolution dropdown
        audio_format_dropdown.config(state=tk.NORMAL)  # Enable format dropdown
    else:
        resolution_dropdown.config(state=tk.NORMAL)  # Enable resolution dropdown
        audio_format_dropdown.config(state=tk.DISABLED)  # Disable format dropdown

def clean_text(text):
    """ Removes unwanted ANSI escape codes from yt-dlp output. """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

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

    if download_is_active():
        messagebox.showwarning("Download In Progress", "Please wait for the current download to finish.")
        return

    download_settings = {
        "url": url,
        "output_dir": output_directory,
        "resolution": resolution_menu.get() or selected_resolution,
        "is_audio_only": audio_only.get(),
        "audio_format": selected_audio_format.get().lower(),
        "cleanup_enabled": delete_temp_files.get(),
        "preserve_upload_date": preserve_upload_date.get(),
    }
    download_cancel_event = threading.Event()

    # Disable the button to prevent multiple clicks
    download_button.config(state=tk.DISABLED)
    status_label.config(text="⏳ Connecting...")

    # Run the download in a separate thread
    download_thread = threading.Thread(
        target=download_video_thread,
        args=(download_settings, download_cancel_event),
    )
    download_thread.start()

def update_resolution_options(*args):
    """Debounces resolution fetching while the URL is being edited."""
    global fetch_delay, fetch_request_id
    url = url_entry.get().strip()

    if fetch_delay:
        root.after_cancel(fetch_delay)
        fetch_delay = None

    if not url:
        return

    fetch_request_id += 1
    request_id = fetch_request_id
    fetch_delay = root.after(500, lambda: start_resolution_fetch(request_id, url))

def start_resolution_fetch(request_id, url):
    global fetch_delay
    fetch_delay = None

    if request_id != fetch_request_id:
        return

    resolution_dropdown.config(state=tk.DISABLED)
    resolution_menu.set("Fetching...")

    threading.Thread(
        target=fetch_resolutions_thread,
        args=(request_id, url),
        daemon=True,
    ).start()

def fetch_resolutions_thread(request_id, url):
    resolutions = fetch_available_resolutions(url)
    queue_ui("resolution_results", request_id, url, resolutions)

def apply_resolution_results(request_id, url, resolutions):
    if request_id != fetch_request_id or url != url_entry.get().strip():
        return

    resolution_dropdown["menu"].delete(0, "end")
    for res in resolutions:
        resolution_dropdown["menu"].add_command(label=res, command=lambda v=res: set_resolution(v))

    resolution_menu.set(resolutions[0])
    set_resolution(resolutions[0])

    state = tk.DISABLED if audio_only.get() else tk.NORMAL
    resolution_dropdown.config(state=state)

def fetch_available_resolutions(url):
    """ Fetch available video resolutions for a given YouTube URL. """
    try:
        with yt_dlp.YoutubeDL(create_ytdlp_options()) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            available_resolutions = set()

            for video_format in info_dict['formats']:
                if 'height' in video_format and video_format['height']:
                    available_resolutions.add(f"{video_format['height']}p")

            # Convert resolutions to integers for proper sorting
            return sorted(available_resolutions, key=lambda x: int(x.replace("p", "")), reverse=True)


    except Exception as e:
        print(f"❌ Error fetching resolutions: {e}")
        return ["Highest Available"]  # Default if fetching fails

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
        status_label.config(text="✅ Download Complete!")
        messagebox.showinfo("Download Complete", f"File saved to:\n{final_path}")
        open_download_folder()
    else:
        details = error_message or "Unknown error"
        status_label.config(text=f"❌ Download Failed\n{details}")
        if details != "Download cancelled":
            messagebox.showerror("Download Failed", details)

    # Re-enable the download button
    download_button.config(state=tk.NORMAL)

def download_video(download_settings, cancel_event):
    """ Downloads a YouTube video or extracts audio based on user selection. """
    url = download_settings["url"]
    output_dir = download_settings["output_dir"]
    resolution = download_settings["resolution"]
    is_audio_only = download_settings["is_audio_only"]
    audio_format = download_settings["audio_format"]
    cleanup_enabled = download_settings["cleanup_enabled"]
    preserve_upload_date_setting = download_settings["preserve_upload_date"]

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

        with yt_dlp.YoutubeDL(create_ytdlp_options()) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            media_title = sanitize_filename(info_dict.get('title', 'output'))  # Sanitize filename
            upload_date = info_dict.get('upload_date', None)  # ✅ Extract Upload Date (YYYYMMDD)

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

# Function to clear the URL entry box
def fill_in_default_url():
    clear_url()
    url_entry.insert(0, default_url)  # Pre-fills the entry box
    update_resolution_options()

def on_close():
    global is_closing

    if download_is_active():
        is_closing = True
        if download_cancel_event:
            download_cancel_event.set()
        status_label.config(text="Canceling active download and cleaning up...")
        download_button.config(state=tk.DISABLED)
        return

    root.destroy()

# 🖥️ GUI Setup
root = tk.Tk()
root.title("YouTube Video Downloader")
root.geometry("700x760")

# Variable to store cleanup option
delete_temp_files = tk.BooleanVar(value=True)  # Default: Enabled
preserve_upload_date = tk.BooleanVar(value=True)

# Variable to store whether "Audio Only" is enabled
audio_only = tk.BooleanVar(value=False)
selected_audio_format = tk.StringVar(value="MP3")  # Default format

diagnostics_label = tk.Label(root, text="Diagnostics: checking...", font=("Arial", 9), justify=tk.LEFT, anchor="w", wraplength=660)
diagnostics_label.pack(pady=8, padx=10, fill=tk.X)

tk.Label(root, text="Enter YouTube URL:", font=("Arial", 12)).pack(pady=5)

# Create a frame to hold the URL entry and buttons
url_frame = tk.Frame(root)
url_frame.pack(pady=5)

# Button to fetch available resolutions
fetch_resolution_button = tk.Button(url_frame, text="🔍", command=update_resolution_options)
fetch_resolution_button.pack(side=tk.RIGHT, padx=5)

# Input field for URL (Pre-filled with default URL)
url_entry = tk.Entry(url_frame, width=50)
url_entry.pack(side=tk.RIGHT, padx=5)
url_entry.bind("<KeyRelease>", update_resolution_options)  # **Trigger fetching on URL entry**
# url_entry.bind("<Control-V>", update_resolution_options)  # ✅ Triggers on paste (Ctrl+V) TODO: STILL TO FIGURE OUT
# url_entry.bind("<Button-3>", update_resolution_options)  # ✅ Triggers on right-click paste (Windows) TODO: STILL TO FIGURE OUT

# Button to clear the URL field
clear_button = tk.Button(url_frame, text="🗑️", command=clear_url)
clear_button.pack(side=tk.LEFT, padx=0)

# Button to clear the URL field
default_url_button = tk.Button(url_frame, text="Default", command=fill_in_default_url)
default_url_button.pack(side=tk.LEFT, padx=2)

# Add "Audio Only" checkbox
audio_checkbox = tk.Checkbutton(root, text="Audio Only", variable=audio_only, command=toggle_audio_mode)
audio_checkbox.pack(pady=5)

# Dropdown menu for selecting audio format
tk.Label(root, text="Select Audio Format:", font=("Arial", 10)).pack(pady=5)
audio_formats = ["MP3", "WAV", "AAC", "FLAC"]
audio_format_dropdown = tk.OptionMenu(root, selected_audio_format, *audio_formats)
audio_format_dropdown.pack(pady=5)
audio_format_dropdown.config(state=tk.DISABLED)  # Initially disabled

# Dropdown menu for resolution selection
tk.Label(root, text="Select Resolution:", font=("Arial", 10)).pack(pady=5)
resolution_options = ["Highest Available", "1080p", "720p", "480p", "360p"]
resolution_menu = tk.StringVar(root)
resolution_menu.set(selected_resolution)  # Default value
resolution_dropdown = tk.OptionMenu(root, resolution_menu, *resolution_options, command=set_resolution)
resolution_dropdown.pack(pady=5)

# Button to choose output folder
folder_button = tk.Button(root, text="Choose Folder", command=select_output_folder)
folder_button.pack(pady=5)

# Label to show selected folder
folder_label = tk.Label(root, text=f"📁 Save to: {output_directory}", font=("Arial", 10))
folder_label.pack()

open_folder_button = tk.Button(root, text="Open Download Folder", command=open_download_folder)
open_folder_button.pack(pady=5)

# Add a checkbox for cleaning up temp files
cleanup_checkbox = tk.Checkbutton(root, text="Delete Temp Files After Download", variable=delete_temp_files)
cleanup_checkbox.pack(pady=5)

timestamp_checkbox = tk.Checkbutton(root, text="Preserve Upload Date", variable=preserve_upload_date)
timestamp_checkbox.pack(pady=5)

# Download button
download_button = tk.Button(root, text="Download", command=download_video_gui)
download_button.pack(pady=10)

# Status label
status_label = tk.Label(root, text="", font=("Arial", 10), wraplength=660, justify=tk.LEFT)
status_label.pack()

root.protocol("WM_DELETE_WINDOW", on_close)
process_ui_queue()
run_startup_diagnostics_async()

# Run GUI
root.mainloop()
