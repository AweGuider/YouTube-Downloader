import os
import sys
import yt_dlp
import tempfile
import re
import tkinter as tk
from tkinter import filedialog, messagebox

### Command to create .exe out of .py
# python -m PyInstaller --onefile downloader.py

### For testing
# 1080p - https://www.youtube.com/watch?v=ps74zeevi-g
# 720p - https://www.youtube.com/watch?v=cUM8OCBy6Ls

# Default output directory (current folder)
output_directory = os.getcwd()

def select_output_folder():
    """ Opens a dialog for the user to select an output folder. """
    global output_directory
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        output_directory = folder_selected
        folder_label.config(text=f"📁 Save to: {output_directory}")

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

    # Run download function
    success = download_video(url, output_directory)

    if success:
        messagebox.showinfo("Success", "Download completed successfully!")
        status_label.config(text="✅ Download Complete!")
    else:
        messagebox.showerror("Error", "Failed to download video. Check console for details.")
        status_label.config(text="❌ Download Failed")

    # Re-enable the button
    download_button.config(state=tk.NORMAL)

def download_video(url, output_dir="."):
    """
    Downloads a YouTube video at 1080p with audio included.
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
            'format': 'bestvideo[height=1080]+bestaudio/best',
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
            # 'progress_hooks': [progress_hook],  # Show progress
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

# def progress_hook(d):
#     """ Provides real-time feedback on the download progress. """
#     if d['status'] == 'downloading':
#         print(f"⏳ Downloading: {d['_percent_str']} at {d['_speed_str']}")
#     elif d['status'] == 'finished':
#         print("✅ Download complete.")

def sanitize_filename(filename):
    """ Removes or replaces invalid characters in filenames """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)  # Replaces invalid characters with "_"

# Main script
# if __name__ == "__main__":
#     if len(sys.argv) < 2:
#         print("Usage: python downloader.py <YouTube_URL> [output_directory]")
#         sys.exit(1)

#     video_url = sys.argv[1]
#     output_directory = sys.argv[2] if len(sys.argv) > 2 else "."

#     download_video(video_url, output_directory)

# 🖥️ GUI Setup
root = tk.Tk()
root.title("YouTube Video Downloader")
root.geometry("500x250")

# Input field for URL
tk.Label(root, text="Enter YouTube URL:", font=("Arial", 12)).pack(pady=5)
url_entry = tk.Entry(root, width=50)
url_entry.pack(pady=5)

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
