// [저장소 메모] v2 — 키트 부품판(바이어스 10 kΩ x5 = 50 kΩ씩). 주의: 실효 부하가 25 kΩ 이하라
//   시정수 25 kΩ x 20 nF = 0.5 ms 로 0.1초 누름 펄스가 대부분 깎인다(MΩ 영역은 못 잰다).
// [저장소 메모] 2026-09-18 실험대(회로 A/B/C)용으로 설계. 하드웨어에서 실행된 기록·데이터는 없다.
//   2026-11-13 5x4 타일 설계에서 '2.5 V 바이어스' 방식은 '디스크마다 전파 정류' 방식으로 대체됐다.

// piezo_A_load (2026-09-18)
// [회로 A] 2.5V 바이어스 + 부하저항 — 타격 링다운 / 느린 압박 측정
//
// 회로:  5V --[R1 1M]--+--[R2 1M]-- GND
//                      |
//                      +-- A0
//                      +-- 압전소자(+)     압전소자(-) -- GND
//                      +-- R_load -------- GND      (가변저항 또는 고정저항)
//
//        8번 핀 -> 220Ω -> LED(+) -> LED(-) -> GND   (선택)
//        ※ 이 LED는 아두이노 전원으로 켜지는 트리거 표시등일 뿐,
//           압전소자가 발전한 전기로 켜지는 것이 아니다. 증거로 쓰면 안 된다.
//
// 확인 포인트: 전원을 넣고 's'를 쳤을 때 baseline이 500~525여야 정상.
//              9 근처면 바이어스가 안 걸린 것이므로 배선부터 고칠 것.
//
// 시리얼 명령 (500000 baud)
//   t        : 타격 트리거 모드 (기본)
//   p        : 느린 압박 모드 (200 Hz 연속) — 보행 모사
//   L10000   : 부하저항 값을 10000 Ω으로 기록 (조건 바꿀 때마다 필수)
//   r        : 베이스라인 재측정
//   s        : 현재 설정 출력

// ===================== 캡처 설정 =====================

const int   LED_PIN    = 8;
const int   N_BUF      = 600;      // 한 번에 저장할 전체 샘플 수
const int   N_POST     = 480;      // 트리거 이후 샘플 수
const int   TRIG_DELTA = 30;       // 이만큼(ADC 단위) 흔들리면 두드림으로 판정
const float VREF       = 5.0;      // 아두이노 기준전압
// 바이어스 저항 1개(=한쪽 체인)의 값.
// 스타터 키트에는 1MΩ이 없으므로 10kΩ 5개를 직렬로 이어 50kΩ을 만든다.
// 멀티미터가 있으면 실측값으로 바꿀 것.
const long  R_BIAS     = 50000L;   // 10kΩ x 5 직렬

// ===================== 내부 변수 =====================

uint16_t buf[N_BUF];
uint16_t baseline = 0;
float    dtUs = 0;
uint16_t eventId = 0;
long     rLoad = 0;                // 0 = 부하저항을 빼놓은 조건
bool     pressMode = false;        // false=트리거, true=느린 압박

inline uint16_t fastRead() {
  ADCSRA |= (1 << ADSC);
  while (ADCSRA & (1 << ADSC)) { }
  return ADC;
}

// 고임피던스 대응: 첫 변환은 버리고 두 번째 값을 쓴다
inline uint16_t safeRead() { fastRead(); return fastRead(); }

void setup() {
  Serial.begin(500000);
  while (!Serial) { }
  Serial.setTimeout(50);

  pinMode(LED_PIN, OUTPUT);

  ADMUX  = (1 << REFS0);                   // 기준전압 AVCC, 채널 A0
  ADCSRA = (1 << ADEN) | (1 << ADPS2);     // ADC 켜기, 분주비 16

  calibrateDt();
  measureBaseline();
  printSettings();
  Serial.println(F("mode,event,n,t_us,adc_raw,v,R_load"));
}

void calibrateDt() {
  const int N = 2000;
  uint32_t t0 = micros();
  for (int i = 0; i < N; i++) fastRead();
  uint32_t t1 = micros();
  dtUs = (float)(t1 - t0) / N;
}

void measureBaseline() {
  uint32_t sum = 0;
  for (int i = 0; i < 1000; i++) sum += safeRead();
  baseline = sum / 1000;
}

// 압전소자가 실제로 보는 부하 = R_load 와 (R1//R2) 의 병렬
float effLoad() {
  float rb = (float)R_BIAS / 2.0;          // 교류 입장에서 R1과 R2는 병렬
  if (rLoad <= 0) return rb;
  return 1.0 / (1.0 / (float)rLoad + 1.0 / rb);
}

void printSettings() {
  Serial.print(F("# piezo_A_load | baseline=")); Serial.print(baseline);
  Serial.print(F(" (")); Serial.print(baseline * (VREF / 1023.0), 3); Serial.print(F(" V)"));
  Serial.print(F(" | dt_us="));  Serial.print(dtUs, 3);
  Serial.print(F(" | fs_Hz="));  Serial.print(1000000.0 / dtUs, 0);
  Serial.print(F(" | R_load=")); Serial.print(rLoad);
  Serial.print(F(" | R_eff="));  Serial.print(effLoad(), 0);
  Serial.print(F(" | mode="));   Serial.println(pressMode ? F("press") : F("trigger"));

  if (baseline < 450 || baseline > 575) {
    Serial.println(F("# [경고] baseline이 512 부근이 아닙니다. 바이어스 배선을 확인하세요."));
  }
}

// ADC 숫자 -> 바이어스 기준의 부호 있는 전압(V)
float toVolt(uint16_t adc) {
  return ((float)adc - (float)baseline) * (VREF / 1023.0);
}

void loop() {
  handleCommand();
  if (pressMode) runPress();
  else           runTrigger();
}

void handleCommand() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'r') {
    measureBaseline();
    Serial.print(F("# rebaseline -> ")); Serial.println(baseline);
  } else if (c == 'L') {
    rLoad = Serial.parseInt();
    Serial.print(F("# R_load -> ")); Serial.print(rLoad);
    Serial.print(F(" | R_eff -> ")); Serial.println(effLoad(), 0);
  } else if (c == 't') {
    pressMode = false; printSettings();
  } else if (c == 'p') {
    pressMode = true;  printSettings();
  } else if (c == 's') {
    printSettings();
  }
}

// ---------- 타격 링다운 ----------
void runTrigger() {
  int wi = 0;
  bool fired = false;
  int post = 0;

  while (true) {
    uint16_t v = fastRead();
    buf[wi] = v;
    wi++;
    if (wi >= N_BUF) wi = 0;

    if (!fired) {
      int16_t d = (int16_t)v - (int16_t)baseline;
      if (d < 0) d = -d;
      if (d >= TRIG_DELTA) {
        fired = true;
        digitalWrite(LED_PIN, HIGH);   // 트리거 표시등 (아두이노 전원)
      }
    } else {
      post++;
      if (post >= N_POST) break;
    }
    if (!fired && (wi & 0x7F) == 0 && Serial.available()) return;
  }

  digitalWrite(LED_PIN, LOW);
  eventId++;
  dumpBuffer(wi);
}

void dumpBuffer(int oldest) {
  int   trigIdx = N_BUF - N_POST;
  float reff = effLoad();
  float vmax = -99, vmin = 99, energy = 0;
  int   clipLow = 0, clipHigh = 0;

  for (int i = 0; i < N_BUF; i++) {
    int idx = oldest + i;
    if (idx >= N_BUF) idx -= N_BUF;

    uint16_t adc = buf[idx];
    float v = toVolt(adc);
    float t_us = (i - trigIdx) * dtUs;

    if (v > vmax) vmax = v;
    if (v < vmin) vmin = v;
    if (adc == 0)    clipLow++;
    if (adc >= 1023) clipHigh++;
    energy += v * v / reff * (dtUs * 1e-6);   // E = ∫ v²/R dt

    Serial.print(F("t,"));
    Serial.print(eventId);     Serial.print(',');
    Serial.print(i - trigIdx); Serial.print(',');
    Serial.print(t_us, 1);     Serial.print(',');
    Serial.print(adc);         Serial.print(',');
    Serial.print(v, 4);        Serial.print(',');
    Serial.println(rLoad);
  }

  Serial.print(F("# event "));     Serial.print(eventId);
  Serial.print(F(" | R_load="));   Serial.print(rLoad);
  Serial.print(F(" | R_eff="));    Serial.print(reff, 0);
  Serial.print(F(" | Vmax="));     Serial.print(vmax, 4);
  Serial.print(F(" | Vmin="));     Serial.print(vmin, 4);
  Serial.print(F(" | P_peak_W=")); Serial.print(vmax * vmax / reff, 9);
  Serial.print(F(" | E_J="));      Serial.print(energy, 12);
  Serial.print(F(" | clip="));     Serial.print(clipLow + clipHigh);
  Serial.print('/');               Serial.println(N_BUF);

  if (clipLow + clipHigh > N_BUF / 100) {
    Serial.println(F("# [경고] 클리핑 발생. 바이어스를 확인하거나 더 약하게 타격하세요."));
  }
}

// ---------- 느린 압박 (보행 모사) ----------
// 천천히 누르고 2초 유지 후 떼기. 뗄 때의 지수 감쇠에서 tau = R_eff x C_p 를 얻는다.
void runPress() {
  static uint32_t n = 0;
  static uint32_t nextUs = 0;
  if (nextUs == 0) nextUs = micros();

  while ((int32_t)(micros() - nextUs) < 0) { }
  nextUs += 5000;                       // 200 Hz

  uint16_t adc = safeRead();
  float v = toVolt(adc);

  Serial.print(F("p,0,"));
  Serial.print(n);           Serial.print(',');
  Serial.print(n * 5000UL);  Serial.print(',');
  Serial.print(adc);         Serial.print(',');
  Serial.print(v, 4);        Serial.print(',');
  Serial.println(rLoad);
  n++;
}
