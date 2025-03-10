@echo off
echo Building the executable...
python -m PyInstaller --onefile --windowed downloader.py
echo Done!
pause