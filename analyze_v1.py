# analyze_v1.py  (2026-09-11)
# v1: 압전소자 직결 측정 CSV -> 파형/공진/유도량 분석 + 그래프 4종

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ---- 한글 폰트 ----
for name in ["Noto Sans CJK JP", "NanumGothic", "Malgun Gothic"]:
    if any(f.name == name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break
plt.rcParams["axes.unicode_minus"] = False

CSV = "data/piezo_capture_data-1.csv"
OUT = "figures"
VREF, ADC_MAX, BASELINE = 5.0, 1023, 9
DT = 16.008e-6          # 스케치가 실측한 샘플 간격
D33 = 400e-12           # PZT 문헌값 (pC/N)


def load(path):
    """CSV를 읽고 중간에 끼어든 헤더 줄을 걷어낸다."""
    df = pd.read_csv(path, comment="#")
    df = df[df["event"] != "event"]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().astype({"event": int, "n": int, "adc_raw": int}).reset_index(drop=True)


def decay_tau(t, v, peak_idx):
    """피크 이후 구간을 지수함수로 피팅해 감쇠 시정수를 구한다."""
    post, tp = v[peak_idx:], t[peak_idx:] - t[peak_idx]
    keep = post > 0.05 * v.max()
    cut = np.where(~keep)[0]
    end = cut[0] if len(cut) else len(post)
    if end < 20:
        return None
    slope = np.polyfit(tp[:end], np.log(post[:end]), 1)[0]
    return -1 / slope


def dominant_freq(v, dt, fmin=500):
    """FFT로 가장 센 주파수를 찾는다. 창 길이 때문에 생기는 저주파는 뺀다."""
    spec = np.abs(np.fft.rfft(v - v.mean()))
    freq = np.fft.rfftfreq(len(v), dt)
    band = freq > fmin
    return freq[band][np.argmax(spec[band])], freq, spec


def analyze_event(df, ev):
    s = df[df.event == ev].sort_values("n").reset_index(drop=True)
    v, t, adc = s.v_piezo.values, s.t_us.values * 1e-6, s.adc_raw.values
    ip = int(np.argmax(v))
    dv = np.diff(v) / np.diff(t)
    f_res, _, _ = dominant_freq(v, DT)
    tau = decay_tau(t, v, ip)
    return {
        "event": ev, "n": len(s),
        "V_peak": v.max(), "V_min": v.min(),
        "clip_pct": (adc == 0).mean() * 100,
        "dVdt_max": dv.max(),
        "f_res": f_res,
        "tau_ms": tau * 1e3 if tau else np.nan,
        "Q_m": np.pi * f_res * tau if tau else np.nan,
        "t": t, "v": v, "ip": ip,
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
            "추정 힘 F (N)": C * V_peak / D33,
            "R_opt @2Hz (MΩ)": 1 / (2 * np.pi * 2 * C) / 1e6,
        })
    return pd.DataFrame(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    df = load(CSV)
    evs = [e for e in sorted(df.event.unique()) if e != 0]
    res = [analyze_event(df, e) for e in evs]

    print("=== 이벤트 요약 ===")
    summary = pd.DataFrame([{k: r[k] for k in
        ["event", "V_peak", "V_min", "clip_pct", "dVdt_max", "f_res", "tau_ms", "Q_m"]} for r in res])
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

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
                   label=f"측정 하한 (−{BASELINE*VREF/ADC_MAX:.3f} V)")
        ax.set_title(f"event {r['event']}  ·  peak {r['V_peak']:.3f} V  ·  클리핑 {r['clip_pct']:.1f}%")
        ax.set_xlabel("시간 (ms)"); ax.set_ylabel("전압 (V)")
        ax.legend(fontsize=8); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(f"{OUT}/fig1_waveform.png", dpi=150); plt.close(fig)

    # 그림 2 — 주파수 스펙트럼
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for r in res:
        _, freq, spec = dominant_freq(r["v"], DT)
        ax.semilogx(freq[1:], spec[1:] / spec[1:].max(), lw=0.9, label=f"event {r['event']}")
    ax.axvline(2, color="green", ls="--", lw=1.2, label="걸음 주파수 2 Hz")
    ax.axvline(best["f_res"], color="crimson", ls="--", lw=1.2,
               label=f"측정 공진 {best['f_res']:.0f} Hz")
    ax.set_xlabel("주파수 (Hz)"); ax.set_ylabel("정규화 크기")
    ax.set_title("주파수 스펙트럼 — 걸음과 공진의 간극")
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
    v = c.v_piezo.values
    starts = np.where(np.diff((v > 0.15).astype(int)) == 1)[0]
    peaks = np.array([v[s:min(s + 80, len(v))].max() for s in starts])
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.bar(range(1, len(peaks) + 1), peaks, color="#c05621", alpha=0.85)
    ax.axhline(peaks.mean(), color="0.3", ls="--",
               label=f"평균 {peaks.mean():.3f} V (CV {peaks.std()/peaks.mean()*100:.0f}%)")
    ax.set_xlabel("두드림 번호"); ax.set_ylabel("피크 전압 (V)")
    ax.set_title("두드림 재현성")
    ax.legend(fontsize=8); ax.grid(alpha=0.25, axis="y")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig4_repeatability.png", dpi=150); plt.close(fig)

    print(f"\n그래프 4장 저장 완료 -> {OUT}/")


if __name__ == "__main__":
    main()
