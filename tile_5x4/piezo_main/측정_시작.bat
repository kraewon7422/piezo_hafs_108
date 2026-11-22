@echo off
chcp 65001 > nul
cd /d "%~dp0"
title 압전 타일 측정
echo ============================================
echo  압전 타일 측정 - 저장 후 자동 분석
echo  * Arduino IDE 시리얼 모니터는 닫아 두세요
echo ============================================
set "PY=python"
where python >nul 2>nul || set "PY=py"
%PY% -c "import serial" 2>nul || (
  echo pyserial 설치 중...
  %PY% -m pip install pyserial
)
%PY% logger.py
set "LAST="
for /f "delims=" %%d in ('dir /b /ad /o-d piezo_* 2^>nul') do (
  set "LAST=%%d"
  goto found
)
:found
if not defined LAST (
  echo 저장된 폴더가 없습니다.
  pause
  exit /b
)
echo.
set "COUNT="
set /p COUNT=측정하는 동안 직접 센 인원 (모르면 그냥 Enter): 
if defined COUNT (
  %PY% analyze.py "%LAST%" --count %COUNT%
) else (
  %PY% analyze.py "%LAST%"
)
echo.
echo 결과 폴더: %LAST%   (passes.csv, summary.txt, columns.txt)
pause
