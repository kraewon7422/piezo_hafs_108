# May 2026 plan — kept as a record, partly refuted by measurement

These five files are the experiment plan written in May 2026, before any tile was built
(experiment design, data sheet, slide outline, circuit/measurement guide, draft slides).
They are kept unchanged (document author metadata removed) so the project history stays honest.
**Several hypotheses in them were tested on 2026-11-21 and turned out wrong.** Do not quote their numbers as results.

| claim in the plan | what was measured (tile_5x4, 2026-11-21) | verdict |
|---|---|---|
| H4: 4–8 discs + a 0.22 F supercapacitor light a high-brightness LED within 100 steps | median stepping pulse 5.6 µJ into the 1.1 MΩ measuring resistor (20 discs). Charging 0.22 F to 2.5 V needs ½·0.22·2.5² = 0.69 J ≈ 0.69 J ÷ 5.6 µJ ≈ 120 000 pulses even with zero loss | **refuted** |
| slide example "0.22 F charged to 2.5 V ≈ 687 mJ" | arithmetic is right, but that charge level is out of reach (row above) | **unreachable** |
| expected output "tens of µJ to a few mJ per step" | largest single stepping pulse 32 µJ, median 5.6 µJ; no pulse reached 1 mJ. (Per-step energy was not measured — steps were not counted.) | **mJ range not reached** |
| measure the stored energy E = ½·C·V² on a capacitor | the built circuit has no storage capacitor; energy is measured per pulse on a resistor (the plan's "E mode" was dropped for lack of parts) | **method changed** |
| prototype: 8 discs in parallel | built with 20 discs, one bridge per disc, 4 row outputs | **design changed** |
| commercial PaveGen = "d31 bimorph + mechanical amplification" | PaveGen describes its tile as electromagnetic induction, 2–4 J per step (sources in `docs/research_report_ko.md` §9) | **wrong mechanism** |

The 0.22 F / LED claim was already marked impossible on 2026-11-13 from the single-disc data ([`docs/AI_FACT_CHECK.md`](../../../docs/AI_FACT_CHECK.md));
the tile measurement now confirms it with 20 discs.

---

## 2026년 5월 계획 — 기록으로 보관, 일부는 실측으로 반박됨

타일을 만들기 전인 2026년 5월에 쓴 실험 계획입니다(실험설계, 기록시트, PPT 구성안, 회로·측정 가이드, 발표 초안).
연구 과정을 그대로 남기려고 내용은 고치지 않았고, 문서 작성자 정보만 지웠습니다.
**2026-11-21 타일 측정으로 여러 가설이 틀린 것으로 확인됐습니다.** 이 문서의 숫자를 결과로 인용하지 마세요.

| 계획의 주장 | 실측 (tile_5x4, 2026-11-21) | 판정 |
|---|---|---|
| H4: 디스크 4~8개 + 0.22 F로 100걸음 안에 LED 점등 | 밟기 펄스 에너지 중앙값 5.6 µJ(디스크 20개). 0.22 F를 2.5 V로 채우려면 0.69 J ≈ 손실 없이도 약 12만 펄스 | **반박됨** |
| "0.22 F에 2.5 V = 약 687 mJ" 예시 | 계산은 맞지만 도달할 수 없는 값 | **도달 불가** |
| 예상 출력 "보당 수십 µJ ~ 수 mJ" | 가장 큰 펄스 32 µJ, 중앙값 5.6 µJ, 1 mJ에 닿은 펄스 없음(걸음 수는 안 셈) | **mJ 범위 미도달** |
| 커패시터 저장 에너지 ½·C·V²로 측정 | 만든 회로에는 저장 커패시터가 없음 — 저항에서 펄스마다 측정 | **방법 변경** |
| 디스크 8개 병렬 | 디스크 20개, 디스크마다 브리지, 출력 4행 | **설계 변경** |
| 상용 PaveGen = "d31 바이모프 + 기계적 증폭" | PaveGen 자료는 전자기 유도, 걸음당 2–4 J (출처: `docs/research_report_ko.md` §9) | **방식 틀림** |
