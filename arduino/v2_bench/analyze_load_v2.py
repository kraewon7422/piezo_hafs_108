# [저장소 메모] 2026-09-18 대화에서 만든 'analyze_v2.py'를 이름만 바꾼 것.
#   저장소 맨 위의 analyze_v2.py(2026-09-11 데이터 재분석)와는 전혀 다른 스크립트다.
#   회로 A/B/C 스케치의 7열 CSV를 읽는다. 실제 데이터로 돌려 본 적은 없다.
#   키트판(v2) 스케치를 썼다면 아래 R_REF = 100_000.0, R_BIAS_PAR = 25_000.0 으로 바꿀 것.
# analyze_v2.py — 부하저항 P-R 곡선 / 에너지 적분 / C_p 피팅
# 사용법:  python analyze_load_v2.py piezo_capture_data.csv
#
# v1과의 차이
#  - R_load 열을 읽어 조건별로 분리 (조건 섞임 방지)
#  - 개방전압 추정이 아니라 부하에 실제로 전달된 에너지 E = ∫ v²/R dt 를 계산
#  - C_p 충전곡선(mode=m)에서 tau 피팅 -> C_p = tau / R_ref
#
# 입력 CSV 열: mode,event,n,t_us,adc_raw,v_signed,R_load
#   예)  t,3,-120,-1920.9,517,0.0244,10000

import sys
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# 한글 폰트 (없으면 경고만 뜨고 진행)
for f in ["Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "AppleGothic"]:
    try:
        matplotlib.rcParams["font.family"] = f
        break
    except Exception:
        pass
matplotlib.rcParams["axes.unicode_minus"] = False

R_REF = 1_000_000.0   # C_p 측정에 실제로 쓴 저항값 — 멀티미터 실측값으로 교체할 것
R_BIAS_PAR = 500_000.0  # 바이어스 1MΩ+1MΩ 의 교류 등가 (병렬) — 실측값으로 교체할 것


def r_eff(r_load):
    """실제로 압전소자가 보는 부하 = R_load ∥ R_bias."""
    if r_load <= 0:
        return R_BIAS_PAR
    return 1.0 / (1.0 / r_load + 1.0 / R_BIAS_PAR)


def load(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("mode,"):
                continue
            p = line.split(",")
            if len(p) < 7:
                continue
            try:
                rows.append((p[0], int(p[1]), int(p[2]), float(p[3]),
                             int(p[4]), float(p[5]), float(p[6])))
            except ValueError:
                continue
    return pd.DataFrame(rows, columns=["mode", "event", "n", "t_us",
                                       "adc", "v", "R_load"])


def pr_curve(df):
    """모드 t(타격) 데이터에서 조건별 피크전력·전달에너지."""
    out = []
    hits = df[df["mode"] == "t"]
    for (ev, r), g in hits.groupby(["event", "R_load"]):
        g = g.sort_values("n")
        dt = np.diff(g["t_us"].values).mean() * 1e-6
        v = g["v"].values
        R = r_eff(r)
        vmax = v.max()
        out.append(dict(event=ev, R_load=r, R_eff=R, Vmax=vmax, Vmin=v.min(),
                        P_peak_W=vmax ** 2 / R,
                        E_J=float(np.sum(v ** 2) / R * dt),
                        clip_low=float((g["adc"] == 0).mean()),
                        clip_high=float((g["adc"] >= 1023).mean())))
    res = pd.DataFrame(out).sort_values(["R_eff", "event"])
    if res.empty:
        print("[!] 타격(mode=t) 데이터가 없습니다.")
        return res

    print("\n=== 조건별 요약 ===")
    print(res.to_string(index=False, float_format=lambda x: f"{x:.6g}"))
    if (res["clip_low"] > 0.01).any() or (res["clip_high"] > 0.01).any():
        print("\n[!] 클리핑이 남아 있습니다. 바이어스가 2.5 V 중앙에 있는지 확인하세요.")

    agg = res.groupby("R_eff").agg(
        n=("event", "count"), Vmax=("Vmax", "mean"),
        P_peak_W=("P_peak_W", "mean"), E_J=("E_J", "mean"),
        E_sd=("E_J", "std")).reset_index()

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].semilogx(agg["R_eff"], agg["P_peak_W"] * 1e6, "o-")
    ax[0].set_xlabel("실효 부하저항 R_eff [Ω]")
    ax[0].set_ylabel("피크 전력 [µW]")
    ax[0].set_title("P–R 곡선 (피크)")
    ax[0].grid(True, which="both", alpha=0.3)

    ax[1].errorbar(agg["R_eff"], agg["E_J"] * 1e9,
                   yerr=(agg["E_sd"].fillna(0) * 1e9), fmt="s-", capsize=3)
    ax[1].set_xscale("log")
    ax[1].set_xlabel("실효 부하저항 R_eff [Ω]")
    ax[1].set_ylabel("1회 타격 전달에너지 [nJ]")
    ax[1].set_title("E–R 곡선 (C_p 가정 없이 적분)")
    ax[1].grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig("fig5_PR_curve.png", dpi=150)
    print("\n[저장] fig5_PR_curve.png")
    return res


def fit_cp(df):
    """모드 m 충전곡선에서 tau 피팅 -> C_p."""
    g = df[df["mode"] == "m"]
    if g.empty:
        print("\n[i] C_p 충전곡선(mode=m) 데이터가 없습니다.")
        return None
    t = g["t_us"].values * 1e-6
    v = g["v"].values

    def model(t, vinf, tau, v0):
        return vinf - (vinf - v0) * np.exp(-t / tau)

    popt, _ = curve_fit(model, t, v,
                        p0=[v.max(), max(t.max() / 3, 1e-4), v.min()],
                        maxfev=20000)
    vinf, tau, v0 = popt
    cp = tau / R_REF
    print("\n=== C_p 피팅 ===")
    print(f"  V_inf = {vinf:.3f} V")
    print(f"  tau   = {tau*1e3:.4f} ms")
    print(f"  R_ref = {R_REF:.0f} Ω  (실측값으로 반드시 교체)")
    print(f"  C_p   = {cp*1e9:.2f} nF")

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(t * 1e3, v, ".", ms=2, label="측정")
    ax.plot(t * 1e3, model(t, *popt), "-", lw=2,
            label=f"피팅 τ={tau*1e3:.3f} ms → C_p={cp*1e9:.2f} nF")
    ax.set_xlabel("시간 [ms]")
    ax.set_ylabel("전압 [V]")
    ax.set_title("압전소자 정전용량 RC 충전곡선")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("fig6_Cp_fit.png", dpi=150)
    print("[저장] fig6_Cp_fit.png")
    return cp


def cap_energy(df, c_store=100e-9):
    """모드 c(축전) 데이터에서 저장 에너지 증가분."""
    g = df[df["mode"] == "c"]
    if g.empty:
        print("\n[i] 축전 감시(mode=c) 데이터가 없습니다.")
        return
    v = g["v"].values
    e = 0.5 * c_store * v ** 2
    print(f"\n=== 축전 결과 (C_store = {c_store*1e9:.0f} nF) ===")
    print(f"  V_start = {v[0]:.4f} V -> V_end = {v[-1]:.4f} V")
    print(f"  E_start = {e[0]*1e9:.3f} nJ -> E_end = {e[-1]*1e9:.3f} nJ")
    print(f"  누적 저장 에너지 = {(e[-1]-e[0])*1e9:.3f} nJ")
    print("  ※ 타격 횟수 N으로 나누면 '실제로 회수된' 걸음당 에너지")
    print("  ※ 무타격 대조군의 누설 감소분을 반드시 빼고 보고할 것")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "piezo_capture_data.csv"
    df = load(path)
    print(f"불러온 행: {len(df)}  |  모드: {sorted(df['mode'].unique())}")
    pr_curve(df)
    fit_cp(df)
    cap_energy(df)
