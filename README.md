# piezo_hafs_108 — Can stepping on a floor tile make electricity?

**A high-school research project that measured how much electricity a piezo disc makes when you press it,
found out why it is so little, and designed a better material on paper.**

<p align="center">
  <a href="https://kraewon7422.github.io/piezo_hafs_108/sim/PiezoAnalyzer_v2.html"><img alt="Analyzer — live demo" src="https://img.shields.io/badge/%E2%96%B6%20Data%20Analyzer-open%20in%20browser-ffb000?style=for-the-badge"></a>
  <a href="https://kraewon7422.github.io/piezo_hafs_108/sim/hafs108-crystal.html"><img alt="3D crystal — live demo" src="https://img.shields.io/badge/%E2%96%B6%203D%20Crystal-open%20in%20browser-256B7C?style=for-the-badge"></a>
  <a href="https://kraewon7422.github.io/piezo_hafs_108/sim/pzt_simulator_v6.html"><img alt="Simulator — live demo" src="https://img.shields.io/badge/%E2%96%B6%20Material%20Simulator-open%20in%20browser-c05621?style=for-the-badge"></a>
</p>

> 🇰🇷 한국어 설명은 [아래](#한국어--처음-보는-사람을-위한-설명)에 있습니다.

---

## The 60-second version

1. **Some crystals make electricity when you squeeze them.** This is called the *piezoelectric effect*
   ("piezo" is Greek for *press*). The little round buzzer inside a greeting card or a toy is one of these.
2. **Idea:** put piezo discs under the floor where hundreds of students walk every day (the cafeteria entrance)
   and collect the electricity.
3. **We measured it.** We connected one 27 mm piezo disc to an Arduino (a small programmable circuit board) and
   recorded the voltage 62,000 times per second while pressing and tapping it.
4. **Result:** one press gives a pulse of about **1.2 volts lasting about 0.1 seconds**. The energy in it is only
   about **15 nanojoules** (0.000000015 J). To keep one small LED (20 mW) lit for one second you would need about
   **a million presses**.
5. **Why so little?** A ceramic disc barely bends (micrometres). Energy is *force × distance*, and when the distance is
   tiny, the energy is tiny — no matter how hard you step. Commercial "energy floors" get far more energy because the
   floor actually sinks a few millimetres.
6. **What we did with that:** we worked out which material property really matters for slow presses like footsteps
   (the product **d·g**, explained below, not the commonly quoted **d₃₃**) and designed a new ceramic composition
   on paper, checked with chemistry rules.
7. **Conclusion so far:** piezo floors are **not a practical power source** for a school, but they are a good
   **self-powered step sensor** (it can count footsteps without any battery). Next step: a 5 × 4 tile of 20 discs,
   designed and ready to build.

---

## What is in this repository?

| If you want to… | Open this | What you'll see |
|---|---|---|
| **understand piezo from zero** | [`docs/00_piezo_basics.md`](docs/00_piezo_basics.md) (Korean) | why pressing makes electricity, and why only a little |
| **play with our real data** | [Data Analyzer v2](https://kraewon7422.github.io/piezo_hafs_108/sim/PiezoAnalyzer_v2.html) | our measured waveform, energy per press, "is it useful for a school?" verdict |
| **see the crystal in 3D** | [HAFS-108 crystal page](https://kraewon7422.github.io/piezo_hafs_108/sim/hafs108-crystal.html) | rotate the atoms of PZT and of our proposed material, see why it is polar |
| **compare piezo materials** | [Material Simulator v6](https://kraewon7422.github.io/piezo_hafs_108/sim/pzt_simulator_v6.html) | PZT, BaTiO₃, PVDF, ZnO, quartz side by side *(illustration only — its numbers are relative, not real watts)* |
| **build the circuits** | [`arduino/`](arduino/) | every Arduino sketch we wrote, with a plain-language run guide |
| **build the 20-disc floor tile** | [5×4 tile guide](https://kraewon7422.github.io/piezo_hafs_108/sim/array5x4_guide_v2.html) | wiring, protection box, cross-section, parts list |
| **read the full research record** | [`docs/research_report_ko.md`](docs/research_report_ko.md) (Korean) | every number, every source, every correction |
| **read our lab logs / report** | [`docs/logs/`](docs/logs/) | session logs and the midterm report |
| **see the whole story in order** | [`docs/PROJECT_HISTORY.md`](docs/PROJECT_HISTORY.md) | March → November, what we tried, what changed and why |
| **check what the AI got wrong** | [`docs/AI_FACT_CHECK.md`](docs/AI_FACT_CHECK.md) | claims from AI chats that we verified, corrected or withdrew |

### Folder map

```
README.md                  ← you are here
piezo_capture_simple.ino   ← the Arduino sketch that recorded our real data (Sept 11)
analyze_v1.py, analyze_v2.py ← turn that recording into the numbers and graphs below
data/                      ← the raw measurement (CSV file, 3,380 rows)
figures/                   ← graphs made by analyze_v2.py
arduino/                   ← all later sketches: load tests, capacitance test, 5×4 tile (with run guide)
sim/                       ← browser tools: analyzer, simulator, 3D crystal, bench & wiring guides
  old/                     ← earlier versions kept on purpose (v1 → v5 …)
calc/verify_composition.py ← checks our proposed material obeys charge and size rules
structures/*.cif           ← crystal-structure files (open in VESTA or any CIF viewer)
docs/                      ← explanations, full report, logs, history, fact-check
```

---

## The key results, explained

| Measurement | Value | What it means in plain words |
|---|---|---|
| Hard tap, peak voltage | **1.13 V** | a bit less than one AA battery, but only for a split second |
| Ringing after a tap | **≈ 3.3 kHz** | the disc vibrates like a tiny bell, 3,300 times a second — this is its *resonance* |
| Hand press | **1.1–1.3 V, ≈ 0.1 s** | one smooth bump; a press is hundreds of times slower than the ringing, so the "bell" effect doesn't help |
| Energy per press | **≈ 15 nJ** | calculated as ½·C·V² with the disc's capacitance (≈ 20 nF from the datasheet) |
| Repeatability (4 presses) | spread ≈ 7–8 % | hand pressing is fairly consistent; a drop-weight jig would be better |

<details>
<summary><b>Why does the reading cut off below 0 V?</b> (a limitation we found)</summary>

An Arduino can only read voltages between 0 and 5 V. A piezo makes both positive and negative voltage, so the
negative half was cut off (29 % of the samples sat at zero). The fix is a "bias" circuit that lifts the signal to
the middle of the range — that circuit is in [`arduino/`](arduino/) but has not been run yet.
</details>

<details>
<summary><b>Why can't you just say how many watts it makes?</b></summary>

Power needs a *load* (something that uses the electricity, like a resistor). We measured the disc with nothing
connected (open circuit), so we know the voltage and can estimate the stored energy, but not the delivered power.
Load-resistor tests are designed (circuit A in `arduino/v2_bench/`) and are the next measurement.
</details>

### Why d·g and not d₃₃? (the idea behind the material design)

Two numbers describe a piezo material:

- **d** — how much electric *charge* you get per newton of force.
- **g** — how much *voltage* that charge makes. g = d ÷ (how much the material "soaks up" charge, its permittivity εᵣ).

The energy stored in one press is charge × voltage, so it grows with **d × g**. Most articles rank materials by
d₃₃ alone, but materials with a big d usually also have a big εᵣ, which kills g. In a published table of 11 materials
(10 commercial ceramics + 1 lab-made composition), the highest-d₃₃ material was only 5th in d·g, and the d·g winner
(the lab composition, which deliberately lowers εᵣ) was 9th in d₃₃. Among the commercial ones alone, d₃₃ and d·g do
move together, so the point is not "d₃₃ is useless" but "lowering εᵣ is a second, separate lever".
So our proposed composition tries to **lower εᵣ while keeping d**:

**(Pb₀.₉₆Sm₀.₀₄)[(Zr₀.₅₂Ti₀.₄₈)₀.₈₈(Zn₁/₃Nb₂/₃)₀.₁₀Mn₀.₀₂]O₃** — charges add up to exactly zero and the
"tolerance factor" (a size rule for this crystal type) is t = 0.984, inside the stable range.
This is a **paper design**: we cannot make it at school (it needs a furnace at ~1,200 °C and lead handling), and the
expected improvement is an estimate between two published results, not a measurement. Details and every source:
[`docs/05_material_design.md`](docs/05_material_design.md).

---

## Try it yourself (no installation)

**Data Analyzer** — open the [live page](https://kraewon7422.github.io/piezo_hafs_108/sim/PiezoAnalyzer_v2.html),
press **실측 데이터 가져오기** (load measured data) and you'll see our real presses, the energy of each, and a
school-feasibility verdict. You can change the assumptions (number of students, electricity price) in the settings tab.

**Reproduce our numbers on your computer** (needs Python 3 with `numpy` and `matplotlib`):

```bash
python analyze_v2.py                 # reads data/piezo_capture_data-1.csv → prints results, saves figures/
python calc/verify_composition.py    # checks the proposed material (charge balance, tolerance factor, rankings)
```

**Repeat the measurement** — you need an Arduino Uno, a 27 mm piezo disc and two wires (disc red → A0, black → GND).
Upload `piezo_capture_simple.ino`, open the Serial Monitor at 500000 baud, tap the disc, and save the output as CSV.
⚠️ Only press or tap it **by hand** in this direct setup — a full footstep can push the disc to tens of volts and
damage the Arduino pin. For foot tests use the protected circuits in `arduino/`.
Full guide: [`arduino/README.md`](arduino/README.md).

---

## Honesty notes

- **What is measured vs. estimated.** Only the September 11 open-circuit recording is real measured data. The load
  tests, capacitance test, energy-storage test and the 5×4 tile are designed but **not yet run**.
- **We publish our mistakes.** Earlier we claimed several things we later withdrew (for example, a force calculation
  using the wrong piezo coefficient, and an "LED lights up" result that was actually powered by the USB cable).
  The full list is in [§2-6 of the report](docs/research_report_ko.md#2-6-다시-분석해서-바로잡은-것).
- **AI use.** We used Claude (several model versions, March–November 2026) as a tutor and coding assistant.
  On 2026-11-13 every AI chat of the project was re-checked against primary sources; what was wrong, where it had
  leaked into this repo, and how it was fixed is listed in [`docs/AI_FACT_CHECK.md`](docs/AI_FACT_CHECK.md).
  Corrections inside documents are marked **⚠️정정(2026-11-13)**.

## Status & next steps

| Step | Status |
|---|---|
| 1. Understand how PZT works | ✅ [basics](docs/00_piezo_basics.md) |
| 2. Simulator + data analyzer | ✅ [`sim/`](sim/) |
| 3. First real measurement (one disc) | ✅ Sept 11 — [`data/`](data/) |
| 4. Material design (d·g criterion) | ✅ Sept 18 — [`docs/05`](docs/05_material_design.md) |
| 5. Midterm report | ✅ Oct — [`docs/logs/`](docs/logs/) |
| 6. 5×4 tile (20 discs) design + parts list | ✅ Nov 13 — [guide](https://kraewon7422.github.io/piezo_hafs_108/sim/array5x4_guide_v2.html) |
| 7. Build the tile, measure real footsteps at the cafeteria | ⏳ next |

A 4-person student team did this project (experiment design & software / literature & 3D housing / data analysis /
report). License: [MIT](LICENSE).

---

## 한국어 — 처음 보는 사람을 위한 설명

**압전 타일을 밟으면 전기가 얼마나 나올까?** — 고등학교 탐구 프로젝트입니다. 압전 디스크를 실제로 눌러 전압을 재고,
왜 전기가 조금밖에 안 나오는지 밝히고, 그 결과를 바탕으로 더 나은 압전 소재를 설계했습니다.

### 1분 요약

1. **어떤 결정은 누르면 전기가 나옵니다.** 이것을 *압전 효과*라고 합니다(그리스어 piezo = 누르다).
   축하 카드나 장난감 속 동그란 부저가 바로 압전 소자입니다.
2. **아이디어:** 학생 수백 명이 매일 지나가는 급식실 입구 바닥에 압전 소자를 깔아 전기를 모으자.
3. **직접 쟀습니다.** 지름 27 mm 압전 디스크 하나를 아두이노(작은 프로그래밍 회로 기판)에 연결하고,
   두드리고 누르는 동안 전압을 1초에 62,000번 기록했습니다.
4. **결과:** 한 번 누르면 **약 1.2 V짜리 펄스가 약 0.1초** 나옵니다. 그 안의 에너지는 **약 15 nJ**
   (0.000000015 J)뿐입니다. 작은 LED(20 mW) 하나를 1초 켜려면 **약 100만 번** 눌러야 합니다.
5. **왜 이렇게 적나?** 세라믹 디스크는 거의 휘지 않습니다(마이크로미터 수준). 에너지 = 힘 × 움직인 거리이므로,
   아무리 세게 밟아도 거리가 작으면 에너지도 작습니다. 상용 발전 바닥은 바닥 자체가 몇 mm 꺼지기 때문에 훨씬 많이 얻습니다.
6. **그래서 한 일:** 발걸음처럼 느린 누름에서는 흔히 쓰는 **d₃₃**가 아니라 **d·g**라는 값이 중요하다는 것을 밝히고,
   그 기준으로 새 세라믹 조성을 화학 규칙(전하 균형, 이온 크기)으로 검증하며 설계했습니다.
7. **지금까지의 결론:** 압전 바닥은 학교 **전력원으로는 비현실적**이지만, 배터리 없이 걸음 수를 세는
   **자가발전 센서**로는 현실적입니다. 다음 단계는 디스크 20개짜리 5 × 4 타일 — 설계와 부품 목록이 준비되어 있습니다.

### 무엇을 어디서 보나

| 하고 싶은 것 | 여기를 여세요 |
|---|---|
| 압전을 처음부터 이해하기 | [압전 기초론](docs/00_piezo_basics.md) |
| 실제 측정 데이터 만져 보기 | [데이터 분석기 v2](https://kraewon7422.github.io/piezo_hafs_108/sim/PiezoAnalyzer_v2.html) → **실측 데이터 가져오기** |
| 결정 구조를 3D로 돌려 보기 | [HAFS-108 결정 페이지](https://kraewon7422.github.io/piezo_hafs_108/sim/hafs108-crystal.html) |
| 압전 소재 비교 | [소재 시뮬레이터 v6](https://kraewon7422.github.io/piezo_hafs_108/sim/pzt_simulator_v6.html) *(설명용 — 화면 수치는 상대값이며 실제 W·J가 아님)* |
| 회로 만들어 보기 | [`arduino/`](arduino/) — 모든 스케치 + 쉬운 실행 안내 |
| 20개짜리 타일 만들기 | [5×4 타일 가이드](https://kraewon7422.github.io/piezo_hafs_108/sim/array5x4_guide_v2.html) |
| 전체 연구 기록(수치·출처·정정 전부) | [연구 보고서](docs/research_report_ko.md) |
| 연구일지·중간보고서 | [`docs/logs/`](docs/logs/) |
| 3월부터 11월까지 흐름 | [프로젝트 연혁](docs/PROJECT_HISTORY.md) |
| AI가 틀린 것과 고친 것 | [AI 사실 확인](docs/AI_FACT_CHECK.md) |

### 핵심 결과 한눈에

| 측정 | 값 | 쉬운 말로 |
|---|---|---|
| 세게 두드렸을 때 최대 전압 | **1.13 V** | 건전지 하나보다 조금 낮지만, 아주 잠깐만 |
| 두드린 뒤 울림 | **약 3.3 kHz** | 작은 종처럼 1초에 3,300번 떨림 = *공진* |
| 손으로 누름 | **1.1–1.3 V, 약 0.1초** | 매끈한 봉우리 하나. 누름은 울림보다 수백 배 느려서 '종' 효과를 못 씀 |
| 누름 1회 에너지 | **약 15 nJ** | ½·C·V² (C ≈ 20 nF, 데이터시트값) |

### 정직하게 밝혀 두는 것

- **실측은 9월 11일 무부하 측정 하나뿐**입니다. 부하저항 실험, 정전용량 측정, 축전 실험, 5×4 타일은 설계만 되어 있고 아직 하지 않았습니다.
- **틀린 것을 숨기지 않습니다.** 철회한 주장(잘못된 계수로 힘을 역산한 것, USB 전원으로 켜진 LED를 발전 증거로 본 것 등)은
  [보고서 §2-6](docs/research_report_ko.md#2-6-다시-분석해서-바로잡은-것)에 모두 있습니다.
- **AI 활용.** 2026년 3–11월 Claude(여러 모델 버전)를 튜터·코딩 도우미로 썼습니다. 2026-11-13에 프로젝트의 모든 AI 대화를
  원 출처와 대조해 다시 확인했고, 틀린 내용과 고친 위치를 [AI 사실 확인](docs/AI_FACT_CHECK.md)에 정리했습니다.
  문서 안의 정정은 **⚠️정정(2026-11-13)**으로 표시했습니다.

### 직접 재현하기

```bash
python analyze_v2.py                 # data/의 실측 CSV → 결과 출력, figures/ 그래프 저장
python calc/verify_composition.py    # 제안 조성의 전하 균형·허용인자·순위 검증
```

측정을 다시 하려면 아두이노 우노, 27 mm 압전 디스크, 전선 2개면 됩니다(빨강 → A0, 검정 → GND).
⚠️ 이렇게 직접 연결한 상태에서는 **손으로만** 누르세요. 발로 밟으면 수십 V가 나와 아두이노 핀이 망가질 수 있습니다(발 실험은 `arduino/`의 보호 회로 사용).
자세한 방법은 [`arduino/README.md`](arduino/README.md)에 있습니다.

4명의 학생 팀이 진행했습니다(실험 설계·소프트웨어 / 선행 조사·3D 하우징 / 데이터 분석 / 보고서). 라이선스: [MIT](LICENSE).
