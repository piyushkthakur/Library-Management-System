@echo off
setlocal
:: Full build: LMS app bundle + Windows installer.
:: Output: packaging\output\LibraryManagementSystem-Setup-1.0.exe
cd /d "%~dp0"

:: [1/3] application bundle (PyInstaller)
call build.bat
if errorlevel 1 exit /b 1

:: [2/3] XAMPP installer must sit in vendor\ under a fixed name
if not exist "vendor\xampp-installer.exe" (
    for %%F in (vendor\xampp-windows-*.exe) do (
        if not exist "vendor\xampp-installer.exe" (
            echo Preparing vendor\xampp-installer.exe from %%~nxF
            copy /y "%%F" "vendor\xampp-installer.exe" >nul
        )
    )
)
if not exist "vendor\xampp-installer.exe" (
    echo.
    echo XAMPP installer not found in packaging\vendor\
    echo Download the official XAMPP Windows installer from https://www.apachefriends.org/download.html
    echo ^(any name matching xampp-windows-*.exe^) and place it there, then run this script again.
    exit /b 1
)

:: VC++ runtime (pre-installed before XAMPP so its vcredist step can't reboot the PC)
if not exist "vendor\vc_redist.x64.exe" (
    echo Downloading Microsoft Visual C++ runtime installer...
    curl.exe -sL --retry 3 -o "vendor\vc_redist.x64.exe" "https://aka.ms/vs/17/release/vc_redist.x64.exe"
)
if not exist "vendor\vc_redist.x64.exe" (
    echo Failed to obtain vendor\vc_redist.x64.exe
    echo Download https://aka.ms/vs/17/release/vc_redist.x64.exe manually into packaging\vendor\ and retry.
    exit /b 1
)

:: [3/3] locate Inno Setup compiler
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo Inno Setup compiler not found. Install it from https://jrsoftware.org/isdl.php
    exit /b 1
)

echo === [3/3] Compiling installer ===
"%ISCC%" setup.iss
if errorlevel 1 (
    echo INSTALLER BUILD FAILED.
    exit /b 1
)
echo.
echo INSTALLER OK: output\LibraryManagementSystem-Setup-1.0.exe
exit /b 0
