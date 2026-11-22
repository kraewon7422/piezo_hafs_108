# Measurement sessions — 5×4 tile, 2026-11-21

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

Row voltage = ADC value × VREF ÷ 1023 × (R1 + R2) ÷ R2 = ADC × 0.0538 V with the values in `meta.csv`.

---

# 측정 기록 — 5×4 타일, 2026-11-21

각 측정이 무엇이었는지는 **실험자 기록**입니다(데이터로 짐작한 것이 아님).
손가락 작동 테스트 3개(19:28, 19:29, 20:12), 실제 밟기 3개(20:23, 20:35, 20:52).

- **올리지 않은 측정**: `192928` — 시작 2초 잡음 기준선을 재는 동안 1행이 눌려(1.02 V) 이후 모든 에너지 값에서 빼는 기준이 틀어졌고, 깨진 줄 13개, 43분 대부분이 빈 시간
- **`192827/summary.txt`의 "직접 센 인원 10명 대비 −50 %"**: 분석할 때 10을 입력했기 때문에 생긴 줄입니다. 손가락 테스트였으므로 사람 수 비교는 해당되지 않습니다
- **`raw.csv`는 용량 때문에 올리지 않았습니다.** `raw_serial.txt`의 R 줄과 같은 내용이라 `python logger.py --replay 폴더/raw_serial.txt`로 다시 만들 수 있습니다
