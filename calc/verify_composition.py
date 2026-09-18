# -*- coding: utf-8 -*-
"""
verify_composition.py
HAFS 유리프 압전 타일 연구 / 1학년 8반 / 5차시 화학구조 제안

제안 조성  (Pb0.96 Sm0.04)[(Zr0.52 Ti0.48)0.88 (Zn1/3 Nb2/3)0.10 Mn0.02] O3
에 대해 다음을 계산으로 검증한다.

  1. 전하 중성            : 합이 0이어야 한다
  2. Goldschmidt 허용인자  : 0.9 < t < 1.0 이어야 페로브스카이트가 유지된다
  3. 결합 기하            : Noheda(2000) 실측 원자좌표에서 B-O 결합길이와 양이온 변위
  4. d33 - d.g 순위상관    : 11종 전체와 상용 10종(UTA 연구 조성 제외)을 나눠 계산
  5. 에너지 비            : 같은 응력/부피에서 조성별 U 비교

실행:  python verify_composition.py
의존성 없음 (표준 라이브러리만 사용)
"""

import math
import sys

# Windows 콘솔에서 한글이 깨지지 않도록
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------------------------------------------------------------- 데이터
# Shannon (1976) 유효 이온반경 [Å]
R_O = 1.40                        # O2-, CN=6
R_A = {"Pb2": 1.49, "Sm3": 1.24}  # CN=12  (Sm3+ CN12는 외삽값)
R_B = {"Zr4": 0.72, "Ti4": 0.605, "Zn2": 0.74,
       "Nb5": 0.64, "Mn2": 0.83, "Mn3": 0.645}   # CN=6

# 제안 조성의 자리별 몰분율
X_SM, X_PZ, X_PZN, X_MN = 0.04, 0.88, 0.10, 0.02

# Noheda et al., Phys. Rev. B 61, 8687 (2000)
# PbZr0.52Ti0.48O3, 공간군 P4mm, 325 K, Rietveld 정밀화
LAT_A, LAT_C = 4.0460, 4.1394                # [Å]
Z_B, Z_O1, Z_O2 = 0.4509, -0.1027, 0.3786    # 분율좌표

# US 7,686,974 B2, FIG.13 — 상용 압전 소재 10종 + 발명자의 UTA 연구 조성 1종
# (이름, d.g [1e-15 m2/N], g33 [1e-3 m2/C], 지수 n)
COMMERCIAL = [
    ("EDO EC-98",         11388, 15.60, 1.249),
    ("Fuji C-8",          12351, 19.70, 1.225),
    ("Morgan PZT-507",    14000, 20.00, 1.226),
    ("APC 855",           12600, 21.00, 1.220),
    ("Channel 5600 Navy", 11110, 22.00, 1.217),
    ("EDO EC-65",          9500, 25.00, 1.205),
    ("APC 850",           10400, 26.00, 1.203),
    ("Channel 5400 Navy",  7830, 26.10, 1.199),
    ("Dongil D211",        8820, 42.00, 1.166),
    ("Ferroperm Pz24",    10260, 54.00, 1.150),
    ("UTA PZT-PZN+Mn",    16168, 55.56, 1.151),
]

EPS0 = 8.8541878128e-12           # 진공 유전율 [F/m]


# ---------------------------------------------------------------- 1. 전하 중성
def charge_balance(x_sm=X_SM, x_pz=X_PZ, x_pzn=X_PZN, x_mn=X_MN, v_mn=2):
    """자리별 기여 전하와 그 합을 돌려준다. 합이 0이면 공공 없이 전하가 맞는다."""
    q_a = (1 - x_sm) * 2 + x_sm * 3
    q_zn_nb = (1 / 3) * 2 + (2 / 3) * 5          # = 4.0, Zr/Ti와 같다
    q_b = x_pz * 4 + x_pzn * q_zn_nb + x_mn * v_mn
    q_o = 3 * (-2)
    return q_a, q_b, q_o, q_a + q_b + q_o


# ---------------------------------------------------------------- 2. 허용인자
def tolerance_factor(r_a, r_b):
    return (r_a + R_O) / (math.sqrt(2) * (r_b + R_O))


def radii_proposed(v_mn=2):
    mn_key = "Mn2" if v_mn == 2 else "Mn3"
    r_a = (1 - X_SM) * R_A["Pb2"] + X_SM * R_A["Sm3"]
    r_pzt = 0.52 * R_B["Zr4"] + 0.48 * R_B["Ti4"]
    r_zn_nb = (1 / 3) * R_B["Zn2"] + (2 / 3) * R_B["Nb5"]
    r_b = X_PZ * r_pzt + X_PZN * r_zn_nb + X_MN * R_B[mn_key]
    return r_a, r_b, r_pzt


# ---------------------------------------------------------------- 3. 결합 기하
def geometry():
    """P4mm 실측 좌표에서 결합길이와 양이온-산소평면 거리를 계산한다."""
    d_short = ((1 + Z_O1) - Z_B) * LAT_C                     # B-O1 짧은 쪽
    d_long = (Z_B - Z_O1) * LAT_C                            # B-O1 긴 쪽
    d_eq = math.hypot(0.5 * LAT_A, (Z_B - Z_O2) * LAT_C)     # B-O2 적도 x4
    shift = (Z_B - Z_O2) * LAT_C          # 양이온이 적도 산소면보다 얼마나 위인가
    return {
        "c_over_a": LAT_C / LAT_A,
        "B_O1_short": d_short,
        "B_O1_long": d_long,
        "B_O1_delta": d_long - d_short,
        "B_O2_equatorial": d_eq,
        "cation_shift": shift,
        "shift_ratio": shift / LAT_C,
        "volume": LAT_A * LAT_A * LAT_C,
    }


# ---------------------------------------------------------------- 4. 상관계수
def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for k, i in enumerate(order):
            r[i] = k + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (sx * sy)


# ---------------------------------------------------------------- 출력
def main():
    line = "-" * 68

    print(line)
    print("1. 전하 중성")
    print(line)
    for v in (2, 3):
        qa, qb, qo, total = charge_balance(v_mn=v)
        need = (4 - v) * X_MN
        print("  Mn(%d+) 가정 : A=%+.4f  B=%+.4f  O=%+.4f  ->  합계 %+.4f"
              % (v, qa, qb, qo, total))
        print("               전하가 맞으려면 x_Sm = (4 - %d) * x_Mn = %.3f" % (v, need))
    print("  현재 x_Sm = %.3f  ->  Mn2+ 가정에서 정확히 성립" % X_SM)
    print("  Mn의 실제 원자가는 XPS 또는 EPR로 확인해야 하는 미결 변수다.")

    print()
    print(line)
    print("2. Goldschmidt 허용인자   t = (rA + rO) / [ sqrt(2) * (rB + rO) ]")
    print(line)
    r_pzt_only = 0.52 * R_B["Zr4"] + 0.48 * R_B["Ti4"]
    t0 = tolerance_factor(R_A["Pb2"], r_pzt_only)
    print("  PZT 52/48 (기준)    rA=%.4f  rB=%.4f  t=%.4f" % (R_A["Pb2"], r_pzt_only, t0))
    for v in (2, 3):
        ra, rb, _ = radii_proposed(v_mn=v)
        t = tolerance_factor(ra, rb)
        print("  제안 조성 Mn(%d+)   rA=%.4f  rB=%.4f  t=%.4f  %s"
              % (v, ra, rb, t, "안정" if 0.9 < t < 1.0 else "확인 필요"))
    print("  주의 1: Sm3+ CN=12 반경 1.24 A는 Shannon 원표에 없어 외삽값을 사용했다.")
    print("  주의 2: 허용인자는 필요조건이지 충분조건이 아니다. 실제 상 형성은")
    print("          XRD로 이차상(pyrochlore 등)의 유무를 확인해야 확정된다.")

    print()
    print(line)
    print("3. 결합 기하   (Noheda 2000, P4mm, 325 K)")
    print(line)
    g = geometry()
    print("  c / a                      = %.4f" % g["c_over_a"])
    print("  단위포 부피                = %.3f A^3" % g["volume"])
    print("  B-O1 짧은 쪽               = %.4f A" % g["B_O1_short"])
    print("  B-O1 긴 쪽                 = %.4f A" % g["B_O1_long"])
    print("  B-O1 비대칭 delta          = %.4f A   <- 압전성의 기하학적 근원" % g["B_O1_delta"])
    print("  B-O2 적도 (x4)             = %.4f A" % g["B_O2_equatorial"])
    print("  양이온 - 적도산소면 거리   = %.4f A   (c축의 %.1f %%)"
          % (g["cation_shift"], g["shift_ratio"] * 100))

    print()
    print(line)
    print("4. 문헌 소재 11종 (상용 10 + UTA 연구 조성 1): d33 과 d.g 의 순위 관계")
    print(line)
    rows = []
    for name, dg, g33, n in COMMERCIAL:
        d33 = dg * 1e-15 / (g33 * 1e-3) / 1e-12       # pC/N
        rows.append((name, d33, g33, dg, n))
    rows.sort(key=lambda r: -r[1])

    print("  %-20s %10s %8s %9s %7s" % ("소재", "d33[pC/N]", "g33", "d.g", "n"))
    for name, d33, g33, dg, n in rows:
        print("  %-20s %10.0f %8.1f %9.0f %7.3f" % (name, d33, g33, dg, n))

    print()
    print("  %-26s %10s %14s" % ("", "11종 전체", "상용 10종만"))
    sets = [rows, [r for r in rows if not r[0].startswith("UTA")]]
    cols = [([r[1] for r in s], [r[2] for r in s], [r[3] for r in s]) for s in sets]
    print("  %-26s %+10.3f %+14.3f   <- 어느 쪽이든 거의 완벽한 역상관"
          % ("Spearman rho (d33, g33)", spearman(cols[0][0], cols[0][1]), spearman(cols[1][0], cols[1][1])))
    print("  %-26s %+10.3f %+14.3f"
          % ("Spearman rho (d33, d.g)", spearman(cols[0][0], cols[0][2]), spearman(cols[1][0], cols[1][2])))
    print("  %-26s %+10.3f %+14.3f"
          % ("Pearson    r (d33, d.g)", pearson(cols[0][0], cols[0][2]), pearson(cols[1][0], cols[1][2])))
    print("  => 상용품끼리는 d33 순위가 d.g 순위를 대체로 따라간다.")
    print("     11종의 상관을 끌어내리는 것은 UTA 한 점 (d33 9위, d.g 1위):")
    print("     d33 을 키우지 않고 eps_r 을 낮춰서도 d.g 1위가 될 수 있다는 반례다.")

    print()
    print(line)
    print("5. 같은 응력 / 같은 부피에서의 에너지 비   U = 0.5 * (d.g) * sigma^2 * V")
    print(line)
    base = 7830
    targets = [
        ("Channel 5400 Navy (기준)", 7830),
        ("APC 850", 10400),
        ("Morgan PZT-507", 14000),
        ("UTA PZT-PZN+Mn", 16168),
        ("[001] 조직화 PMN-PZT", 59000),
        ("제안 조성 하한 2.0e4 (추정)", 20000),
        ("제안 조성 상한 4.0e4 (추정)", 40000),
    ]
    for name, dg in targets:
        print("  %-30s %5.2f 배" % (name, dg / base))

    print()
    print("  참고: 위 d.g 는 모두 33 모드 값이다. 굽힘으로 동작하는 27 mm 디스크에")
    print("        실제로 걸리는 계수는 d31 * g31 이므로 절대값은 훨씬 작다.")
    print("        소재 사이의 '비'를 비교하는 용도로만 사용할 것.")
    print()


if __name__ == "__main__":
    main()
