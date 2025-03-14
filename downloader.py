import os
import time
# import win32con
# import win32file
import platform
import ctypes
import sys
import yt_dlp
import tempfile
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import shutil  # Add this to the top of the script

### TODO:
# - After Unsuccess get rid of the temp folder (currently only cleans up after success)
# - Add button to Paste link from clipboard (clear + insert from clipboard)
# - Can't finalize download (move file to the download folder) if such file already exists
# - Add an option to either keep upload date or use current download date
# - (Skip) Stop merging

### Command to create .exe out of .py
# python -m PyInstaller --onefile downloader.py

### For testing
# 1080p - https://www.youtube.com/watch?v=ps74zeevi-g
# 720p - https://www.youtube.com/watch?v=cUM8OCBy6Ls

# Auto-fill test URL (Replace with any default video link)
default_url = "https://www.youtube.com/watch?v=ps74zeevi-g"

# Default output directory (current folder)
# output_directory = os.getcwd()
# Set default output folder to "Downloads/YouTubeDownloads/"
default_output_folder = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloads")
# Ensure the folder exists
os.makedirs(default_output_folder, exist_ok=True)
# Use this as the initial output directory
output_directory = default_output_folder

selected_resolution = "1080p"  # Default resolution

fetch_delay = None  # Global variable to track scheduled fetch calls

# For future implementation of stable progress UI update
latest_progress = {"percent": "0%", "speed": "N/A", "eta": "Unknown"}

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

def progress_hook(d):
    """ Updates the status label with download progress. """
    if d['status'] == 'downloading':
        percent = clean_text(d.get('_percent_str', '0%'))
        speed = clean_text(d.get('_speed_str', 'N/A'))
        eta = clean_text(d.get('_eta_str', 'Unknown'))

        # Cleaned-up progress message with line breaks for better readability
        progress_text = f"⏳ Progress: {percent}\n🚀 Speed: {speed}\n⏳ ETA: {eta}"

        # Schedule UI update
        root.after(1000, lambda: status_label.config(text=progress_text))
    
    elif d['status'] == 'finished':
        root.after(1000, lambda: status_label.config(text="✅ Download Complete!"))

    else:
        root.after(1000, lambda: status_label.config(text="🔄 Merging..."))

def download_video_gui():
    """
    Function triggered when the Download button is clicked.
    """
    url = url_entry.get().strip()
    
    if not url:
        messagebox.showerror("Error", "Please enter a YouTube URL")
        return

    # Disable the button to prevent multiple clicks
    download_button.config(state=tk.DISABLED)
    status_label.config(text="⏳ Connecting...")

    # Run the download in a separate thread
    download_thread = threading.Thread(target=download_video_thread, args=(url,))
    download_thread.start()

def update_resolution_options(*args):
    """ Automatically fetch resolutions when URL is entered. """

    """ Updates the resolution dropdown based on available formats. """
    global fetch_delay
    url = url_entry.get().strip()

    if not url:
        # messagebox.showerror("Error", "Please enter a YouTube URL first.")
        # return
        return  # Don't fetch if URL is empty
    
        # **Cancel any previous scheduled fetch call**
    if fetch_delay:
        root.after_cancel(fetch_delay)

    # **Disable dropdown while fetching**
    resolution_dropdown.config(state=tk.DISABLED)
    resolution_menu.set("Fetching...")  # Show fetching status

    # **Fetch resolutions in background**
    root.after(300, lambda: fetch_and_update_resolutions(url))

def fetch_and_update_resolutions(url):
    """ Fetch available resolutions and update the dropdown. """
    resolutions = fetch_available_resolutions(url)

    # **Clear old options & add new ones**
    resolution_dropdown['menu'].delete(0, 'end')
    for res in resolutions:
        resolution_dropdown['menu'].add_command(label=res, command=lambda v=res: set_resolution(v))

    # **Set the first available resolution as default**
    resolution_menu.set(resolutions[0])

    # # Set the first available resolution as default
    set_resolution(resolutions[0])

    # **Re-enable the dropdown after fetching**
    resolution_dropdown.config(state=tk.NORMAL)

def fetch_available_resolutions(url):
    """ Fetch available video resolutions for a given YouTube URL. """
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            available_resolutions = set()

            for video_format in info_dict['formats']:
                if 'height' in video_format and video_format['height']:
                    available_resolutions.add(f"{video_format['height']}p")

            # return sorted(available_resolutions, reverse=True)
            # Convert resolutions to integers for proper sorting
            return sorted(available_resolutions, key=lambda x: int(x.replace("p", "")), reverse=True)


    except Exception as e:
        print(f"❌ Error fetching resolutions: {e}")
        return ["Highest Available"]  # Default if fetching fails

def download_video_thread(url):
    """ Runs the video download process in a separate thread. """
    global output_directory, selected_resolution

    success = download_video(url, output_directory, selected_resolution)

    # Update the UI after the download completes (use root.after() to avoid threading issues)
    root.after(0, lambda: update_ui_after_download(success))

def update_ui_after_download(success):
    """ Updates the UI after the download is completed. """
    if success:
        # messagebox.showinfo("Success", f"Download completed successfully!\nSaved to: {output_directory}")
        status_label.config(text="✅ Download Complete!")
    else:
        # messagebox.showerror("Error", "Failed to download video. Check console for details.")
        status_label.config(text="❌ Download Failed")

    # Re-enable the download button
    download_button.config(state=tk.NORMAL)

def download_video(url, output_dir, resolution):
    """ Downloads a YouTube video or extracts audio based on user selection. """
    print(f"🎥 Fetching media... Audio Only: {audio_only.get()}")

    # Ensure audio_format is always defined, whether in audio-only or video download mode
    audio_format = selected_audio_format.get().lower() if audio_only.get() else None

    # Use a temporary directory for processing
    temp_dir = tempfile.mkdtemp()

    # If the user has not changed the output folder, use the default folder
    if output_dir == os.getcwd():
        output_dir = default_output_folder
        
    # Ensure the output folder exists
    os.makedirs(output_dir, exist_ok=True)

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            media_title = sanitize_filename(info_dict.get('title', 'output'))  # Sanitize filename
            upload_date = info_dict.get('upload_date', None)  # ✅ Extract Upload Date (YYYYMMDD)

        # Check if Audio-Only mode is enabled
        if audio_only.get():
            audio_format = selected_audio_format.get().lower()  # Convert MP3 -> mp3
            output_file = os.path.join(temp_dir, f"{media_title}.{audio_format}")

            ydl_opts = {
                'format': 'bestaudio/best',  # Download best audio only
                'outtmpl': output_file,  # Save as the selected format
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_format,
                    'preferredquality': '192',
                }]
            }

        else:
            # Normal video download
            resolution_map = {
                "1080p": "bestvideo[height=1080]+bestaudio/best",
                "720p": "bestvideo[height=720]+bestaudio/best",
                "480p": "bestvideo[height=480]+bestaudio/best",
                "360p": "bestvideo[height=360]+bestaudio/best",
                "Highest Available": "bestvideo+bestaudio/best"
            }

            selected_format = resolution_map.get(resolution, "bestvideo[height=1080]+bestaudio/best")

            print(f"Resolution Selected: {resolution}, Format Selected: {selected_format}")

            if audio_only.get():
                output_file = os.path.join(temp_dir, f"{media_title}.{audio_format}")
            else:
                output_file = os.path.join(temp_dir, f"{media_title}.mp4")  # Ensure MP4 is set correctly

            ydl_opts = {
                'format': selected_format,
                'merge_output_format': 'mp4',
                'outtmpl': output_file,
                # 'postprocessor_args': ['-c:a', 'aac', '-b:a', '192k', '-c:v', 'copy'],
                # 'postprocessor_args': [
                #     "-c:v copy -c:a copy"  # ⚡ Merge without re-encoding
                # ],
                'fragment_retries': 10,
                'nocheckcertificate': True,
                'concurrent_fragments': 5,
                'progress_hooks': [progress_hook],  # 🏎️ Show progress
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Fix: Handle duplicate extensions caused by FFmpeg
        expected_file = f"{output_file}.{audio_format}"  # Expected (e.g., song.mp3)
        converted_file = f"{output_file}.m4a"  # FFmpeg might save it as .m4a

        # Ensure the final correct file is identified
        # If FFmpeg adds an extra extension, detect and fix it
        if os.path.exists(converted_file) and audio_format == "aac":
            final_audio_file = converted_file  # Use FFmpeg's .m4a file
            fixed_name = final_audio_file.replace(".m4a", ".aac")  # Rename to .aac
            os.rename(final_audio_file, fixed_name)
            final_audio_file = fixed_name  # Update reference
        elif os.path.exists(expected_file):
            final_audio_file = expected_file  # Use expected format
        else:
            final_audio_file = output_file  # Fallback

        # Fix: Remove unnecessary duplicated extensions (e.g., .mp3.mp3 -> .mp3)
        if final_audio_file.endswith(f".{audio_format}.{audio_format}"):
            fixed_name = final_audio_file.rsplit(f".{audio_format}", 1)[0]  # Remove extra extension
            os.rename(final_audio_file, fixed_name)
            final_audio_file = fixed_name

        # Move the correct file to the output directory
        final_path = os.path.join(output_dir, os.path.basename(final_audio_file))
        os.rename(final_audio_file, final_path)

        print(f"✅ Download complete: {final_path}")

        # **Delete temporary files if the checkbox is enabled**
        if delete_temp_files.get():
            print("🗑️ Cleaning up temporary files...")
            shutil.rmtree(temp_dir, ignore_errors=True)

        finalize_download(final_path, upload_date)

        return True

    except Exception as e:
        print(f"❌ Error downloading media: {e}")
        return False
    
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
    
def finalize_download(final_path, upload_date):
    """ Final actions after download: show success & open folder. """
    messagebox.showinfo("Download Complete", f"File saved to:\n{final_path}")

    # ✅ Get the current timestamp to preserve "Date Created"
    current_time = time.time()

    if upload_date:
        try:
            # ✅ Apply upload date to "Last Modified" and "Last Accessed"
            os.utime(final_path, (current_time, current_time))

            print(f"✅ File timestamps updated: Modified/Accessed -> {upload_date}")

        except Exception as e:
            print(f"❌ Error updating timestamps: {e}")

    # **Automatically open folder after successful download**
    open_download_folder()

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

# 🖥️ GUI Setup
root = tk.Tk()
root.title("YouTube Video Downloader")
root.geometry("600x600")

# Variable to store cleanup option
delete_temp_files = tk.BooleanVar(value=True)  # Default: Enabled

# Variable to store whether "Audio Only" is enabled
audio_only = tk.BooleanVar(value=False)
selected_audio_format = tk.StringVar(value="MP3")  # Default format

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

# Download button
download_button = tk.Button(root, text="Download", command=download_video_gui)
download_button.pack(pady=10)

# Status label
status_label = tk.Label(root, text="", font=("Arial", 10))
status_label.pack()

# Run GUI
root.mainloop()
