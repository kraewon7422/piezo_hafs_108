# 압전 타일 분석 v3 — logger.py가 만든 폴더를 읽어 통과(사람) 단위로 묶고 요약
# 실행: python analyze.py piezo_20261205_123000            (추가 패키지 필요 없음)
#       python analyze.py piezo_20261205_123000 --people 812 --count 95
#         --people : 하루 통행 인원(일일 에너지 추정용)
#         --count  : 측정하는 동안 직접 센 통과 인원(센서 정확도 비교용)
#
# 용어
#   펄스  : 아두이노가 잡은 전압 덩어리 1개 (디딜 때 1개, 뗄 때 1개가 보통)
#   통과  : 펄스 사이 간격이 PASS_GAP_MS 이하로 이어진 묶음 ≈ 사람 1명이 타일을 지나감
import sys, csv, os, statistics as st

PASS_GAP_MS = 1000


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def main():
    if len(sys.argv) < 2:
        print("사용법: python analyze.py 폴더이름 [--people 하루인원] [--count 직접센인원]")
        return
    folder = sys.argv[1]
    args = sys.argv[2:]
    people = num(args[args.index("--people") + 1]) if "--people" in args else None
    manual = num(args[args.index("--count") + 1]) if "--count" in args else None

    pulses = read_csv(os.path.join(folder, "pulses.csv"))
    status = read_csv(os.path.join(folder, "status.csv"))
    base = read_csv(os.path.join(folder, "baseline.csv"))
    meta = read_csv(os.path.join(folder, "meta.csv"))
    if not pulses:
        print("pulses.csv가 비어 있습니다.")
        return

    # ---- 펄스 정리
    P = []
    for r in pulses:
        p = {"no": int(num(r["pulse_no"])), "t0": num(r["t_start_ms"]), "dur": num(r["dur_ms"]),
             "order": r["order"], "rows": int(num(r["rows_hit"]))}
        p["t1"] = p["t0"] + p["dur"]
        p["E"] = [num(r[f"r{i}_E_uJ"]) for i in range(1, 5)]
        p["Q"] = [num(r[f"r{i}_Q_nC"]) for i in range(1, 5)]
        p["peak"] = [num(r[f"r{i}_peak_V"]) for i in range(1, 5)]
        p["clip"] = any(num(r[f"r{i}_clip"]) > 0 for i in range(1, 5))
        P.append(p)
    P.sort(key=lambda p: p["t0"])

    # ---- 통과 단위로 묶기
    passes, cur = [], [P[0]]
    for p in P[1:]:
        if p["t0"] - cur[-1]["t1"] <= PASS_GAP_MS:
            cur.append(p)
        else:
            passes.append(cur); cur = [p]
    passes.append(cur)

    rows_out = []
    for k, g in enumerate(passes, 1):
        E = sum(sum(p["E"]) for p in g)
        e_odd = sum(sum(p["E"]) for p in g[0::2])     # 1·3·5번째 펄스 (디딤으로 추정)
        e_even = sum(sum(p["E"]) for p in g[1::2])    # 2·4·6번째 펄스 (뗌으로 추정)
        first = g[0]["order"]
        direction = 0
        if len(first) >= 2 and first != "0":
            direction = 1 if first[0] < first[-1] else -1   # +1: 1행→4행 쪽, -1: 반대
        rows_union = sorted({c for p in g for c in p["order"] if c != "0"})
        rows_out.append({
            "pass_no": k, "t_start_ms": int(g[0]["t0"]), "t_end_ms": int(g[-1]["t1"]),
            "n_pulses": len(g), "E_total_uJ": round(E, 4),
            "E_odd_uJ(디딤 추정)": round(e_odd, 4), "E_even_uJ(뗌 추정)": round(e_even, 4),
            "Q_total_nC": round(sum(sum(p["Q"]) for p in g), 2),
            "peak_max_V": round(max(max(p["peak"]) for p in g), 2),
            "rows_touched": "".join(rows_union), "direction": direction,
            "first_order": first, "clipped": int(any(p["clip"] for p in g)),
        })

    with open(os.path.join(folder, "passes.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)

    # ---- 요약
    Es = [r["E_total_uJ"] for r in rows_out]
    t_first = P[0]["t0"]; t_last = P[-1]["t1"]
    if status:
        t_last = max(t_last, num(status[-1]["t_ms"]))
    dur_s = max((t_last - (num(base[0]["t_ms"]) if base else t_first)) / 1000.0, 1e-9)
    row_E = [sum(p["E"][i] for p in P) for i in range(4)]
    tot_E = sum(row_E)
    dropped = int(num(status[-1]["dropped_samples"])) if status else 0

    lines = []
    add = lines.append
    if meta:
        m = meta[-1]
        add(f"설정: VREF {m['VREF']} V, R1 {m['R1']} Ω, R2 {m['R2']} Ω, 샘플 {m['sample_us']} µs, 문턱 {m['th_on_V']} V")
    if base:
        b = base[-1]
        add("시작 잡음 최대(V): " + ", ".join(b[f"max{i}_V"] for i in range(1, 5)))
    add(f"측정 시간: {dur_s/60:.1f}분, 놓친 샘플: {dropped}개")
    add(f"펄스 {len(P)}개 → 통과 {len(rows_out)}회 (통과당 펄스 평균 {len(P)/len(rows_out):.2f}개)")
    if manual:
        add(f"직접 센 인원 {int(manual)}명 대비 통과 수 오차: {(len(rows_out)-manual)/manual*100:+.1f}%")
    add(f"통과 1회 에너지: 평균 {st.mean(Es):.3f} µJ, 중앙값 {st.median(Es):.3f} µJ, "
        f"최대 {max(Es):.3f} µJ")
    add(f"총 에너지 {tot_E:.3f} µJ, 평균 전력 {tot_E/dur_s:.4f} µW (분압 저항 1.1 MΩ에 전달된 값)")
    add("행별 에너지 비율: " + ", ".join(f"{i+1}행 {row_E[i]/tot_E*100:.0f}%" if tot_E else f"{i+1}행 0%" for i in range(4)))
    dirs = [r["direction"] for r in rows_out]
    add(f"방향: 1행→4행 {dirs.count(1)}회, 4행→1행 {dirs.count(-1)}회, 판단 불가 {dirs.count(0)}회")
    nclip = sum(r["clipped"] for r in rows_out)
    add(f"클램프에 걸려 값이 잘린 통과: {nclip}회" + (" → R2를 47 kΩ로 바꿔 범위를 넓힐 것" if nclip else ""))
    if people:
        day_J = st.mean(Es) * 1e-6 * people
        add(f"하루 {int(people)}명 통과 가정 → 타일 1장 하루 약 {day_J*1000:.3f} mJ ({day_J:.6f} J)")
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(folder, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("\n저장:", os.path.join(folder, "passes.csv"), ",", os.path.join(folder, "summary.txt"))


if __name__ == "__main__":
    main()
