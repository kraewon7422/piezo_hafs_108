// [저장소 메모] 2026-09-18 실험대(회로 A/B/C)용으로 설계. 하드웨어에서 실행된 기록·데이터는 없다.
//   2026-11-13 5x4 타일 설계에서 '2.5 V 바이어스' 방식은 '디스크마다 전파 정류' 방식으로 대체됐다.
//   이 파일은 A/B/C를 한 스케치에 모은 통합판. 회로별로 나눈 판은 piezo_A/B/C_*.ino.

// piezo_capture_v2 (2026-09-18)
// 2.5V 바이어스 + 부하저항 + 정류축전 + C_p 실측 통합 버전
//
// [회로 A] 바이어스 + 가변부하  (모드 t, p)
//   5V --[R1 1M]--+--[R2 1M]-- GND
//                 |
//                 +-- A0
//                 +-- PZT(+)   PZT(-) -- GND
//                 +-- R_load -- GND     (가변저항 또는 고정저항)
//
// [회로 B] C_p 실측            (모드 m)
//   D2 --[R_ref 1M]--+-- A0
//                    +-- PZT(+)   PZT(-) -- GND
//   ※ 바이어스 저항 2개는 반드시 뽑고 진행
//
// [회로 C] 반파정류 + 축전      (모드 c, d)
//   PZT(+) --|>|-- +-- A0
//            D1    +-- C_store(104) -- GND
//   PZT(-) ---------------- GND
//   D3 --[1k]-- A0 노드  (방전용, 평소 INPUT)
//
// 시리얼 명령 (500000 baud)
//   t : 트리거 캡처 모드 (타격 링다운, 62 kHz)
//   p : 느린 압박 모드   (누르기/떼기, 200 Hz)  <- 보행 모사
//   m : C_p 측정 모드    (RC 충전곡선)
//   c : 축전 감시 모드   (커패시터 전압, 10 Hz)
//   d : 축전 커패시터 방전
//   r : 베이스라인 재측정
//   s : 현재 설정 출력
//   L : 부하저항 값 입력 (예: L10000 <엔터>)  -> CSV 전 행에 기록됨

const int PIN_DISCHARGE = 3;    // 축전 커패시터 방전용
const int PIN_DRIVE     = 2;    // C_p 측정 시 구동핀
const int N_BUF   = 600;
const int N_POST  = 480;
const int TRIG_DELTA = 30;
const float VREF  = 5.0;
const float LSB   = VREF / 1023.0;

uint16_t buf[N_BUF];
uint16_t baseline = 512;        // 바이어스 후에는 512 부근이어야 정상
float    dtUs = 0;
uint16_t eventId = 0;
char     mode = 't';
long     rLoad = 0;             // 0 = 개방(바이어스만)

inline uint16_t fastRead() {
  ADCSRA |= (1 << ADSC);
  while (ADCSRA & (1 << ADSC)) { }
  return ADC;
}

// 고임피던스 소스 대응: 첫 변환은 버리고 두 번째를 쓴다
inline uint16_t safeRead() { fastRead(); return fastRead(); }

void setADCFast()  { ADCSRA = (1 << ADEN) | (1 << ADPS2); }                                // 분주 16
void setADCSlow()  { ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0); }  // 분주 128

void setup() {
  Serial.begin(500000);
  while (!Serial) { }
  pinMode(PIN_DRIVE, INPUT);          // 평소에는 하이임피던스
  pinMode(PIN_DISCHARGE, INPUT);
  ADMUX  = (1 << REFS0);              // AVCC 기준, A0
  setADCFast();
  calibrateDt();
  measureBaseline();
  printSettings();
  Serial.println(F("mode,event,n,t_us,adc_raw,v_signed,R_load"));
}

void calibrateDt() {
  const int N = 2000;
  uint32_t t0 = micros();
  for (int i = 0; i < N; i++) fastRead();
  dtUs = (float)(micros() - t0) / N;
}

void measureBaseline() {
  uint32_t sum = 0;
  for (int i = 0; i < 1000; i++) sum += safeRead();
  baseline = sum / 1000;
}

void printSettings() {
  Serial.print(F("# v2 | mode="));   Serial.print(mode);
  Serial.print(F(" | baseline="));   Serial.print(baseline);
  Serial.print(F(" ("));             Serial.print(baseline * LSB, 3); Serial.print(F(" V)"));
  Serial.print(F(" | dt_us="));      Serial.print(dtUs, 3);
  Serial.print(F(" | fs_Hz="));      Serial.print(1000000.0 / dtUs, 0);
  Serial.print(F(" | R_load="));     Serial.println(rLoad);
}

// 바이어스 기준으로 부호 있는 전압 (음 반주기도 살아있음)
float toVolt(uint16_t adc) { return ((float)adc - (float)baseline) * LSB; }
// 절대 전압 (축전 커패시터처럼 GND 기준으로 읽을 때)
float toAbs(uint16_t adc)  { return (float)adc * LSB; }

void loop() {
  handleCommand();
  switch (mode) {
    case 't': runTrigger();   break;
    case 'p': runSlowPress(); break;
    case 'c': runCapWatch();  break;
    case 'm': runCpMeasure(); break;
    default:  break;                   // 'x' = 대기
  }
}

void handleCommand() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'L') {                       // L10000 형식으로 부하저항 값 기록
    rLoad = Serial.parseInt();
    Serial.print(F("# R_load -> ")); Serial.println(rLoad);
  } else if (c == 'r') {
    measureBaseline(); printSettings();
  } else if (c == 's') {
    printSettings();
  } else if (c == 'd') {
    dischargeCap();
  } else if (c == 't' || c == 'p' || c == 'c' || c == 'm') {
    mode = c;
    if (mode == 'c') setADCSlow(); else setADCFast();
    calibrateDt();
    printSettings();
  }
}

// ---------- 모드 t : 타격 링다운 ----------
void runTrigger() {
  int wi = 0, post = 0;
  bool fired = false;
  while (true) {
    uint16_t v = fastRead();
    buf[wi] = v;
    if (++wi >= N_BUF) wi = 0;
    if (!fired) {
      int16_t d = (int16_t)v - (int16_t)baseline;
      if (d < 0) d = -d;
      if (d >= TRIG_DELTA) fired = true;
    } else if (++post >= N_POST) break;
    if (!fired && (wi & 0x7F) == 0 && Serial.available()) return;
  }
  eventId++;
  dumpBuffer(wi);
}

void dumpBuffer(int oldest) {
  int trigIdx = N_BUF - N_POST;
  float vmax = -99, vmin = 99, e = 0;
  for (int i = 0; i < N_BUF; i++) {
    int idx = oldest + i;  if (idx >= N_BUF) idx -= N_BUF;
    float v = toVolt(buf[idx]);
    if (v > vmax) vmax = v;
    if (v < vmin) vmin = v;
    if (rLoad > 0) e += v * v / (float)rLoad * (dtUs * 1e-6);   // ∫v²/R dt
    Serial.print(F("t,")); Serial.print(eventId);  Serial.print(',');
    Serial.print(i - trigIdx);                     Serial.print(',');
    Serial.print((i - trigIdx) * dtUs, 1);         Serial.print(',');
    Serial.print(buf[idx]);                        Serial.print(',');
    Serial.print(v, 4);                            Serial.print(',');
    Serial.println(rLoad);
  }
  Serial.print(F("# event ")); Serial.print(eventId);
  Serial.print(F(" | Vmax=")); Serial.print(vmax, 4);
  Serial.print(F(" | Vmin=")); Serial.print(vmin, 4);
  Serial.print(F(" | R_load=")); Serial.print(rLoad);
  if (rLoad > 0) {
    Serial.print(F(" | P_peak_W=")); Serial.print(vmax * vmax / (float)rLoad, 9);
    Serial.print(F(" | E_J="));      Serial.print(e, 12);
  }
  Serial.println();
}

// ---------- 모드 p : 느린 압박 (보행 모사) ----------
void runSlowPress() {
  static uint32_t n = 0, nextUs = 0;
  if (nextUs == 0) nextUs = micros();
  while ((int32_t)(micros() - nextUs) < 0) { }
  nextUs += 5000;                       // 200 Hz
  uint16_t adc = safeRead();
  Serial.print(F("p,0,"));  Serial.print(n);       Serial.print(',');
  Serial.print(n * 5000UL); Serial.print(',');
  Serial.print(adc);        Serial.print(',');
  Serial.print(toVolt(adc), 4); Serial.print(',');
  Serial.println(rLoad);
  n++;
}

// ---------- 모드 c : 축전 커패시터 감시 ----------
void runCapWatch() {
  static uint32_t n = 0, nextMs = 0;
  if (nextMs == 0) nextMs = millis();
  while ((int32_t)(millis() - nextMs) < 0) { }
  nextMs += 100;                        // 10 Hz
  uint16_t adc = safeRead();
  Serial.print(F("c,0,")); Serial.print(n);        Serial.print(',');
  Serial.print(n * 100000UL); Serial.print(',');
  Serial.print(adc);       Serial.print(',');
  Serial.print(toAbs(adc), 4); Serial.print(',');  // GND 기준 절대 전압
  Serial.println(rLoad);
  n++;
}

void dischargeCap() {
  pinMode(PIN_DISCHARGE, OUTPUT);
  digitalWrite(PIN_DISCHARGE, LOW);
  delay(300);
  pinMode(PIN_DISCHARGE, INPUT);
  Serial.println(F("# cap discharged"));
}

// ---------- 모드 m : C_p 실측 (RC 충전곡선) ----------
// D2 --[R_ref]-- A0 -- PZT -- GND  로 배선한 뒤 실행.
// 1) D2를 LOW로 완전 방전 -> 2) HIGH로 올리고 A0를 빠르게 샘플링
// 3) 파이썬에서 V(t)=V_inf(1-exp(-t/tau)) 피팅 -> C_p = tau / R_ref
// 샘플 간격 50 us x 400점 = 20 ms 관측창.
// R_ref=1M, C_p=15nF -> tau=15ms (1.3tau 관측, 첫 tau에 300점)
// R_ref=100k, C_p=15nF -> tau=1.5ms (13tau 관측, 첫 tau에 30점)
// 둘 다 피팅 가능. 62 kHz 그대로 쓰면 6.4 ms밖에 못 봐서 1M에서는 피팅이 안 된다.
void runCpMeasure() {
  const int N = 400;
  const uint16_t CP_DT_US = 50;
  static uint16_t rec[400];
  pinMode(PIN_DRIVE, OUTPUT);
  digitalWrite(PIN_DRIVE, LOW);
  delay(500);                            // 완전 방전
  setADCFast();
  digitalWrite(PIN_DRIVE, HIGH);
  uint32_t t0 = micros(), next = t0;
  for (int i = 0; i < N; i++) {
    while ((int32_t)(micros() - next) < 0) { }
    next += CP_DT_US;
    rec[i] = fastRead();
  }
  digitalWrite(PIN_DRIVE, LOW);
  pinMode(PIN_DRIVE, INPUT);

  Serial.println(F("# Cp charge curve start"));
  for (int i = 0; i < N; i++) {
    Serial.print(F("m,0,")); Serial.print(i);     Serial.print(',');
    Serial.print((float)i * CP_DT_US, 1);         Serial.print(',');
    Serial.print(rec[i]);                         Serial.print(',');
    Serial.print(toAbs(rec[i]), 4);               Serial.print(',');
    Serial.println(rLoad);
  }
  Serial.println(F("# Cp charge curve end  (한 번 더 하려면 m 다시 입력)"));
  mode = 'x';                            // 1회만 실행하고 대기
}
