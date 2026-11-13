@echo off
setlocal
for /f "delims=" %%i in ('python -c "import certifi;print(certifi.where())" 2^>nul') do set "SSL_CERT_FILE=%%i"
for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'Scripts','flet.exe'))"') do set "FLET_EXE=%%i"
"%FLET_EXE%" %*
