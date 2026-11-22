@echo off
chcp 65001 > nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
title 압전 발판 실시간 GUI
echo ============================================
echo  압전 발판 실시간 GUI  (piezo_gui_v1.py)
echo  * Arduino IDE 시리얼 모니터와 logger.py 는 닫아 두세요
echo ============================================
set "PY=python"
python --version >nul 2>nul || set "PY=py"
%PY% -c "import serial, pygame" >nul 2>nul || goto install
goto ready
:install
echo 필요한 패키지를 설치합니다: pyserial, pygame-ce
%PY% -m pip install pyserial pygame-ce
:ready

rem raw_serial.txt 를 이 bat 파일 위에 끌어다 놓으면 바로 재생
if not "%~1"=="" (
  %PY% piezo_gui_v1.py --replay "%~1"
  goto end
)

echo.
echo   1. 실시간 측정 - 아두이노 연결
echo   2. 재생 - 가장 최근 측정 데이터, 아두이노 없이 시연
echo.
choice /c 12 /n /m "번호를 누르세요 [1/2]: "
if errorlevel 2 goto replay
%PY% piezo_gui_v1.py
goto end

:replay
set "LAST="
for /f "delims=" %%d in ('dir /b /ad /o-n "..\piezo_main\piezo_*" 2^>nul') do (
  if not defined LAST if exist "..\piezo_main\%%d\raw_serial.txt" set "LAST=%%d"
)
if not defined LAST (
  echo piezo_main 폴더에 저장된 측정 데이터가 없습니다.
  goto end
)
echo 재생할 데이터: %LAST%
%PY% piezo_gui_v1.py --replay "..\piezo_main\%LAST%\raw_serial.txt"

:end
echo.
pause
