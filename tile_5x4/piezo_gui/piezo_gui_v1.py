# -*- coding: utf-8 -*-
"""
압전 발판 실시간 GUI v1 — 가로형(16:9) 발표·시연용

실행
  python piezo_gui_v1.py                       아두이노 실시간 (포트 자동 검색, piezo_main 에 측정 폴더 저장)
  python piezo_gui_v1.py --port COM5           포트 직접 지정
  python piezo_gui_v1.py --replay 파일.txt      저장된 raw_serial.txt 재생 (아두이노 없이 시연)
  python piezo_gui_v1.py --replay 파일.txt --speed 4
  python piezo_gui_v1.py --replay 파일.txt --snapshot 폴더 --until 20   (검증용: 20초 지점 화면을 PNG로 저장)

키
  Tab 화면 전환(A 실시간 → B 설계 vs 측정 → C 확장 → D 개선)   F11 전체화면   F12 화면 PNG 저장   Esc 종료
  Z 잡음 기준선 다시 측정(실시간)   R 기록 초기화
  재생: Space 일시정지, 1/2/4/8 속도
  화면 D: ↑↓ 항목 선택, ←→ 값 바꾸기

piezo_main/logger.py 의 parse_line·Writer 를 그대로 써서, 실시간 측정 때 logger.py 와 똑같은 폴더가 저장됨
(→ 측정 후 piezo_main/analyze.py 로 같은 분석 가능)
"""
import os, sys, time, math, queue, threading, argparse, datetime, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_DIR = os.path.normpath(os.path.join(HERE, "..", "piezo_main"))
sys.path.insert(0, MAIN_DIR)
import logger  # noqa: E402  (piezo_main/logger.py)

# ═════════════ 발표 전에 바꿀 수 있는 가정값 ═════════════
DEFAULT_E_STEP_UJ = 8.30        # 실측 통과가 아직 없을 때 쓸 걸음(통과)당 에너지 µJ (2026-11-21 시험 측정 평균)
COMMERCIAL_J_PER_STEP = 3.0     # 상용 발전 타일 걸음당 에너지 J (가정, 업체 발표 2~5 J 수준, 대부분 전자기 방식)
TILE_W_M, TILE_L_M = 0.5, 0.4    # 발판 1장 크기 (가로 × 걷는 방향) m — 조립 매뉴얼 50 × 40 cm 예시
STRIDE_M = 0.65                 # 보폭 m → 1명이 발판 위를 걷는 걸음 수 = 통로 길이 ÷ 보폭
SCENARIOS = [                   # 발판 장수 = (폭 ÷ 발판 가로) × (길이 ÷ 발판 세로), 하루 걸음 = 인원 × 끼니 × 1명당 걸음
    dict(name="외대부고 급식실", color="ORG", people=1200, per_day=3, area_w=2.0, area_l=2.4,
         who="학생·교직원 1,200명 × 하루 3끼", where="급식실 입구 통로"),
    dict(name="도심 지하철역", color="CYAN", people=150000, per_day=1, area_w=10.0, area_l=4.0,
         who="하루 승하차 15만 명 (번화가 역)", where="개찰구 앞 통로"),
]


def scenario_numbers(sc):
    """(발판 장수, 1명당 걸음, 하루 걸음)"""
    tiles = math.ceil(sc["area_w"] / TILE_W_M - 1e-9) * math.ceil(sc["area_l"] / TILE_L_M - 1e-9)
    per_person = max(1, round(sc["area_l"] / STRIDE_M))
    return tiles, per_person, sc["people"] * sc["per_day"] * per_person


UNITS = [  # (이름, 설명, 종류, 기준값)  count: 1회당 J / time: 전력 W / pct: 완충 J
    ("IoT 센서 무선 전송", "1회 약 100 µJ", "count", 100e-6),
    ("LED 표시등 켜기", "20 mW", "time", 0.02),
    ("사과 1개를 1 m 들어 올리기", "약 1 J", "count", 0.98),
    ("10 W LED 전구 켜기", "", "time", 10.0),
    ("스마트폰 충전", "완충 약 15 Wh", "pct", 54000.0),
]
LEVERS = [  # 화면 C 개선 계산기: (이름, 원리 설명, [(값 표시, 배수)])
    ("디스크 수", "E ∝ 디스크 수 · 지금 20개 (4행 × 5열)",
     [("20개", 1), ("40개", 2), ("60개", 3), ("80개", 4)]),
    ("디스크로 가는 힘", "E ∝ F² · 상판·범폰·받침을 거치며 힘이 나뉨",
     [("지금", 1), ("1.5배", 2.25), ("2배", 4), ("3배", 9)]),
    ("압전 소재·형태", "E ∝ d²/C · 적층형·고성능 PZT",
     [("지금", 1), ("×2", 2), ("×4", 4), ("×8", 8)]),
    ("수확 회로", "측정 저항 → 정류·저장 최적화 → 능동 회로(SSHI 등)",
     [("지금", 1), ("×2", 2), ("×3", 3), ("×4", 4)]),
]
LIMITS = [
    ("측정 방식", "1.1 MΩ 측정 저항에서 쓰인 에너지 — 모아서 저장한 양이 아님"),
    ("디스크 배치", "디스크 20개(4행 × 5열) 중 한 걸음에 실제로 눌리는 건 일부뿐"),
    ("힘 전달", "체중이 디스크 20개와 판·받침에 나뉘어 실려 디스크 하나는 조금만 휨"),
    ("회로", "브리지 다이오드 전압 손실, 저장·변환 회로 없음"),
    ("인원 감지", "같은 사람이 여러 번 밟으면 1명으로 묶임 (오차 있음)"),
]
# ═══════════════════════════════════════════════════════

# ── 설계(이론)값: 실제 발판(조립 매뉴얼) + piezo_sim.py 의 압전계수·하중 ──
TH_D_EFF = 11e-9                # 유효 압전계수 C/N (굽힘 모드 디스크, 가정 — piezo_sim.py)
TH_N_DISK = 20                  # 디스크 수 (4행 × 5열, 디스크마다 브리지 정류기 — 조립 매뉴얼)
TH_ROWS = 4
TH_CP_DISK = 20e-9              # 27 mm 디스크 1개 정전용량 F (매뉴얼: 15~25 nF, 멀티미터로 재면 바꾸기)
TH_FORCE = 760.0                # 걸음 하중 피크 N (약 65 kg + 충격)
TH_RISE_MS = 70                 # 하중 상승 시간 ms

PASS_GAP_MS = 1000              # analyze.py 와 같은 값: 펄스 간격이 이 이하면 같은 통과(사람)
MAX_PULSE_MS = 3000             # piezo_main.ino 의 MAX_PULSE_MS
WIN_MS = 6000                   # 파형 창
GLOW_FULL_V = 4.0               # 이 전압이면 최대 밝기
BAR_FULL_V = 6.0
W, H = 1920, 1080
DISK_X = [140, 270, 400, 530]   # 단면도에서 1~4행 디스크 x 위치
FOOT_UP = 120.0                 # 발을 든 높이(px)
FOOT_CX = 335                   # 발(=발판) 가운데 x
FOOT_SCALE = 1.4                # 발 크기: 신발 폭 약 500 px ≈ 발판 폭 538 px

BG0, BG1 = (16, 20, 32), (8, 10, 18)
PANEL, BORDER, INK = (22, 28, 44), (52, 62, 88), (12, 16, 26)
TXT, DIM = (232, 236, 246), (165, 175, 196)
MIN_FONT = 17                   # 이보다 작은 글자는 쓰지 않음 (가는 획이 흐려짐)
YEL, CYAN, GRN, RED, ORG = (255, 204, 48), (70, 205, 255), (90, 232, 150), (255, 96, 86), (255, 150, 60)
COLORS = dict(YEL=YEL, CYAN=CYAN, GRN=GRN, RED=RED, ORG=ORG)
ROWC = [YEL, ORG, CYAN, GRN]    # 1~4행 색 (발판 그림과 파형에 공통)

FONT_R = r"C:\Windows\Fonts\malgun.ttf"
FONT_B = r"C:\Windows\Fonts\malgunbd.ttf"


# ───────────────────────── 숫자 표시 ─────────────────────────
def fmt_E(j):
    """J → (숫자 문자열, 단위)"""
    a = abs(j)
    for lim, div, u in ((1e-3, 1e-6, "µJ"), (1, 1e-3, "mJ"), (1e3, 1, "J"), (1e6, 1e3, "kJ"), (1e99, 1e6, "MJ")):
        if a < lim:
            v = j / div
            return (f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}" if abs(v) < 100 else f"{v:,.0f}"), u
    return f"{j:.3g}", "J"


def fmt_count(x):
    if x >= 1e12:
        return f"{x/1e12:,.0f}조" if x >= 1e15 else f"{x/1e12:.3g}조"
    if x >= 1e8:
        return f"{x/1e8:,.0f}억" if x >= 99950e8 else f"{x/1e8:.3g}억"
    if x >= 1e4:
        return f"{x/1e4:,.0f}만" if x >= 9995e4 else f"{x/1e4:.3g}만"
    if x >= 100:
        return f"{x:,.0f}"
    if x >= 1:
        return f"{x:.3g}"
    if x <= 0:
        return "0"
    return f"{x:.2g}"


def fmt_time(s):
    if s < 1:
        if s <= 0:
            return "0초"
        return f"{s*1000:.3g} ms" if s >= 0.001 else "1 ms 미만"
    if s < 60:
        return f"{s:.3g}초"
    if s < 3600:
        return f"{s/60:.3g}분"
    if s < 86400:
        return f"{s/3600:.3g}시간"
    return f"{s/86400:.3g}일"


def fmt_unit(j, kind, base):
    if kind == "count":
        n, u = j / base, ("회" if base < 0.5 else "번")
        return fmt_count(n) + u if n >= 0.01 or n <= 0 else f"0.01{u} 미만"
    if kind == "time":
        return fmt_time(j / base)
    p = j / base * 100
    if p >= 100:
        return f"완충 {fmt_count(p/100)}회"
    return f"{p:.2g} %" if p >= 0.001 else "0.001 % 미만"


def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def mix(c1, c2, u):
    u = max(0.0, min(1.0, u))
    return tuple(int(a + (b - a) * u) for a, b in zip(c1, c2))


# ───────────────────────── 데이터 상태 ─────────────────────────
class State:
    """아두이노 줄(M/B/R/P/S)을 받아 화면에 필요한 값으로 정리. 시간은 모두 '세션 ms'(우노 재시작해도 이어짐)."""

    def __init__(self):
        self.rate = 1.0
        self.paused = False
        self.reset_all()

    def reset_all(self):
        self.k = 5.0 / 1023 * 1.1e6 / 1e5      # ADC 1칸 → 행 전압(V) (M 줄로 갱신)
        self.th_on = 1.0
        self.rload = 1.1e6
        self.raw = collections.deque(maxlen=int(WIN_MS / 2 * 1.4))
        self.off = 0
        self.last_t = None
        self.last_wall = time.time()
        self.prev_now = None
        self.expect_cal = False
        self.have_B = False
        self.calibrating = False
        self.got_data = False
        self.cur_v = [0.0] * 4
        self.foot_x, self.foot_lift, self.last_active = FOOT_CX, FOOT_UP, -1e9
        self.fmax = [0.0] * 4
        self.env = [0.0] * 4
        self.hold = [0.0] * 4
        self.hold_t = [0] * 4
        self.t_stat0 = None
        self.dropped_raw = 0
        self.reset_stats()

    def reset_stats(self):
        self.pulses = 0
        self.passes = []
        self.cur = None
        self.total_E = 0.0           # µJ
        self.cumE = []               # (세션 ms, 누적 µJ)
        self.peak_V = 0.0
        self.dropped = 0
        self.dropped0 = self.dropped_raw      # R 키로 초기화하면 그때까지 놓친 샘플은 빼고 셈
        self.clipped = False
        self.events = []             # 발자국·에너지 팝업
        self.plist = []              # 펄스별 (E µJ, Q µC, 최대 V, 상승 ms) — 설계 비교용
        self.last_dir = 0
        if self.last_t is not None:
            self.t_stat0 = self.last_t

    # 우노 시각 → 세션 시각 (우노가 재시작해 시간이 줄어들면 이어 붙임)
    def _st(self, t):
        st = t + self.off
        if self.last_t is not None and st < self.last_t - 1500 and t < 10000:
            self.off = self.last_t + 2 - t       # 우노 재시작 → 시간 이어 붙이기
            st = t + self.off
            self.raw.clear()
            self.have_B = False
            self.dropped0 = self.dropped_raw = 0
        return st

    def _advance(self, st):
        if self.last_t is None or st > self.last_t:
            self.last_t = st
            self.last_wall = time.time()

    def feed(self, kind, v):
        try:
            self._feed(kind, v)
        except (ValueError, IndexError):
            pass                      # 깨진 줄은 무시 (logger 가 errors.txt 에 따로 남김)

    def _feed(self, kind, v):
        if kind == "RESTART":         # 재생 파일을 처음부터 다시
            r, p = self.rate, self.paused
            self.reset_all()
            self.rate, self.paused = r, p
            return
        if kind == "M":
            # parse_line 은 M·B 줄에서 종류 글자도 값에 넣음: M,버전,VREF,R1,R2,샘플us,TH_ON,TH_OFF
            vref, r1, r2 = float(v[2]), float(v[3]), float(v[4])
            self.k = vref / 1023 * (r1 + r2) / r2
            self.rload = r1 + r2
            self.th_on = float(v[6])
            self.expect_cal = True
        elif kind == "B":                       # B,ms,평균1~4,최대1~4
            self.calibrating = False
            self.have_B = True
            st = self._st(int(v[1]))
            self._advance(st)
            if self.t_stat0 is None:
                self.t_stat0 = st
        elif kind == "R":
            t = int(v[0])
            if self.expect_cal:
                self.expect_cal = False
                if t < 2100 and not self.have_B:
                    self.calibrating = True
            st = self._st(t)
            vs = [int(x) * self.k for x in v[1:5]]
            self.raw.append((st, *vs))
            self._advance(st)
            self.got_data = True
            if self.t_stat0 is None and not self.calibrating and t > 2100:
                self.t_stat0 = st
            for i in range(4):
                self.cur_v[i] = vs[i]
                if vs[i] > self.fmax[i]:
                    self.fmax[i] = vs[i]
                if vs[i] >= self.hold[i]:
                    self.hold[i], self.hold_t[i] = vs[i], st
        elif kind == "P":
            dur = int(v[2])
            t1 = self._st(int(v[1]) + dur)
            t0 = t1 - dur
            self._advance(t1)
            order = v[5]
            E = sum(float(v[6 + 7 * i + 4]) for i in range(4))
            peaks = [float(v[6 + 7 * i]) for i in range(4)]
            if any(v[6 + 7 * i + 6] == "1" for i in range(4)):
                self.clipped = True
            Q = sum(float(v[6 + 7 * i + 5]) for i in range(4)) / 1000      # nC → µC
            tps = [float(v[6 + 7 * i + 2]) for i in range(4) if v[6 + 7 * i + 1] != "-1"]
            self.plist.append(dict(E=E, Q=Q, peak=max(peaks), tr=(sum(tps) / len(tps)) if tps else None))
            self.plist = self.plist[-3000:]
            self.pulses += 1
            self.total_E += E
            self.cumE.append((t1, self.total_E))
            self.peak_V = max(self.peak_V, max(peaks))
            if self.cur and t0 - self.cur["t1"] <= PASS_GAP_MS:
                c = self.cur
            else:
                self._finish()
                d = 0
                if len(order) >= 2 and order != "0":
                    d = 1 if order[0] < order[-1] else -1
                c = self.cur = dict(E=0.0, t0=t0, t1=t1, n=0, dir=d, peak=0.0)
            c["E"] += E
            c["t1"] = max(c["t1"], t1)
            c["n"] += 1
            c["peak"] = max(c["peak"], max(peaks))
            row = int(order[0]) - 1 if order not in ("", "0") and order[0].isdigit() else peaks.index(max(peaks))
            self.events.append(dict(t=self.last_t, row=max(0, min(3, row)), E=E, dir=c["dir"]))
            self.events = self.events[-8:]
        elif kind == "S":
            st = self._st(int(v[0]))
            self._advance(st)
            d = int(v[2])
            self.dropped_raw = d
            if d < self.dropped0:
                self.dropped0 = 0
            self.dropped = d - self.dropped0

    def _finish(self):
        if self.cur:
            self.passes.append(self.cur)
            if self.cur["dir"]:
                self.last_dir = self.cur["dir"]
            self.cur = None

    def now(self):
        if self.last_t is None:
            return 0
        if self.paused:
            return self.last_t
        return self.last_t + min(250.0, (time.time() - self.last_wall) * 1000 * self.rate)

    def update(self, now):
        dt = 0 if self.prev_now is None else max(0.0, now - self.prev_now)
        self.prev_now = now
        for i in range(4):
            self.env[i] = max(self.fmax[i], self.env[i] * math.exp(-dt / 220))
            self.fmax[i] = 0.0
            if now - self.hold_t[i] > 1200:
                self.hold[i] = max(self.env[i], self.hold[i] * math.exp(-dt / 400))
        # P 줄은 펄스가 '끝난 뒤' 도착하므로(최대 3초 펄스) 그만큼 더 기다린 뒤 통과를 마감
        # 발 애니메이션: 문턱을 넘은 뒤 0.45초 동안은 발이 발판을 누르고 있는 것으로 표시
        tot = sum(self.env)
        if max(self.env) > self.th_on:
            self.last_active = now
            tx = sum(x * e for x, e in zip(DISK_X, self.env)) / tot
            self.foot_x += (tx - self.foot_x) * min(1.0, dt / 90)
        elif now - self.last_active > 450:          # 발을 들면 수평으로 돌아옴
            self.foot_x += (FOOT_CX - self.foot_x) * min(1.0, dt / 300)
        target = 0.0 if now - self.last_active < 450 else FOOT_UP
        k = dt / 18 if target < self.foot_lift else dt / 160
        self.foot_lift += (target - self.foot_lift) * min(1.0, k)
        if self.cur and now - self.cur["t1"] > PASS_GAP_MS + MAX_PULSE_MS + 100:
            self._finish()
        self.events = [e for e in self.events if now - e["t"] < 2200]

    # 요약값
    def people(self):
        return len(self.passes) + (1 if self.cur else 0)

    def e_step(self):
        """(걸음당 µJ, 근거 인원, 실측 여부)"""
        if self.passes:
            return sum(p["E"] for p in self.passes) / len(self.passes), len(self.passes), True
        if self.cur:
            return self.cur["E"], 1, True
        return DEFAULT_E_STEP_UJ, 0, False

    def elapsed_s(self, now):
        return 0.0 if self.t_stat0 is None else max(0.0, (now - self.t_stat0) / 1000)


# ───────────────────────── 입력: 시리얼 ─────────────────────────
def auto_port():
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    for p in ports:
        desc = f"{p.description} {p.manufacturer or ''} {p.hwid}".lower()
        if any(k in desc for k in ("ch340", "arduino", "wch", "usb-serial", "1a86", "2341")):
            return p.device
    return ports[0].device if len(ports) == 1 else None


class SerialSource(threading.Thread):
    live = True

    def __init__(self, q, port=None):
        super().__init__(daemon=True)
        self.q, self.port = q, port
        self.status, self.ok = "아두이노 포트 찾는 중...", False
        self.writer, self.folder = None, None
        self.stop_ev = threading.Event()
        self.cmd = queue.Queue()

    def send(self, b):
        self.cmd.put(b)

    def run(self):
        import serial
        try:
            while not self.stop_ev.is_set():
                port = self.port or auto_port()
                if not port:
                    self.status, self.ok = "아두이노 없음 — USB 연결 확인", False
                    self.stop_ev.wait(2)
                    continue
                try:
                    with serial.Serial(port, 250000, timeout=0.2) as ser:
                        if self.writer is None:
                            name = datetime.datetime.now().strftime("piezo_%Y%m%d_%H%M%S")
                            self.folder = os.path.join(MAIN_DIR, name)
                            self.writer = logger.Writer(self.folder)
                        self.status, self.ok = f"측정 중 · {port}", True
                        t_open, asked = time.time(), False
                        while not self.stop_ev.is_set():
                            while not self.cmd.empty():
                                ser.write(self.cmd.get())
                            if not asked and time.time() - t_open > 3:
                                ser.write(b"m")       # 설정값(M)을 놓쳤을 때 대비 (logger.py 와 같음)
                                asked = True
                            raw = ser.readline()
                            if not raw:
                                continue
                            r = self.writer.handle(raw.decode("utf-8", "ignore"))
                            if r:
                                self.q.put(r)
                except (serial.SerialException, OSError) as e:
                    msg = str(e)
                    if "PermissionError" in msg or "denied" in msg.lower() or "거부" in msg:
                        self.status = f"{port} 사용 중 — logger·시리얼 모니터 닫기"
                    else:
                        self.status = f"연결 끊김 ({port}) — 재연결 중"
                    self.ok = False
                    self.stop_ev.wait(2)
        finally:
            if self.writer:
                self.writer.close()

    def stop(self):
        self.stop_ev.set()


# ───────────────────────── 입력: 재생 ─────────────────────────
class ReplaySource(threading.Thread):
    live = False

    def __init__(self, q, path, speed=1.0):
        super().__init__(daemon=True)
        self.q, self.path, self.speed = q, path, speed
        self.paused, self.rebase = False, True
        self.stop_ev = threading.Event()
        self.ok, self.bad = True, False
        self.folder = os.path.dirname(os.path.abspath(path))

    @property
    def status(self):
        if self.bad:
            return "재생 파일에 원자료(R 줄)가 없습니다"
        s = f"재생 {self.speed:g}×" + (" · 일시정지" if self.paused else "")
        return s + f" · {os.path.basename(self.folder)}"

    def set_speed(self, s):
        self.speed, self.rebase = s, True

    def send(self, b):
        pass

    def run(self):
        while not self.stop_ev.is_set():
            got_r = False
            with open(self.path, encoding="utf-8", errors="ignore") as f:
                t_base = wall_base = None
                for line in f:
                    if self.stop_ev.is_set():
                        return
                    kind, v = logger.parse_line(line)
                    if kind is None:
                        continue
                    if kind == "R":
                        try:
                            t = int(v[0])
                        except ValueError:
                            continue
                        got_r = True
                        while self.paused and not self.stop_ev.is_set():
                            time.sleep(0.05)
                            self.rebase = True
                        if self.rebase or t_base is None or t < t_base:
                            t_base, wall_base, self.rebase = t, time.time(), False
                        d = wall_base + (t - t_base) / 1000 / self.speed - time.time()
                        if d > 0.001:
                            time.sleep(d)
                    self.q.put((kind, v))
            if not got_r:                      # 원자료(R)가 없는 파일 → 반복하지 않고 멈춤
                self.bad = True
                return
            self.q.put(("RESTART", None))      # 끝나면 처음부터 반복

    def stop(self):
        self.stop_ev.set()


# ───────────────────────── 그리기 ─────────────────────────
class ScaledDraw:
    """pygame.draw 와 같은 모양으로 부르되, 기준 좌표(1920×1080)에 배율 k 를 곱해 실제 해상도에 바로 그림.
    (화면 전체를 줄이면 맑은 고딕의 가는 가로획(ㅡ)이 사라지므로, 줄이지 않고 처음부터 그 크기로 그림)"""

    def __init__(self, pg):
        self.pg, self.k = pg, 1.0

    def _p(self, pt):
        return (round(pt[0] * self.k), round(pt[1] * self.k))

    def _w(self, w):
        return 0 if w == 0 else max(1, round(w * self.k))

    def rect(self, surf, col, r, width=0, border_radius=0, **kw):
        x, y, w, h = r
        x0, y0 = self._p((x, y))
        x1, y1 = self._p((x + w, y + h))
        kw = {k: (v if v < 0 else round(v * self.k)) for k, v in kw.items()}
        return self.pg.draw.rect(surf, col, (x0, y0, max(0, x1 - x0), max(0, y1 - y0)), self._w(width),
                                 round(border_radius * self.k), **kw)

    def line(self, surf, col, a, b, width=1):
        return self.pg.draw.line(surf, col, self._p(a), self._p(b), self._w(width))

    def lines(self, surf, col, closed, pts, width=1):
        return self.pg.draw.lines(surf, col, closed, [self._p(q) for q in pts], self._w(width))

    def polygon(self, surf, col, pts, width=0):
        return self.pg.draw.polygon(surf, col, [self._p(q) for q in pts], self._w(width))

    def circle(self, surf, col, c, r, width=0):
        return self.pg.draw.circle(surf, col, self._p(c), max(1, round(r * self.k)), self._w(width))


class UI:
    def __init__(self, pg):
        self.pg = pg
        self.D = ScaledDraw(pg)
        self.k = None
        self.set_scale(1.0)
        self.screen = 0
        self.enter_wall = time.time()
        self.lever_sel = 0
        self.lever_idx = [0] * len(LEVERS)

    def set_scale(self, k):
        """출력 배율 k (창 크기 ÷ 1920). 바뀔 때만 캔버스·배경·글자 캐시를 다시 만듦"""
        if self.k is not None and abs(k - self.k) < 1e-6:
            return
        pg = self.pg
        self.k = self.D.k = k
        w, h = max(1, round(W * k)), max(1, round(H * k))
        self.S = pg.Surface((w, h))
        g = pg.Surface((w, h))
        for y in range(h):
            pg.draw.line(g, mix(BG0, BG1, y / h), (0, y), (w, y))
        self.bg = g
        self.glows = [self._glow(c, max(4, round(95 * k))) for c in ROWC]
        self._fonts, self._txt = {}, {}

    def _glow(self, col, r):
        s = self.pg.Surface((r * 2, r * 2), self.pg.SRCALPHA)
        for k in range(r, 0, -2):
            a = int(150 * (1 - k / r) ** 1.6)
            self.pg.draw.circle(s, col + (a,), (r, r), k)
        return s

    def font(self, size, bold=False):
        """실제 픽셀 크기의 폰트 (size 는 기준 1920 해상도 기준, 최소 MIN_FONT)"""
        px = max(8, round(max(size, MIN_FONT) * self.k))
        key = (px, bold)
        if key not in self._fonts:
            self._fonts[key] = self.pg.font.Font(FONT_B if bold else FONT_R, px)
        return self._fonts[key]

    def measure(self, s, size, bold=False):
        """글자 폭(기준 좌표 단위)"""
        return self.font(size, bold).size(s)[0] / self.k

    def text(self, s, size, col, pos, anchor="la", bold=False, alpha=255):
        key = (s, size, col, bold)
        img = self._txt.get(key)
        if img is None:
            if len(self._txt) > 3000:
                self._txt.clear()
            img = self._txt[key] = self.font(size, bold).render(s, True, col)
        r = img.get_rect()
        setattr(r, {"l": "left", "m": "centerx", "r": "right"}[anchor[0]], round(pos[0] * self.k))
        setattr(r, {"a": "top", "m": "centery", "b": "bottom"}[anchor[1]], round(pos[1] * self.k))
        if alpha < 255:
            img = img.copy()
            img.set_alpha(max(0, int(alpha)))
        self.S.blit(img, r)
        k = self.k                                  # 돌려주는 사각형은 기준 좌표 단위
        return self.pg.Rect(round(r.x / k), round(r.y / k), round(r.w / k), round(r.h / k))

    def panel(self, x0, y0, x1, y1, title=None, sub=None):
        pg = self.pg
        self.D.rect(self.S, PANEL, (x0, y0, x1 - x0, y1 - y0), border_radius=18)
        self.D.rect(self.S, BORDER, (x0, y0, x1 - x0, y1 - y0), 2, border_radius=18)
        if title:
            r = self.text(title, 28, TXT, (x0 + 22, y0 + 14), bold=True)
            if sub:
                self.text(sub, 19, DIM, (r.right + 14, r.centery + 2), "lm")

    def dashed(self, x0, x1, y, col, dash=8):
        x = x0
        while x < x1:
            self.D.line(self.S, col, (x, y), (min(x + dash, x1), y), 1)
            x += dash * 2

    # ── 공통 머리말
    def header(self, st, src, now, title, sub):
        self.text(title, 44, TXT, (40, 22), bold=True)
        self.text(sub, 21, DIM, (42, 82))
        col = (CYAN if not src.live else GRN) if src.ok else RED
        label = ("● " if src.live else "▶ ") + src.status
        img_w = self.measure(label, 22, True)
        x1, x0 = 1890, 1890 - img_w - 40
        self.D.rect(self.S, (30, 38, 58), (x0, 26, x1 - x0, 46), border_radius=12)
        self.text(label, 22, col, ((x0 + x1) / 2, 49), "mm", bold=True)
        el = st.elapsed_s(now)
        info = f"측정 시간 {int(el // 60):02d}:{int(el % 60):02d}"
        if st.dropped:
            info += f" · 놓친 샘플 {st.dropped}"
        if src.live and src.folder:
            info += f" · 저장: {os.path.basename(src.folder)}"
        if st.clipped:
            info += " · ※ 54 V 넘어 잘린 값 있음"
        self.text(info, 19, DIM, (1890, 92), "ra")

    def footer(self, src):
        keys = "Tab 화면 전환 · F11 전체화면 · F12 화면 저장 · R 기록 초기화 · Esc 종료"
        keys += " · Z 기준선 다시" if src.live else " · Space 일시정지 · 1/2/4/8 속도"
        if self.screen == 3:
            keys = "↑↓ 항목 · ←→ 값 바꾸기 · " + keys
        self.text(keys, 18, DIM, (1890, 1068), "rb")
        names = ["A 실시간 측정", "B 설계 vs 측정", "C 확장하면?", "D 개선하면?"]
        x = 30
        for i, n in enumerate(names):
            on = i == self.screen
            w = self.measure(n, 18, True) + 24
            self.D.rect(self.S, (40, 52, 80) if on else (22, 28, 44), (x, 1042, w, 30), border_radius=8)
            self.text(n, 18, TXT if on else DIM, (x + w / 2, 1057), "mm", bold=on)
            x += w + 8

    # ═════ 화면 A: 실시간 측정 ═════
    def draw_live(self, st, src, now):
        S, pg = self.S, self.pg
        S.blit(self.bg, (0, 0))
        self.header(st, src, now, "압전 발판 실시간 발전 측정",
                    "Piezoelectric Floor Tile · 아두이노 실측 데이터 (2 ms마다 4행 전압)")
        self.tile(st, now)
        self.waves(st, now)
        self.cards(st, now)
        self.pass_bars(st)
        self.cum_graph(st, now)
        if not st.got_data:
            msg = src.status if src.live or getattr(src, "bad", False) else "재생 파일을 읽는 중..."
            self.D.rect(S, (30, 22, 30), (460, 420, 1000, 150), border_radius=18)
            self.D.rect(S, RED if src.live and not src.ok else BORDER, (460, 420, 1000, 150), 2, border_radius=18)
            self.text("데이터를 기다리는 중", 36, TXT, (960, 465), "mm", bold=True)
            self.text(msg, 24, DIM, (960, 520), "mm")
        self.footer(src)

    def tile(self, st, now):
        """영상(piezo_sim)과 같은 단면도: 옆에서 보면 각 행의 디스크가 1개씩 보임(한 행에 5개), 발이 실제 전압에 맞춰 누름"""
        S, pg = self.S, self.pg
        self.panel(30, 130, 640, 805, "① 발판 단면", "옆에서 본 모습 · 1~4행 (한 행에 디스크 5개)")
        press = min(1.0, max(st.env) / GLOW_FULL_V)
        ground, base_top = 470, 540
        disk_y = base_top - 30
        pdisp = 9 * (1 - st.foot_lift / FOOT_UP) * (0.5 + 0.5 * press)
        plate_bot = disk_y - 30 + pdisp
        plate_top = plate_bot - 20
        tx0, tx1 = 66, 604
        # 바닥
        self.D.rect(S, (70, 74, 84), (46, ground, tx0 - 46, 90))
        self.D.rect(S, (70, 74, 84), (tx1, ground, 624 - tx1, 90))
        self.D.rect(S, (26, 27, 34), (tx0, ground, tx1 - tx0, base_top + 20 - ground))
        self.D.rect(S, (48, 44, 40), (46, base_top + 20, 578, 26))
        self.D.line(S, (120, 124, 134), (46, ground), (tx0, ground), 3)
        self.D.line(S, (120, 124, 134), (tx1, ground), (624, ground), 3)
        self.D.rect(S, (92, 98, 112), (tx0, base_top, tx1 - tx0, 18), border_radius=3)
        for sx in (tx0 + 12, tx1 - 12):          # 스프링
            pts = [(sx + (9 if k % 2 else -9) * (0 < k < 8), plate_bot + (base_top - plate_bot) * k / 8)
                   for k in range(9)]
            self.D.lines(S, (170, 175, 190), False, pts, 3)
        for i, cx in enumerate(DISK_X):
            g = min(1.0, st.env[i] / GLOW_FULL_V)
            sag = 2 + 9 * g
            for sx in (-50, 46):
                self.D.rect(S, (130, 136, 150), (cx + sx, disk_y + 2, 5, base_top - disk_y - 2))
            if g > 0.03:
                gl = self.glows[i]
                gl.set_alpha(int(255 * min(1, g * 1.3)))
                S.blit(gl, gl.get_rect(center=(round(cx * self.k), round((disk_y + sag - 4) * self.k))))
            brass = [(cx + x, disk_y + sag * (1 - (x / 50) ** 2)) for x in range(-50, 51, 5)]
            self.D.lines(S, (205, 165, 80), False, brass, 5)
            cer = [(cx + x, disk_y - 5 + sag * (1 - (x / 50) ** 2)) for x in range(-32, 33, 4)]
            self.D.lines(S, mix((228, 228, 238), ROWC[i], g * 1.5), False, cer, 6)
            self.D.rect(S, (150, 156, 170), (cx - 5, plate_bot, 10, max(1, disk_y + sag - 8 - plate_bot)))
            if g > 0.15:
                a = 255 * min(1, g * 1.5)
                self.text("+", 22, (255, 120, 90), (cx - 20, disk_y + sag - 22), "mm", True, a)
                self.text("+", 22, (255, 120, 90), (cx + 20, disk_y + sag - 22), "mm", True, a)
                self.text("-", 22, (110, 190, 255), (cx, disk_y + sag + 16), "mm", True, a)
        self.D.rect(S, (62, 68, 82), (tx0 + 4, plate_top, tx1 - tx0 - 8, plate_bot - plate_top), border_radius=4)
        self.D.rect(S, (158, 166, 182), (tx0 + 4, plate_top, tx1 - tx0 - 8, 5), border_radius=3)
        # 발
        b = plate_top - st.foot_lift
        d = st.cur["dir"] if st.cur and st.cur["dir"] else st.last_dir
        # 발은 발판과 거의 같은 크기 → 가운데에 두고, 전압이 나온 행 쪽으로 기울여 그쪽이 먼저 닿게 함
        tilt = max(-1.0, min(1.0, (st.foot_x - FOOT_CX) / (DISK_X[-1] - FOOT_CX)))
        S.set_clip(pg.Rect(round(32 * self.k), round(186 * self.k), round(606 * self.k), round(600 * self.k)))
        self.shoe(FOOT_CX, b, -1 if d == -1 else 1, math.radians(7) * tilt)
        S.set_clip(None)
        if st.foot_lift < 30 and press > 0.1:          # 힘 화살표
            ay = b - 150
            self.D.line(S, ORG, (590, ay - 40), (590, ay + 30), 6)
            self.D.polygon(S, ORG, [(578, ay + 28), (602, ay + 28), (590, ay + 48)])
        for e in st.events:                             # 에너지 팝업
            age = max(0.0, (now - e["t"]) / 1000)
            a = 1 - ease(age / 2.0)
            if a > 0:
                self.text(f"+{e['E']:.2f} µJ", 30, YEL, (DISK_X[e["row"]], ground - 150 - 60 * ease(age / 1.2)),
                          "mm", True, 255 * a)
        # 행별 전압 막대 (디스크 바로 아래)
        for i, cx in enumerate(DISK_X):
            self.text(f"{i+1}행", 22, ROWC[i], (cx, 600), "mm", bold=True)
            self.text(f"{st.env[i]:.2f} V", 22, ROWC[i] if st.env[i] > st.th_on else DIM, (cx, 630), "mm", bold=True)
            bx0, bw, by = cx - 55, 110, 652
            self.D.rect(S, INK, (bx0, by, bw, 16), border_radius=5)
            fw = int(bw * min(1, st.env[i] / BAR_FULL_V))
            if fw > 2:
                self.D.rect(S, ROWC[i], (bx0, by, fw, 16), border_radius=5)
            hx = bx0 + int(bw * min(1, st.hold[i] / BAR_FULL_V))
            self.D.line(S, TXT, (hx, by - 3), (hx, by + 18), 2)
            thx = bx0 + int(bw * st.th_on / BAR_FULL_V)
            self.D.line(S, DIM, (thx, by + 18), (thx, by + 24), 2)
        self.text(f"막대 0~{BAR_FULL_V:g} V · 흰 선 = 최근 최대 · 아래 눈금 = 문턱 {st.th_on:g} V",
                  16, DIM, (335, 684), "ma")
        dtxt = {1: "걷는 방향  1행 → 4행  →", -1: "걷는 방향  4행 → 1행  ←", 0: "걷는 방향  —"}[d]
        self.text(dtxt, 24, TXT if d else DIM, (335, 724), "ma", bold=bool(d))
        self.text("방향 = 처음 문턱을 넘은 행 순서 · 발은 전압이 나온 행 쪽으로 기울어짐",
                  16, DIM, (335, 762), "ma")
        if st.calibrating:
            self.D.rect(S, (60, 40, 20), (60, 250, 550, 110), border_radius=14)
            self.D.rect(S, ORG, (60, 250, 550, 110), 2, border_radius=14)
            self.text("잡음 기준선 측정 중", 30, ORG, (335, 285), "mm", bold=True)
            self.text("2초 동안 발판을 밟지 마세요", 24, TXT, (335, 328), "mm")

    def shoe(self, cx, b, flip, ang=0.0):
        """piezo_sim.py 의 발 모양 (flip=-1 이면 왼쪽을 향함, ang>0 이면 오른쪽이 내려감).
        가장 낮은 밑창 점이 b 에 닿도록 맞춤"""
        pg, sc = self.pg, FOOT_SCALE
        ca, sa = math.cos(ang), math.sin(ang)

        def P(pts):
            out = []
            for x, y in pts:
                dx, dy = (x - 549) * sc * flip, (y - b) * sc
                out.append((cx + dx * ca - dy * sa, b + dx * sa + dy * ca))
            return out
        top = b - 700
        polys = [((42, 62, 112), P([(398, b - 74), (548, b - 70), (560, top), (390, top)])),
                 ((210, 210, 220), P([(398, b - 92), (548, b - 92), (548, b - 70), (398, b - 70)])),
                 ((118, 66, 34), P([(372, b), (712, b), (726, b - 18), (712, b - 42), (630, b - 60),
                                    (530, b - 74), (400, b - 80), (370, b - 52)])),
                 ((40, 30, 26), P([(368, b - 12), (724, b - 12), (724, b), (368, b)]))]
        lace = P([(560, b - 66), (640, b - 54)])
        shift = b - max(y for _, y in polys[3][1])
        for col, pts in polys:
            self.D.polygon(self.S, col, [(x, y + shift) for x, y in pts])
        self.D.line(self.S, (160, 100, 60), (lace[0][0], lace[0][1] + shift), (lace[1][0], lace[1][1] + shift), 3)

    def waves(self, st, now):
        import numpy as np
        S, pg = self.S, self.pg
        self.panel(660, 130, 1440, 805, "② 행별 전압 파형", f"최근 {WIN_MS//1000}초 · 점선 = 펄스 문턱 {st.th_on:g} V")
        px0, px1 = 760, 1420
        lanes = [(200 + i * 144, 200 + i * 144 + 118) for i in range(4)]
        pw = px1 - px0
        data = np.array(st.raw, dtype=float) if st.raw else np.zeros((0, 5))
        t0 = now - WIN_MS
        if len(data):
            data = data[data[:, 0] >= t0 - 4]
        vmax = float(data[:, 1:].max()) if len(data) else 0.0
        scale = next((s for s in (2, 5, 10, 20, 30, 60) if vmax * 1.1 <= s), 60)
        cols = None
        if len(data):
            cols = np.clip(((data[:, 0] - t0) / WIN_MS * pw).astype(int), 0, pw - 1)
        for i, (y0, y1) in enumerate(lanes):
            self.D.rect(S, INK, (px0, y0, pw, y1 - y0))
            self.text(f"{i+1}행", 24, ROWC[i], (690, (y0 + y1) / 2 - 12), "lm", bold=True)
            self.text("[V]", 17, DIM, (692, (y0 + y1) / 2 + 16), "lm")
            for tv in (0, scale):
                y = y1 - tv / scale * (y1 - y0)
                self.D.line(S, (40, 48, 68), (px0, y), (px1, y), 1)
                self.text(f"{tv:g}", 16, DIM, (px0 - 8, y), "rm")
            yth = y1 - st.th_on / scale * (y1 - y0)
            self.dashed(px0, px1, yth, (120, 110, 80))
            if cols is not None and len(cols) > 1:
                col_max = np.full(pw, -1.0)
                np.maximum.at(col_max, cols, data[:, i + 1])
                xs = np.nonzero(col_max >= 0)[0]
                if len(xs) > 1:
                    ys = y1 - np.clip(col_max[xs], 0, scale) / scale * (y1 - y0 - 2) - 1
                    pts = list(zip((xs + px0).tolist(), ys.tolist()))
                    self.D.lines(S, ROWC[i], False, pts, 2)
        yb = lanes[-1][1] + 6
        for k in range(0, WIN_MS // 1000 + 1):
            x = px0 + pw * k / (WIN_MS / 1000)
            lab = "지금" if k == WIN_MS // 1000 else f"-{WIN_MS//1000 - k}s"
            self.text(lab, 16, DIM, (x, yb), "ma")

    def card(self, x0, y0, x1, y1, label, value, unit, col, sub=None):
        pg = self.pg
        self.D.rect(self.S, INK, (x0, y0, x1 - x0, y1 - y0), border_radius=14)
        self.D.rect(self.S, (60, 70, 96), (x0, y0, x1 - x0, y1 - y0), 2, border_radius=14)
        self.text(label, 21, DIM, (x0 + 20, y0 + 12))
        r = self.text(value, 50, col, (x0 + 20, y1 - 12), "lb", bold=True)
        if unit:
            self.text(unit, 24, col, (r.right + 8, r.bottom - 10), "lb")
        if sub:
            self.text(sub, 18, DIM, (x1 - 18, y0 + 14), "ra")

    def cards(self, st, now):
        self.panel(1460, 130, 1890, 805, "③ 지금까지")
        x0, x1 = 1478, 1872
        ys = [182 + k * 118 for k in range(5)]
        h = 106
        n = st.people()
        self.card(x0, ys[0], x1, ys[0] + h, "통과 인원", f"{n}", "명", TXT, f"펄스 {st.pulses}개")
        last = st.cur or (st.passes[-1] if st.passes else None)
        lv, lu = fmt_E(last["E"] * 1e-6) if last else ("—", "")
        self.card(x0, ys[1], x1, ys[1] + h, "방금 통과한 1명 에너지", lv, lu, YEL,
                  "진행 중" if st.cur else None)
        es, ne, meas = st.e_step()
        mv, mu = fmt_E(es * 1e-6)
        self.card(x0, ys[2], x1, ys[2] + h, "1명당 평균 에너지", mv if meas else "—", mu if meas else "",
                  ORG, f"{ne}명 평균" if meas else None)
        tv, tu = fmt_E(st.total_E * 1e-6)
        self.card(x0, ys[3], x1, ys[3] + h, "누적 에너지", tv, tu, GRN)
        el = st.elapsed_s(now)
        p = st.total_E / el if el > 1 else 0.0
        self.card(x0, ys[4], x1, ys[4] + h, "평균 전력", f"{p:.3f}", "µW", CYAN, f"최대 전압 {st.peak_V:.2f} V")
        self.text("값 = 1.1 MΩ 측정 저항에 전달된 에너지", 17, DIM, (1675, 790), "mb")

    def pass_bars(self, st):
        S, pg = self.S, self.pg
        self.panel(30, 822, 1250, 1032, "④ 사람(통과)별 에너지", "최근 40명 · 주황 = 지금 지나가는 중")
        items = st.passes[-40 + (1 if st.cur else 0):] + ([st.cur] if st.cur else [])
        items = items[-40:]
        px0, px1, py0, py1 = 70, 1230, 880, 1010
        self.D.rect(S, INK, (px0, py0, px1 - px0, py1 - py0))
        if not items:
            self.text("아직 지나간 사람이 없어요 — 발판을 밟아 보세요", 22, DIM, ((px0 + px1) / 2, (py0 + py1) / 2), "mm")
            return
        top = max(p["E"] for p in items) or 1
        bw = (px1 - px0) / 40
        first_no = st.people() - len(items) + 1
        for k, p in enumerate(items):
            hh = (py1 - py0 - 26) * p["E"] / top
            x = px0 + k * bw + 3
            col = ORG if p is st.cur else YEL
            self.D.rect(S, col, (x, py1 - hh, bw - 6, hh), border_top_left_radius=4, border_top_right_radius=4)
            if p["E"] == top:
                self.text(f"{p['E']:.1f} µJ", 16, TXT, (x + bw / 2 - 3, py1 - hh - 2), "mb")
        self.text(f"{first_no}번째", 15, DIM, (px0 + 2, py1 + 2), "la")
        if len(items) >= 4:
            self.text(f"{st.people()}번째", 15, DIM, (px0 + len(items) * bw - 3, py1 + 2), "ra")

    def cum_graph(self, st, now):
        S, pg = self.S, self.pg
        tv, tu = fmt_E(st.total_E * 1e-6)
        self.panel(1270, 822, 1890, 1032, "⑤ 누적 에너지", f"지금 {tv} {tu}")
        px0, px1, py0, py1 = 1300, 1870, 880, 1010
        self.D.rect(S, INK, (px0, py0, px1 - px0, py1 - py0))
        if st.t_stat0 is None or not st.cumE or now <= st.t_stat0:
            return
        span = max(1.0, now - st.t_stat0)
        top = st.total_E or 1
        pts = [(px0, py1)]
        for t, e in st.cumE:
            x = px0 + (px1 - px0) * min(1, max(0, (t - st.t_stat0) / span))
            pts.append((x, pts[-1][1]))
            pts.append((x, py1 - (py1 - py0 - 8) * e / top))
        pts.append((px1, pts[-1][1]))
        self.D.lines(S, GRN, False, pts, 3)
        self.text("시작", 15, DIM, (px0, py1 + 2), "la")
        self.text("지금", 15, DIM, (px1, py1 + 2), "ra")

    # ═════ 화면 B: 설계(이론) vs 측정 ═════
    def draw_theory(self, st, src, now):
        S, pg = self.S, self.pg
        S.blit(self.bg, (0, 0))
        cp_tot = TH_N_DISK * TH_CP_DISK
        q_th = TH_D_EFF * TH_FORCE * 1e6                 # µC
        v_th = q_th * 1e-6 / cp_tot                      # V (개방회로)
        e_th = (q_th * 1e-6) ** 2 / (2 * cp_tot) * 1e6   # µJ (1번 누름, 개방회로 최대)
        cp_row = cp_tot / TH_ROWS
        rc_ms = st.rload * cp_row * 1000
        self.header(st, src, now, "설계(이론)와 비교하면? — 차이는 어디서 날까",
                    f"설계값: 디스크 {TH_N_DISK}개(4행 × 5열) · Cp {TH_CP_DISK*1e9:g} nF × {TH_N_DISK} · "
                    f"하중 {TH_FORCE:g} N · d_eff {TH_D_EFF*1e9:g} nC/N(가정) · 하중이 디스크에 고르게 나뉜다고 가정")
        P = st.plist
        n = len(P)
        es, ne, meas = st.e_step()
        qm = q2 = vm = em = 0.0
        trm = None
        if n:
            qm = sum(p["Q"] for p in P) / n
            q2 = sum(p["Q"] ** 2 for p in P) / n
            vm = sum(p["peak"] for p in P) / n
            em = sum(p["E"] for p in P) / n
            trs = [p["tr"] for p in P if p["tr"] is not None]
            trm = sum(trs) / len(trs) if trs else None
        # ── 왼쪽: 비교표
        self.panel(30, 130, 940, 1032, "1번 누를 때(펄스 1개) 비교",
                   f"측정 = 펄스 {n}개 평균" if n else "아직 측정된 펄스가 없어요")
        hy = 190
        for txt, x, an in (("항목", 52, "la"), ("설계", 470, "ra"), ("측정", 655, "ra"), ("측정 ÷ 설계", 800, "ma")):
            self.text(txt, 20, DIM, (x, hy), an)
        self.D.line(S, BORDER, (52, hy + 30), (918, hy + 30), 1)
        rows = [
            ("발생 전하 Q", "Q = d·F", f"{q_th:.2f} µC", f"{qm:.3f} µC" if n else "—", qm / q_th if n else None),
            ("최대 전압", "설계 = 760 N 전부가 디스크에 실릴 때 Q/C", f"{v_th:.1f} V", f"{vm:.2f} V" if n else "—",
             vm / v_th if n else None),
            ("에너지", "설계 = Q²/2C (최대치)", f"{e_th:.0f} µJ", f"{em:.3f} µJ" if n else "—",
             em / e_th if n else None),
            ("누르는 시간", "하중(전압)이 최고가 될 때까지", f"{TH_RISE_MS} ms", f"{trm:.0f} ms" if trm else "—", None),
            ("1걸음(통과) 에너지", "설계 = 누를 때 + 뗄 때 2번 × Q²/2C", f"{2 * e_th:.0f} µJ",
             f"{es:.2f} µJ" if meas else "—", es / (2 * e_th) if meas else None),
        ]
        for j, (lab, note, dv, mv, r) in enumerate(rows):
            y = hy + 44 + j * 78
            self.text(lab, 24, TXT, (52, y), bold=True)
            self.text(note, 16, DIM, (52, y + 34))
            self.text(dv, 24, CYAN, (470, y + 4), "ra", bold=True)
            self.text(mv, 24, YEL, (655, y + 4), "ra", bold=True)
            bx0, bw = 690, 220
            self.D.rect(S, INK, (bx0, y + 8, bw, 22), border_radius=6)
            if r is not None and r > 0:
                f = max(0.0, min(1.0, r))                              # 선형 0 ~ 100 %
                self.D.rect(S, ORG, (bx0, y + 8, max(3, bw * f), 22), border_radius=6)
                frac = f"  (약 1/{1/r:.0f})" if r < 0.5 else ""
                self.text(f"{r*100:.2g} %{frac}", 18, TXT, (bx0 + bw / 2, y + 36), "ma", bold=True)
            elif j == 3:
                self.text("참고", 18, DIM, (bx0 + bw / 2, y + 19), "mm")
        self.text("막대 = 0 ~ 100 % (꽉 차면 설계와 같음)", 15, DIM, (918, hy + 44 + 5 * 78 - 8), "ra")
        # 산점도: 펄스별 전하-에너지
        y0 = 650
        self.text("펄스마다 전하 Q와 에너지 E (로그 눈금) · 파란 선 = 이론 E = Q²/2C", 20, DIM, (52, y0))
        px0, px1, py0, py1 = 140, 910, y0 + 40, 985
        self.D.rect(S, INK, (px0, py0, px1 - px0, py1 - py0))
        qlo, qhi, elo, ehi = 0.01, 30.0, 1e-4, 1e3

        def X(q):
            return px0 + (px1 - px0) * (math.log10(max(qlo, min(qhi, q))) - math.log10(qlo)) / math.log10(qhi / qlo)

        def Y(e):
            return py1 - (py1 - py0) * (math.log10(max(elo, min(ehi, e))) - math.log10(elo)) / math.log10(ehi / elo)
        for k in range(-2, 2):
            x = X(10 ** k)
            self.D.line(S, (40, 48, 68), (x, py0), (x, py1), 1)
            self.text(f"{10**k:g}", 15, DIM, (x, py1 + 3), "ma")
        for k in range(-4, 4):
            y = Y(10 ** k)
            self.D.line(S, (40, 48, 68), (px0, y), (px1, y), 1)
            self.text(f"{10**k:g}", 15, DIM, (px0 - 6, y), "rm")
        self.text("Q [µC]", 15, DIM, (px1, py1 + 22), "ra")
        self.text("E [µJ]", 15, DIM, (px0 + 10, py0 + 36), "la")
        line = [(X(q), Y((q * 1e-6) ** 2 / (2 * cp_tot) * 1e6))
                for q in [qlo * (qhi / qlo) ** (k / 40) for k in range(41)]]
        self.D.lines(S, CYAN, False, line, 2)
        for p in P[-400:]:
            if p["Q"] > 0 and p["E"] > 0:
                self.D.circle(S, ORG, (int(X(p["Q"])), int(Y(p["E"]))), 4)
        sx, sy = X(q_th), Y(e_th)
        self.D.circle(S, CYAN, (int(sx), int(sy)), 9)
        self.D.circle(S, TXT, (int(sx), int(sy)), 9, 2)
        self.text("설계", 18, CYAN, (sx - 16, sy), "rm", bold=True)
        self.text("● 측정 펄스", 18, ORG, (px0 + 10, py0 + 8), bold=True)

        # ── 오른쪽: 차이 분석
        self.panel(960, 130, 1890, 1032, "차이 분석 — 에너지가 어디서 줄었나?")
        if not n:
            self.text("발판을 밟으면 분석이 시작됩니다", 26, DIM, (1425, 560), "mm")
            self.footer(src)
            return
        rq = math.sqrt(q2) / q_th
        e_q = e_th * rq ** 2
        eta = em / e_q if e_q > 0 else 0
        bx0, bx1 = 1000, 1700

        def BX(e):                                   # 선형: ① 설계 최대 = 꽉 찬 막대
            return bx0 + (bx1 - bx0) * max(0.0, min(1.0, e / e_th))
        steps = [("① 설계 최대 (개방회로, 1번 누름)", e_th, CYAN, f"전하 {q_th:.2f} µC 가 모두 생겼다면"),
                 ("② 전하만 실제 측정값으로 바꾸면", e_q, ORG,
                  f"전하가 설계의 {rq*100:.2g} % → 에너지는 제곱이라 {rq**2*100:.2g} %"),
                 ("③ 실제 측정 에너지", em, YEL, f"회로·부하로 전달된 비율 ×{eta:.2g}")]
        for j, (lab, val, col, why) in enumerate(steps):
            y = 186 + j * 98
            self.text(lab, 22, col, (bx0, y), bold=True)
            self.text(why, 17, DIM, (1860, y + 4), "ra")
            x = BX(val)
            self.D.rect(S, col, (bx0, y + 36, max(3, x - bx0), 26), border_radius=4)
            v, u = fmt_E(val * 1e-6)
            self.text(f"{v} {u}", 20, TXT, (x + 10, y + 49), "lm", bold=True)
        self.text("실제 길이 비율 (① = 꽉 찬 막대)", 15, DIM, (1860, 186 + 3 * 98 - 12), "ra")
        cy = 500
        self.text("② 전하가 적은 이유 — 힘·소재 쪽", 22, ORG, (1000, cy), bold=True)
        for k, t in enumerate(["· 디스크 하나에 걸린 힘이 760 N ÷ 20보다 작을 수 있음 — 판·받침이 힘을 나눠 받음",
                               "· d_eff 11 nC/N 은 가정값 — 고정 방식에 따라 실제는 더 작을 수 있음",
                               "· 디스크가 충분히 휘지 않음 (받침 간격·상판 강성)"]):
            self.text(t, 19, TXT, (1010, cy + 36 + k * 30))
        cy = 650
        self.text("③ 회로·부하 쪽 — 측정 저항", 22, YEL, (1000, cy), bold=True)
        tr_s = f"{trm:.0f} ms" if trm else "—"
        for k, t in enumerate([f"· 부하 RC = {st.rload/1e6:.1f} MΩ × 행당 {cp_row*1e9:.0f} nF = {rc_ms:.0f} ms"
                               f"  vs  누르는 시간 {tr_s}",
                               f"· 누르는 동안 전하가 저항으로 빠져 전압이 설계 {v_th:.0f} V까지 못 오름",
                               "· 저항에 흐른 전하만 세므로 실제 발생 전하보다 조금 작게 잡힘"]):
            self.text(t, 19, TXT, (1010, cy + 36 + k * 30))
        loss_q = -math.log10(max(1e-12, rq ** 2))
        loss_c = -math.log10(min(1.0, max(1e-12, eta)))
        self.D.rect(S, (26, 34, 54), (982, 820, 886, 196), border_radius=14)
        if loss_q >= loss_c:
            c1 = "결론: 에너지가 줄어든 대부분은 '전하 부족(힘 전달·소재)' 때문"
            c2 = "→ 화면 D의 '디스크로 가는 힘'·'압전 소재'를 고치는 것이 가장 효과적"
        else:
            c1 = "결론: '회로·부하 손실'이 전하 부족보다 큼"
            c2 = "→ 화면 D의 '수확 회로' 개선이 우선"
        self.text(c1, 24, TXT, (1004, 838), bold=True)
        self.text(c2, 20, YEL, (1004, 878))
        self.text(f"전하 ×{rq:.2g} → 에너지 ×{rq**2:.2g}   ·   회로 ×{eta:.2g}   ⇒   측정 = 설계의 {em/e_th*100:.2g} %",
                  20, TXT, (1004, 918))
        note = ("※ 회로 비율이 1보다 크게 나오는 건 저항 부하에서 E = Q²/2C 가 근사식이라서 — 약 1로 보면 됨"
                if eta > 1 else "※ d_eff·하중은 가정값 — 디스크 정전용량(멀티미터)·실제 하중을 재서 넣으면 더 정확해짐")
        self.wrap(note, 16, DIM, 1004, 958, 840, 22)
        self.footer(src)

    # ═════ 화면 C: 확장하면? ═════
    def draw_scale(self, st, src, now):
        S, pg = self.S, self.pg
        S.blit(self.bg, (0, 0))
        es, ne, meas = st.e_step()
        basis = f"실측 {ne}명 평균" if meas else "아직 실측 없음 → 기본값(이전 시험 측정)"
        self.header(st, src, now, "이 발판을 곳곳에 깔면? — 하루 동안 모이는 에너지",
                    f"기준: 1걸음(통과)당 {es:.2f} µJ ({basis})")
        u = ease((time.time() - self.enter_wall) / 1.4)
        e_step_J = es * 1e-6
        el = st.elapsed_s(now)
        cards = [dict(name="지금까지 (실측)", color=GRN, steps=st.people(), tiles=1,
                      lines=[f"{st.people()}명 통과 · 측정 {int(el//60)}분 {int(el%60)}초",
                             "실제로 만든 발판 1장에서 모인 에너지",
                             "(가정 없음)"],
                      E=st.total_E * 1e-6, steps_label="통과 인원", per="지금까지")]
        for sc in SCENARIOS:
            tiles, pp, steps = scenario_numbers(sc)
            cards.append(dict(name=sc["name"], color=COLORS[sc["color"]], steps=steps, tiles=tiles,
                              lines=[sc["who"],
                                     f"{sc['where']} {sc['area_w']:g} m × {sc['area_l']:g} m에 발판 {tiles}장",
                                     f"1명이 발판 위를 약 {pp}걸음 (보폭 {STRIDE_M:g} m) — 가정"],
                              E=steps * e_step_J, steps_label="하루 걸음 수", per="하루"))
        for k, c in enumerate(cards):
            x0 = 30 + k * 630
            x1 = x0 + 600
            a = ease((time.time() - self.enter_wall - k * 0.18) / 0.6)
            yo = int((1 - a) * 40)
            y0 = 130 + yo
            self.D.rect(S, PANEL, (x0, y0, 600, 770), border_radius=18)
            self.D.rect(S, BORDER, (x0, y0, 600, 770), 2, border_radius=18)
            self.D.rect(S, c["color"], (x0, y0 + 18, 8, 44), border_radius=4)
            self.text(c["name"], 32, c["color"], (x0 + 26, y0 + 16), bold=True)
            tl = f"발판 {c['tiles']}장"                      # 설치 장수를 크게
            tw = self.measure(tl, 26, True) + 28
            self.D.rect(S, (30, 40, 64), (x1 - 20 - tw, y0 + 18, tw, 42), border_radius=10)
            self.D.rect(S, c["color"], (x1 - 20 - tw, y0 + 18, tw, 42), 2, border_radius=10)
            self.text(tl, 26, c["color"], (x1 - 20 - tw / 2, y0 + 39), "mm", bold=True)
            for j, ln in enumerate(c["lines"]):
                self.text(ln, 19, DIM, (x0 + 26, y0 + 66 + j * 25))
            self.text(c["steps_label"], 21, DIM, (x0 + 26, y0 + 150))
            self.text(fmt_count(c["steps"] * u) + ("명" if k == 0 else "걸음"), 26, TXT,
                      (x1 - 24, y0 + 148), "ra", bold=True)
            self.text(f"{c['per']} 에너지 (우리 발판)", 21, DIM, (x0 + 26, y0 + 192))
            ev, eu = fmt_E(c["E"] * u)
            r = self.text(ev, 64, YEL, (x0 + 24, y0 + 296), "lb", bold=True)
            self.text(eu, 32, YEL, (r.right + 10, r.bottom - 12), "lb", bold=True)
            yy = y0 + 312
            self.D.line(S, BORDER, (x0 + 20, yy), (x1 - 20, yy), 1)
            self.text("= 이만큼이에요", 19, DIM, (x0 + 26, yy + 8))
            for j, (nm, desc, kind, base) in enumerate(UNITS):
                ry = yy + 40 + j * 58
                self.text(nm, 22, TXT, (x0 + 26, ry))
                if desc:
                    self.text(desc, 16, DIM, (x0 + 26, ry + 28))
                self.text(fmt_unit(c["E"] * u, kind, base), 26, TXT, (x1 - 24, ry + 4), "ra", bold=True)
            yy = y0 + 655
            self.D.line(S, BORDER, (x0 + 20, yy), (x1 - 20, yy), 1)
            Ec = c["steps"] * COMMERCIAL_J_PER_STEP
            cv, cu = fmt_E(Ec * u)
            self.text(f"상용 발전 타일(걸음당 {COMMERCIAL_J_PER_STEP:g} J)이었다면", 19, DIM, (x0 + 26, yy + 10))
            self.text(f"{cv} {cu}", 30, CYAN, (x0 + 26, yy + 40), bold=True)
            self.text("= 스마트폰 " + fmt_unit(Ec * u, "pct", 54000.0), 22, CYAN, (x1 - 24, yy + 50), "ra")
        # 결론 띠
        self.D.rect(S, (26, 34, 54), (30, 918, 1860, 112), border_radius=16)
        ratio = COMMERCIAL_J_PER_STEP / e_step_J if e_step_J > 0 else 0
        self.text(f"우리 발판 1걸음 약 {fmt_E(e_step_J)[0]} {fmt_E(e_step_J)[1]}   vs   상용 타일 1걸음 약 "
                  f"{COMMERCIAL_J_PER_STEP:g} J   →   약 {fmt_count(ratio)}배 차이", 28, TXT, (960, 948), "mm", bold=True)
        self.text("→ 지금 구조로는 큰 전력보다 센서·무선 IoT 같은 초저전력 장치에 맞음 · 원인 분석은 화면 B · 개선은 화면 D",
                  22, YEL, (960, 988), "mm")
        self.text("실측값 = 1.1 MΩ 측정 저항에 전달된 에너지 · 인원·걸음 수·상용 타일 값은 가정 (piezo_gui_v1.py 맨 위에서 수정)",
                  17, DIM, (960, 1017), "mm")
        self.footer(src)

    # ═════ 화면 D: 부족한 점과 개선 ═════
    def lever_factor(self):
        f = 1.0
        for (nm, desc, opts), idx in zip(LEVERS, self.lever_idx):
            f *= opts[idx][1]
        return f

    def draw_improve(self, st, src, now):
        S, pg = self.S, self.pg
        S.blit(self.bg, (0, 0))
        es, ne, meas = st.e_step()
        e0 = es * 1e-6
        self.header(st, src, now, "부족한 점, 그리고 무엇을 고치면 늘어날까?",
                    "압전 에너지  E = Q² / 2C = (d·F)² / 2C   — 힘(F)·소재(d)·개수·회로가 열쇠")
        # 왼쪽: 지금의 한계
        self.panel(30, 130, 760, 1032, "지금 발판의 한계", "있는 그대로")
        for i, (k, d) in enumerate(LIMITS):
            y = 196 + i * 150
            self.D.rect(S, INK, (52, y, 686, 132), border_radius=14)
            self.D.rect(S, RED, (52, y + 16, 6, 100), border_radius=3)
            self.text(f"{i+1}. {k}", 26, TXT, (76, y + 18), bold=True)
            self.wrap(d, 21, DIM, 76, y + 62, 640, 30)
        # 오른쪽: 개선 계산기
        self.panel(780, 130, 1890, 1032, "개선 계산기", "←→ 로 바꿔 보세요 (배수는 가정·예상치)")
        for i, ((nm, desc, opts), idx) in enumerate(zip(LEVERS, self.lever_idx)):
            y = 192 + i * 112
            sel = i == self.lever_sel
            self.D.rect(S, (30, 40, 64) if sel else INK, (802, y, 1066, 100), border_radius=14)
            self.D.rect(S, YEL if sel else (60, 70, 96), (802, y, 1066, 100), 2, border_radius=14)
            self.text(nm, 26, YEL if sel else TXT, (826, y + 14), bold=True)
            self.text(desc, 18, DIM, (826, y + 58))
            bx = 1290
            for j, (lab, fac) in enumerate(opts):
                on = j == idx
                w = 132
                x = bx + j * (w + 10)
                self.D.rect(S, (60, 80, 120) if on else (26, 32, 50), (x, y + 22, w, 56), border_radius=10)
                if on:
                    self.D.rect(S, YEL, (x, y + 22, w, 56), 2, border_radius=10)
                self.text(lab, 22, TXT if on else DIM, (x + w / 2, y + 40), "mm", bold=on)
                self.text(f"×{fac:g}", 15, YEL if on else DIM, (x + w / 2, y + 64), "mm")
        f = self.lever_factor()
        e1 = e0 * f
        # 선형 막대: 상용 타일 = 꽉 찬 막대 (우리 값이 얼마나 작은지 그대로 보이게)
        y0 = 650
        self.text(f"1걸음 에너지 비교 — 실제 길이 비율 (상용 타일 {COMMERCIAL_J_PER_STEP:g} J = 꽉 찬 막대)",
                  21, DIM, (806, y0))
        bx0, bx1 = 1010, 1860

        def xpos(j):
            return bx0 + (bx1 - bx0) * max(0.0, min(1.0, j / COMMERCIAL_J_PER_STEP))
        for q in range(5):
            x = bx0 + (bx1 - bx0) * q / 4
            self.D.line(S, (40, 48, 68), (x, y0 + 38), (x, y0 + 214), 1)
            self.text(f"{COMMERCIAL_J_PER_STEP * q / 4:g} J", 15, DIM, (x, y0 + 218), "ma")
        rows = [("지금 (실측)", e0, ORG), ("개선하면", e1, YEL), ("상용 타일", COMMERCIAL_J_PER_STEP, CYAN)]
        for i, (lab, val, col) in enumerate(rows):
            y = y0 + 44 + i * 58
            self.text(lab, 22, col, (806, y + 20), "lm", bold=True)
            x = xpos(val)
            self.D.rect(S, col, (bx0, y + 4, max(3, x - bx0), 34), border_radius=4)
            v, u_ = fmt_E(val)
            pct = val / COMMERCIAL_J_PER_STEP * 100
            lab2 = f"{v} {u_}" + ("" if pct >= 99.5 else f"  (상용의 {pct:.2g} %)")
            tx = x + 12 if x < bx1 - 330 else x - 12
            self.text(lab2, 22, TXT, (tx, y + 21), "lm" if x < bx1 - 330 else "rm", bold=True)
        # 결과
        sub = SCENARIOS[-1]
        n_tiles, _, steps = scenario_numbers(sub)
        gap = COMMERCIAL_J_PER_STEP / e1 if e1 > 0 else 0
        self.D.rect(S, (26, 34, 54), (802, 900, 1066, 116), border_radius=14)
        ev, eu = fmt_E(e1)
        self.text(f"개선 배수 ×{fmt_count(f)}  →  1걸음 {ev} {eu}", 28, YEL, (826, 914), bold=True)
        dv, du = fmt_E(steps * e1)
        self.text(f"{sub['name']}(발판 {n_tiles}장) 하루: {dv} {du} = IoT 센서 전송 {fmt_unit(steps * e1, 'count', 100e-6)}"
                  f" · 10 W 전구 {fmt_unit(steps * e1, 'time', 10.0)}", 21, TXT, (826, 956))
        self.text(f"상용 타일까지 아직 약 {fmt_count(gap)}배 — 상용 타일은 대부분 압전이 아니라 전자기(코일) 방식"
                  if gap > 1 else "상용 타일 수준에 도달!", 19, DIM, (826, 986))
        self.footer(src)

    def wrap(self, s, size, col, x, y, width, lh):
        line = ""
        for ch in s.split(" "):
            t = (line + " " + ch).strip()
            if self.measure(t, size) > width and line:
                self.text(line, size, col, (x, y))
                y += lh
                line = ch
            else:
                line = t
        if line:
            self.text(line, size, col, (x, y))

    def draw(self, st, src, now):
        [self.draw_live, self.draw_theory, self.draw_scale, self.draw_improve][self.screen](st, src, now)
        return self.S


# ───────────────────────── 실행 ─────────────────────────
def fit_scale(pg):
    ww, wh = pg.display.get_surface().get_size()
    return min(ww / W, wh / H)


def present(pg, canvas):
    """캔버스는 이미 창 크기에 맞게 그려져 있음 → 가운데에 그대로 붙임 (축소하지 않음)"""
    win = pg.display.get_surface()
    ww, wh = win.get_size()
    cw, ch = canvas.get_size()
    if (cw, ch) != (ww, wh):
        win.fill((0, 0, 0))
    win.blit(canvas, ((ww - cw) // 2, (wh - ch) // 2))
    pg.display.flip()


def snapshot(args):
    """검증용: 재생 파일을 --until 초까지 한 번에 읽고 세 화면을 PNG 로 저장"""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame as pg
    pg.init()
    pg.display.set_mode((1, 1))
    st = State()
    ui = UI(pg)

    class Src:
        live, ok, folder = False, True, os.path.dirname(os.path.abspath(args.replay))
        status = "재생 1× · " + os.path.basename(folder)
    until = args.until * 1000
    last_upd = None
    with open(args.replay, encoding="utf-8", errors="ignore") as f:
        for line in f:
            kind, v = logger.parse_line(line)
            if kind is None:
                continue
            st.feed(kind, v)
            if kind == "R" and st.last_t is not None:
                if last_upd is None or st.last_t - last_upd >= 25:   # 40 fps 처럼 갱신
                    st.update(st.last_t)
                    last_upd = st.last_t
                if int(v[0]) >= until:
                    break
    os.makedirs(args.snapshot, exist_ok=True)
    now = st.last_t or 0
    st.update(now)
    ui.enter_wall = time.time() - 10
    for i, name in enumerate(("A_live", "B_theory", "C_scale", "D_improve")):
        ui.screen = i
        if i == 3:
            ui.lever_idx = [1, 2, 1, 2]
        for wpx in (1920, 1280):
            ui.set_scale(wpx / W)
            c = ui.draw(st, Src, now)
            p = os.path.join(args.snapshot, f"{name}_{wpx}.png")
            pg.image.save(c, p)
        print("saved", p)
    print(f"people={st.people()} pulses={st.pulses} total={st.total_E:.3f}uJ e_step={st.e_step()}")


def main():
    ap = argparse.ArgumentParser(description="압전 발판 실시간 GUI")
    ap.add_argument("--port")
    ap.add_argument("--replay")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--snapshot")
    ap.add_argument("--until", type=float, default=30)
    args = ap.parse_args()
    if args.snapshot:
        return snapshot(args)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()   # 윈도우 배율 때문에 흐려지지 않게
        except Exception:
            pass
    import pygame as pg
    pg.init()
    pg.display.set_caption("압전 발판 실시간 발전 측정")
    pg.display.set_mode((1600, 900), pg.RESIZABLE)
    fullscreen = False
    q = queue.Queue()
    src = ReplaySource(q, args.replay, args.speed) if args.replay else SerialSource(q, args.port)
    src.start()
    st, ui = State(), UI(pg)
    st.rate = args.speed if args.replay else 1.0
    clock = pg.time.Clock()
    running = True
    try:
        while running:
            for ev in pg.event.get():
                if ev.type == pg.QUIT:
                    running = False
                elif ev.type == pg.KEYDOWN:
                    k = ev.key
                    if k == pg.K_ESCAPE:
                        if fullscreen:
                            fullscreen = False
                            pg.display.set_mode((1600, 900), pg.RESIZABLE)
                        else:
                            running = False
                    elif k == pg.K_TAB:
                        ui.screen = (ui.screen + (-1 if ev.mod & pg.KMOD_SHIFT else 1)) % 4
                        ui.enter_wall = time.time()
                    elif k == pg.K_F11:
                        fullscreen = not fullscreen
                        pg.display.set_mode((0, 0), pg.FULLSCREEN) if fullscreen else pg.display.set_mode((1600, 900), pg.RESIZABLE)
                    elif k == pg.K_F12:
                        p = os.path.join(HERE, datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png"))
                        pg.image.save(ui.S, p)
                        print("화면 저장:", p)
                    elif k == pg.K_r:
                        st.reset_stats()
                    elif k == pg.K_z and src.live:
                        src.send(b"z")
                        st.calibrating = True
                    elif not src.live and k == pg.K_SPACE:
                        src.paused = st.paused = not src.paused
                    elif not src.live and k in (pg.K_1, pg.K_2, pg.K_4, pg.K_8):
                        sp = {pg.K_1: 1, pg.K_2: 2, pg.K_4: 4, pg.K_8: 8}[k]
                        src.set_speed(sp)
                        st.rate = sp
                    elif ui.screen == 3 and k in (pg.K_UP, pg.K_DOWN):
                        ui.lever_sel = (ui.lever_sel + (1 if k == pg.K_DOWN else -1)) % len(LEVERS)
                    elif ui.screen == 3 and k in (pg.K_LEFT, pg.K_RIGHT):
                        n = len(LEVERS[ui.lever_sel][2])
                        i = ui.lever_idx[ui.lever_sel] + (1 if k == pg.K_RIGHT else -1)
                        ui.lever_idx[ui.lever_sel] = max(0, min(n - 1, i))
            t_end = time.time() + 0.012
            while time.time() < t_end:          # 한 프레임에 너무 오래 붙잡히지 않게
                try:
                    kind, v = q.get_nowait()
                except queue.Empty:
                    break
                st.feed(kind, v)
            now = st.now()
            st.update(now)
            ui.set_scale(fit_scale(pg))
            present(pg, ui.draw(st, src, now))
            clock.tick(40)
    finally:                                # 오류로 끝나도 저장 파일은 꼭 닫기
        src.stop()
        src.join(timeout=2)
        pg.quit()
    if src.live and src.folder and os.path.exists(os.path.join(src.folder, "pulses.csv")):
        print("\n저장 폴더:", src.folder)
        print("analyze.py 로 요약을 만듭니다...\n")
        subprocess.run([sys.executable, os.path.join(MAIN_DIR, "analyze.py"), src.folder])
    elif src.live and src.folder:
        print("\n저장 폴더:", src.folder, "(펄스 0개)")


if __name__ == "__main__":
    main()
