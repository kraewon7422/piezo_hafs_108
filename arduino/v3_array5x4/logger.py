# [저장소 메모] 2026-11-13 piezo_array_5x4.ino 용 CSV 저장 도구. 아직 실제 보드로 돌려 보지 않았다.
# pip install pyserial  /  python logger.py <포트>   예) 윈도우 COM3, 맥 /dev/cu.usbmodemXXXX
import sys, serial, datetime

port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
name = datetime.datetime.now().strftime("piezo_%Y%m%d_%H%M%S.csv")
with serial.Serial(port, 115200, timeout=1) as ser, open(name, "w", encoding="utf-8") as f:
    print("저장 중:", name, "(끝내려면 Ctrl+C)")
    try:
        while True:
            line = ser.readline().decode("utf-8", "ignore").strip()
            if not line:
                continue
            stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
            f.write(stamp + "," + line + "\n")
            f.flush()
            if line.startswith("STEP"):
                print(line)
    except KeyboardInterrupt:
        print("종료")
