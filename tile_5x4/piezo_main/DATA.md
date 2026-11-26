# Measurement sessions — 5×4 tile, 2026-11-21 (preliminary), 2026-11-23 and 2026-11-26 (cafeteria)

Recorded with `piezo_main.ino` v3.1 + `logger.py` v3.1 (this folder). One folder per run, named `piezo_YYYYMMDD_HHMMSS`
(laptop clock when the logger started). What each run was is **the experimenter's record**; it was not inferred from the data.

| folder | what was done | kept? | recording | raw-sample completeness | dropped samples | corrupted lines | baseline (first 2 s) |
|---|---|---|---|---|---|---|---|
| `piezo_20261121_192827` | finger-press function test (discs pressed one at a time) | ✅ | 0.6 min | 98.5 % | 77 | 0 | clean |
| `piezo_20261121_192928` | finger-press function test | ❌ **not uploaded** | 43.4 min | 99.7 % | 247 | 13 | **row 1 reached 1.02 V while the baseline was being taken** |
| `piezo_20261121_201257` | finger-press function test | ✅ | 9.2 min | 99.7 % | 363 | 1 | clean |
| `piezo_20261121_202319` | stepping on the tile | ✅ | 2.5 min | 95.9 % | 346 | 0 | clean |
| `piezo_20261121_203520` | stepping on the tile (activity in the first ~2 min, then idle) | ✅ | 16.5 min | 99.3 % | 310 | 0 | clean |
| `piezo_20261121_205200` | stepping on the tile | ✅ | 1.7 min | 96.2 % | 122 | 0 | clean |
| `piezo_20261123_134435` | **cafeteria entrance at lunch** — people walked across the tile; 50 crossings counted by hand at the same time | ✅ | 3.8 min | 96.6 % | 407 | 4 | clean |
| `piezo_20261126_130851` | **cafeteria entrance, first-year students walking to lunch** (before the main run); 20 people counted by hand | ✅ | 4.8 min | 98.6 % | 140 | 3 | clean |
| `piezo_20261126_131358` | **cafeteria entrance, first-year students walking to lunch** (main run); not counted by hand — the GUI's 87 is the tile's own count; some students jumped on or stopped on the tile | ✅ | 13.3 min | 96.7 % | 986 | 1 | clean |

- *Raw-sample completeness* = R lines received ÷ (recording time × 500 per s). Missing samples happen mostly while the
  Arduino is sending a long pulse-summary line (see the "sampling and serial speed" row of the assembly manual review).
- `192928` was left out because its noise baseline was taken while a row was pressed (the Arduino subtracts that
  baseline from every later energy value), it has 13 corrupted lines, and it is mostly idle.
- `192827/summary.txt` contains "직접 센 인원 10명 대비 −50 %": `10` was typed into the analysis prompt at the time.
  Because this run was a finger-press test, the pass-vs-person comparison in that line does not apply.

## Files in each folder

| file | content |
|---|---|
| `raw_serial.txt` | every line the Arduino sent, unchanged — the primary record |
| `meta.csv`, `baseline.csv` | settings (VREF, R1, R2, thresholds) and the 2-s noise baseline |
| `pulses.csv` | one row per pulse: duration, row order, per-row peak V / energy µJ / charge nC / clip flag |
| `status.csv` | every 10 s: pulse count, dropped samples, idle noise per row |
| `passes.csv`, `summary.txt` | output of `analyze.py` (pulses less than 1 s apart grouped into one "pass") |
| `columns.txt` | meaning and unit of every column (Korean) |
| `errors.txt` | lines that did not match the format and were skipped |

`raw.csv` (2-ms ADC values) is **not uploaded** to save space — it is exactly the R lines of `raw_serial.txt` and can be
rebuilt: `python logger.py --replay piezo_20261121_205200/raw_serial.txt` (writes a new folder with all CSV files).

- `134435/summary.txt` line "직접 센 인원 50명 대비 통과 수 오차: +2.0%" compares the hand count (50) with the 51 crossings found by `analyze.py`. Totals only — crossings were not time-matched one by one.
- `130851/summary.txt` line "직접 센 인원 20명 대비 통과 수 오차: -15.0%" is the same comparison (20 counted, 17 crossings). `130851/raw_serial.txt` has one garbled line whose timestamp reads 2458 instead of 245884; `tile_results.py` sorts the time axis, which removes it.
- On 11-26 everyone walked one way, towards the cafeteria. Which tile row faced the cafeteria was not recorded.

Row voltage = ADC value × VREF ÷ 1023 × (R1 + R2) ÷ R2 = ADC × 0.0538 V with the values in `meta.csv`.

---

# 측정 기록 — 5×4 타일, 2026-11-21(예비 측정)·2026-11-23·2026-11-26(급식실)

각 측정이 무엇이었는지는 **실험자 기록**입니다(데이터로 짐작한 것이 아님).
11-21: 손가락 작동 테스트 3개(19:28, 19:29, 20:12), 실제 밟기 3개(20:23, 20:35, 20:52).
11-23: 점심시간 급식실 입구에서 사람들이 발판을 밟고 지나간 측정 1개(13:44부터 약 4분). 같은 시간 동안 통과를 손으로 세어 50회를 기록했고, 발판이 센 통과는 51회(총수 차이 +2 %)입니다.
11-26: 1학년 학생들이 점심을 먹으러 급식실로 걸어가는 동안 같은 입구에서 2개. `130851`(13:08, 약 5분)은 지나간 사람을 손으로 세어 20명, 발판은 17회(−15 %). `131358`(13:14, 약 13분)이 본 측정이며 손으로 따로 세지 않았습니다(GUI의 87명은 발판이 센 수). 모두 급식실 쪽 한 방향으로 걸었지만 발판 위에서 뛰거나 멈춘 학생도 있었고, 어느 행이 급식실 쪽이었는지는 기록하지 않았습니다.

- **올리지 않은 측정**: `192928` — 시작 2초 잡음 기준선을 재는 동안 1행이 눌려(1.02 V) 이후 모든 에너지 값에서 빼는 기준이 틀어졌고, 깨진 줄 13개, 43분 대부분이 빈 시간
- **`192827/summary.txt`의 "직접 센 인원 10명 대비 −50 %"**: 분석할 때 10을 입력했기 때문에 생긴 줄입니다. 손가락 테스트였으므로 사람 수 비교는 해당되지 않습니다
- **`raw.csv`는 용량 때문에 올리지 않았습니다.** `raw_serial.txt`의 R 줄과 같은 내용이라 `python logger.py --replay 폴더/raw_serial.txt`로 다시 만들 수 있습니다
