# -*- coding: utf-8 -*-
"""
젯슨 오린 나노 + AI Starter Kit 하드웨어 모듈 (piezo_jetson_v1.py 가 사용)

  ① CameraCounter     카메라로 사람 수 세기 (영상은 저장하지 않음 — 모자이크 미리보기만 화면에)
  ② UltrasonicCounter 초음파 센서로 사람 수 세기
  ③ Outputs           LCD(16×2) · 4자리 숫자 표시기 · LED (+ 부저·RGB 매트릭스 자리)
  ④ EnvSensor         온습도 센서 기록

모듈 하나가 없거나 실패해도 나머지는 계속 동작합니다(화면에 "없음"으로 표시).
핀·주소는 아래 CONFIG 에서 바꿉니다. 키트 판에 적힌 "D26" 같은 번호는 BCM 번호로 가정했습니다.
"""
import math, random, threading, time

CONFIG = dict(
    # ── ① 카메라
    camera=True,
    camera_source="auto",        # "auto" = CSI(리본 케이블) 먼저, 안 되면 USB 0번 / "csi" / 0, 1 (USB 번호)
    camera_size=(1280, 720),
    detector="auto",             # "auto" = YOLO(설치돼 있으면, GPU) → 없으면 HOG(OpenCV 기본, CPU)
    yolo_model="yolov8n.pt",
    line_axis="y",               # 세는 선: "y" = 가로선(사람이 위↔아래로 지나감), "x" = 세로선(좌↔우)
    line_pos=0.5,                # 선 위치 (화면 비율 0~1)
    privacy_pixel=24,            # 미리보기 모자이크 칸 수(가로). 작을수록 더 흐림. 영상 파일은 어떤 경우에도 저장 안 함
    # ── ② 초음파 (키트 표기 TRIG-D26, ECHO-D16 → BCM 26, 16 으로 가정)
    ultrasonic=True,
    us_trig=26, us_echo=16,
    us_drop_cm=30,               # 평소 거리보다 이만큼 가까워지면 "사람 있음"
    us_min_gap_s=0.7,            # 한 사람을 두 번 세지 않도록 최소 간격
    # ── ③ 출력 (I2C 주소는 키트 판 표기)
    i2c=True,
    i2c_buses=(7, 1, 8, 0),      # 앞에서부터 찾아봄 (오린 나노 40핀: 3·5번 핀 = 7번 버스)
    lcd_addr=0x27,               # LCD (PCF8574)
    seg_addr=0x70,               # 4자리 숫자 표시기 (HT16K33 으로 가정)
    led_pin=18,                  # LED (키트 표기 D18 → BCM 18 로 가정)
    # ── ④ 온습도 (I2C 0x38, AHT20/AHT10)
    env_addr=0x38,
)


# ═════════════════════ ① 카메라 사람 수 ═════════════════════
class LineCounter:
    """가운데 선을 넘어간 사람 수 (간단한 중심점 추적). 좌표는 0~1 비율."""

    def __init__(self, axis="y", pos=0.5, max_dist=0.2, max_missed=10):
        self.axis, self.pos, self.max_dist, self.max_missed = axis, pos, max_dist, max_missed
        self.tracks = {}            # id → [x, y, missed, side]
        self.next_id = 0
        self.count_fwd = self.count_back = 0

    DEAD = 0.04                     # 선 주변 ±4 % 는 판단 보류 (선 위에서 흔들려도 여러 번 세지 않게)

    def _side(self, x, y, prev=None):
        v = y if self.axis == "y" else x
        if v > self.pos + self.DEAD:
            return 1
        if v < self.pos - self.DEAD:
            return 0
        return prev if prev is not None else (1 if v >= self.pos else 0)

    def update(self, centers):
        used = set()
        for tid, tr in list(self.tracks.items()):
            best, bd = None, self.max_dist
            for i, (x, y) in enumerate(centers):
                if i in used:
                    continue
                d = math.hypot(x - tr[0], y - tr[1])
                if d < bd:
                    best, bd = i, d
            if best is None:
                tr[2] += 1
                if tr[2] > self.max_missed:
                    del self.tracks[tid]
                continue
            used.add(best)
            x, y = centers[best]
            side = self._side(x, y, tr[3])
            if side != tr[3]:
                if side == 1:
                    self.count_fwd += 1
                else:
                    self.count_back += 1
            self.tracks[tid] = [x, y, 0, side]
        for i, (x, y) in enumerate(centers):
            if i not in used:
                self.tracks[self.next_id] = [x, y, 0, self._side(x, y)]
                self.next_id += 1

    @property
    def count(self):
        return self.count_fwd + self.count_back

    def reset(self):
        self.count_fwd = self.count_back = 0


def _open_camera(cv2, src, size):
    w, h = size
    if src in ("auto", "csi"):
        pipe = (f"nvarguscamerasrc ! video/x-raw(memory:NVMM),width={w},height={h},framerate=30/1 ! "
                "nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! "
                "appsink drop=1 max-buffers=1")
        cap = cv2.VideoCapture(pipe, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            return cap, "CSI 카메라"
        if src == "csi":
            return None, "CSI 카메라를 열 수 없음"
        src = 0
    cap = cv2.VideoCapture(int(src))
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        return cap, f"USB 카메라 {src}"
    return None, "카메라를 찾지 못함"


def _make_detector(cv2, prefer, model):
    """(이름, 함수) — 함수는 BGR 프레임을 받아 사람 상자 [(x1,y1,x2,y2) 0~1] 를 돌려줌"""
    if prefer in ("auto", "yolo"):
        try:
            from ultralytics import YOLO
            m = YOLO(model)

            def yolo(frame):
                r = m(frame, verbose=False, classes=[0], conf=0.4)[0]
                return [tuple(b) for b in r.boxes.xyxyn.cpu().numpy().tolist()]
            try:
                import torch
                dev = "GPU" if torch.cuda.is_available() else "CPU"
            except ImportError:
                dev = "CPU"
            return f"YOLO ({dev})", yolo
        except Exception:
            if prefer == "yolo":
                raise
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def hog_fn(frame):
        h, w = frame.shape[:2]
        s = 640 / w
        small = cv2.resize(frame, (640, int(h * s)))
        rects, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
        sh, sw = small.shape[:2]
        return [(x / sw, y / sh, (x + bw) / sw, (y + bh) / sh)
                for (x, y, bw, bh), wt in zip(rects, weights) if float(wt) > 0.5]
    return "HOG (CPU)", hog_fn


def pixelate(cv2, frame, cells):
    """개인정보 보호용 모자이크 미리보기 (RGB, 480×270)"""
    cells = max(8, min(64, int(cells)))     # 64칸보다 선명하게는 못 하게 (프라이버시)
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (cells, max(1, int(cells * h / w))), interpolation=cv2.INTER_AREA)
    big = cv2.resize(small, (480, 270), interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(big, cv2.COLOR_BGR2RGB)


class CameraCounter(threading.Thread):
    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.ok, self.status, self.method, self.fps = False, "카메라 준비 중...", "", 0.0
        self.counter = LineCounter(cfg["line_axis"], cfg["line_pos"])
        self.preview, self.boxes = None, []
        self.lock = threading.Lock()
        self.stop_ev = threading.Event()

    @property
    def count(self):
        return self.counter.count

    def reset(self):
        self.counter.reset()

    def snapshot(self):
        with self.lock:
            return self.preview, list(self.boxes)

    def run(self):
        try:
            import cv2
        except ImportError:
            self.status = "OpenCV 없음"
            return
        cap, name = _open_camera(cv2, self.cfg["camera_source"], self.cfg["camera_size"])
        if cap is None:
            self.status = name
            return
        try:
            self.method, detect = _make_detector(cv2, self.cfg["detector"], self.cfg["yolo_model"])
        except Exception as e:
            self.status = f"탐지기 오류: {e}"
            cap.release()
            return
        self.ok, self.status = True, f"{name} · {self.method}"
        t_last, n, bad_since = time.time(), 0, None
        try:
            while not self.stop_ev.is_set():
                good, frame = cap.read()
                if not good:
                    bad_since = bad_since or time.time()
                    if time.time() - bad_since > 2:
                        self.ok, self.status = False, f"{name}: 화면이 들어오지 않음 (케이블 확인)"
                    time.sleep(0.05)
                    continue
                if bad_since:
                    bad_since, self.ok, self.status = None, True, f"{name} · {self.method}"
                boxes = detect(frame)
                self.counter.update([((x1 + x2) / 2, (y1 + y2) / 2) for x1, y1, x2, y2 in boxes])
                prev = pixelate(cv2, frame, self.cfg["privacy_pixel"])
                with self.lock:
                    self.preview, self.boxes = prev, boxes
                del frame                                  # 원본 프레임은 바로 버림 (저장 안 함)
                n += 1
                if time.time() - t_last >= 1:
                    self.fps, n, t_last = n / (time.time() - t_last), 0, time.time()
        finally:
            cap.release()

    def stop(self):
        self.stop_ev.set()


# ═════════════════════ ② 초음파 사람 수 ═════════════════════
class UltrasonicCounter(threading.Thread):
    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.ok, self.status, self.count, self.dist = False, "초음파 준비 중...", 0, None
        self.baseline = None
        self.stop_ev = threading.Event()

    def reset(self):
        self.count = 0

    def _measure(self, GPIO):
        t, e = self.cfg["us_trig"], self.cfg["us_echo"]
        GPIO.output(t, True)
        time.sleep(0.00001)
        GPIO.output(t, False)
        t0 = time.perf_counter()
        while not GPIO.input(e):
            if time.perf_counter() - t0 > 0.03:
                return None
        s = time.perf_counter()
        while GPIO.input(e):
            if time.perf_counter() - s > 0.03:
                return None
        return (time.perf_counter() - s) * 34300 / 2      # cm

    def run(self):
        try:
            import Jetson.GPIO as GPIO
        except Exception:
            self.status = "Jetson.GPIO 없음 (젯슨이 아님)"
            return
        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.cfg["us_trig"], GPIO.OUT, initial=False)
            GPIO.setup(self.cfg["us_echo"], GPIO.IN)
            samples, tries = [], 0
            self.status = "초음파: 평소 거리 재는 중 (앞을 비워 두세요)"
            while len(samples) < 30 and tries < 100 and not self.stop_ev.is_set():
                tries += 1
                d = self._measure(GPIO)
                if d:
                    samples.append(d)
                time.sleep(0.06)
            if not samples:
                self.status = "초음파 응답 없음 (배선·핀 확인)"
                return
            self.baseline = sorted(samples)[len(samples) // 2]
            self.ok, self.status = True, f"초음파 · 평소 {self.baseline:.0f} cm"
            present, last = False, 0.0
            while not self.stop_ev.is_set():
                d = self._measure(GPIO)
                if d:
                    self.dist = d
                    near = d < self.baseline - self.cfg["us_drop_cm"]
                    if near and not present and time.time() - last > self.cfg["us_min_gap_s"]:
                        self.count += 1
                        last = time.time()
                    present = near
                time.sleep(0.06)
        except Exception as e:
            self.ok, self.status = False, f"초음파 오류: {e}"
        finally:
            try:
                GPIO.cleanup([self.cfg["us_trig"], self.cfg["us_echo"]])
            except Exception:
                pass

    def stop(self):
        self.stop_ev.set()


# ═════════════════════ ③④ I2C 장치 ═════════════════════
class LCD1602:
    """PCF8574 백팩 16×2 LCD (영문·숫자만 — LCD 글꼴에 한글 없음)"""
    BL, EN, RS = 0x08, 0x04, 0x01

    def __init__(self, bus, addr):
        self.bus, self.addr = bus, addr
        time.sleep(0.05)                        # 전원 켠 뒤 대기
        for cmd in (0x33, 0x32, 0x28, 0x0C, 0x06, 0x01):
            self._byte(cmd, 0)
            time.sleep(0.005)                   # HD44780: 초기화·화면 지우기에 시간이 필요

    def _w(self, v):
        self.bus.write_byte(self.addr, v | self.BL)

    def _nib(self, v):
        self._w(v | self.EN)
        time.sleep(0.0005)
        self._w(v & ~self.EN)
        time.sleep(0.0001)

    def _byte(self, v, mode):
        self._nib(mode | (v & 0xF0))
        self._nib(mode | ((v << 4) & 0xF0))

    def lines(self, a, b):
        for row, s in ((0x80, a), (0xC0, b)):
            self._byte(row, 0)
            for ch in s[:16].ljust(16):
                self._byte(ord(ch) if ord(ch) < 128 else ord("?"), self.RS)


class Seg4:
    """HT16K33 4자리 7세그먼트 (Adafruit 배치: 자리 0,1,3,4 / 2 = 콜론) — 키트가 다르면 숫자 순서만 바꾸면 됨"""
    DIG = {str(i): v for i, v in enumerate((0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F))}
    POS = (0, 1, 3, 4)

    def __init__(self, bus, addr):
        self.bus, self.addr = bus, addr
        bus.write_byte(addr, 0x21)      # 발진기 켜기
        bus.write_byte(addr, 0x81)      # 표시 켜기
        bus.write_byte(addr, 0xEF)      # 밝기 최대

    def number(self, n):
        s = str(max(0, min(9999, int(n)))).rjust(4)
        buf = [0] * 16
        for i, ch in enumerate(s):
            buf[self.POS[i] * 2] = self.DIG.get(ch, 0)
        self.bus.write_i2c_block_data(self.addr, 0x00, buf)


class AHT:
    """AHT20/AHT10 온습도"""

    def __init__(self, bus, addr):
        self.bus, self.addr = bus, addr
        try:
            bus.write_i2c_block_data(addr, 0xBE, [0x08, 0x00])     # AHT20
        except OSError:
            bus.write_i2c_block_data(addr, 0xE1, [0x08, 0x00])     # AHT10
        time.sleep(0.02)

    def read(self):
        from smbus2 import i2c_msg
        self.bus.write_i2c_block_data(self.addr, 0xAC, [0x33, 0x00])
        for _ in range(5):
            time.sleep(0.08)
            m = i2c_msg.read(self.addr, 7)
            self.bus.i2c_rdwr(m)
            d = list(m)
            if not d[0] & 0x80:                 # 측정 끝 (busy 비트 0)
                break
        hum = ((d[1] << 12) | (d[2] << 4) | (d[3] >> 4)) / 1048576 * 100
        tmp = (((d[3] & 0x0F) << 16) | (d[4] << 8) | d[5]) / 1048576 * 200 - 50
        return tmp, hum


def kit_buzzer_beep():
    """부저: 키트 판에 'I2C-EXIO-STC8 P0.2' 로 연결돼 있어 키트 전용 확장칩 명령이 필요합니다.
    키트 예제 코드의 부저 켜기/끄기 함수를 여기에 넣으면 걸음마다 소리가 납니다."""
    pass


def kit_matrix_rows(levels):
    """8×8 RGB 매트릭스: 키트의 RP2040 이 구동하므로 키트 예제의 방법이 필요합니다.
    levels = 1~4행 밝기(0~1). 키트 예제 코드를 여기에 넣으면 행별로 빛나게 할 수 있습니다."""
    pass


class Outputs(threading.Thread):
    """LCD·숫자 표시기·LED·온습도를 한 스레드에서 처리 (I2C 를 동시에 쓰지 않도록)"""

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.status = {"LCD": "없음", "숫자 표시기": "없음", "온습도": "없음", "LED": "없음"}
        self.temp = self.hum = None
        self.lines = ("PIEZO TILE", "starting...")
        self.number = 0
        self.flash_pending = threading.Event()
        self.stop_ev = threading.Event()

    def flash(self):
        self.flash_pending.set()
        kit_buzzer_beep()

    def _led_loop(self, gpio, pin):
        """LED 는 I2C 와 따로 — LCD 갱신 때문에 깜박임을 놓치지 않게"""
        while not self.stop_ev.is_set():
            if self.flash_pending.wait(0.2):
                self.flash_pending.clear()
                try:
                    gpio.output(pin, True)
                    time.sleep(0.08)
                    gpio.output(pin, False)
                except Exception:
                    return

    def run(self):
        lcd = seg = env = gpio = None
        if self.cfg["i2c"]:
            try:
                from smbus2 import SMBus
                for n in self.cfg["i2c_buses"]:
                    try:
                        bus = SMBus(n)
                    except (OSError, FileNotFoundError):
                        continue
                    found = []
                    for a in (self.cfg["lcd_addr"], self.cfg["seg_addr"], self.cfg["env_addr"]):
                        try:
                            bus.read_byte(a)
                            found.append(a)
                        except OSError:
                            pass
                    if not found:
                        bus.close()
                        continue
                    for key, addr, cls in (("LCD", self.cfg["lcd_addr"], LCD1602),
                                           ("숫자 표시기", self.cfg["seg_addr"], Seg4),
                                           ("온습도", self.cfg["env_addr"], AHT)):
                        if addr in found:
                            try:
                                dev = cls(bus, addr)
                                self.status[key] = f"I2C-{n} 0x{addr:02X}"
                                if key == "LCD":
                                    lcd = dev
                                elif key == "숫자 표시기":
                                    seg = dev
                                else:
                                    env = dev
                            except OSError as e:
                                self.status[key] = f"오류 {e}"
                    break
            except ImportError:
                for k in ("LCD", "숫자 표시기", "온습도"):
                    self.status[k] = "smbus2 없음"
        try:
            import Jetson.GPIO as GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.cfg["led_pin"], GPIO.OUT, initial=False)
            gpio = GPIO
            self.status["LED"] = f"BCM {self.cfg['led_pin']}"
        except Exception:
            pass
        if gpio:
            threading.Thread(target=self._led_loop, args=(gpio, self.cfg["led_pin"]), daemon=True).start()
        t_disp = t_env = 0.0
        while not self.stop_ev.is_set():
            now = time.time()
            if now - t_disp > 0.5:
                t_disp = now
                for key, fn in (("LCD", lambda: lcd.lines(*self.lines) if lcd else None),
                                ("숫자 표시기", lambda: seg.number(self.number) if seg else None)):
                    try:
                        fn()
                    except Exception as e:          # 장치 하나가 고장 나도 나머지는 계속
                        self.status[key] = f"오류 {type(e).__name__}"
            if env and now - t_env > 5:
                t_env = now
                try:
                    self.temp, self.hum = env.read()
                except Exception as e:
                    self.status["온습도"] = f"오류 {type(e).__name__}"
            time.sleep(0.05)
        if gpio:
            try:
                gpio.output(self.cfg["led_pin"], False)
                gpio.cleanup([self.cfg["led_pin"]])
            except Exception:
                pass

    def stop(self):
        self.stop_ev.set()


# ═════════════════════ 시뮬레이션 (젯슨 없이 화면 시험용) ═════════════════════
class SimCamera:
    """가짜 카메라: 움직이는 상자를 그린 모자이크 미리보기 + 발판 인원에 잡음을 섞은 가짜 숫자.
    화면에 '시뮬레이션'으로 표시되므로 발표 데이터로 쓰면 안 됨"""
    ok, method, fps = True, "시뮬레이션", 15.0
    status = "시뮬레이션 (가짜 데이터)"

    def __init__(self, cfg):
        import numpy as np
        self.np, self.cfg = np, cfg
        self.count = 0
        self.t0 = time.time()

    def start(self):
        pass

    def stop(self):
        pass

    def reset(self):
        self.count = 0

    def follow(self, people):
        self.count = max(self.count, int(round(people * 1.6)))

    def snapshot(self):
        np = self.np
        img = np.full((270, 480, 3), (40, 46, 60), np.uint8)
        t = time.time() - self.t0
        boxes = []
        for k in range(2):
            y = (0.15 + 0.5 * ((t * 0.12 + k * 0.5) % 1.0))
            x = 0.3 + 0.35 * k
            x1, y1, x2, y2 = x - 0.06, y - 0.12, x + 0.06, y + 0.12
            boxes.append((x1, y1, x2, y2))
            img[int(y1 * 270):int(y2 * 270), int(x1 * 480):int(x2 * 480)] = (120, 110, 100)
        cell = 480 // max(8, min(64, int(self.cfg["privacy_pixel"])))
        small = img[::cell, ::cell]
        img = np.repeat(np.repeat(small, cell, 0), cell, 1)[:270, :480]
        return img, boxes


class SimUltrasonic:
    ok, status, dist = True, "시뮬레이션 (가짜 데이터)", 120.0

    def __init__(self, cfg):
        self.count = 0

    def start(self):
        pass

    def stop(self):
        pass

    def reset(self):
        self.count = 0

    def follow(self, people):
        self.count = max(self.count, people + (1 if people > 2 else 0))


# ═════════════════════ 묶음 ═════════════════════
class Missing:
    ok, count, dist, method, fps = False, 0, None, "", 0.0

    def __init__(self, status):
        self.status = status

    def start(self):
        pass

    def stop(self):
        pass

    def reset(self):
        pass

    def snapshot(self):
        return None, []


class Hardware:
    def __init__(self, cfg=CONFIG, sim=False, camera=True, ultrasonic=True, i2c=True):
        self.cfg, self.sim = dict(cfg), sim
        self.cfg["i2c"] = cfg["i2c"] and i2c
        cam_on = cfg["camera"] and camera
        us_on = cfg["ultrasonic"] and ultrasonic
        if sim:
            self.camera = SimCamera(self.cfg) if cam_on else Missing("꺼짐")
            self.ultra = SimUltrasonic(self.cfg) if us_on else Missing("꺼짐")
        else:
            self.camera = CameraCounter(self.cfg) if cam_on else Missing("꺼짐 (--no-camera)")
            self.ultra = UltrasonicCounter(self.cfg) if us_on else Missing("꺼짐 (--no-ultra)")
        self.camera_enabled = cam_on
        self.out = Outputs(self.cfg)
        self.last_pulses = 0

    def start(self):
        self.camera.start()
        self.ultra.start()
        if not self.sim:
            self.out.start()

    def stop(self):
        for m in (self.camera, self.ultra, self.out):
            m.stop()
        for m in (self.camera, self.ultra, self.out):
            if isinstance(m, threading.Thread) and m.is_alive():
                m.join(timeout=2)

    def reset_counts(self):
        self.camera.reset()
        self.ultra.reset()

    def tick(self, st):
        """매 프레임: 새 펄스면 LED·부저, 표시기 내용 갱신"""
        if st.pulses > self.last_pulses:
            self.out.flash()
        self.last_pulses = st.pulses
        people = st.people()
        if self.sim:
            for m in (self.camera, self.ultra):
                if hasattr(m, "follow"):
                    m.follow(people)
        e = st.total_E
        e_txt = f"{e:.1f}uJ" if e < 1000 else f"{e/1000:.2f}mJ"
        cam = self.camera.count if self.camera.ok else "-"
        us = self.ultra.count if self.ultra.ok else "-"
        self.out.lines = (f"P{people} C{cam} U{us}", f"E {e_txt}" + (f" {self.out.temp:.0f}C" if self.out.temp else ""))
        self.out.number = people
        kit_matrix_rows([min(1.0, v / 4.0) for v in st.env])
