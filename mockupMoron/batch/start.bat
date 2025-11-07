@echo off
rem === Launch Photoshop headless batch ===
set "PS_PATH=C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe"
set "JSX_PATH=C:\Users\Santiago\Desktop\batch test\headless_batch_replace.jsx"

rem Optional: change to the script folder so relative paths resolve
cd /d "%~dp0"

echo Launching Photoshop with %JSX_PATH% ...
"%PS_PATH%" "%JSX_PATH%"
echo Done.
pause
