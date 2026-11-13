# [저장소 메모] v1 — piezo_capture_v1.ino 용으로 만든 CSV 저장 도구.
#   주의: 첫 데이터 줄 앞에 6열 헤더(event,n,t_us,adc_raw,v_piezo,p_mW)를 고정으로 쓴다.
#   piezo_capture_simple.ino(5열) 출력을 받으면 헤더 열 수가 맞지 않으니,
#   그 경우에는 receive_csv_v1.ps1(받은 줄을 그대로 저장)을 쓰거나 CSV 첫 헤더 줄을 고쳐 쓴다.
# serial_to_csv v1 (2026-09-11)
# v1: 아두이노 시리얼 -> output 폴더에 CSV 저장 + 이벤트 요약 화면 출력

import argparse
import os
import sys
from datetime import datetime

BAUD = 500000
HEADER = "event,n,t_us,adc_raw,v_piezo,p_mW"


def list_ports():
    """연결된 시리얼 포트를 보여준다."""
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    if not ports:
        print("포트를 못 찾았습니다. 아두이노 USB가 꽂혀 있는지 확인하세요.")
        return
    print("사용 가능한 포트:")
    for p in ports:
        print(f"  {p.device}  -  {p.description}")


def make_outpath(tag):
    """output/piezo_1M_20260911_1530.csv 같은 파일 경로를 만든다."""
    os.makedirs("output", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"piezo_{tag}_{stamp}.csv" if tag else f"piezo_{stamp}.csv"
    return os.path.join("output", name)


def process_line(line, state, csv_file):
    """한 줄을 받아서 CSV에 쓰거나 화면에 요약을 띄운다.

    state는 딕셔너리 하나로 상태를 들고 다닌다 (헤더 썼는지, 이벤트 몇 개인지).
    """
    line = line.strip()
    if not line:
        return

    if line.startswith("#"):
        # 설정/요약 줄은 화면에 보여주고, CSV에도 주석으로 남긴다
        print(line)
        csv_file.write(line + "\n")
        if line.startswith("# event"):
            state["events"] += 1
        return

    if line.startswith("event,"):
        # 아두이노가 보낸 헤더는 한 번만 쓴다
        if not state["header_written"]:
            csv_file.write(HEADER + "\n")
            state["header_written"] = True
        return

    if not state["header_written"]:
        csv_file.write(HEADER + "\n")
        state["header_written"] = True

    csv_file.write(line + "\n")
    state["rows"] += 1


def run_serial(port, tag):
    import serial

    path = make_outpath(tag)
    state = {"header_written": False, "rows": 0, "events": 0}

    print(f"포트 {port} 연결 중... (Ctrl+C 로 종료)")
    ser = serial.Serial(port, BAUD, timeout=1)

    with open(path, "w", encoding="utf-8") as f:
        try:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                process_line(raw.decode("utf-8", errors="ignore"), state, f)
                f.flush()   # 중간에 뽑아도 데이터가 남도록 매번 저장
        except KeyboardInterrupt:
            print("\n중단했습니다.")
        finally:
            ser.close()

    print(f"저장 완료: {path}")
    print(f"  이벤트 {state['events']}개 / 데이터 {state['rows']}줄")


def run_demo(src, tag):
    """시리얼 없이 텍스트 파일로 동작을 확인하는 모드."""
    path = make_outpath(tag)
    state = {"header_written": False, "rows": 0, "events": 0}
    with open(src, encoding="utf-8") as inp, open(path, "w", encoding="utf-8") as f:
        for line in inp:
            process_line(line, state, f)
    print(f"저장 완료: {path}")
    print(f"  이벤트 {state['events']}개 / 데이터 {state['rows']}줄")


def main():
    ap = argparse.ArgumentParser(description="압전 데이터 CSV 로거")
    ap.add_argument("--port", help="예: COM3 (윈도우) / /dev/ttyUSB0 (맥·리눅스)")
    ap.add_argument("--tag", default="", help="파일 이름에 붙일 메모. 예: 1M")
    ap.add_argument("--list", action="store_true", help="포트 목록만 보기")
    ap.add_argument("--demo", help="시리얼 대신 텍스트 파일로 테스트")
    args = ap.parse_args()

    if args.list:
        list_ports()
    elif args.demo:
        run_demo(args.demo, args.tag)
    elif args.port:
        run_serial(args.port, args.tag)
    else:
        print("사용법: python serial_to_csv_v1.py --port COM3 --tag 1M")
        print("       python serial_to_csv_v1.py --list")
        sys.exit(1)


if __name__ == "__main__":
    main()
