#!/usr/bin/env bash
# 압전 발판 젯슨 버전 실행
#   ./run_jetson.sh              → 메뉴 (1 실시간 / 2 최근 측정 재생)
#   ./run_jetson.sh --sim        → 옵션을 주면 메뉴 없이 그대로 실행 (piezo_jetson_v1.py 옵션)
cd "$(dirname "$0")"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export LANG="${LANG:-C.UTF-8}"
export DISPLAY="${DISPLAY:-:0}"          # ssh 로 실행해도 모니터에 뜨게
if [ "$#" -gt 0 ]; then
  exec python3 piezo_jetson_v1.py "$@"
fi
echo "============================================"
echo " 압전 발판 — 젯슨 (Esc 종료, Tab 화면 전환)"
echo " * logger.py / 아두이노 IDE 시리얼 모니터는 닫아 두세요"
echo "============================================"
echo "  1. 실시간 측정 - 아두이노 USB 연결"
echo "  2. 재생 - 가장 최근 측정 데이터"
read -r -p "번호 [1/2]: " n
if [ "$n" = "2" ]; then
  last=""
  for d in $(ls -1d ../piezo_main/piezo_* 2>/dev/null | sort -r); do
    if [ -f "$d/raw_serial.txt" ]; then last="$d"; break; fi
  done
  if [ -z "$last" ]; then echo "piezo_main 에 측정 데이터가 없습니다."; exit 1; fi
  echo "재생: $last"
  python3 piezo_jetson_v1.py --replay "$last/raw_serial.txt"
else
  python3 piezo_jetson_v1.py
fi
