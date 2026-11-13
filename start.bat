@echo off
setlocal

:: Find SSL cert path via Python, set it for flet
for /f "usebackq delims=" %%i in (`python -c "import certifi; print(certifi.where())" 2^>nul`) do (
    set "SSL_CERT_FILE=%%i"
)

if defined SSL_CERT_FILE (
    echo SSL_CERT_FILE=%SSL_CERT_FILE%
) else (
    echo WARNING: certifi not found. Run: pip install certifi
)

python start.py %*
