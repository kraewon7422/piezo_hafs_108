# analyze_v2.py  (2026-09-18)
# v2: 4차시에 철회한 항목을 분석 코드에서도 걷어낸 판.
#   - 추정 힘 F = Q/d33, 최적 부하 R_opt 계산 삭제 (근거: README §2-3, §2-4)
#   - 공진 검출: FFT 최대가 탐색 하한(500 Hz) 바로 첫 칸이면 "미검출"로 본다 (event 13)
#   - 감쇠 시정수 τ·기계적 Q 삭제: v1은 최대점 뒤 약 1주기(0.38 ms)만 맞춰
#     포락선 감쇠가 아니라 진동 한 번을 잰 값이었다 (README §2-2)
#   - 공진 교차 확인: 파형 봉우리 간격으로 주파수를 한 번 더 잰다
#   - 그림 2: '걸음 2 Hz' 선을 빼고 선형 축으로 공진 봉우리를 보여 준다
#   - 그림 4: 0.15 V 초과 구간을 한 번씩만 세고, 폭으로 '누름'과 '짧은 흔들림'을 나눈다
#     (v1은 11개 구간을 모두 두드림으로 세고 80 ms 창이 겹쳐 같은 봉우리를 두 번 셌다)
# v1(analyze_v1.py)은 기록으로 남겨 둔다.

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ---- 한글 폰트 ----
for name in ["Noto Sans CJK JP", "Malgun Gothic", "NanumGothic"]:
    if any(f.name == name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break
plt.rcParams["axes.unicode_minus"] = False

CSV = "data/piezo_capture_data-1.csv"
OUT = "figures"
VREF, ADC_MAX, BASELINE = 5.0, 1023, 9
DT = 16.008e-6          # 스케치가 실측한 샘플 간격
FMIN = 500              # 이보다 낮은 칸은 측정창 길이(9.6 ms)가 만드는 성분이라 제외
PRESS_MS = 30           # 연속 모드에서 이 폭 이상 0.15 V를 넘으면 '누름'으로 본다


def load(path):
    """CSV를 읽고 중간에 끼어든 헤더 줄을 걷어낸다."""
    df = pd.read_csv(path, comment="#")
    df = df[df["event"] != "event"]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().astype({"event": int, "n": int, "adc_raw": int}).reset_index(drop=True)


def dominant_freq(v, dt, fmin=FMIN):
    """FFT로 FMIN 위에서 가장 센 주파수를 찾는다.
    그 최대가 탐색 구간의 첫 칸이면 봉우리가 아니라 저주파 성분의 꼬리이므로 None."""
    spec = np.abs(np.fft.rfft(v - v.mean()))
    freq = np.fft.rfftfreq(len(v), dt)
    band = freq > fmin
    i = int(np.argmax(spec[band]))
    f = None if i == 0 else freq[band][i]
    return f, freq, spec


def crest_freq(t, v, f_guess, vmin=0.2):
    """0.2 V 넘는 파형 봉우리들의 간격 중앙값으로 주파수를 다시 잰다 (FFT와 독립)."""
    lm = [i for i in range(1, len(v) - 1) if v[i] > v[i - 1] and v[i] >= v[i + 1] and v[i] > vmin]
    crests, gap = [], 0.5 / f_guess          # 반주기보다 가까운 봉우리는 같은 봉우리로 본다
    for i in lm:
        if crests and t[i] - t[crests[-1]] < gap:
            if v[i] > v[crests[-1]]:
                crests[-1] = i
        else:
            crests.append(i)
    return 1 / np.median(np.diff(t[crests])), len(crests)


def analyze_event(df, ev):
    s = df[df.event == ev].sort_values("n").reset_index(drop=True)
    v, t, adc = s.v_piezo.values, s.t_us.values * 1e-6, s.adc_raw.values
    dv = np.diff(v) / np.diff(t)
    f_res, _, _ = dominant_freq(v, DT)
    f_crest, n_crest = crest_freq(t, v, f_res) if f_res else (None, 0)
    return {
        "event": ev, "n": len(s),
        "V_peak": v.max(), "V_min": v.min(),
        "clip_pct": (adc == 0).mean() * 100,
        "dVdt_max": dv.max(),
        "f_res_fft": f_res, "f_res_crest": f_crest, "n_crest": n_crest,
        "t": t, "v": v,
    }


def derived_table(V_peak, dVdt):
    """정전용량을 모르므로 가정값별로 유도량을 표로 만든다."""
    rows = []
    for C in [10e-9, 15e-9, 20e-9, 30e-9]:
        rows.append({
            "C_p (nF)": C * 1e9,
            "전하 Q (nC)": C * V_peak * 1e9,
            "에너지 E (nJ)": 0.5 * C * V_peak ** 2 * 1e9,
            "변위전류 i (µA)": C * dVdt * 1e6,
        })
    return pd.DataFrame(rows)


def fmt_hz(f):
    return "미검출" if f is None else f"{f:,.0f} Hz"


def main():
    os.makedirs(OUT, exist_ok=True)
    df = load(CSV)
    evs = [e for e in sorted(df.event.unique()) if e != 0]
    res = [analyze_event(df, e) for e in evs]
    df_hz = 1 / (res[0]["n"] * DT)

    print("=== 이벤트 요약 ===")
    print(f"FFT 칸 간격 = 1/(N·dt) = {df_hz:.1f} Hz")
    for r in res:
        crest = "" if r["f_res_crest"] is None else \
            f"  (봉우리 {r['n_crest']}개 간격으로 {r['f_res_crest']:,.0f} Hz)"
        print(f"event {r['event']}: V_peak {r['V_peak']:.3f} V  V_min {r['V_min']:+.3f} V  "
              f"클리핑 {r['clip_pct']:.1f} %  dV/dt_max {r['dVdt_max']:,.0f} V/s  "
              f"공진 {fmt_hz(r['f_res_fft'])}{crest}")

    best = max(res, key=lambda r: r["V_peak"])
    print("\n=== 유도량 (최대 이벤트 기준) ===")
    print(derived_table(best["V_peak"], best["dVdt_max"]).to_string(index=False,
          float_format=lambda x: f"{x:.2f}"))

    # 그림 1 — 트리거 파형
    fig, axes = plt.subplots(1, len(res), figsize=(5.5 * len(res), 3.6))
    axes = np.atleast_1d(axes)
    for ax, r in zip(axes, res):
        ax.plot(r["t"] * 1e3, r["v"], lw=0.9, color="#c05621")
        ax.axhline(0, color="0.6", lw=0.7)
        ax.axhline(-BASELINE * VREF / ADC_MAX, color="crimson", ls="--", lw=0.8,
                   label=f"측정 하한 (-{BASELINE*VREF/ADC_MAX:.3f} V)")
        ax.set_title(f"event {r['event']}  ·  peak {r['V_peak']:.3f} V  ·  클리핑 {r['clip_pct']:.1f}%")
        ax.set_xlabel("시간 (ms)"); ax.set_ylabel("전압 (V)")
        ax.legend(fontsize=8); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(f"{OUT}/fig1_waveform.png", dpi=150); plt.close(fig)

    # 그림 2 — 주파수 스펙트럼 (선형 축)
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.axvspan(0, FMIN, color="0.85", label=f"{FMIN} Hz 미만 제외 (측정창 성분)")
    for r, col in zip(res, ["#2b6cb0", "#c05621"]):
        _, freq, spec = dominant_freq(r["v"], DT)
        ax.plot(freq[1:], spec[1:] / spec[1:].max(), lw=1.0, color=col, marker=".", ms=3,
                label=f"event {r['event']} — 공진 {fmt_hz(r['f_res_fft'])}")
    ax.axvline(best["f_res_fft"], color="crimson", ls="--", lw=1.0)
    ax.set_xlim(0, 8000)
    ax.set_xlabel("주파수 (Hz)"); ax.set_ylabel("정규화 크기")
    ax.set_title(f"주파수 스펙트럼 (FFT, 칸 간격 {df_hz:.0f} Hz)")
    ax.legend(fontsize=8); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(f"{OUT}/fig2_spectrum.png", dpi=150); plt.close(fig)

    # 그림 3 — 연속 모드 두드림 열
    c = df[df.event == 0].sort_values("n").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.plot(c.n.values / 1000, c.v_piezo.values, lw=0.7, color="#1a7a4a")
    ax.axhline(0.15, color="crimson", ls="--", lw=0.8, label="검출 임계 0.15 V")
    ax.set_xlabel("시간 (초)"); ax.set_ylabel("전압 (V)")
    ax.set_title(f"연속 모드 1 kHz — {len(c)/1000:.2f}초, 클리핑 {(c.adc_raw==0).mean()*100:.1f}%")
    ax.legend(fontsize=8); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(f"{OUT}/fig3_continuous.png", dpi=150); plt.close(fig)

    # 그림 4 — 두드림 세기 산포
    # 0.15 V를 넘은 구간을 하나씩 따로 센다 (v1은 80 ms 창이 겹쳐 같은 봉우리를 두 번 셌다).
    # 30 ms 이상 이어진 구간 = 누름, 그보다 짧은 구간 = 누름 직후의 흔들림·약한 접촉.
    v = c.v_piezo.values
    above = np.r_[False, v > 0.15, False]
    edges = np.flatnonzero(np.diff(above.astype(int)))
    runs = [(a, b) for a, b in zip(edges[::2], edges[1::2])]          # [a, b) 1 ms 단위
    width = np.array([b - a for a, b in runs])
    peaks = np.array([v[a:b].max() for a, b in runs])
    press = width >= PRESS_MS
    pp = peaks[press]
    print(f"\n=== 연속 모드 재현성 ===\n0.15 V 초과 구간 {len(runs)}개: 누름 {press.sum()}개 "
          f"(폭 {width[press].min()}–{width[press].max()} ms), 짧은 구간 {(~press).sum()}개 "
          f"(폭 {width[~press].min()}–{width[~press].max()} ms, 피크 {peaks[~press].min():.3f}–{peaks[~press].max():.3f} V)")
    print(f"누름만: 피크 {', '.join(f'{p:.3f}' for p in pp)} V  평균 {pp.mean():.3f} V  "
          f"표준편차 {pp.std():.3f} V  CV {pp.std()/pp.mean()*100:.1f} %")
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    x = np.arange(1, len(runs) + 1)
    ax.bar(x[press], peaks[press], color="#c05621", label=f"누름 (≥{PRESS_MS} ms)")
    ax.bar(x[~press], peaks[~press], color="0.65", label=f"짧은 흔들림·접촉 (<{PRESS_MS} ms)")
    for xi, p, w in zip(x, peaks, width):
        ax.text(xi, p + 0.02, f"{w}ms", ha="center", fontsize=7)
    ax.axhline(pp.mean(), color="0.3", ls="--", lw=0.9,
               label=f"누름 평균 {pp.mean():.2f} V (CV {pp.std()/pp.mean()*100:.0f}%)")
    ax.set_xlabel("0.15 V 초과 구간 번호"); ax.set_ylabel("피크 전압 (V)")
    ax.set_title("연속 모드 — 누름과 짧은 흔들림 구분")
    ax.legend(fontsize=8); ax.grid(alpha=0.25, axis="y")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig4_repeatability.png", dpi=150); plt.close(fig)

    print(f"\n그래프 4장 저장 완료 -> {OUT}/")


if __name__ == "__main__":
    main()
