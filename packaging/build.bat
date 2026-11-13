@echo off
setlocal
:: One-shot build: PyInstaller bundle for the LMS.
:: Output: dist\LibraryManagementSystem\LibraryManagementSystem.exe
cd /d "%~dp0.."

echo === [1/2] PyInstaller build (this takes a few minutes) ===
:: flet's build hook bundles the whole ~/.flet client cache (~150MB, unused at
:: runtime — the app reads vendor\flet-windows.zip instead). Point it at an
:: empty stub so it adds nothing.
if not exist "packaging\hook_stub" mkdir "packaging\hook_stub"
if not exist "packaging\hook_stub\_placeholder.txt" echo stub> "packaging\hook_stub\_placeholder.txt"
set "FLET_VIEW_PATH=%CD%\packaging\hook_stub"
pyinstaller --noconfirm --clean packaging\lms.spec
if errorlevel 1 (
    echo BUILD FAILED: pyinstaller exited with an error.
    exit /b 1
)

echo === [2/2] Verifying bundle ===
set "D=dist\LibraryManagementSystem"
set MISSING=0
for %%F in (
    LibraryManagementSystem.exe
    _internal\alembic.ini
    _internal\migrations\env.py
    _internal\migrations\versions\0001_baseline.py
    _internal\assets\bgdashboard.jpg
    _internal\assets\softwarelogo.png
    _internal\flet_desktop\app\flet-windows.zip
    _internal\certifi\cacert.pem
) do (
    if not exist "%D%\%%F" (
        echo MISSING: %%F
        set MISSING=1
    )
)
if "%MISSING%"=="1" (
    echo BUILD FAILED: bundle is incomplete.
    exit /b 1
)
echo BUILD OK: %D%
exit /b 0
