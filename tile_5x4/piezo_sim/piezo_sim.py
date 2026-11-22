# -*- coding: utf-8 -*-
"""
압전 발판(Piezoelectric floor tile) 발전 시뮬레이션 + 세로형 영상(1080x1920) 렌더러

회로 모델
  압전 디스크 8개(병렬)  : 전하원  i = d_eff * dF/dt  +  내부 정전용량 Cp  +  누설저항
  브리지 정류기          : 이상 다이오드 4개 (순방향 전압 Vd)
  저장 커패시터          : Cs
  전압감지 스위치 + LED  : Vc >= V_ON 이면 LED 켜짐, Vc <= V_OFF 이면 꺼짐 (히스테리시스)

실행:  python piezo_sim.py   ->  압전발판_시뮬레이션.mp4
"""
import math, os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

# ───────────────────────── 1. 파라미터 ─────────────────────────
N_DISK   = 8          # 압전 디스크 수 (2 x 4 배열, 병렬)
CP_DISK  = 40e-9      # 디스크 1개 정전용량 [F]
D_EFF    = 11e-9      # 유효 압전계수(굽힘 모드) [C/N]  -> 760 N 에서 약 8.4 uC
R_LEAK   = 1e6        # 압전 소자 누설/측정 저항 [ohm]
VD       = 0.3        # 쇼트키 다이오드 순방향 전압 [V]
CS       = 47e-6      # 저장 커패시터 [F]
CS_LEAK  = 10e6       # 커패시터 누설 [ohm]
V_ON, V_OFF = 4.0, 2.6
VF_LED, R_LED = 1.9, 1000.0

BODY_F   = 760.0      # 걸음 하중 피크 [N] (약 65 kg + 충격)
PERIOD   = 0.9        # 걸음 간격 [s]
TR, TH, TF = 0.07, 0.38, 0.09   # 하중 상승 / 유지 / 해제 시간
TC = TR + TH + TF

FPS, W, H, S = 30, 1080, 1920, 2   # S: 슈퍼샘플링 배율
T_INTRO, T_SIM, T_OUT = 4.0, 26.0, 8.0
DT = 5e-5
REC = 1000            # 기록 샘플레이트 [Hz]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_MP4 = os.path.join(HERE, "압전발판_시뮬레이션.mp4")

# ───────────────────────── 2. 물리 시뮬레이션 ─────────────────────────
rng = np.random.default_rng(7)
steps = []
t = 0.8
while t + TC < T_SIM - 0.3:
    steps.append((t, BODY_F * (1 + 0.07 * rng.standard_normal())))
    t += PERIOD

n = int(T_SIM / DT) + 1
tt = np.arange(n) * DT
F = np.zeros(n)
for ts, fp in steps:
    u = tt - ts
    m1 = (u >= 0) & (u < TR)
    m2 = (u >= TR) & (u < TR + TH)
    m3 = (u >= TR + TH) & (u < TC)
    F[m1] = fp * (0.5 - 0.5 * np.cos(np.pi * u[m1] / TR))
    F[m2] = fp * (1 - 0.10 * np.sin(np.pi * (u[m2] - TR) / TH))
    F[m3] = fp * 0.9 * 0 + fp * (0.5 + 0.5 * np.cos(np.pi * (u[m3] - TR - TH) / TF))
dQ = (D_EFF * np.diff(F)).tolist()

CP = N_DISK * CP_DISK
stride = int(round(1 / (REC * DT)))
nrec = n // stride + 1
r_vp = np.zeros(nrec); r_vs = np.zeros(nrec); r_led = np.zeros(nrec, bool)
r_qac = np.zeros(nrec); r_qdc = np.zeros(nrec); r_qled = np.zeros(nrec); r_eled = np.zeros(nrec)

vp = vs = 0.0; led = False
qac = qdc = qled = eled = 0.0
led_events = []
kp = DT / (R_LEAK * CP); ks = DT / (CS_LEAK * CS)
for i in range(n - 1):
    vp += dQ[i] / CP - vp * kp
    thr = vs + 2 * VD
    if vp > thr:
        dv = (vp - thr) * CP / (CP + CS); vs += dv; vp = vs + 2 * VD
        qac += dv * CS; qdc += dv * CS
    elif vp < -thr:
        dv = (-vp - thr) * CP / (CP + CS); vs += dv; vp = -(vs + 2 * VD)
        qac -= dv * CS; qdc += dv * CS
    if not led and vs >= V_ON:
        led = True; led_events.append(i * DT)
    if led:
        il = max(0.0, (vs - VF_LED) / R_LED)
        vs -= il * DT / CS
        qled += il * DT; eled += vs * il * DT
        if vs <= V_OFF:
            led = False
    vs -= vs * ks
    if i % stride == 0:
        k = i // stride
        r_vp[k], r_vs[k], r_led[k] = vp, vs, led
        r_qac[k], r_qdc[k], r_qled[k], r_eled[k] = qac, qdc, qled, eled
last = (n - 2) // stride
for arr in (r_vp, r_vs, r_led, r_qac, r_qdc, r_qled, r_eled):
    arr[last + 1:] = arr[last]

E_ideal_step = 2 * (D_EFF * BODY_F) ** 2 / (2 * CP)          # 압축 + 복원 (개방회로 최대)
E_store_final = 0.5 * CS * r_vs[-1] ** 2
E_harv = E_store_final + r_eled[-1]
n_steps = len(steps)
E_per_step = E_harv / n_steps
print(f"steps={n_steps}  Q/press={D_EFF*BODY_F*1e6:.2f}uC  Voc={D_EFF*BODY_F/CP:.1f}V")
print(f"E_ideal/step={E_ideal_step*1e6:.1f}uJ  E_harv={E_harv*1e6:.1f}uJ  per step={E_per_step*1e6:.1f}uJ  "
      f"eff={E_per_step/E_ideal_step*100:.1f}%  LED flashes={len(led_events)}")

# ───────────────────────── 3. 그리기 도구 ─────────────────────────
FONT_R = r"C:\Windows\Fonts\malgun.ttf"
FONT_B = r"C:\Windows\Fonts\malgunbd.ttf"
FONT_M = r"C:\Windows\Fonts\consolab.ttf"
_fc = {}
def font(size, kind="r"):
    key = (size, kind)
    if key not in _fc:
        path = {"r": FONT_R, "b": FONT_B, "m": FONT_M}[kind]
        _fc[key] = ImageFont.truetype(path, int(size * S))
    return _fc[key]

BG0, BG1 = (16, 20, 32), (8, 10, 18)
PANEL, BORDER = (22, 28, 44), (52, 62, 88)
TXT, DIM = (232, 236, 246), (140, 150, 172)
YEL, CYAN, GRN, RED, ORG = (255, 204, 48), (70, 205, 255), (90, 232, 150), (255, 96, 86), (255, 150, 60)

class C:
    def __init__(self, img):
        self.img = img; self.d = ImageDraw.Draw(img, "RGBA")
    def P(self, pts): return [(x * S, y * S) for x, y in pts]
    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=1, r=0):
        b = [x0 * S, y0 * S, x1 * S, y1 * S]
        if r: self.d.rounded_rectangle(b, radius=r * S, fill=fill, outline=outline, width=int(w * S))
        else: self.d.rectangle(b, fill=fill, outline=outline, width=int(w * S))
    def line(self, pts, fill, w=2):
        self.d.line(self.P(pts), fill=fill, width=max(1, int(w * S)), joint="curve")
    def ell(self, cx, cy, rx, ry, fill=None, outline=None, w=1):
        self.d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill, outline=outline, width=int(w * S))
    def poly(self, pts, fill=None, outline=None, w=1):
        self.d.polygon(self.P(pts), fill=fill, outline=outline, width=int(w * S))
    def text(self, x, y, s, f, fill=TXT, anchor="la"):
        self.d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)
    def dashed(self, x0, y, x1, fill, w=2, dash=10):
        x = x0
        while x < x1:
            self.line([(x, y), (min(x + dash, x1), y)], fill, w); x += dash * 2
    def glow(self, cx, cy, r, col, g):
        if g <= 0.02: return
        for k, a in ((1.0, 0.18), (0.7, 0.25), (0.45, 0.35)):
            self.ell(cx, cy, r * k, r * k, fill=col + (int(255 * a * min(1, g)),))

def lerp(a, b, u): return a + (b - a) * u
def mix(c1, c2, u): return tuple(int(lerp(a, b, max(0, min(1, u)))) for a, b in zip(c1, c2))
def ease(u): u = max(0.0, min(1.0, u)); return u * u * (3 - 2 * u)

def make_bg():
    img = Image.new("RGB", (W * S, H * S))
    g = np.linspace(0, 1, H * S)[:, None, None]
    arr = (np.array(BG0) * (1 - g) + np.array(BG1) * g).astype(np.uint8)
    img = Image.fromarray(np.broadcast_to(arr, (H * S, W * S, 3)).copy())
    return img

BG = make_bg()

# ───────────────────────── 4. 장면 요소 ─────────────────────────
DISK_X = [315, 465, 615, 765]
TX0, TX1 = 240, 840

def draw_tile(c, dy, disp, e=0.0, glow=0.0, vp=0.0):
    base_top = 680 + dy + 60 * e
    disk_y = base_top - 30 - 70 * e
    plate_bot = disk_y - 36 + disp - 170 * e
    plate_top = plate_bot - 26
    # 베이스 & 받침
    c.rect(TX0, base_top, TX1, base_top + 22, fill=(92, 98, 112), r=3)
    for cx in DISK_X:
        for sx in (-54, 54):
            c.rect(cx + sx - 5, base_top - 30 + 2, cx + sx + 5, base_top, fill=(130, 136, 150))
    # 스프링
    for sx in (262, 818):
        pts, nz = [], 9
        for k in range(nz + 1):
            y = lerp(plate_bot, base_top, k / nz)
            pts.append((sx + (12 if k % 2 else -12) * (0 < k < nz), y))
        c.line(pts, (170, 175, 190), 3)
    # 압전 디스크
    for cx in DISK_X:
        sag = disp
        def yy(x): return disk_y + sag * (1 - ((x - cx) / 60) ** 2)
        c.glow(cx, disk_y + sag - 4, 78, YEL, glow)
        brass = [(cx + x, yy(cx + x)) for x in range(-60, 61, 6)]
        c.line(brass, (205, 165, 80), 6)
        cer = [(cx + x, yy(cx + x) - 6) for x in range(-38, 39, 4)]
        c.line(cer, mix((228, 228, 238), YEL, glow * 1.4), 7)
        a = min(1.0, abs(vp) / 4.0)
        if a > 0.05:
            top, bot = ("+", "-") if vp > 0 else ("-", "+")
            col_t = (255, 120, 90, int(255 * a)) if top == "+" else (110, 190, 255, int(255 * a))
            col_b = (110, 190, 255, int(255 * a)) if top == "+" else (255, 120, 90, int(255 * a))
            c.text(cx - 22, disk_y + sag - 22, top, font(24, "b"), col_t, "mm")
            c.text(cx + 22, disk_y + sag - 22, top, font(24, "b"), col_t, "mm")
            c.text(cx, disk_y + sag + 18, bot, font(24, "b"), col_b, "mm")
        # 가압 핀
        c.rect(cx - 7, plate_bot, cx + 7, disk_y + sag - 9, fill=(150, 156, 170))
    # 상판
    c.rect(TX0 + 4, plate_top, TX1 - 4, plate_bot, fill=(62, 68, 82), r=4)
    c.rect(TX0 + 4, plate_top, TX1 - 4, plate_top + 6, fill=(158, 166, 182), r=3)
    for k in range(9):
        x = TX0 + 30 + k * 66
        c.line([(x, plate_top + 12), (x + 30, plate_top + 12)], (90, 98, 115), 3)
    return dict(base_top=base_top, disk_y=disk_y, plate_top=plate_top, plate_bot=plate_bot)

def draw_floor(c):
    c.rect(30, 588, 236, 720, fill=(70, 74, 84))
    c.rect(844, 588, 1050, 720, fill=(70, 74, 84))
    c.rect(236, 588, 844, 704, fill=(26, 27, 34))
    c.rect(30, 704, 1050, 790, fill=(48, 44, 40))
    r2 = np.random.default_rng(3)
    for _ in range(70):
        x = r2.uniform(36, 1044); y = r2.uniform(596, 780)
        if 236 < x < 844 and y < 704: continue
        c.ell(x, y, 2, 2, fill=(100, 100, 108))
    c.line([(30, 588), (236, 588)], (120, 124, 134), 3)
    c.line([(844, 588), (1050, 588)], (120, 124, 134), 3)

def draw_foot(c, b):
    """b: 신발 밑창 y"""
    top_clip = 196
    leg = [(398, b - 74), (548, b - 70), (560, top_clip), (390, top_clip)]
    c.poly(leg, fill=(42, 62, 112))
    c.line([(475, b - 74), (478, top_clip)], (32, 48, 92), 3)
    c.rect(398, b - 92, 548, b - 70, fill=(210, 210, 220))
    shoe = [(372, b), (712, b), (726, b - 18), (712, b - 42), (630, b - 60), (530, b - 74), (400, b - 80), (370, b - 52)]
    c.poly(shoe, fill=(118, 66, 34))
    c.rect(368, b - 12, 724, b, fill=(40, 30, 26), r=5)
    c.line([(560, b - 66), (640, b - 54)], (160, 100, 60), 3)

def foot_state(ts):
    lift_h, md = 150.0, 0.16
    for k, (s0, fp) in enumerate(steps):
        s1 = s0 + TC
        if s0 - md <= ts < s0: return lift_h * (1 - ease((ts - (s0 - md)) / md))
        if s0 <= ts < s1: return 0.0
        if s1 <= ts < s1 + md: return lift_h * ease((ts - s1) / md)
    return lift_h

def step_count(ts): return sum(1 for s0, _ in steps if s0 <= ts)

def path_dots(c, pts, phase, col, alpha, spacing=30, r=5):
    if alpha < 0.03: return
    segs, total = [], 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b); segs.append((a, b, total, L)); total += L
    off = phase % spacing
    s = off
    while s < total:
        for a, b, s0, L in segs:
            if s0 <= s <= s0 + L:
                u = (s - s0) / L
                x, y = lerp(a[0], b[0], u), lerp(a[1], b[1], u)
                c.ell(x, y, r + 4, r + 4, fill=col + (int(70 * alpha),))
                c.ell(x, y, r, r, fill=col + (int(255 * alpha),))
                break
        s += spacing

# 회로 좌표
RT, RB = 985, 1160
P_AC = [(130, 1046), (130, RT), (300, RT)]
P_AC2 = [(300, RB), (130, RB), (130, 1094)]
P_DC = [(460, RT), (600, RT), (600, 1052)]
P_DC2 = [(600, 1092), (600, RB), (460, RB)]
P_LED = [(600, RT), (930, RT), (930, RB), (600, RB)]

def draw_circuit(c, vp, vs, led, sw_on, led_glow, cur):
    c.rect(30, 820, 1050, 1290, fill=PANEL, outline=BORDER, w=2, r=18)
    c.text(52, 836, "② 수확 회로", font(30, "b"), TXT)
    wire = (175, 185, 205)
    for p in (P_AC, P_AC2, P_DC, P_DC2):
        c.line(p, wire, 4)
    c.line([(600, RT), (700, RT)], wire, 4); c.line([(820, RT), (930, RT)], wire, 4)
    c.line([(930, RT), (930, 1012)], wire, 4); c.line([(930, 1128), (930, RB)], wire, 4)
    c.line([(600, RB), (930, RB)], wire, 4)
    for x, y in ((600, RT), (600, RB)): c.ell(x, y, 7, 7, fill=wire)
    # 압전 소자
    c.text(130, 900, "압전 디스크", font(24, "b"), YEL, "mm"); c.text(130, 930, "×8 병렬", font(21), DIM, "mm")
    c.line([(92, 1046), (168, 1046)], wire, 5); c.line([(92, 1094), (168, 1094)], wire, 5)
    c.rect(100, 1052, 160, 1088, fill=mix((70, 70, 90), YEL, min(1, abs(vp) / 5)), outline=(220, 220, 230), w=2)
    # 브리지 정류기
    c.text(380, 900, "브리지 정류기", font(24, "b"), TXT, "mm"); c.text(380, 930, "쇼트키 ×4", font(21), DIM, "mm")
    c.rect(300, 955, 460, 1190, fill=(30, 38, 58), outline=(120, 130, 160), w=2, r=10)
    cx, cy, hs = 380, 1072, 62
    dia = [(cx - hs, cy), (cx, cy - hs), (cx + hs, cy), (cx, cy + hs), (cx - hs, cy)]
    c.line(dia, (120, 130, 160), 3)
    for (ax, ay), (bx, by) in zip(dia, dia[1:]):
        mx, my = (ax + bx) / 2, (ay + by) / 2
        dx, dy = (bx - ax), (by - ay); L = math.hypot(dx, dy); ux, uy = dx / L, dy / L
        if (ax, ay) in ((cx - hs, cy), (cx, cy + hs)) and False: pass
        # 모든 다이오드가 + 단자(오른쪽 꼭짓점) 방향을 향하도록
        if (bx, by) == (cx + hs, cy) or (ax, ay) == (cx + hs, cy):
            if (ax, ay) == (cx + hs, cy): ux, uy = -ux, -uy
        else:
            if (bx, by) == (cx - hs, cy): ux, uy = -ux, -uy
        px, py = -uy, ux
        tri = [(mx - ux * 10 + px * 10, my - uy * 10 + py * 10), (mx - ux * 10 - px * 10, my - uy * 10 - py * 10), (mx + ux * 10, my + uy * 10)]
        c.poly(tri, fill=(200, 210, 230))
        c.line([(mx + ux * 10 + px * 10, my + uy * 10 + py * 10), (mx + ux * 10 - px * 10, my + uy * 10 - py * 10)], (200, 210, 230), 3)
    c.text(312, RT - 14, "~", font(22, "b"), DIM); c.text(312, RB - 34, "~", font(22, "b"), DIM)
    c.text(448, RT - 14, "+", font(22, "b"), RED, "ra"); c.text(448, RB - 34, "-", font(22, "b"), CYAN, "ra")
    # 커패시터
    c.text(600, 900, "커패시터", font(24, "b"), CYAN, "mm"); c.text(600, 930, "47 µF", font(21), DIM, "mm")
    c.line([(565, 1052), (635, 1052)], wire, 6); c.line([(565, 1092), (635, 1092)], wire, 6)
    lvl = max(0, min(1, vs / 5.0))
    c.rect(652, 1030, 672, 1114, outline=(90, 110, 140), w=2, r=4)
    c.rect(654, 1112 - 80 * lvl, 670, 1112, fill=CYAN, r=3)
    c.dashed(648, 1112 - 80 * V_ON / 5, 678, GRN, 2, 3)
    # 스위치
    c.text(770, 900, "감지 스위치", font(24, "b"), TXT, "mm"); c.text(770, 930, "4.0V↑ON 2.6V↓OFF", font(21), DIM, "mm")
    c.rect(700, 950, 820, 1020, fill=(30, 38, 58), outline=GRN if sw_on else (110, 120, 145), w=2, r=8)
    c.ell(728, RT, 6, 6, fill=wire); c.ell(792, RT, 6, 6, fill=wire)
    if sw_on: c.line([(728, RT), (792, RT)], GRN, 5)
    else: c.line([(728, RT), (786, RT - 26)], (170, 175, 190), 5)
    c.text(760, 1040, "ON" if sw_on else "OFF", font(22, "b"), GRN if sw_on else DIM, "mm")
    # 저항 + LED
    c.text(960, 900, "LED", font(24, "b"), RED, "mm"); c.text(960, 930, "+ 1 kΩ", font(21), DIM, "mm")
    zz = [(930, 1012)] + [(930 + (10 if k % 2 else -10), 1012 + k * 6) for k in range(1, 8)] + [(930, 1060)]
    c.line(zz, wire, 3)
    c.line([(930, 1060), (930, 1076)], wire, 4)
    c.glow(930, 1098, 95, (255, 70, 60), led_glow)
    c.poly([(912, 1078), (948, 1078), (930, 1110)], fill=mix((120, 50, 50), (255, 90, 80), led_glow))
    c.line([(910, 1112), (950, 1112)], wire, 4); c.line([(930, 1112), (930, 1128)], wire, 4)
    if led_glow > 0.2:
        for k in (-1, 1):
            c.line([(958, 1084 + k * 8), (980, 1072 + k * 8)], (255, 140, 120, int(255 * led_glow)), 3)
    # 전류 흐름 점 (전하 이동량에 비례하여 이동)
    qac, qdc, qled, aac, adc, aled = cur
    path_dots(c, P_AC, qac * 9e6, YEL, aac)
    path_dots(c, list(reversed(P_AC2)), -qac * 9e6, YEL, aac)
    path_dots(c, P_DC, qdc * 9e6, CYAN, adc)
    path_dots(c, P_DC2, qdc * 9e6, CYAN, adc)
    path_dots(c, P_LED, qled * 1.2e6, RED, aled)
    # 계측기
    for i, (lab, val, col) in enumerate((("V 압전", f"{vp:+6.2f} V", YEL), ("V 커패시터", f"{vs:5.2f} V", CYAN),
                                         ("저장 에너지", f"{0.5*CS*vs*vs*1e6:6.1f} µJ", GRN))):
        x0 = 52 + i * 334
        c.rect(x0, 1206, x0 + 310, 1272, fill=(12, 16, 26), outline=(60, 70, 96), w=2, r=10)
        c.text(x0 + 16, 1239, lab, font(22), DIM, "lm")
        c.text(x0 + 296, 1239, val, font(30, "m"), col, "rm")

def draw_graph(c, ts):
    c.rect(30, 1305, 1050, 1745, fill=PANEL, outline=BORDER, w=2, r=18)
    c.text(52, 1321, "③ 전압 파형  (최근 6초)", font(30, "b"), TXT)
    gx0, gx1 = 140, 1025
    win = 6.0
    t0 = ts - win
    xs = np.arange(gx0, gx1)
    tq = t0 + (xs - gx0) / (gx1 - gx0) * win
    idx = np.clip((tq * REC).astype(int), 0, nrec - 1)
    valid = tq >= 0
    for (y0, y1, lo, hi, data, col, name, ticks) in (
            (1375, 1535, -6, 6, r_vp, YEL, "V압전", (-5, 0, 5)),
            (1570, 1720, 0, 5, r_vs, CYAN, "Vc", (0, 2.6, 4, 5))):
        c.rect(gx0, y0, gx1, y1, fill=(12, 16, 26))
        for tv in ticks:
            y = y1 - (tv - lo) / (hi - lo) * (y1 - y0)
            if tv in (V_ON, V_OFF) and name == "Vc":
                c.dashed(gx0, y, gx1, GRN if tv == V_ON else ORG, 2, 8)
            else:
                c.line([(gx0, y), (gx1, y)], (40, 48, 68), 1)
            c.text(gx0 - 10, y, f"{tv:g}", font(18), DIM, "rm")
        c.text(48, (y0 + y1) / 2 - 12, name, font(20, "b"), col, "lm")
        c.text(48, (y0 + y1) / 2 + 14, "[V]", font(18), DIM, "lm")
        v = data[idx]
        ys = y1 - (np.clip(v, lo, hi) - lo) / (hi - lo) * (y1 - y0)
        pts = [(float(x), float(y)) for x, y, ok in zip(xs, ys, valid) if ok]
        if len(pts) > 1: c.line(pts, col, 3)
    c.text(gx0 + 6, 1548, "ON 4.0V", font(16), GRN); c.text(gx0 + 110, 1548, "OFF 2.6V", font(16), ORG)
    c.text(gx1, 1726, f"t = {ts:5.1f} s", font(18), DIM, "ra")

def draw_header(c, ts=None):
    c.text(54, 52, "압전 발판 발전 시뮬레이션", font(50, "b"), TXT)
    c.text(56, 120, "Piezoelectric Floor Tile · 회로 시간영역 해석", font(25), DIM)
    if ts is not None:
        c.rect(860, 60, 1030, 116, fill=(30, 38, 58), r=12)
        c.text(945, 88, f"{ts:5.1f} s", font(32, "m"), TXT, "mm")

def draw_stats(c, ts, k, led_cnt):
    st = step_count(ts)
    eh = 0.5 * CS * r_vs[k] ** 2 + r_eled[k]
    items = (("걸음 수", f"{st}", TXT), ("누적 수확", f"{eh*1e6:.0f} µJ", GRN),
             ("걸음당", f"{(eh/st*1e6 if st else 0):.0f} µJ", YEL), ("LED 점등", f"{led_cnt}회", RED))
    for i, (lab, val, col) in enumerate(items):
        x0 = 30 + i * 258
        c.rect(x0, 1762, x0 + 246, 1890, fill=PANEL, outline=BORDER, w=2, r=16)
        c.text(x0 + 123, 1796, lab, font(24), DIM, "mm")
        c.text(x0 + 123, 1848, val, font(40, "b"), col, "mm")

# ───────────────────────── 5. 프레임 구성 ─────────────────────────
def frame_intro(t):
    img = BG.copy(); c = C(img)
    a = ease(t / 0.8)
    c.text(540, 250, "압전 발판", font(110, "b"), mix(BG0, YEL, a), "mm")
    c.text(540, 370, "걸을 때마다 전기가 생길까?", font(46), mix(BG0, TXT, a), "mm")
    e = 1 - ease((t - 1.0) / 1.8)
    g = draw_tile(c, 170, 0, e=e, glow=0.0)
    lab = dict(plate=(g["plate_top"] + g["plate_bot"]) / 2, disk=g["disk_y"], base=g["base_top"] + 11)
    for key, txt, col in (("plate", "상판 (밟는 면)", TXT), ("disk", "압전 디스크", YEL), ("base", "베이스", TXT)):
        y = lab[key]
        c.line([(842, y), (870, y)], DIM, 2)
        c.text(878, y, txt, font(26, "b"), col, "lm")
    c.text(540, 1000, "단면도  ·  디스크 2×4 = 8개", font(26), DIM, "mm")
    lines = ("① 발로 밟으면 상판이 눌리고", "② 압전 디스크가 휘면서 전하 발생  Q = d·F",
             "③ 정류 → 커패시터에 저장 → LED 점등")
    for i, s in enumerate(lines):
        u = ease((t - 1.2 - i * 0.7) / 0.5)
        if u > 0:
            c.text(90 + (1 - u) * 40, 1180 + i * 90, s, font(38, "b" if i == 1 else "r"), mix(BG0, TXT if i != 1 else YEL, u))
    img = img.reduce(S)
    if t > T_INTRO - 0.35: img = Image.blend(img, Image.new("RGB", img.size), ease((t - (T_INTRO - 0.35)) / 0.35))
    return img

led_glow_mem = {"v": 0.0, "t": -1}
def frame_sim(ts):
    k = min(int(ts * REC), nrec - 1)
    vp, vs, led = r_vp[k], r_vs[k], bool(r_led[k])
    Fn = F[min(int(ts / DT), n - 1)]
    disp = 13 * Fn / 800
    lift = foot_state(ts)
    kb = max(0, k - 40)
    # 최근 40ms 동안 이동한 전하로 점 표시 강도 결정
    aac = min(1, abs(r_qac[k] - r_qac[kb]) / 4e-7)
    adc = min(1, abs(r_qdc[k] - r_qdc[kb]) / 4e-7)
    aled = min(1, abs(r_qled[k] - r_qled[kb]) / 2e-6)
    last_on = max([e for e in led_events if e <= ts], default=-9)
    led_glow = max(1.0 if led else 0.0, math.exp(-(ts - last_on) / 0.35) if ts >= last_on else 0)
    led_cnt = sum(1 for e in led_events if e <= ts)
    disk_glow = min(1, abs(r_qac[k] - r_qac[max(0, k - 60)]) / 3e-6) + min(0.4, abs(vp) / 12)

    img = BG.copy(); c = C(img)
    draw_header(c, ts)
    c.rect(30, 180, 1050, 800, fill=PANEL, outline=BORDER, w=2, r=18)
    c.text(52, 196, "① 발판 단면", font(30, "b"), TXT)
    c.text(52, 240, "(변형은 과장하여 표시)", font(20), DIM)
    draw_floor(c)
    g = draw_tile(c, 0, disp, 0, disk_glow, vp)
    draw_foot(c, g["plate_top"] - lift)
    c.rect(770, 196, 1032, 300, fill=(12, 16, 26), outline=(60, 70, 96), w=2, r=12)
    c.text(786, 226, "하중 F", font(22), DIM, "lm")
    c.text(1018, 226, f"{Fn:4.0f} N", font(30, "m"), ORG, "rm")
    c.text(786, 270, "전하 Q", font(22), DIM, "lm")
    c.text(1018, 270, f"{D_EFF*Fn*1e6:4.1f} µC", font(30, "m"), YEL, "rm")
    if Fn > 40:
        ay = g["plate_top"] - lift - 120
        c.line([(760, ay - 60), (760, ay + 40)], ORG, 7)
        c.poly([(744, ay + 36), (776, ay + 36), (760, ay + 62)], fill=ORG)
    c.text(1030, 772, "전하 → ② 회로", font(22, "b"), YEL, "rm")
    draw_circuit(c, vp, vs, led, led, led_glow, (r_qac[k], r_qdc[k], r_qled[k], aac, adc, aled))
    draw_graph(c, ts)
    draw_stats(c, ts, k, led_cnt)
    img = img.reduce(S)
    if ts < 0.35: img = Image.blend(Image.new("RGB", img.size), img, ease(ts / 0.35))
    return img

def frame_outro(t, last):
    dark = Image.blend(last, Image.new("RGB", last.size, (6, 8, 14)), 0.92 * ease(t / 0.6))
    img = dark.resize((W * S, H * S), Image.BILINEAR); c = C(img)
    n_led = len(led_events)
    day = 50000 * E_per_step
    rows = [
        ("시뮬레이션 결과", f"{T_SIM:.0f}초 · {n_steps}걸음", TXT, 56),
        ("한 번 밟을 때 발생 전하", f"{D_EFF*BODY_F*1e6:.1f} µC  (개방전압 {D_EFF*BODY_F/CP:.0f} V)", YEL, 40),
        ("이론상 최대 에너지 / 걸음", f"{E_ideal_step*1e6:.0f} µJ", TXT, 40),
        ("실제 저장·사용 에너지 / 걸음", f"{E_per_step*1e6:.0f} µJ  (효율 {E_per_step/E_ideal_step*100:.0f}%)", GRN, 40),
        ("LED 점등", f"{n_led}회  (1회당 약 {0.5*CS*(V_ON**2-V_OFF**2)*1e6:.0f} µJ)", RED, 40),
        ("하루 5만 걸음 통로라면", f"{day:.1f} J  (약 {day/3.6:.1f} mWh)", CYAN, 40),
    ]
    y = 330
    for i, (lab, val, col, fs) in enumerate(rows):
        u = ease((t - 0.5 - i * 0.55) / 0.5)
        if u <= 0: break
        if i == 0:
            c.text(540, y, lab, font(64, "b"), mix(BG0, TXT, u), "mm")
            c.text(540, y + 80, val, font(36), mix(BG0, DIM, u), "mm")
            y += 210; continue
        c.rect(70, y - 10, 1010, y + 140, fill=(22, 28, 44, int(230 * u)), outline=BORDER + (int(255 * u),), w=2, r=18)
        c.text(100, y + 30, lab, font(28), mix(BG0, DIM, u), "lm")
        c.text(100 + (1 - u) * 30, y + 92, val, font(fs, "b"), mix(BG0, col, u), "lm")
        y += 170
    u = ease((t - 4.2) / 0.6)
    if u > 0:
        c.text(540, 1500, "→ 압전 발판은 큰 전력보다", font(38, "b"), mix(BG0, TXT, u), "mm")
        c.text(540, 1560, "센서·무선 IoT 같은 초저전력 장치에 적합", font(38, "b"), mix(BG0, YEL, u), "mm")
        c.text(540, 1680, f"모델: Q = d·F,  Cp = 40 nF × 8,  다이오드 {VD} V,  C = 47 µF", font(22), mix(BG0, DIM, u), "mm")
        c.text(540, 1720, "d_eff = 11 nC/N (굽힘 모드 디스크 유효값, 가정)", font(22), mix(BG0, DIM, u), "mm")
    return img.reduce(S)

# ───────────────────────── 6. 오디오 ─────────────────────────
def make_audio(path):
    sr = 44100; total = T_INTRO + T_SIM + T_OUT
    a = np.zeros(int(sr * total))
    def add(t0, sig):
        i0 = int(t0 * sr); j = min(len(a), i0 + len(sig)); a[i0:j] += sig[: j - i0]
    tt_ = np.arange(int(0.25 * sr)) / sr
    thump = (np.sin(2 * np.pi * 70 * tt_) * 0.7 + rng.standard_normal(len(tt_)) * 0.12) * np.exp(-tt_ * 22)
    tt2 = np.arange(int(0.6 * sr)) / sr
    ding = (np.sin(2 * np.pi * 1320 * tt2) + 0.5 * np.sin(2 * np.pi * 1980 * tt2)) * np.exp(-tt2 * 6) * 0.25
    for s0, _ in steps: add(T_INTRO + s0, thump * 0.8)
    for e in led_events: add(T_INTRO + e, ding)
    a = np.clip(a, -1, 1)
    pcm = (a * 26000).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

# ───────────────────────── 7. 렌더링 ─────────────────────────
def main():
    wav = os.path.join(HERE, "_audio_tmp.wav")
    make_audio(wav)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", OUT_MP4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nf_i, nf_s, nf_o = int(T_INTRO * FPS), int(T_SIM * FPS), int(T_OUT * FPS)
    last = None
    for f in range(nf_i):
        p.stdin.write(frame_intro(f / FPS).tobytes())
    for f in range(nf_s):
        last = frame_sim(f / FPS); p.stdin.write(last.tobytes())
        if f % 150 == 0: print(f"sim frame {f}/{nf_s}", flush=True)
    for f in range(nf_o):
        p.stdin.write(frame_outro(f / FPS, last).tobytes())
    p.stdin.close(); p.wait()
    os.remove(wav)
    print("saved:", OUT_MP4)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        frame_intro(3.0).save(os.path.join(HERE, "_prev_intro.png"))
        for ts in (5.32, 10.0):
            frame_sim(ts).save(os.path.join(HERE, f"_prev_sim_{ts:.0f}.png"))
        frame_outro(6.5, frame_sim(T_SIM - 0.05)).save(os.path.join(HERE, "_prev_outro.png"))
    else:
        main()
