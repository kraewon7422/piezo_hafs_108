// [저장소 메모] v2 — 키트 부품판(R_ref = 10 kΩ x10 직렬 = 100 kΩ, 20 µs 간격).
// [저장소 메모] 2026-09-18 실험대(회로 A/B/C)용으로 설계. 하드웨어에서 실행된 기록·데이터는 없다.
//   2026-11-13 5x4 타일 설계에서 '2.5 V 바이어스' 방식은 '디스크마다 전파 정류' 방식으로 대체됐다.

// piezo_B_cp (2026-09-18)
// [회로 B] 압전소자 정전용량 C_p 실측 — RC 충전곡선법
//
// 회로:  D2 --[R_ref]--+-- A0
//                      +-- 압전소자(+)     압전소자(-) -- GND
//
// ※ 회로 A의 바이어스 저항 2개와 부하저항은 반드시 뽑고 진행할 것.
//    남아 있으면 R_ref와 병렬로 붙어 tau가 작게 나오고 C_p가 과소평가된다.
// ※ 측정 중 압전소자를 건드리면 압전 전압이 충전곡선에 얹혀 피팅이 망가진다.
//
// 원리:  D2를 LOW로 완전 방전 -> HIGH로 올려 R_ref를 통해 압전소자를 충전
//        V(t) = 5V x (1 - e^(-t/tau)),  tau = R_ref x C_p
//        63.2%(=3.16V) 도달 시각이 곧 tau. 스케치가 그 자리에서 추정해 준다.
//        정밀한 값은 CSV를 analyze_load_v2.py 로 지수 피팅해서 얻는다.
//
// 시리얼 명령 (500000 baud)
//   m : 충전곡선 1회 측정 (3회 반복 권장)
//   d : 샘플 간격 전환 20 / 100 / 500 us
//   s : 현재 설정 출력

// ===================== 측정 설정 =====================

const int   PIN_DRIVE = 2;
const float VREF      = 5.0;
const int   N_REC     = 400;          // 기록할 샘플 수

// R_ref는 반드시 멀티미터로 잰 실측값으로 바꿀 것. 이 값의 오차가 곧 C_p 오차다.
const float R_REF = 100000.0;         // 10kΩ x 10 직렬 (키트에 1MΩ이 없다)

// ===================== 내부 변수 =====================

uint16_t rec[N_REC];
uint16_t sampleUs = 20;               // 20 us x 400 = 8 ms 관측창 (R_ref=100k 기준 5.3 tau)
uint16_t runId = 0;

inline uint16_t fastRead() {
  ADCSRA |= (1 << ADSC);
  while (ADCSRA & (1 << ADSC)) { }
  return ADC;
}

void setup() {
  Serial.begin(500000);
  while (!Serial) { }
  Serial.setTimeout(50);

  pinMode(PIN_DRIVE, INPUT);           // 평소에는 하이임피던스로 띄워 둔다

  ADMUX  = (1 << REFS0);
  ADCSRA = (1 << ADEN) | (1 << ADPS2);

  printSettings();
  Serial.println(F("mode,run,n,t_us,adc_raw,v,R_ref"));
  Serial.println(F("# 'm' 을 눌러 측정을 시작하세요."));
}

void printSettings() {
  float windowMs = (float)sampleUs * (float)N_REC / 1000.0;
  Serial.print(F("# piezo_B_cp | R_ref=")); Serial.print(R_REF, 0);
  Serial.print(F(" | dt_us="));             Serial.print(sampleUs);
  Serial.print(F(" | window_ms="));         Serial.print(windowMs, 1);
  Serial.print(F(" | 측정가능 tau <= "));     Serial.print(windowMs, 1);
  Serial.println(F(" ms"));
}

float toAbs(uint16_t adc) { return (float)adc * (VREF / 1023.0); }

void loop() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'm') {
    measureCp();
  } else if (c == 'd') {
    if      (sampleUs == 20)  sampleUs = 100;
    else if (sampleUs == 100) sampleUs = 500;
    else                      sampleUs = 20;
    printSettings();
  } else if (c == 's') {
    printSettings();
  }
}

void measureCp() {
  // 1) 완전 방전
  pinMode(PIN_DRIVE, OUTPUT);
  digitalWrite(PIN_DRIVE, LOW);
  delay(500);

  // 2) 충전 시작과 동시에 일정 간격으로 기록
  uint32_t next = micros();
  digitalWrite(PIN_DRIVE, HIGH);
  for (int i = 0; i < N_REC; i++) {
    while ((int32_t)(micros() - next) < 0) { }
    next += sampleUs;
    rec[i] = fastRead();
  }

  // 3) 뒷정리 — 다시 방전시키고 핀을 띄운다
  digitalWrite(PIN_DRIVE, LOW);
  delay(200);
  pinMode(PIN_DRIVE, INPUT);

  runId++;
  dumpCurve();
}

void dumpCurve() {
  for (int i = 0; i < N_REC; i++) {
    Serial.print(F("m,"));
    Serial.print(runId);                  Serial.print(',');
    Serial.print(i);                      Serial.print(',');
    Serial.print((uint32_t)i * sampleUs); Serial.print(',');
    Serial.print(rec[i]);                 Serial.print(',');
    Serial.print(toAbs(rec[i]), 4);       Serial.print(',');
    Serial.println(R_REF, 0);
  }
  estimateTau();
}

// 63.2% 도달 시각으로 tau를 현장 추정한다.
// V_inf 는 구동핀 HIGH 전압(약 5V)으로 둔다 — 관측창이 tau보다 짧아도 성립한다.
void estimateTau() {
  const uint16_t target = (uint16_t)(0.632 * 1023.0);   // 5V의 63.2% = ADC 646

  int hit = -1;
  for (int i = 0; i < N_REC; i++) {
    if (rec[i] >= target) { hit = i; break; }
  }

  Serial.print(F("# run "));    Serial.print(runId);
  Serial.print(F(" | V_end=")); Serial.print(toAbs(rec[N_REC - 1]), 3); Serial.print(F(" V"));

  if (hit <= 0) {
    Serial.println(F(" | tau 추정 실패: 관측창 안에서 63.2%에 도달하지 못했습니다."));
    Serial.println(F("#   -> 'd' 로 샘플 간격을 늘리거나, R_ref를 더 작은 값으로 바꾸세요."));
    return;
  }

  float tauUs = (float)hit * (float)sampleUs;
  float cp    = (tauUs * 1e-6) / R_REF;                 // C = tau / R

  Serial.print(F(" | tau=")); Serial.print(tauUs / 1000.0, 3); Serial.print(F(" ms"));
  Serial.print(F(" | Cp="));  Serial.print(cp * 1e9, 2);       Serial.println(F(" nF (현장 추정)"));
  Serial.println(F("#   정밀값은 CSV를 analyze_load_v2.py 로 지수 피팅해서 확인하세요."));

  if (hit < 5) {
    Serial.println(F("# [경고] 63.2% 도달이 5샘플 이내입니다. 분해능 부족 — 'd' 로 간격을 줄이세요."));
  }
}
