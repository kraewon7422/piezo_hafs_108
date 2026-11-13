// [저장소 메모] v1 — 첫 AI 초안(분압기 910k/100k + 부하저항 회로용). 실제 2026-09-11 측정에는 쓰지 않았다.
//   실제로 쓴 코드는 저장소 맨 위의 piezo_capture_simple.ino (디스크를 A0에 바로 연결)이다.
//   v1.1 = 대화 중 적용된 '함수 미리 선언' 수정을 반영한 판. 하드웨어에서 돌린 기록은 없다.

// piezo_capture v1 (2026-09-11)
// v1.1: 함수 프로토타입 추가 (컴파일 오류 수정) / v1: 트리거 기반 고속 캡처 + CSV 출력
//
// 대상 보드 : Arduino Uno / Nano (ATmega328P, 16MHz) 전용
//            ※ Mega/Leonardo/ESP32는 ADC 레지스터가 달라서 그대로는 안 됨
// 회로      : 압전 원판 양단에 (1) 부하저항 R  (2) 분압기 910k+100k 를 병렬 연결
//            분압 중간점 -> A0,  아래쪽 -> GND,  보호 다이오드 2개(A0->5V, GND->A0)

// ===================== 실험할 때마다 고치는 값 =====================

const float R_LOAD = 1000000.0;   // 지금 꽂아둔 부하저항 (Ω). 10k면 10000.0

// ===================== 회로가 바뀌면 고치는 값 =====================

const float R_DIV_TOTAL = 1010000.0;  // 분압기 합 (910k + 100k)
const float DIV_RATIO   = 10.1;       // (910k+100k) / 100k
const float VREF        = 5.0;        // 아두이노 기준전압

// ===================== 캡처 설정 =====================

const int N_BUF  = 600;   // 한 번에 저장할 전체 샘플 수 (SRAM 때문에 700 이하)
const int N_POST = 480;   // 트리거 이후 샘플 수 -> 앞 120개는 밟기 직전 파형
const int TRIG_DELTA = 8; // 이만큼(ADC 단위) 흔들리면 발걸음으로 판정

// ===================== 내부 변수 =====================

uint16_t buf[N_BUF];      // 원형 버퍼 (1200바이트)
uint16_t baseline = 0;    // 가만히 있을 때의 ADC 값
float    dtUs = 0;        // 샘플 하나당 실제 걸린 시간 (µs)
float    rEff = 0;        // 분압기까지 고려한 진짜 부하저항 (Ω)
uint16_t eventId = 0;
bool     continuousMode = false;

// 아래에서 쓰는 함수들을 미리 선언해 둔다 (선언 순서 때문에 나는 오류 방지)
void calibrateDt();
void measureBaseline();
void printSettings();
float toVolt(uint16_t adc);
void handleCommand();
void runTrigger();
void runContinuous();
void dumpBuffer(int oldest);

// ADC를 직접 두드려서 analogRead()보다 빠르게 읽는다
inline uint16_t fastRead() {
  ADCSRA |= (1 << ADSC);              // 변환 시작
  while (ADCSRA & (1 << ADSC)) { }    // 끝날 때까지 대기
  return ADC;
}

void setup() {
  Serial.begin(500000);
  while (!Serial) { }

  ADMUX  = (1 << REFS0);                   // 기준전압 AVCC, 채널 A0
  ADCSRA = (1 << ADEN) | (1 << ADPS2);     // ADC 켜기, 분주비 16 -> ADC클럭 1MHz

  // 분압기도 전류를 조금 먹으므로 병렬 합성저항이 진짜 부하다
  rEff = (R_LOAD * R_DIV_TOTAL) / (R_LOAD + R_DIV_TOTAL);

  calibrateDt();
  measureBaseline();
  printSettings();
  Serial.println(F("event,n,t_us,adc_raw,v_piezo,p_mW"));
}

// 샘플 하나에 실제로 몇 µs 걸리는지 재둔다 (타임스탬프 계산용)
void calibrateDt() {
  const int N = 2000;
  uint32_t t0 = micros();
  for (int i = 0; i < N; i++) fastRead();
  uint32_t t1 = micros();
  dtUs = (float)(t1 - t0) / N;
}

// 아무도 안 밟은 상태의 평균값 = 0V 기준선
void measureBaseline() {
  uint32_t sum = 0;
  for (int i = 0; i < 1000; i++) sum += fastRead();
  baseline = sum / 1000;
}

void printSettings() {
  Serial.print(F("# piezo_capture v1 | baseline="));  Serial.print(baseline);
  Serial.print(F(" | dt_us="));      Serial.print(dtUs, 3);
  Serial.print(F(" | fs_Hz="));      Serial.print(1000000.0 / dtUs, 0);
  Serial.print(F(" | R_load="));     Serial.print(R_LOAD, 0);
  Serial.print(F(" | R_eff="));      Serial.print(rEff, 0);
  Serial.print(F(" | div="));        Serial.print(DIV_RATIO, 2);
  Serial.print(F(" | trig="));       Serial.print(TRIG_DELTA);
  Serial.print(F(" | mode="));       Serial.println(continuousMode ? F("continuous") : F("trigger"));
}

// ADC 숫자 -> 압전 소자 양단의 실제 전압(V)
float toVolt(uint16_t adc) {
  return ((float)adc - (float)baseline) * (VREF / 1023.0) * DIV_RATIO;
}

void loop() {
  handleCommand();
  if (continuousMode) runContinuous();
  else               runTrigger();
}

// 시리얼로 한 글자 보내면 동작을 바꾼다
void handleCommand() {
  if (!Serial.available()) return;
  char c = Serial.read();
  if (c == 'r') {                       // 기준선 다시 재기
    measureBaseline();
    Serial.print(F("# rebaseline -> ")); Serial.println(baseline);
  } else if (c == 'c') {                // 연속 모드 켜기/끄기
    continuousMode = !continuousMode;
    printSettings();
  } else if (c == 's') {
    printSettings();
  }
}

// ---------- 트리거 모드: 밟는 순간의 파형만 통째로 저장 ----------
void runTrigger() {
  int wi = 0;            // 원형 버퍼에서 다음에 쓸 자리
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
      if (d >= TRIG_DELTA) fired = true;
    } else {
      post++;
      if (post >= N_POST) break;
    }
    if (!fired && (wi & 0x7F) == 0 && Serial.available()) return;  // 명령 확인
  }

  eventId++;
  dumpBuffer(wi);
}

// 버퍼를 오래된 것부터 CSV로 뱉는다
void dumpBuffer(int oldest) {
  int trigIdx = N_BUF - N_POST;   // 밟은 순간이 몇 번째 줄인지
  float peakV = 0, peakP = 0, energy_mJ = 0, prevP = 0;

  for (int i = 0; i < N_BUF; i++) {
    int idx = oldest + i;
    if (idx >= N_BUF) idx -= N_BUF;

    uint16_t adc = buf[idx];
    float v = toVolt(adc);
    float p_mW = (v * v / rEff) * 1000.0;
    float t_us = (i - trigIdx) * dtUs;

    if (v > peakV) peakV = v;
    if (p_mW > peakP) peakP = p_mW;
    // 사다리꼴 적분: mW * µs = nJ -> 1e-6 곱해서 mJ
    if (i > 0) energy_mJ += 0.5 * (p_mW + prevP) * dtUs * 1e-6;
    prevP = p_mW;

    Serial.print(eventId);   Serial.print(',');
    Serial.print(i - trigIdx); Serial.print(',');
    Serial.print(t_us, 1);   Serial.print(',');
    Serial.print(adc);       Serial.print(',');
    Serial.print(v, 4);      Serial.print(',');
    Serial.println(p_mW, 4);
  }

  Serial.print(F("# event ")); Serial.print(eventId);
  Serial.print(F(" | peak_V="));   Serial.print(peakV, 3);
  Serial.print(F(" | peak_mW="));  Serial.print(peakP, 3);
  Serial.print(F(" | E_mJ="));     Serial.print(energy_mJ, 5);
  Serial.print(F(" | R_load="));   Serial.println(R_LOAD, 0);
}

// ---------- 연속 모드: 1kHz로 계속 흘려보냄 (걸음 세기/장시간 기록용) ----------
void runContinuous() {
  static uint32_t n = 0;
  static uint32_t nextUs = 0;
  if (nextUs == 0) nextUs = micros();

  while (micros() < nextUs) { }
  nextUs += 1000;                       // 1000µs = 1kHz

  uint16_t adc = fastRead();
  float v = toVolt(adc);
  float p_mW = (v * v / rEff) * 1000.0;

  Serial.print(F("0,"));
  Serial.print(n);       Serial.print(',');
  Serial.print(n * 1000UL); Serial.print(',');
  Serial.print(adc);     Serial.print(',');
  Serial.print(v, 4);    Serial.print(',');
  Serial.println(p_mW, 4);
  n++;
}
