// [저장소 메모] 2026-09-18 실험대(회로 A/B/C)용으로 설계. 하드웨어에서 실행된 기록·데이터는 없다.
//   2026-11-13 5x4 타일 설계에서 '2.5 V 바이어스' 방식은 '디스크마다 전파 정류' 방식으로 대체됐다.
//   다이오드·커패시터가 없어 이 회로는 만들지 못했다.
//   참고: '브리지는 전하가 안 넘어간다'는 설명은 손으로 가볍게 두드린 1.1 V 조건에서만 맞다.
//   발로 밟으면 수십 V가 나올 수 있어 브리지(특히 쇼트키 다이오드)도 쓸 수 있다.

// piezo_C_harvest (2026-09-18)
// [회로 C] 반파 정류 + 축전 — 실제로 회수되는 에너지 측정
//
// 회로:  압전소자(+) --|>|--+-- A0
//                     D1    +-- C_store -- GND
//        압전소자(-) ---------------------- GND
//
//        D3 --[1kΩ]-- A0 노드            (방전용, 평소에는 INPUT으로 띄워 둠)
//
// ※ 다이오드는 띠(캐소드)가 커패시터 쪽을 향해야 한다. 반대면 전혀 충전되지 않는다.
// ※ 이 회로에는 바이어스 저항을 달지 않는다. 커패시터 전압은 항상 양수다.
// ※ 다이오드 4개짜리 전파 브리지는 순방향 강하가 두 번(약 1.2V) 걸려,
//    압전 출력이 1.1V 수준인 지금 조건에서는 전하가 넘어가지 않는다. 반파 1개만 쓴다.
//
// 실험 순서
//   1) 'd' 방전  ->  'b' 누설 대조군 30초 (건드리지 않는다)
//   2) 'd' 방전  ->  'c' 기록 시작  ->  1초에 한 번씩 50회 타격  ->  'c' 정지
//   3) 저장 에너지 E = 1/2 x C x V^2 를 타격 횟수로 나누면 1회당 회수 에너지
//
// 시리얼 명령 (500000 baud)
//   c : 기록 시작/정지 (10 Hz)
//   d : 커패시터 방전
//   b : 누설 대조군 30초 자동 측정
//   s : 현재 설정 출력

// ===================== 측정 설정 =====================

const int   PIN_DISCHARGE = 3;
const float VREF     = 5.0;
const float C_STORE  = 100e-9;     // 실제로 꽂은 커패시터 값. 103이면 10e-9 로 바꿀 것
const int   STEP_ADC = 2;          // 이만큼(ADC 단위) 오르면 타격 1회로 자동 집계

// ===================== 내부 변수 =====================

bool     logging = false;
uint32_t sampleN = 0;
uint16_t lastAdc = 0;
uint16_t hitCount = 0;
uint16_t startAdc = 0;

inline uint16_t fastRead() {
  ADCSRA |= (1 << ADSC);
  while (ADCSRA & (1 << ADSC)) { }
  return ADC;
}

// 커패시터는 고임피던스 소스다. 첫 변환은 버리고 두 번째를 쓴다.
inline uint16_t safeRead() { fastRead(); return fastRead(); }

void setup() {
  Serial.begin(500000);
  while (!Serial) { }
  Serial.setTimeout(50);

  pinMode(PIN_DISCHARGE, INPUT);           // 평소에는 띄워 둔다

  ADMUX  = (1 << REFS0);
  ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);  // 분주비 128 (느리고 정확하게)

  printSettings();
  Serial.println(F("mode,run,n,t_us,adc_raw,v,hits"));
  Serial.println(F("# 'd' 로 방전한 뒤 'b'(대조군) 또는 'c'(기록)로 시작하세요."));
}

void printSettings() {
  Serial.print(F("# piezo_C_harvest | C_store=")); Serial.print(C_STORE * 1e9, 1);
  Serial.print(F(" nF | fs=10 Hz | LSB="));        Serial.print(VREF / 1023.0 * 1000.0, 2);
  Serial.print(F(" mV | 자동집계 문턱="));           Serial.print(STEP_ADC);
  Serial.print(F(" LSB | logging="));              Serial.println(logging ? F("on") : F("off"));
}

float toAbs(uint16_t adc) { return (float)adc * (VREF / 1023.0); }

float energyJ(uint16_t adc) {
  float v = toAbs(adc);
  return 0.5 * C_STORE * v * v;
}

void loop() {
  handleCommand();
  if (logging) runLog();
}

void handleCommand() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'd') {
    dischargeCap();
  } else if (c == 'c') {
    logging = !logging;
    if (logging) {
      sampleN  = 0;
      hitCount = 0;
      startAdc = safeRead();
      lastAdc  = startAdc;
      Serial.print(F("# 기록 시작 | V_start=")); Serial.print(toAbs(startAdc), 4);
      Serial.println(F(" V"));
    } else {
      reportSummary();
    }
  } else if (c == 'b') {
    leakageControl();
  } else if (c == 's') {
    printSettings();
  }
}

void dischargeCap() {
  pinMode(PIN_DISCHARGE, OUTPUT);
  digitalWrite(PIN_DISCHARGE, LOW);
  delay(300);
  pinMode(PIN_DISCHARGE, INPUT);
  Serial.print(F("# 방전 완료 -> ")); Serial.print(toAbs(safeRead()), 4);
  Serial.println(F(" V"));
}

// ---------- 10 Hz 기록 ----------
void runLog() {
  static uint32_t nextMs = 0;
  if (nextMs == 0) nextMs = millis();
  while ((int32_t)(millis() - nextMs) < 0) { }
  nextMs += 100;

  uint16_t adc = safeRead();

  // 전압이 계단식으로 오르면 타격 1회로 집계 (손으로 세는 오차를 없애기 위함)
  if ((int16_t)adc - (int16_t)lastAdc >= STEP_ADC) hitCount++;
  lastAdc = adc;

  Serial.print(F("c,0,"));
  Serial.print(sampleN);            Serial.print(',');
  Serial.print(sampleN * 100000UL); Serial.print(',');
  Serial.print(adc);                Serial.print(',');
  Serial.print(toAbs(adc), 4);      Serial.print(',');
  Serial.println(hitCount);
  sampleN++;
}

void reportSummary() {
  uint16_t adc = safeRead();
  float dE = energyJ(adc) - energyJ(startAdc);

  Serial.println(F("# ---- 기록 정지 ----"));
  Serial.print(F("# V: "));  Serial.print(toAbs(startAdc), 4);
  Serial.print(F(" -> "));   Serial.print(toAbs(adc), 4); Serial.println(F(" V"));
  Serial.print(F("# 누적 저장 에너지 = ")); Serial.print(dE * 1e9, 4); Serial.println(F(" nJ"));
  Serial.print(F("# 자동집계 타격 수 = ")); Serial.println(hitCount);

  if (hitCount > 0 && dE > 0) {
    float per = dE / (float)hitCount;
    Serial.print(F("# 1회당 회수 에너지 = ")); Serial.print(per * 1e9, 5);
    Serial.println(F(" nJ/타격"));
    Serial.print(F("# 0.06W LED를 1초 켜려면 약 ")); Serial.print(0.06 / per, 0);
    Serial.println(F(" 회 타격이 필요합니다."));
  }
  Serial.println(F("# ※ 대조군('b')의 누설분을 빼고 보고할 것. 손으로 센 횟수와도 대조할 것."));
}

// ---------- 누설 대조군 ----------
// 아무것도 하지 않고 30초간 기록한다. 이 구간의 변화가 곧 누설이다.
void leakageControl() {
  Serial.println(F("# ---- 누설 대조군 30초 시작. 아무것도 건드리지 마세요 ----"));
  uint16_t a0 = safeRead();
  uint32_t nextMs = millis();

  for (uint32_t i = 0; i < 300; i++) {          // 10 Hz x 30초
    while ((int32_t)(millis() - nextMs) < 0) { }
    nextMs += 100;
    uint16_t adc = safeRead();

    Serial.print(F("b,0,"));
    Serial.print(i);             Serial.print(',');
    Serial.print(i * 100000UL);  Serial.print(',');
    Serial.print(adc);           Serial.print(',');
    Serial.print(toAbs(adc), 4); Serial.print(',');
    Serial.println(0);
  }

  uint16_t a1 = safeRead();
  Serial.println(F("# ---- 대조군 종료 ----"));
  Serial.print(F("# V: "));  Serial.print(toAbs(a0), 4);
  Serial.print(F(" -> "));   Serial.print(toAbs(a1), 4); Serial.println(F(" V / 30초"));
  Serial.print(F("# 누설 기울기 = "));
  Serial.print((toAbs(a1) - toAbs(a0)) / 30.0 * 1000.0, 4);
  Serial.println(F(" mV/s"));
}
