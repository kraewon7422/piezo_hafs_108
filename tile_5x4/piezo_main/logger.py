# 압전 타일 로거 v3.1 — 아두이노 출력을 줄 종류별 CSV로 나눠 저장
# 설치: pip install pyserial
# 실행: python logger.py                (우노 포트를 자동으로 찾음)
#       python logger.py COM5           (포트를 직접 지정할 때, 맥: /dev/cu.usbmodemXXXX)
# 끝내기: q 키 (윈도우) 또는 Ctrl+C
# ※ Arduino IDE의 시리얼 모니터는 꼭 닫고 실행 (한 포트는 한 프로그램만 열 수 있음)
# 재처리: python logger.py --replay 저장된_원본.txt   (시리얼 대신 파일을 읽어 같은 CSV를 다시 만듦)
#
# 만들어지는 폴더: piezo_날짜_시각/
#   raw_serial.txt  아두이노가 보낸 모든 줄 그대로 (원자료 보존)
#   meta.csv        설정값(M)
#   baseline.csv    시작 2초 잡음 기준선(B)
#   raw.csv         2 ms마다 ADC 값 (R)
#   pulses.csv      펄스마다 요약 (P)
#   status.csv      10초마다 상태 (S)
#   errors.txt      형식이 맞지 않아 버린 줄
#   columns.txt     각 CSV 열의 뜻과 단위
import sys, csv, os, time, datetime

ROW_FIELDS = ["peak_V", "t_first_ms", "t_peak_ms", "above_ms", "E_uJ", "Q_nC", "clip"]
SCHEMA = {
    "M": ["pc_time", "type", "version", "VREF", "R1", "R2", "sample_us", "th_on_V", "th_off_V"],
    "B": ["pc_time", "type", "t_ms"] + [f"mean{i}_V" for i in range(1, 5)] + [f"max{i}_V" for i in range(1, 5)],
    "R": ["pc_time", "t_ms", "a1", "a2", "a3", "a4"],
    "P": ["pc_time", "pulse_no", "t_start_ms", "dur_ms", "gap_ms", "rows_hit", "order"]
         + [f"r{i}_{f}" for i in range(1, 5) for f in ROW_FIELDS],
    "S": ["pc_time", "t_ms", "pulses", "dropped_samples"] + [f"idle_max{i}_V" for i in range(1, 5)],
}
COLUMN_DOC = """각 CSV 열의 뜻과 단위
공통: pc_time = 노트북 시각(년-월-일T시:분:초.밀리초), t_ms = 우노가 켜진 뒤 흐른 시간(ms)

meta.csv     version 코드 버전 / VREF 우노 5V 전압(V) / R1·R2 분압 저항(Ω) / sample_us 샘플 간격(µs) / th_on_V·th_off_V 펄스 시작·끝 문턱(V, 행 전압 기준)
baseline.csv mean1~4_V 아무도 안 밟았을 때 행별 평균 전압 / max1~4_V 같은 때 최대 전압 (V)
raw.csv      a1~a4 = 1~4행 ADC 값(0~1023). 행 전압(V) = a × VREF ÷ 1023 × (R1 + R2) ÷ R2  (기본값이면 a × 0.0538)
pulses.csv   pulse_no 펄스 번호 / t_start_ms 시작 시각 / dur_ms 지속 시간 / gap_ms 앞 펄스 끝에서 이 펄스 시작까지(첫 펄스는 0)
             rows_hit 문턱을 넘은 행 수 / order 행이 처음 넘은 순서(예: 12 = 1행 다음 2행, 0 = 없음)
             r1~r4_peak_V 행별 최대 전압(V) / r?_t_first_ms 펄스 시작부터 그 행이 문턱을 넘기까지(ms, -1 = 안 넘음)
             r?_t_peak_ms 펄스 시작부터 그 행 최대값까지(ms) / r?_above_ms 문턱 위에 있던 시간(ms)
             r?_E_uJ 1.1 MΩ 부하에 전달된 에너지(µJ) = Σ V²/R × Δt / r?_Q_nC 부하로 흐른 전하(nC) = Σ V/R × Δt
             r?_clip 1이면 측정 한계(약 54 V)를 넘어 값이 잘림
status.csv   pulses 지금까지 펄스 수 / dropped_samples 밀려서 놓친 샘플 수 / idle_max1~4_V 최근 10초 동안 안 밟았을 때 최대 전압
"""


def find_port():
    """우노(CH340·Arduino) 포트를 자동으로 찾음. 못 찾으면 목록을 보여 주고 물어봄."""
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    for p in ports:
        desc = f"{p.description} {p.manufacturer or ''} {p.hwid}".lower()
        if any(k in desc for k in ("ch340", "arduino", "wch", "usb-serial", "1a86", "2341")):
            return p.device
    if len(ports) == 1:
        return ports[0].device
    print("우노 포트를 자동으로 못 찾았습니다. 연결된 포트:")
    for p in ports:
        print("  ", p.device, "-", p.description)
    return input("사용할 포트 이름을 입력하세요 (예: COM5): ").strip()


def stop_key_pressed():
    if os.name == "nt":
        import msvcrt
        if msvcrt.kbhit() and msvcrt.getwch() in ("q", "Q"):
            return True
    return False


FILES = {"M": "meta.csv", "B": "baseline.csv", "R": "raw.csv", "P": "pulses.csv", "S": "status.csv"}


def parse_line(line):
    """아두이노 한 줄 → (종류, 값 목록) 또는 (None, 이유)."""
    line = line.strip()
    if not line:
        return None, "empty"
    parts = line.split(",")
    kind = parts[0]
    if kind not in SCHEMA:
        return None, "unknown"
    expect = len(SCHEMA[kind]) - 1          # pc_time 제외
    if kind in ("M", "B"):
        values = parts                       # 종류 글자도 type 열로 저장
    else:
        values = parts[1:]
    if len(values) != expect:
        return None, f"fields {len(values)} != {expect}"
    return kind, values


class Writer:
    def __init__(self, folder):
        os.makedirs(folder, exist_ok=True)
        self.folder = folder
        self.raw = open(os.path.join(folder, "raw_serial.txt"), "w", encoding="utf-8")
        self.err = open(os.path.join(folder, "errors.txt"), "w", encoding="utf-8")
        with open(os.path.join(folder, "columns.txt"), "w", encoding="utf-8") as f:
            f.write(COLUMN_DOC)
        self.files, self.writers = {}, {}
        self.count = {k: 0 for k in SCHEMA}
        self.bad = 0
        self.last_flush = time.time()

    def _writer(self, kind):
        name = FILES[kind]
        if name not in self.files:
            f = open(os.path.join(self.folder, name), "w", newline="", encoding="utf-8-sig")  # 엑셀 한글 안 깨짐
            w = csv.writer(f)
            w.writerow(SCHEMA[kind])
            self.files[name], self.writers[name] = f, w
        return self.writers[name]

    def handle(self, line, pc_time=None):
        pc_time = pc_time or datetime.datetime.now().isoformat(timespec="milliseconds")
        self.raw.write(line.rstrip("\r\n") + "\n")
        kind, values = parse_line(line)
        if kind is None:
            if values not in ("empty",):
                self.bad += 1
                self.err.write(f"{pc_time}\t{values}\t{line.strip()}\n")
            return None
        self._writer(kind).writerow([pc_time] + values)
        self.count[kind] += 1
        if time.time() - self.last_flush > 1.0:
            self.flush()
        return kind, values

    def flush(self):
        for f in list(self.files.values()) + [self.raw, self.err]:
            f.flush()
        self.last_flush = time.time()

    def close(self):
        self.flush()
        for f in list(self.files.values()) + [self.raw, self.err]:
            f.close()


def main():
    folder = datetime.datetime.now().strftime("piezo_%Y%m%d_%H%M%S")
    replay = len(sys.argv) >= 3 and sys.argv[1] == "--replay"
    w = Writer(folder)
    try:
        if replay:
            with open(sys.argv[2], encoding="utf-8") as f:
                for line in f:
                    w.handle(line, pc_time="replay")
        else:
            import serial
            port = sys.argv[1] if len(sys.argv) >= 2 else find_port()
            print(f"포트 {port}, 250000 baud 로 연결합니다. 저장 폴더: {folder}")
            with serial.Serial(port, 250000, timeout=0.5) as ser:
                # 포트를 열면 우노가 재시작됨. 버퍼를 비우지 않고 처음 줄(M·B)부터 모두 받음.
                t_open = time.time()
                asked_meta = False
                last_print = 0
                print("기록 중... (끝내려면 q 또는 Ctrl+C)")
                print("처음 2초 동안은 타일을 밟지 마세요 (잡음 기준선 측정).")
                while True:
                    if stop_key_pressed():
                        break
                    if not asked_meta and time.time() - t_open > 3:
                        ser.write(b"m")          # 혹시 놓쳤을 때를 대비해 설정값을 한 번 더 요청
                        asked_meta = True
                    raw = ser.readline()
                    if not raw:
                        continue
                    r = w.handle(raw.decode("utf-8", "ignore"))
                    if not r:
                        continue
                    kind, v = r
                    if kind == "B":
                        print("잡음 기준선 측정 완료 → 이제 밟아도 됩니다.")
                    elif kind == "P":
                        print(f"펄스 {v[0]:>4}: {v[2]:>4} ms, 행 순서 {v[5]:>4}, "
                              f"피크 {v[6]} / {v[13]} / {v[20]} / {v[27]} V")
                    elif kind == "S":
                        print(f"[상태] 펄스 {v[1]}개, 놓친 샘플 {v[2]}개, 원자료 {w.count['R']}줄 저장")
                    elif kind == "R" and w.count["R"] == 1:
                        print("원자료(R) 수신 시작")
                    if time.time() - last_print > 30 and w.count["R"] == 0 and time.time() - t_open > 5:
                        print("※ 원자료가 안 들어옵니다. 우노 코드 버전(v3 이상)과 포트를 확인하세요.")
                        last_print = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        w.close()
        print("\n저장 완료:", folder)
        print("  줄 수:", {k: v for k, v in w.count.items() if v}, " 버린 줄:", w.bad)
        if w.count["P"] == 0:
            print("  ※ 펄스가 0개입니다. 판 연결이나 문턱(1 V)을 확인하세요.")
    return folder


if __name__ == "__main__":
    main()
