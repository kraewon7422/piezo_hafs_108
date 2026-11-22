# -*- coding: utf-8 -*-
"""
압전 발판 GUI — 젯슨 오린 나노(우분투) 버전 v1

piezo_gui_v1.py 의 화면 A~D 를 그대로 쓰고, 젯슨 키트 기능을 더함
  ① 카메라 AI 사람 수 세기   ② 발판·카메라·초음파 사람 수 비교(화면 E)
  ③ 키트 LCD·숫자 표시기·LED  ④ 상시 측정(온습도와 사람 수를 10초마다 CSV 기록)
카메라가 켜져 있으면 모든 화면 맨 위에 "개인 프라이버시를 위해 영상은 저장하지 않습니다!" 를 띄움.

실행 (젯슨):  ./run_jetson.sh                  아두이노 실시간 + 키트 장치 (전체화면)
              ./run_jetson.sh --replay 파일.txt  저장된 측정 재생
옵션: --port /dev/ttyUSB0  --windowed  --no-camera  --no-ultra  --no-i2c
      --sim  (젯슨·카메라 없이 화면 시험: 가짜 카메라·초음파 숫자. 발표 데이터로 쓰면 안 됨)
      --snapshot 폴더 --until 초  (검증용: 재생 파일로 화면 A~E 를 PNG 저장)

필요한 폴더 구조 (arduino 폴더를 통째로 복사):  arduino/piezo_main  arduino/piezo_gui  arduino/piezo_jetson
"""
import os, sys, time, csv, queue, argparse, datetime, subprocess, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "piezo_gui")))
import piezo_gui_v1 as G   # noqa: E402  (화면 A~D, 데이터 처리, 시리얼·재생 — 그대로 재사용)
import jetson_hw as HW     # noqa: E402

W, H = G.W, G.H
BANNER_H = 46                   # 프라이버시 안내 띠 높이 (기준 좌표)
PRIVACY_TEXT = "개인 프라이버시를 위해 영상은 저장하지 않습니다!"
YEL, CYAN, GRN, ORG, RED, TXT, DIM, INK = G.YEL, G.CYAN, G.GRN, G.ORG, G.RED, G.TXT, G.DIM, G.INK


def setup_fonts():
    """우분투에는 맑은 고딕이 없으므로 Noto Sans CJK(또는 나눔고딕)로 바꿈"""
    if os.path.exists(G.FONT_R):
        return "맑은 고딕"
    cands = [("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
             ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")]
    cands += [(p, p.replace("Regular", "Bold")) for p in glob.glob("/usr/share/fonts/**/NotoSansCJK*-Regular.tt*", recursive=True)]
    for r, b in cands:
        if os.path.exists(r):
            G.FONT_R, G.FONT_B = r, (b if os.path.exists(b) else r)
            return os.path.basename(r)
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK KR"], capture_output=True, text=True).stdout
        if r and os.path.exists(r):
            G.FONT_R = G.FONT_B = r
            return os.path.basename(r)
    except OSError:
        pass
    raise SystemExit("한글 글꼴이 없습니다. setup_jetson.sh 를 먼저 실행하세요 (fonts-noto-cjk 설치).")


# ───────────────────────── 화면 ─────────────────────────
class JetsonUI(G.UI):
    NAMES = ["A 실시간 측정", "B 설계 vs 측정", "C 확장하면?", "D 개선하면?", "E 사람 수 비교"]

    def __init__(self, pg, hw):
        self.hw = hw
        self.banner_h = BANNER_H if hw.camera_enabled else 0
        self.series = []            # (경과 초, 발판, 카메라, 초음파)
        self.t_start = time.time()
        super().__init__(pg)

    def set_scale(self, k):
        changed = self.k is None or abs(k - self.k) > 1e-6
        super().set_scale(k)
        if changed:
            pg = self.pg
            self.F = pg.Surface((max(1, round(W * k)), max(1, round((H + self.banner_h) * k))))
            self.BN = pg.Surface((max(1, round(W * k)), max(1, round(max(1, self.banner_h) * k))))

    def footer(self, src):
        keys = "Tab 화면 전환 · F11 전체화면 · F12 화면 저장 · R 기록 초기화 · Esc 종료"
        keys += " · Z 기준선 다시" if src.live else " · Space 일시정지 · 1/2/4/8 속도"
        if self.screen == 3:
            keys = "↑↓ 항목 · ←→ 값 바꾸기 · " + keys
        self.text(keys, 18, DIM, (1890, 1068), "rb")
        x = 30
        for i, n in enumerate(self.NAMES):
            on = i == self.screen
            w = self.measure(n, 18, True) + 24
            self.D.rect(self.S, (40, 52, 80) if on else (22, 28, 44), (x, 1042, w, 30), border_radius=8)
            self.text(n, 18, TXT if on else DIM, (x + w / 2, 1057), "mm", bold=on)
            x += w + 8

    def record(self, st):
        t = time.time() - self.t_start
        if not self.series or t - self.series[-1][0] >= 1.0:
            cam = self.hw.camera.count if self.hw.camera.ok else None
            us = self.hw.ultra.count if self.hw.ultra.ok else None
            self.series.append((t, st.people(), cam, us))
            self.series = self.series[-3600:]

    def draw(self, st, src, now):
        if self.screen == 4:
            self.draw_compare(st, src, now)
        else:
            [self.draw_live, self.draw_theory, self.draw_scale, self.draw_improve][self.screen](st, src, now)
        if not self.banner_h:
            return self.S
        base = self.S
        self.S = self.BN                                   # 띠는 별도 표면에 그림
        self.S.fill((92, 62, 8))
        self.D.rect(self.S, YEL, (0, self.banner_h - 3, W, 3))
        on = self.hw.camera.ok
        self.text("● 카메라 작동 중" if on else "○ 카메라 연결 안 됨", 22, (255, 120, 90) if on else (200, 180, 150),
                  (40, self.banner_h / 2 - 1), "lm", bold=True)
        self.text(PRIVACY_TEXT, 26, (255, 230, 150), (W / 2, self.banner_h / 2 - 1), "mm", bold=True)
        self.text("사람 수만 기록", 20, (255, 210, 140), (1890, self.banner_h / 2 - 1), "rm")
        self.S = base
        self.F.blit(self.BN, (0, 0))
        self.F.blit(base, (0, round(self.banner_h * self.k)))
        return self.F

    # ═════ 화면 E: 사람 수 비교 ═════
    def draw_compare(self, st, src, now):
        S, pg, hw = self.S, self.pg, self.hw
        S.blit(self.bg, (0, 0))
        self.header(st, src, now, "사람 수 비교 — 압전 발판 vs 카메라 AI vs 초음파",
                    "같은 시간 동안 세 가지 방법으로 센 인원 · 카메라 영상은 저장하지 않고 사람 수만 기록")
        # ── 카메라 미리보기 (모자이크)
        self.panel(30, 130, 990, 805, "① 카메라 AI", "모자이크 미리보기 · 선을 넘으면 1명")
        px0, py0, pw, ph = 52, 186, 916, 515
        self.D.rect(S, INK, (px0, py0, pw, ph))
        prev, boxes = hw.camera.snapshot() if hw.camera_enabled else (None, [])
        if prev is not None:
            surf = pg.image.frombuffer(prev.tobytes(), (prev.shape[1], prev.shape[0]), "RGB")
            surf = pg.transform.scale(surf, (round(pw * self.k), round(ph * self.k)))
            S.blit(surf, (round(px0 * self.k), round(py0 * self.k)))
            axis, pos = hw.cfg["line_axis"], hw.cfg["line_pos"]
            if axis == "y":
                self.D.line(S, YEL, (px0, py0 + ph * pos), (px0 + pw, py0 + ph * pos), 3)
            else:
                self.D.line(S, YEL, (px0 + pw * pos, py0), (px0 + pw * pos, py0 + ph), 3)
            for x1, y1, x2, y2 in boxes:
                self.D.rect(S, CYAN, (px0 + pw * x1, py0 + ph * y1, pw * (x2 - x1), ph * (y2 - y1)), 3)
            self.D.rect(S, (20, 24, 36), (px0 + 12, py0 + 12, 330, 40), border_radius=8)
            self.text("영상 저장 안 함 · 모자이크", 20, YEL, (px0 + 26, py0 + 32), "lm", bold=True)
        else:
            self.text(hw.camera.status if hw.camera_enabled else "카메라 꺼짐", 26, DIM,
                      (px0 + pw / 2, py0 + ph / 2), "mm")
        cs = hw.camera.status + (f" · {hw.camera.fps:.0f} fps" if hw.camera.ok and hw.camera.fps else "")
        self.text(cs, 19, DIM, (52, 716))
        self.text("사람이 노란 선을 넘어가면 1명으로 셉니다 (선 위치·방향은 jetson_hw.py 의 CONFIG)", 17, DIM, (52, 748))

        # ── 세 가지 숫자
        self.panel(1010, 130, 1890, 805, "② 같은 시간 동안 센 사람 수")
        tile = st.people()
        items = [("압전 발판", tile, YEL, True, "펄스 1초 안 묶음 = 1명 (전기도 만듦)"),
                 ("카메라 AI", hw.camera.count, CYAN, hw.camera.ok, hw.camera.status),
                 ("초음파 센서", hw.ultra.count, GRN, hw.ultra.ok, hw.ultra.status)]
        for i, (lab, n, col, ok, sub) in enumerate(items):
            y = 186 + i * 132
            self.D.rect(S, INK, (1032, y, 836, 118), border_radius=14)
            self.D.rect(S, col if ok else (60, 70, 96), (1032, y, 836, 118), 2, border_radius=14)
            self.text(lab, 26, col, (1056, y + 16), bold=True)
            self.text(sub, 17, DIM, (1056, y + 80))
            if ok:
                rm = self.text("명", 26, col, (1844, y + 92), "rb")
                self.text(f"{n}", 64, col, (rm.left - 8, y + 104), "rb", bold=True)
            else:
                self.text("없음", 40, DIM, (1840, y + 60), "rm", bold=True)
        ref = hw.camera.count if hw.camera.ok and hw.camera.count > 0 else None
        y = 596
        self.text("카메라 AI 를 기준(100 %)으로 본 비율", 20, DIM, (1032, y))
        for j, (lab, n, col, ok) in enumerate([("압전 발판", tile, YEL, True), ("초음파", hw.ultra.count, GRN, hw.ultra.ok)]):
            yy = y + 40 + j * 66
            self.text(lab, 22, col, (1032, yy + 13), "lm", bold=True)
            bx0, bw = 1180, 480
            self.D.rect(S, INK, (bx0, yy, bw, 26), border_radius=6)
            self.D.line(S, DIM, (bx0 + bw / 1.5, yy - 4), (bx0 + bw / 1.5, yy + 30), 1)   # 100 % 눈금 (막대 끝 = 150 %)
            if ref and ok:
                r = n / ref
                self.D.rect(S, col, (bx0, yy, max(3, bw * min(1.0, r / 1.5)), 26), border_radius=6)
                self.text(f"{r*100:.0f} %", 24, TXT, (1868, yy + 13), "rm", bold=True)
            else:
                self.text("—", 24, DIM, (1868, yy + 13), "rm", bold=True)
        self.text("세로 눈금 = 100 % (카메라와 같음) · 막대 끝 = 150 %", 16, DIM, (1032, 770))

        # ── 누적 그래프
        self.panel(30, 822, 1250, 1032, "③ 시간에 따른 누적 인원")
        gx0, gx1, gy0, gy1 = 70, 1230, 880, 1010
        self.D.rect(S, INK, (gx0, gy0, gx1 - gx0, gy1 - gy0))
        ser = self.series
        if len(ser) > 1:
            t_end = max(1.0, ser[-1][0])
            top = max(1, max(max(v for v in s[1:] if v is not None) for s in ser))
            for idx, col in ((1, YEL), (2, CYAN), (3, GRN)):
                pts = [(gx0 + (gx1 - gx0) * s[0] / t_end, gy1 - (gy1 - gy0 - 6) * s[idx] / top)
                       for s in ser if s[idx] is not None]
                if len(pts) > 1:
                    self.D.lines(S, col, False, pts, 3)
            self.text(f"{int(t_end//60)}분 {int(t_end%60)}초", 15, DIM, (gx1, gy1 + 2), "ra")
            self.text(f"최대 {top}명", 15, DIM, (gx0 + 6, gy0 + 4))
        else:
            self.text("기록이 쌓이면 그래프가 그려집니다", 20, DIM, ((gx0 + gx1) / 2, (gy0 + gy1) / 2), "mm")
        # ── 방법 비교 + 환경
        self.panel(1270, 822, 1890, 1032, "④ 방법별 특징")
        rows = [("압전 발판", YEL, "전기 생산 O · 카메라 없음 · 반복 밟기 오차"),
                ("초음파", GRN, "싸고 단순 · 여러 명 동시 통과 오차"),
                ("카메라 AI", CYAN, "가장 정확 · 개인정보 주의")]
        for i, (lab, col, d) in enumerate(rows):
            self.text(lab, 19, col, (1292, 878 + i * 34), bold=True)
            self.text(d, 17, TXT, (1410, 880 + i * 34))
        o = hw.out
        env = f"온도 {o.temp:.1f} °C · 습도 {o.hum:.0f} %" if o.temp is not None else "온습도 센서 없음"
        self.text(env, 17, DIM, (1292, 990))
        self.footer(src)


# ───────────────────────── 기록 (④ 상시 측정) ─────────────────────────
class CountLog:
    """10초마다 사람 수·에너지·온습도를 CSV 로 (측정 폴더 안 jetson_counts.csv)"""

    def __init__(self, folder):
        self.path = os.path.join(folder, "jetson_counts.csv") if folder else None
        self.last = 0.0
        if self.path:
            with open(self.path, "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(["pc_time", "tile_people", "camera_people", "ultrasonic_people",
                                        "total_E_uJ", "temp_C", "humidity_pct"])

    def tick(self, st, hw, force=False):
        if not self.path or (not force and time.time() - self.last < 10):
            return
        self.last = time.time()
        o = hw.out
        with open(self.path, "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow([datetime.datetime.now().isoformat(timespec="seconds"), st.people(),
                                    hw.camera.count if hw.camera.ok else "", hw.ultra.count if hw.ultra.ok else "",
                                    round(st.total_E, 4), "" if o.temp is None else round(o.temp, 1),
                                    "" if o.hum is None else round(o.hum, 1)])


# ───────────────────────── 실행 ─────────────────────────
def fit_scale(pg, ui):
    ww, wh = pg.display.get_surface().get_size()
    return min(ww / W, wh / (H + ui.banner_h))


def snapshot(args):
    """검증용: 재생 파일을 --until 초까지 읽고 화면 A~E 를 PNG 로 저장 (가짜 하드웨어)"""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame as pg
    pg.init()
    pg.display.set_mode((1, 1))
    setup_fonts()
    hw = HW.Hardware(sim=True)
    st, ui = G.State(), None
    ui = JetsonUI(pg, hw)

    class Src:
        live, ok, folder = False, True, os.path.dirname(os.path.abspath(args.replay))
        status = "재생 1× · " + os.path.basename(folder)
    last_upd = None
    with open(args.replay, encoding="utf-8", errors="ignore") as f:
        for line in f:
            kind, v = G.logger.parse_line(line)
            if kind is None:
                continue
            st.feed(kind, v)
            if kind == "R" and st.last_t is not None:
                if last_upd is None or st.last_t - last_upd >= 25:
                    st.update(st.last_t)
                    last_upd = st.last_t
                    hw.tick(st)
                    if not ui.series or st.last_t / 1000 - ui.series[-1][0] >= 1:
                        ui.series.append((st.last_t / 1000, st.people(), hw.camera.count, hw.ultra.count))
                if int(v[0]) >= args.until * 1000:
                    break
    now = st.last_t or 0
    st.update(now)
    hw.tick(st)
    ui.enter_wall = time.time() - 10
    os.makedirs(args.snapshot, exist_ok=True)
    for i, name in enumerate(("A_live", "B_theory", "C_scale", "D_improve", "E_compare")):
        ui.screen = i
        for wpx, hpx in ((1920, 1080 + BANNER_H), (1280, 800)):      # 1280×800 = 11인치 모니터 예시
            ui.set_scale(min(wpx / W, hpx / (H + ui.banner_h)))
            c = ui.draw(st, Src, now)
            p = os.path.join(args.snapshot, f"{name}_{wpx}.png")
            pg.image.save(c, p)
        print("saved", p)
    print(f"people={st.people()} camera(sim)={hw.camera.count} ultra(sim)={hw.ultra.count}")


def main():
    ap = argparse.ArgumentParser(description="압전 발판 GUI — 젯슨 버전")
    ap.add_argument("--port")
    ap.add_argument("--replay")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--no-camera", action="store_true")
    ap.add_argument("--no-ultra", action="store_true")
    ap.add_argument("--no-i2c", action="store_true")
    ap.add_argument("--sim", action="store_true", help="가짜 카메라·초음파 (화면 시험용)")
    ap.add_argument("--snapshot")
    ap.add_argument("--until", type=float, default=30)
    args = ap.parse_args()
    if args.snapshot:
        return snapshot(args)
    import pygame as pg
    font = setup_fonts()
    pg.init()
    pg.display.set_caption("압전 발판 — 젯슨")
    fullscreen = not args.windowed
    pg.display.set_mode((0, 0), pg.FULLSCREEN) if fullscreen else pg.display.set_mode((1280, 800), pg.RESIZABLE)
    pg.mouse.set_visible(not fullscreen)
    q = queue.Queue()
    src = G.ReplaySource(q, args.replay, args.speed) if args.replay else G.SerialSource(q, args.port)
    hw = HW.Hardware(sim=args.sim, camera=not args.no_camera, ultrasonic=not args.no_ultra, i2c=not args.no_i2c)
    src.start()
    hw.start()
    st, ui = G.State(), JetsonUI(pg, hw)
    st.rate = args.speed if args.replay else 1.0
    log = None
    print(f"글꼴: {font} · 카메라: {'켜짐' if hw.camera_enabled else '꺼짐'}")
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
                        running = False
                    elif k == pg.K_TAB:
                        ui.screen = (ui.screen + (-1 if ev.mod & pg.KMOD_SHIFT else 1)) % len(ui.NAMES)
                        ui.enter_wall = time.time()
                    elif k == pg.K_F11:
                        fullscreen = not fullscreen
                        pg.display.set_mode((0, 0), pg.FULLSCREEN) if fullscreen else pg.display.set_mode((1280, 800), pg.RESIZABLE)
                        pg.mouse.set_visible(not fullscreen)
                    elif k == pg.K_F12:
                        p = os.path.join(HERE, datetime.datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png"))
                        pg.image.save(pg.display.get_surface(), p)
                        print("화면 저장:", p)
                    elif k == pg.K_r:
                        st.reset_stats()
                        hw.reset_counts()
                        ui.series, ui.t_start = [], time.time()
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
                        ui.lever_sel = (ui.lever_sel + (1 if k == pg.K_DOWN else -1)) % len(G.LEVERS)
                    elif ui.screen == 3 and k in (pg.K_LEFT, pg.K_RIGHT):
                        n = len(G.LEVERS[ui.lever_sel][2])
                        i = ui.lever_idx[ui.lever_sel] + (1 if k == pg.K_RIGHT else -1)
                        ui.lever_idx[ui.lever_sel] = max(0, min(n - 1, i))
            t_end = time.time() + 0.012
            while time.time() < t_end:
                try:
                    kind, v = q.get_nowait()
                except queue.Empty:
                    break
                st.feed(kind, v)
            now = st.now()
            st.update(now)
            hw.tick(st)
            ui.record(st)
            if log is None and src.live and src.folder:
                log = CountLog(src.folder)                 # 측정 폴더가 생기면 기록 시작
            if log:
                log.tick(st, hw)
            ui.set_scale(fit_scale(pg, ui))
            G.present(pg, ui.draw(st, src, now))
            clock.tick(30)
    finally:
        if log:
            log.tick(st, hw, force=True)
        hw.stop()
        src.stop()
        src.join(timeout=2)
        pg.quit()
        hung = [t.name for t in __import__("threading").enumerate() if t.daemon and t.is_alive()
                and t is not src and not t.name.startswith(("Dummy", "pydevd"))]
    print(f"\n사람 수 — 발판 {st.people()}명, 카메라 {hw.camera.count if hw.camera.ok else '없음'}, "
          f"초음파 {hw.ultra.count if hw.ultra.ok else '없음'}")
    if src.live and src.folder and os.path.exists(os.path.join(src.folder, "pulses.csv")):
        print("저장 폴더:", src.folder)
        subprocess.run([sys.executable, os.path.join(G.MAIN_DIR, "analyze.py"), src.folder])
    if hung:                                  # 카메라·CUDA 스레드가 안 끝나면 강제로 종료 (저장 파일은 이미 닫힘)
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
