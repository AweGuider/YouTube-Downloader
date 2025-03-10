import os
import sys
import yt_dlp
import tempfile
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import threading

### TODO:
# - Show progress of merging (no user feedback at the moment)
# - Stop download
# - Stop merging
# - When unfocusing, it might break/lag in long videos
# - Make Downloads as default output folder
# - After Success/Unsuccess get rid of the temp folder (?)
# - Set download's time instead of when video was uploaded
# - First search for video. If it finds it, show available resolutions instead of manually checking
# - Improve merging, for some reason it takes very long now
# - Add a button to clear URL line instead of having to manually select all and erase
# - At the end of download it shows a new window saying its been downloaded and user needs to press on it, potentially move it inside the YouTUbe Video Donwloader?

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
    """ Downloads a YouTube video in the selected resolution. """
    print(f"🎥 Fetching video at {resolution} resolution...")
    
    # Map resolution to yt-dlp format selectors
    resolution_map = {
        "1080p": "bestvideo[height=1080]+bestaudio/best",
        "720p": "bestvideo[height=720]+bestaudio/best",
        "480p": "bestvideo[height=480]+bestaudio/best",
        "360p": "bestvideo[height=360]+bestaudio/best",
        "Highest Available": "bestvideo+bestaudio/best"
    }
    
    selected_format = resolution_map.get(resolution, "bestvideo[height=1080]+bestaudio/best")


    """
    Saves the file in the specified output directory.
    """
    print("🎥 Fetching video and audio...")

    # Use a temporary directory for the download process
    temp_dir = tempfile.mkdtemp()

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)  # Get metadata without downloading
            video_title = sanitize_filename(info_dict.get('title', 'output'))  # Sanitize here
            video_file = os.path.join(temp_dir, f"{video_title}.mp4")

        # yt-dlp options
        ydl_opts = {
            'format': selected_format,
            'merge_output_format': 'mp4',  # Ensure output is always .mp4
            'outtmpl': video_file,  # Save using the sanitized filename
            'postprocessor_args': [
                '-c:a', 'aac',  # Convert audio to AAC (Windows-compatible)
                '-b:a', '192k',  # Set audio bitrate to 192kbps for good quality
                '-c:v', 'copy'  # Keep video unchanged (no re-encoding)
            ],
            'fragment_retries': 10,  # Retry failed downloads up to 10 times
            'nocheckcertificate': True,  # Prevent SSL issues
            'concurrent_fragments': 5,  # 🏎️ Download 5 fragments at once (adjustable)
            'progress_hooks': [progress_hook],  # 🏎️ Show progress
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Move the file to the output directory
        final_path = os.path.join(output_dir, f"{video_title}.mp4")
        os.rename(video_file, final_path)

        print(f"✅ Download complete: {final_path}")
        return True

    except Exception as e:
        print(f"❌ Error downloading video: {e}")
        return False

def sanitize_filename(filename):
    """ Removes or replaces invalid characters in filenames """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)  # Replaces invalid characters with "_"

# 🖥️ GUI Setup
root = tk.Tk()
root.title("YouTube Video Downloader")
root.geometry("600x420")

# Input field for URL
tk.Label(root, text="Enter YouTube URL:", font=("Arial", 12)).pack(pady=5)
url_entry = tk.Entry(root, width=50)
url_entry.pack(pady=5)

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

# Download button
download_button = tk.Button(root, text="Download", command=download_video_gui)
download_button.pack(pady=10)

# Status label
status_label = tk.Label(root, text="", font=("Arial", 10))
status_label.pack()

# Run GUI
root.mainloop()
