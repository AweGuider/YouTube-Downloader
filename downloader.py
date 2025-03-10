import os
import subprocess
import sys
import yt_dlp
import tempfile
import re

### For testing
# 1080p - https://www.youtube.com/watch?v=ps74zeevi-g
# 720p - https://www.youtube.com/watch?v=cUM8OCBy6Ls

# def download_video(url, output_filename="output.mp4"):
#     """
#     Downloads a YouTube video at 1080p with audio included.
#     Saves the file in the specified output directory.
#     """
#     print("🎥 Fetching video and audio...")

#     # Video & audio file paths
#     video_file = "video.mp4.mkv"
#     audio_file = "audio.m4a"

#     # yt-dlp options
#     ydl_opts = {
#         'format': 'bestvideo[height=1080]+bestaudio',  # Best 1080p video + best audio
#         'outtmpl': video_file,  # Save video
#     }

#     try:
#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             ydl.download([url])

#         # Download audio separately (in case it's missing)
#         audio_opts = {
#             'format': 'bestaudio',
#             'outtmpl': audio_file,
#         }
#         with yt_dlp.YoutubeDL(audio_opts) as ydl:
#             ydl.download([url])

#     except Exception as e:
#         print(f"❌ Error downloading video/audio: {e}")
#         return False

#     # # Merge video and audio using FFmpeg
#     # print("🔄 Merging video and audio with FFmpeg...")
#     # merge_cmd = [
#     #     "ffmpeg",
#     #     "-i", video_file,
#     #     "-i", audio_file,
#     #     "-c:v", "copy",
#     #     "-c:a", "aac",
#     #     "-strict", "experimental",
#     #     output_filename
#     # ]
    
#     # try:
#     #     subprocess.run(merge_cmd, check=True)
#     #     print(f"✅ Download complete: {output_filename}")

#     #     # Optional: Clean up raw video/audio files
#     #     os.remove(video_file)
#     #     os.remove(audio_file)

#     # except subprocess.CalledProcessError:
#     #     print("❌ Error merging video and audio.")
#     #     return False

#     print(f"✅ Download complete: {video_file}")

#     return True

# # Main script
# if __name__ == "__main__":
#     if len(sys.argv) < 2:
#         print("Usage: python downloader.py <YouTube_URL>")
#         sys.exit(1)

#     video_url = sys.argv[1]
#     download_video(video_url)


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
            'progress_hooks': [progress_hook],  # Show progress
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

def progress_hook(d):
    """ Provides real-time feedback on the download progress. """
    if d['status'] == 'downloading':
        print(f"⏳ Downloading: {d['_percent_str']} at {d['_speed_str']}")
    elif d['status'] == 'finished':
        print("✅ Download complete.")

def sanitize_filename(filename):
    """ Removes or replaces invalid characters in filenames """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)  # Replaces invalid characters with "_"

# Main script
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python downloader.py <YouTube_URL> [output_directory]")
        sys.exit(1)

    video_url = sys.argv[1]
    output_directory = sys.argv[2] if len(sys.argv) > 2 else "."

    download_video(video_url, output_directory)
