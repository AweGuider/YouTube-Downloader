@echo off
echo Building the executable...
python -m PyInstaller --onefile --windowed --add-data "ffmpeg.exe;." downloader.py
echo Done!
pause