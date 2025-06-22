@echo off
setlocal enabledelayedexpansion

title YouTube Downloader Build Script

:: === Prompt for App Name ===
set /p FILE_NAME=Enter executable name (default: YouTubeDownloader): 
if "%FILE_NAME%"=="" set FILE_NAME=YouTubeDownloader_by_AweDev

:: === Prompt for ZIP Name ===
set /p ZIP_NAME=Enter ZIP archive name (default: %FILE_NAME%-Build.zip): 
if "%ZIP_NAME%"=="" set ZIP_NAME=%FILE_NAME%-Build.zip

:: === Ask About Overwriting Existing Files ===
set /p OVERWRITE=Overwrite existing files if they exist? (y/n): 
set OVERWRITE=!OVERWRITE:~0,1!

:: === Ask if user wants to zip the build (default: yes)
set /p DO_ZIP=Zip the executable after building? (y/n): 
if /i "!DO_ZIP!"=="n" (
    set DO_ZIP=false
) else (
    set DO_ZIP=true
)

:: === Create timestamp for log file ===
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set LOG_TIMESTAMP=%%i

:: === Paths ===
set SOURCE=downloader.py
set EXE_PATH=dist\%FILE_NAME%.exe
set LOG_FILE=build_log_!LOG_TIMESTAMP!.txt

:: === Point to external ffmpeg path (assumes added to PATH too)
set FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
if not exist "%FFMPEG_PATH%" (
    echo ffmpeg.exe not found at %FFMPEG_PATH% >> %LOG_FILE%
	echo ffmpeg.exe not found at %FFMPEG_PATH%
    pause
    exit /b
)

echo Cleaning previous log...
:: === Optional: Keep only last 5 logs, delete older
for /f "skip=5 delims=" %%F in ('dir /b /o-d build_log_*.txt') do del "%%F"

:: === Remove existing EXE if overwrite allowed ===
if exist %EXE_PATH% (
    if /i "%OVERWRITE%"=="y" (
        del /q %EXE_PATH%
        echo Removed existing EXE >> %LOG_FILE%
    ) else (
        call :generate_unique_name
    )
)

:: === RUN PYINSTALLER ===
echo Building executable: %FILE_NAME%.exe...
python -m PyInstaller --noconfirm --onefile --windowed --name "%FILE_NAME%" --add-data "%FFMPEG_PATH%;." %SOURCE% >> %LOG_FILE% 2>&1

if errorlevel 1 (
    echo Build failed! Check !LOG_FILE! for details.
    pause
    exit /b
)

echo Build complete: %EXE_PATH% >> %LOG_FILE%
echo Build complete: %EXE_PATH%

:: === ZIP Handling ===
if "!DO_ZIP!"=="true" (
	if exist !ZIP_NAME! (
		if /i "!OVERWRITE!"=="y" (
			del /q "!ZIP_NAME!"
			echo Overwriting ZIP: !ZIP_NAME!
		) else (
			call :generate_unique_zip_name
		)
	)
	
	:: === ZIP FINAL BUILD ===
	echo Zipping %EXE_PATH% build into %ZIP_NAME%...
	powershell -Command "Compress-Archive -Path !EXE_PATH! -DestinationPath !ZIP_NAME!" >> !LOG_FILE! 2>&1
	
	:: === CLEAN DIST after ZIP ===
    echo Removing executable after zipping...
    del /q "!EXE_PATH!" >> !LOG_FILE!
	
) else (
    echo Skipping ZIP. Keeping built .exe
)

:: === CLEAN UP ===
echo Cleaning up...
rmdir /s /q build >> %LOG_FILE%
del /q *.spec >> %LOG_FILE%
echo Cleaned up temporary build files

echo Done! Output file: %ZIP_NAME%
echo See %LOG_FILE% for build log.
pause
exit /b

:: === Helper: Generate Unique EXE Name ===
:generate_unique_name
set COUNT=1
:try_exe_name
set ALT_NAME=%FILE_NAME%_v!COUNT!
set EXE_PATH=dist\!ALT_NAME!.exe
if exist !EXE_PATH! (
    set /a COUNT+=1
    goto try_exe_name
)
set FILE_NAME=!ALT_NAME!
echo 🆕 Using new EXE name: !FILE_NAME!
goto :eof

:: === Helper: Generate Unique ZIP Name ===
:generate_unique_zip_name
set COUNT=1
:try_zip_name
set ALT_ZIP=%ZIP_NAME:~0,-4%_v!COUNT!.zip
if exist !ALT_ZIP! (
    set /a COUNT+=1
    goto try_zip_name
)
set ZIP_NAME=!ALT_ZIP!
echo 🆕 Using new ZIP name: !ZIP_NAME!
goto :eof
