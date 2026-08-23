@echo off
setlocal enabledelayedexpansion

title YouTube Downloader Build Script

set "SOURCE=downloader.py"

:: === Prompt for App Name ===
set /p "FILE_NAME=Enter executable name (default: YouTubeDownloader): "
if "%FILE_NAME%"=="" set "FILE_NAME=YouTubeDownloader_by_AweDev"

:: === Prompt for ZIP Name ===
set /p "ZIP_NAME=Enter ZIP archive name (default: %FILE_NAME%-Build.zip): "
if "%ZIP_NAME%"=="" set "ZIP_NAME=%FILE_NAME%-Build.zip"

:: === Ask About Overwriting Existing Files ===
set /p "OVERWRITE=Overwrite existing files if they exist? (y/n): "
set "OVERWRITE=!OVERWRITE:~0,1!"

:: === Ask if user wants to zip the build (default: yes) ===
set /p "DO_ZIP=Zip the executable after building? (y/n): "
if /i "!DO_ZIP!"=="n" (
    set "DO_ZIP=false"
) else (
    set "DO_ZIP=true"
)

:: === Create timestamp for log file ===
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "LOG_TIMESTAMP=%%i"

:: === Paths ===
set "EXE_PATH=dist\%FILE_NAME%.exe"
set "LOG_FILE=build_log_!LOG_TIMESTAMP!.txt"

if not exist "%SOURCE%" (
    echo Source file not found: %SOURCE%
    pause
    exit /b 1
)

echo Checking Python build prerequisites...
python -c "import tkinter as tk; tk.Tcl(); import yt_dlp; import yt_dlp_ejs; import PyInstaller" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo Python build prerequisite check failed. Check !LOG_FILE! for details.
    echo Repair Python Tcl/Tk support or use a Python install with working Tkinter, then rerun this script.
    pause
    exit /b 1
)

call :resolve_tool ffmpeg FFMPEG_PATH
if errorlevel 1 (
    echo ffmpeg was not found.
    goto missing_prerequisite
)

call :resolve_tool ffprobe FFPROBE_PATH
if errorlevel 1 (
    echo ffprobe was not found.
    goto missing_prerequisite
)

set "JS_RUNTIME_NAME="
set "JS_RUNTIME_PATH="

call :resolve_tool deno DENO_PATH
if not errorlevel 1 (
    call :is_readable "!DENO_PATH!"
    if not errorlevel 1 (
        set "JS_RUNTIME_NAME=deno"
        set "JS_RUNTIME_PATH=!DENO_PATH!"
    ) else (
        echo deno was found but cannot be read by PyInstaller: !DENO_PATH!
        echo Falling back to node...
    )
)

if not defined JS_RUNTIME_PATH (
    call :resolve_tool node NODE_PATH
    if errorlevel 1 (
        echo deno was not bundleable and node was not found.
        goto missing_prerequisite
    )

    call :is_readable "!NODE_PATH!"
    if errorlevel 1 (
        echo node was found but cannot be read by PyInstaller: !NODE_PATH!
        goto missing_prerequisite
    )

    set "JS_RUNTIME_NAME=node"
    set "JS_RUNTIME_PATH=!NODE_PATH!"
)

echo Runtime tools for release build:
echo   ffmpeg:     %FFMPEG_PATH%
echo   ffprobe:    %FFPROBE_PATH%
echo   JS runtime: %JS_RUNTIME_NAME% at %JS_RUNTIME_PATH%
echo.

echo Cleaning previous logs...
:: === Optional: Keep only last 5 logs, delete older ===
for /f "skip=5 delims=" %%F in ('dir /b /o-d build_log_*.txt 2^>nul') do del "%%F"

:: === Remove existing EXE if overwrite allowed ===
if exist "%EXE_PATH%" (
    if /i "%OVERWRITE%"=="y" (
        del /q "%EXE_PATH%"
        echo Removed existing EXE >> "%LOG_FILE%"
    ) else (
        call :generate_unique_name
    )
)

:: === RUN PYINSTALLER ===
echo Building executable: %FILE_NAME%.exe...
python -m PyInstaller ^
    --clean ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "%FILE_NAME%" ^
    --add-binary "%FFMPEG_PATH%;." ^
    --add-binary "%FFPROBE_PATH%;." ^
    --add-binary "%JS_RUNTIME_PATH%;." ^
    --hidden-import yt_dlp_ejs ^
    --collect-data yt_dlp_ejs ^
    --collect-submodules yt_dlp_ejs ^
    --copy-metadata yt-dlp ^
    --copy-metadata yt-dlp-ejs ^
    "%SOURCE%" >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo Build failed! Check !LOG_FILE! for details.
    pause
    exit /b 1
)

echo Build complete: !EXE_PATH! >> "%LOG_FILE%"
echo Build complete: !EXE_PATH!

:: === ZIP Handling ===
if "!DO_ZIP!"=="true" (
    if exist "!ZIP_NAME!" (
        if /i "!OVERWRITE!"=="y" (
            del /q "!ZIP_NAME!"
            echo Overwriting ZIP: !ZIP_NAME!
        ) else (
            call :generate_unique_zip_name
        )
    )

    echo Zipping !EXE_PATH! build into !ZIP_NAME!...
    tar -a -cf "!ZIP_NAME!" -C "dist" "!FILE_NAME!.exe" >> "!LOG_FILE!" 2>&1
    if errorlevel 1 (
        echo Zip creation failed! Keeping built executable at !EXE_PATH!.
        echo Check !LOG_FILE! for details.
        pause
        exit /b 1
    )

    echo Removing executable after zipping...
    del /q "!EXE_PATH!" >> "!LOG_FILE!"
    set "OUTPUT_PATH=!ZIP_NAME!"
) else (
    echo Skipping ZIP. Keeping built .exe
    set "OUTPUT_PATH=!EXE_PATH!"
)

:: === CLEAN UP ===
echo Cleaning up...
rmdir /s /q build >> "%LOG_FILE%" 2>&1
del /q *.spec >> "%LOG_FILE%" 2>&1
echo Cleaned up temporary build files

echo Done. Output file: !OUTPUT_PATH!
echo See %LOG_FILE% for build log.
pause
exit /b 0

:missing_prerequisite
echo Missing release build prerequisite.
echo Install ffmpeg/ffprobe and a bundleable JavaScript runtime, such as node or deno.
echo Ensure they are discoverable by PATH or PowerShell Get-Command, then rerun this script.
pause
exit /b 1

:: === Helper: Resolve a tool from PATH or PowerShell command discovery ===
:resolve_tool
set "%~2="
for /f "delims=" %%I in ('where %~1 2^>nul') do (
    if not defined %~2 set "%~2=%%I"
)
if not defined %~2 (
    for /f "delims=" %%I in ('powershell -NoProfile -Command "$cmd = Get-Command -Name '%~1' -ErrorAction SilentlyContinue; if ($cmd) { $cmd.Source }" 2^>nul') do (
        if not defined %~2 set "%~2=%%I"
    )
)
if not defined %~2 exit /b 1
exit /b 0

:: === Helper: Verify PyInstaller can read a binary path ===
:is_readable
powershell -NoProfile -Command "try { $s=[IO.File]::Open('%~1',[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite); $s.Dispose(); exit 0 } catch { exit 1 }"
exit /b %errorlevel%

:: === Helper: Generate Unique EXE Name ===
:generate_unique_name
set COUNT=1
:try_exe_name
set "ALT_NAME=%FILE_NAME%_v!COUNT!"
set "EXE_PATH=dist\!ALT_NAME!.exe"
if exist "!EXE_PATH!" (
    set /a COUNT+=1
    goto try_exe_name
)
set "FILE_NAME=!ALT_NAME!"
echo Using new EXE name: !FILE_NAME!
goto :eof

:: === Helper: Generate Unique ZIP Name ===
:generate_unique_zip_name
set COUNT=1
:try_zip_name
set "ALT_ZIP=%ZIP_NAME:~0,-4%_v!COUNT!.zip"
if exist "!ALT_ZIP!" (
    set /a COUNT+=1
    goto try_zip_name
)
set "ZIP_NAME=!ALT_ZIP!"
echo Using new ZIP name: !ZIP_NAME!
goto :eof
