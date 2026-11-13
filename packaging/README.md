# Packaging — Windows installer

One command builds everything:

```
packaging\build_installer.bat
```

Output: `packaging\output\LibraryManagementSystem-Setup-1.0.exe` (~280 MB).

The setup detects XAMPP (drives C:..G: + registry). If missing it first
installs the Microsoft VC++ runtime quietly (no reboot — XAMPP's own
vcredist step would otherwise restart the PC before its Start Menu shortcuts
are created), then offers the bundled official XAMPP 8.3.36 installer, runs
it, waits, then continues. It installs to
`C:\Program Files\LibraryManagementSystem`, adds Start Menu +
optional desktop shortcuts, and writes a credential-free `.env` to
`%LOCALAPPDATA%\LibraryManagementSystem\` (never overwrites an existing one).
The app creates the database and runs migrations on first launch; failures
are logged to `%LOCALAPPDATA%\LibraryManagementSystem\lms.log`.

## Prerequisites (build machine only)

- Python 3.11 + `pip install pyinstaller` (project deps installed)
- Inno Setup 6 or 7 (ISCC.exe) — https://jrsoftware.org/isdl.php
- `packaging\vendor\xampp-installer.exe` — official XAMPP Windows installer,
  e.g. from https://www.apachefriends.org/download.html (any
  `xampp-windows-*.exe` dropped into `vendor\` is auto-renamed by the script)
- `packaging\vendor\vc_redist.x64.exe` — Microsoft VC++ runtime; downloaded
  automatically by `build_installer.bat` if missing
- `packaging\vendor\flet-windows.zip` — offline flet desktop client. Rebuild
  after a flet version bump:
  `Compress-Archive -Path "$env:USERPROFILE\.flet\client\flet-desktop-full-<ver>\flet" -DestinationPath packaging\vendor\flet-windows.zip`

## Pieces

| File | Role |
| --- | --- |
| `lms.spec` | PyInstaller onedir windowed spec (assets, migrations, flet zip, excludes) |
| `build.bat` | PyInstaller build + bundle verification |
| `setup.iss` | Inno Setup script (XAMPP probe/page, shortcuts, `.env`) |
| `env.template` | Clean `.env` shipped to the user data dir |
| `app.ico` | Icon (generated from `app/assets/softwarelogo.png`) |

Skip `build.bat` alone if you only want the app bundle (`dist\LibraryManagementSystem\`).
