// piezo_capture_simple (2026-09-11)
// 압전소자 직결(A0) + LED(8번 핀) 버전
// 분압기/부하저항 없이 압전소자 양단을 바로 A0, GND에 연결한 상태 기준
//
// 회로: 압전소자 (+) -> A0,  압전소자 (-) -> GND
//       8번 핀 -> 저항(220Ω) -> LED(+) -> LED(-) -> GND
//
// ※ 주의: 8번 핀 LED는 "트리거 표시등"이며 아두이노 USB 전원으로 켜진다.
//         압전소자가 발전한 전기로 켜지는 것이 아니다.

// ===================== 캡처 설정 =====================

const int LED_PIN = 8;
const int N_BUF  = 600;   // 한 번에 저장할 전체 샘플 수
const int N_POST = 480;   // 트리거 이후 샘플 수
const int TRIG_DELTA = 30; // 이만큼(ADC 단위) 흔들리면 두드림으로 판정
const float VREF = 5.0;   // 아두이노 기준전압

// ===================== 내부 변수 =====================

uint16_t buf[N_BUF];
uint16_t baseline = 0;
float    dtUs = 0;
uint16_t eventId = 0;
bool     continuousMode = false;

inline uint16_t fastRead() {
  ADCSRA |= (1 << ADSC);
  while (ADCSRA & (1 << ADSC)) { }
  return ADC;
}

void setup() {
  Serial.begin(500000);
  while (!Serial) { }

  pinMode(LED_PIN, OUTPUT);

  ADMUX  = (1 << REFS0);                   // 기준전압 AVCC, 채널 A0
  ADCSRA = (1 << ADEN) | (1 << ADPS2);     // ADC 켜기, 분주비 16

  calibrateDt();
  measureBaseline();
  printSettings();
  Serial.println(F("event,n,t_us,adc_raw,v_piezo"));
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
  for (int i = 0; i < 1000; i++) sum += fastRead();
  baseline = sum / 1000;
}

void printSettings() {
  Serial.print(F("# piezo_capture_simple | baseline="));  Serial.print(baseline);
  Serial.print(F(" | dt_us="));      Serial.print(dtUs, 3);
  Serial.print(F(" | fs_Hz="));      Serial.print(1000000.0 / dtUs, 0);
  Serial.print(F(" | trig="));       Serial.print(TRIG_DELTA);
  Serial.print(F(" | mode="));       Serial.println(continuousMode ? F("continuous") : F("trigger"));
}

// ADC 숫자 -> 전압(V), 분압기 없으니 그대로 변환
float toVolt(uint16_t adc) {
  return ((float)adc - (float)baseline) * (VREF / 1023.0);
}

void loop() {
  handleCommand();
  if (continuousMode) runContinuous();
  else               runTrigger();
}

void handleCommand() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'r') {
    measureBaseline();
    Serial.print(F("# rebaseline -> ")); Serial.println(baseline);
  } else if (c == 'c') {
    continuousMode = !continuousMode;
    printSettings();
  } else if (c == 's') {
    printSettings();
  }
}

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
        digitalWrite(LED_PIN, HIGH);   // 두드리는 순간 LED 켜짐 (표시등)
      }
    } else {
      post++;
      if (post >= N_POST) break;
    }
    if (!fired && (wi & 0x7F) == 0 && Serial.available()) return;
  }

  digitalWrite(LED_PIN, LOW);  // 캡처 끝나면 LED 끔
  eventId++;
  dumpBuffer(wi);
}

void dumpBuffer(int oldest) {
  int trigIdx = N_BUF - N_POST;
  float peakV = 0;

  for (int i = 0; i < N_BUF; i++) {
    int idx = oldest + i;
    if (idx >= N_BUF) idx -= N_BUF;

    uint16_t adc = buf[idx];
    float v = toVolt(adc);
    float t_us = (i - trigIdx) * dtUs;

    if (v > peakV) peakV = v;

    Serial.print(eventId);   Serial.print(',');
    Serial.print(i - trigIdx); Serial.print(',');
    Serial.print(t_us, 1);   Serial.print(',');
    Serial.print(adc);       Serial.print(',');
    Serial.println(v, 4);
  }

  Serial.print(F("# event ")); Serial.print(eventId);
  Serial.print(F(" | peak_V="));   Serial.println(peakV, 3);
}

void runContinuous() {
  static uint32_t n = 0;
  static uint32_t nextUs = 0;
  if (nextUs == 0) nextUs = micros();

  while (micros() < nextUs) { }
  nextUs += 1000;

  uint16_t adc = fastRead();
  float v = toVolt(adc);

  Serial.print(F("0,"));
  Serial.print(n);       Serial.print(',');
  Serial.print(n * 1000UL); Serial.print(',');
  Serial.print(adc);     Serial.print(',');
  Serial.println(v, 4);
  n++;
}
