import os
import sys
import yt_dlp
import tempfile
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import shutil  # Add this to the top of the script

### TODO:
# - Show progress of merging (no user feedback at the moment)
# - Stop download
# - Stop merging
# - Make Downloads as default output folder
# - After Success/Unsuccess get rid of the temp folder (?)
# - Set download's time instead of when video was uploaded
# - First search for video. If it finds it, show available resolutions instead of manually checking
# - Improve merging, for some reason it takes very long now
# - Add a button to clear URL line instead of having to manually select all and erase
# - At the end of download it shows a new window saying its been downloaded and user needs to press on it, potentially move it inside the YouTUbe Video Donwloader?
# - Have a test video URL already placed in the line so I dont need to paste it myself everytime

### Command to create .exe out of .py
# python -m PyInstaller --onefile downloader.py

### For testing
# 1080p - https://www.youtube.com/watch?v=ps74zeevi-g
# 720p - https://www.youtube.com/watch?v=cUM8OCBy6Ls

# Default output directory (current folder)
output_directory = os.getcwd()
selected_resolution = "1080p"  # Default resolution

# For future implementation of stable progress UI update
latest_progress = {"percent": "0%", "speed": "N/A", "eta": "Unknown"}

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
    status_label.config(text="⏳ Downloading...")

    # Run the download in a separate thread
    download_thread = threading.Thread(target=download_video_thread, args=(url,))
    download_thread.start()

def download_video_thread(url):
    """ Runs the video download process in a separate thread. """
    global output_directory, selected_resolution

    success = download_video(url, output_directory, selected_resolution)

    # Update the UI after the download completes (use root.after() to avoid threading issues)
    root.after(0, lambda: update_ui_after_download(success))

def update_ui_after_download(success):
    """ Updates the UI after the download is completed. """
    if success:
        messagebox.showinfo("Success", f"Download completed successfully!\nSaved to: {output_directory}")
        status_label.config(text="✅ Download Complete!")
    else:
        messagebox.showerror("Error", "Failed to download video. Check console for details.")
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

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            media_title = sanitize_filename(info_dict.get('title', 'output'))  # Sanitize filename

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
            if audio_only.get():
                output_file = os.path.join(temp_dir, f"{media_title}.{audio_format}")
            else:
                output_file = os.path.join(temp_dir, f"{media_title}.mp4")  # Ensure MP4 is set correctly

            ydl_opts = {
                'format': selected_format,
                'merge_output_format': 'mp4',
                'outtmpl': output_file,
                'postprocessor_args': ['-c:a', 'aac', '-b:a', '192k', '-c:v', 'copy'],
                'fragment_retries': 10,
                'nocheckcertificate': True,
                'concurrent_fragments': 5,
                #'progress_hooks': [progress_hook],  # 🏎️ Show progress
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
            
        return True

    except Exception as e:
        print(f"❌ Error downloading media: {e}")
        return False

def sanitize_filename(filename):
    """ Removes or replaces invalid characters in filenames """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)  # Replaces invalid characters with "_"

# 🖥️ GUI Setup
root = tk.Tk()
root.title("YouTube Video Downloader")
root.geometry("600x600")

# Variable to store cleanup option
delete_temp_files = tk.BooleanVar(value=True)  # Default: Enabled

# Variable to store whether "Audio Only" is enabled
audio_only = tk.BooleanVar(value=False)
selected_audio_format = tk.StringVar(value="MP3")  # Default format

# Input field for URL
tk.Label(root, text="Enter YouTube URL:", font=("Arial", 12)).pack(pady=5)
url_entry = tk.Entry(root, width=50)
url_entry.pack(pady=5)

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
