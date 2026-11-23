# arduino/ — 측정 코드 실행 가이드

압전 디스크(누르면 전기가 나오는 동전 모양 부품)의 전압을 **아두이노 우노**로 읽어 컴퓨터에 CSV(엑셀로 열리는 표 파일)로 저장하는 코드 모음이다.
압전을 전혀 몰라도 따라 할 수 있도록 용어부터 설명한다. (English summary at the bottom.)

> **먼저 알아 둘 것 — 실제 데이터가 있는 것은 하나뿐이다.**
> 2026-09-11 측정(`data/piezo_capture_data-1.csv`)에 쓴 코드는 저장소 맨 위의 `piezo_capture_simple.ino`이다.
> 이 폴더의 나머지 스케치는 설계까지만 했고 **하드웨어에서 돌린 기록이 없다**. 숫자를 인용하기 전에 꼭 직접 시험할 것.
>
> **추가 (2026-11-22):** 5 × 4 타일을 실제로 측정한 코드는 이 폴더의 `v3_array5x4/`가 아니라 고친 판인 v3.1이며, [`../tile_5x4/piezo_main/`](../tile_5x4/piezo_main/)에 측정 데이터와 함께 있다.

---

## 1. 용어 풀이

| 용어 | 쉬운 뜻 |
|---|---|
| 압전 디스크 (PZT 디스크) | 얇은 황동판에 세라믹을 붙인 원판. 휘게 누르면 전압이 생긴다. 이 연구는 지름 27 mm짜리를 쓴다. |
| 아두이노 우노 | 손바닥만 한 작은 컴퓨터 보드. A0~A5 핀으로 0~5 V 전압을 읽는다. |
| 스케치 (.ino) | 아두이노에 올리는 프로그램 파일. |
| ADC | 전압을 숫자로 바꾸는 장치. 우노는 0~5 V를 0~1023으로 바꾼다(1칸 ≈ 4.9 mV). **0 V보다 낮은 전압은 0으로만 읽는다.** |
| 시리얼 (Serial) | 아두이노와 컴퓨터가 USB 선으로 글자를 주고받는 통로. 속도(baud)를 양쪽이 같게 맞춰야 한다. |
| 시리얼 명령 | 시리얼 모니터 입력창에 한 글자(예: `t`)를 보내 아두이노의 동작을 바꾸는 것. |
| 개방전압 | 디스크에 아무것도 연결하지 않았을 때의 전압. 이것만으로는 전력(실제로 쓸 수 있는 전기)을 알 수 없다. |
| 부하저항 R_load | 디스크에 연결해 전기를 "쓰게" 하는 저항. 저항에 걸린 전압 v로 전력 P = v²/R을 구한다. |
| 정전용량 C_p | 디스크가 전기를 담아 두는 능력(축전기처럼). 단위 nF. 같은 크기 상용품 데이터시트 값은 약 20 nF ± 30 %. |
| 시정수 τ = R × C | 저항과 정전용량이 만드는 "전압이 빠지는 데 걸리는 시간". 누름(약 0.1초)보다 짧으면 전압이 깎여 보인다. |
| 바이어스 | 저항 두 개로 A0에 2.5 V 기준점을 만들어 음(−) 전압도 읽게 하는 방법. |
| 정류 / 브리지 정류기 | 다이오드로 −전압을 +로 뒤집는 것. 브리지(다이오드 4개)는 약 0.7~2 V를 잃는다. |
| 클램프 다이오드 / 제너 | 핀에 5 V를 넘는 전압이 들어가지 않게 막는 보호 부품. |
| 분압 | 저항 두 개로 큰 전압을 작게 줄여 읽는 것. 예) 1 MΩ/100 kΩ → 1/11. |

---

## 2. 어떤 실험에 어떤 스케치?

| 폴더 / 파일 | 날짜 | 무엇을 하나 | 상태 |
|---|---|---|---|
| `../piezo_capture_simple.ino` (저장소 맨 위) | 09-11 | 디스크를 A0·GND에 바로 연결해 전압 파형 기록(트리거 62 kHz / 연속 1 kHz) | **실제 사용, 데이터 있음** |
| `v1_capture/piezo_capture_v1.ino` | 09-11 | 분압기 910k/100k + 부하저항용 첫 초안 | v1 — 쓰지 않음. simple로 대체(부품이 없어서) |
| `v1_capture/serial_to_csv_v1.py` | 09-11 | 컴퓨터에서 시리얼 → CSV 저장(파이썬) | v1용. simple 출력에는 헤더 열 수가 안 맞음(파일 맨 위 메모 참고) |
| `v1_capture/receive_csv_v1.ps1` | 09-11 | 설치 없이 윈도우 PowerShell로 CSV 저장 | 받은 줄을 그대로 저장 — simple에도 사용 가능 |
| `v2_bench/piezo_capture_v2.ino` | 09-18 | 회로 A/B/C를 한 스케치에 모은 통합판 | 실행 기록 없음 |
| `v2_bench/piezo_A_load_v1_1Mohm.ino` | 09-18 | 회로 A: 2.5 V 바이어스(1 MΩ×2) + 부하저항, 파형·에너지 | v1 — 키트에 1 MΩ이 없어 v2로 교체 |
| `v2_bench/piezo_A_load_v2_kit10k.ino` | 09-18 | 회로 A 키트판(10 kΩ×5 직렬) | 실행 기록 없음. 실효 부하 ≤ 25 kΩ이라 MΩ 영역은 못 잰다 |
| `v2_bench/piezo_B_cp_v1_1Mohm.ino` | 09-18 | 회로 B: RC 충전 곡선으로 C_p 측정(R_ref 1 MΩ) | v1 — v2로 교체 |
| `v2_bench/piezo_B_cp_v2_kit10k.ino` | 09-18 | 회로 B 키트판(R_ref 100 kΩ = 10 kΩ×10) | 실행 기록 없음 |
| `v2_bench/piezo_C_harvest.ino` | 09-18 | 회로 C: 반파 정류 + 커패시터에 모인 에너지 | 부품이 없어 못 만듦 |
| `v2_bench/pot_measure.ino` | 09-18 | 멀티미터 없이 가변저항 값 읽기 | 보조 |
| `v2_bench/analyze_load_v2.py` | 09-18 | 회로 A/B/C CSV → P–R 곡선, C_p 피팅 | 저장소 맨 위 `analyze_v2.py`와 **다른 스크립트** |
| `v3_array5x4/piezo_array_5x4.ino` | 11-13 | 디스크 20개(5×4) 타일: 행별 발걸음(STEP) + 커패시터 누적(CAP) | 실행 기록 없음(부품 주문 전) |
| `v3_array5x4/logger.py` | 11-13 | 위 스케치 출력을 시간 도장과 함께 CSV로 저장 | 실행 기록 없음 |
| `v3_array5x4/parts_list_2026-11-13.csv` | 11-13 | 타일 부품 목록과 가격 (합계 96,845원, 배송비 별도, 아두이노 포함). 쿠팡 항목은 추정가 | 2026-11-13 기준 |

배선 그림이 있는 안내 페이지: 회로 A/B/C는 `../sim/piezo_bench.html`, 키트 배선표는 `../sim/piezo_wiring.html`, 5×4 타일은 `../tile_5x4/docs/assembly_manual_5x4_v2.html`(조립 매뉴얼).

---

## 3. 배선 요약

**09-11 (simple, 실제 사용)** — 디스크 빨간 선(+) → A0, 검은 선(−) → GND. 8번 핀 → 220 Ω → LED → GND (트리거 표시등; **USB 전원으로 켜지므로 발전의 증거가 아니다**).
⚠ 손으로 누를 때는 1~1.3 V였지만, **발로 밟으면 수십 V가 나올 수 있다.** 이렇게 바로 연결한 채 밟으면 아두이노 핀이 망가질 수 있으니, 발 시험 전에는 직렬 1 MΩ(최소 100 kΩ) + 클램프 다이오드(A0→5V, GND→A0) + A0–GND 10 nF를 넣을 것. 그러면 읽는 값은 개방전압이 아니라 부하가 걸린 전압이 된다.

**09-18 회로 A** — 5V –[R]– A0 –[R]– GND 로 2.5 V 기준점, 디스크(+)를 A0, (−)를 GND, 부하저항을 A0–GND. 처음 `s`를 보냈을 때 baseline이 500~525여야 정상.
**09-18 회로 B** — D2 –[R_ref]– A0, 디스크(+)를 A0, (−)를 GND. 회로 A의 저항은 모두 뺀다.
**09-18 회로 C** — 디스크(+) –|>|– A0, A0–커패시터–GND, D3 –[1 kΩ]– A0 (방전용).

**11-13 5×4 타일** — 디스크마다 브리지 정류기 1개 → 행(5개)마다 병렬 → ROW1~4 → 측정 박스(1 MΩ 직렬 / 100 kΩ GND 쪽 / 클램프 / 10 nF) → A0~A3. 저장 커패시터 47 µF는 10 MΩ/2.2 MΩ 분압으로 A4. 자세한 그림은 `../tile_5x4/docs/assembly_manual_5x4_v2.html`(조립 매뉴얼).
이 타일 코드의 주의점:
- 브리지 정류기가 약 0.7~1 V를 먹는다 → **손가락으로 누르면 0 근처로 읽힐 수 있다. 고장이 아니다.** 발로 시험할 것.
- 행 부하 1.1 MΩ × 디스크 약 20 nF = 시정수 약 22 ms(누름 0.1초보다 짧다) → **A0 값은 개방전압이 아니다**(대략 0.2~0.8배).
- 분해능: 행 전압 기준 1칸 ≈ **53.7 mV** (5 V ÷ 1023 × 11).
- BAT85를 못 구하면 5.1 V 제너보다 **1N4148 두 개**(A핀→5V, GND→A핀)가 측정을 덜 왜곡한다(제너는 1 V에서도 최대 10 µA 샐 수 있음).

---

## 4. Arduino IDE로 올리는 법

1. [Arduino IDE](https://www.arduino.cc/en/software)를 설치하고 우노를 USB로 꽂는다.
2. `.ino` 파일을 연다. **"스케치는 같은 이름의 폴더 안에 있어야 한다"는 창이 뜨면 [확인]** — IDE가 폴더를 만들어 그 파일만 옮긴다.
3. 메뉴 **툴 → 보드 → Arduino Uno**, **툴 → 포트 → COM○** (윈도우 예: COM3, 맥 예: /dev/cu.usbmodem…) 선택. 포트가 안 보이면 USB 선이나 드라이버(CH340 클론 보드) 문제다.
4. 체크(✓) 버튼으로 먼저 **컴파일**만 해 보고, 빨간 오류가 없으면 화살표(→) 버튼으로 **업로드**.
5. 파일 맨 위 상수(저항값, R_LOAD 등)를 **실제로 꽂은 부품 값**으로 고친 뒤 다시 업로드. 멀티미터로 잰 값이면 더 정확하다.
6. 업로드 직후 2초 동안은 디스크를 건드리지 않는다(기준선 측정 중).

## 5. 시리얼 명령 (시리얼 모니터 오른쪽 아래 속도를 맞춘 뒤 한 글자 입력)

| 스케치 | 속도 | 명령 |
|---|---|---|
| `piezo_capture_simple`, `piezo_capture_v1` | 500000 | `r` 기준선 다시 재기, `c` 연속↔트리거 전환, `s` 설정 보기 |
| `piezo_capture_v2` | 500000 | `t` 타격 캡처, `p` 느린 압박(200 Hz), `m` C_p 측정, `c` 축전 감시, `d` 방전, `r` 기준선, `s` 설정, `L10000` 부하저항 값 기록 |
| `piezo_A_load_*` | 500000 | `t`, `p`, `L<옴>`(조건 바꿀 때마다 필수), `r`, `s` |
| `piezo_B_cp_*` | 500000 | `m` 1회 측정(3회 권장), `d` 샘플 간격 20/100/500 µs, `s` |
| `piezo_C_harvest` | 500000 | `c` 기록 시작/정지, `d` 방전, `b` 누설 대조군 30초, `s` |
| `pot_measure` | 9600 | 없음(계속 R_ohm 출력) |
| `piezo_array_5x4` | 115200 | `r` RAW 파형 출력 켜기/끄기 |

## 6. CSV로 저장하기

**시리얼 모니터와 아래 도구는 동시에 쓸 수 없다**(포트를 하나만 잡을 수 있음). 모니터를 닫고 실행한다.

- **방법 1 — 설치 없이 (윈도우):** `v1_capture` 폴더에서
  `powershell -ExecutionPolicy Bypass -File receive_csv_v1.ps1 -Port COM3 -Tag 1M`
  → 아무 키나 누르면 멈추고 `output/piezo_1M_날짜.csv`로 저장. 받은 줄을 그대로 쓰므로 어느 스케치에나 쓸 수 있다.
- **방법 2 — 파이썬:** `pip install pyserial` 후
  `python serial_to_csv_v1.py --list` (포트 목록) → `python serial_to_csv_v1.py --port COM3 --tag 1M` (Ctrl+C로 종료).
  5×4 타일은 `python logger.py COM3` → `piezo_YYYYMMDD_HHMMSS.csv`.
- **방법 3 — 복사·붙여넣기:** 시리얼 모니터 내용을 전체 선택 → 복사 → 메모장에 붙여넣고 `.csv`로 저장. 모니터는 오래된 줄을 지우므로 자주 나눠 저장.

`#`으로 시작하는 줄은 메모(설정·요약)다. 파이썬에서는 `pd.read_csv("파일.csv", comment="#")`로 읽는다.
분석: 회로 A/B/C 데이터는 `python v2_bench/analyze_load_v2.py 파일.csv` (키트판을 썼다면 스크립트 위쪽 `R_REF = 100_000.0`, `R_BIAS_PAR = 25_000.0`으로 바꿀 것). 09-11 데이터 재분석은 저장소 맨 위 `analyze_v2.py`.

---

## English summary

Arduino Uno sketches for reading a 27 mm piezo (PZT) disc. **Only `../piezo_capture_simple.ino` was actually used** (data in `data/`); everything here is design-stage code with no hardware run.

- `v1_capture/` (Sep 11): first draft sketch for a divider + load resistor (unused; compile fix applied as v1.1), and two serial→CSV loggers (Python, or no-install PowerShell that saves lines verbatim).
- `v2_bench/` (Sep 18): circuit A (2.5 V bias + load sweep), B (RC charge curve → C_p), C (half-wave rectify + store), an all-in-one `piezo_capture_v2.ino`, a pot reader, and `analyze_load_v2.py` (P–R curve / C_p fit; *not* the root `analyze_v2.py`). A and B exist as `_v1_1Mohm` and `_v2_kit10k` (starter kit had no 1 MΩ). The bias approach was later replaced by per-disc rectification.
- `v3_array5x4/` (Nov 13): 20-disc tile, per-disc bridge rectifiers, rows on A0–A3 via 1 MΩ/100 kΩ, storage cap on A4. Caveats: bridges drop ~0.7–1 V (hand presses may read ~0), the 22 ms time constant means readings are not open-circuit voltage, and 1 count ≈ 53.7 mV at the row.

Upload: open the `.ino` in Arduino IDE (accept the "move into folder" prompt), Tools → Board → Arduino Uno, pick the port, Verify, Upload. Set the Serial Monitor baud to match the table above. Close the monitor before running a logger. Do not step on a disc wired straight to A0: foot strikes can produce tens of volts.
