@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 本目录尚未安装文献工具运行环境，请把此提示告诉agent。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "service_launcher.py" --open
if errorlevel 1 (
  pause
  exit /b 1
)
timeout /t 3 /nobreak >nul
exit /b 0
