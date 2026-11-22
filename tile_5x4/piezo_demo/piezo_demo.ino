// 유리프 압전 타일 5x4 측정 코드 — Arduino Uno
// A0~A3 : ROW1~4 측정 노드 (R1 1MΩ / R2 100kΩ 분압)   → S모드
// A4    : 저장 커패시터 노드 (R3 10MΩ / R4 2.2MΩ 분압) → E모드
// 시리얼 115200. 'r' 를 보내면 RAW 파형 출력 켜기/끄기

const float VREF = 5.00;                  // 멀티미터로 잰 5V 핀 실제 전압으로 바꿀 것
const float R1 = 1000000.0, R2 = 100000.0;  // 실측 저항값으로 바꿀 것
const float R3 = 10000000.0, R4 = 2200000.0;
const float C_STORE = 47e-6;              // 47 µF

const int ROW_PIN[4] = {A0, A1, A2, A3};
const int CAP_PIN = A4;
const int LED_PIN = 8;                    // 발걸음 표시용 (USB 전원 — 발전 증거 아님)

const float TH_ON  = 1.0;                 // 발걸음 시작: 어느 행이든 1.0 V 초과
const float TH_OFF = 0.3;                 // 발걸음 끝: 모든 행 0.3 V 미만이 50 ms 지속
const unsigned long SAMPLE_US = 1000;     // 1 kHz (5채널 순차 읽기)
const unsigned long NONE = 0xFFFFFFFF;

float kRow, kCap, dt;
bool inStep = false, rawMode = false;
unsigned long lastSample, lastCapPrint, stepStart, quietSince, stepCount = 0;
float peakV[4], energyJ[4];
unsigned long firstHit[4];
byte rawDiv = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  kRow = VREF / 1023.0 * (R1 + R2) / R2;   // ADC 값 → 행 버스 실제 전압
  kCap = VREF / 1023.0 * (R3 + R4) / R4;   // ADC 값 → 커패시터 실제 전압
  dt = SAMPLE_US * 1e-6;
  Serial.println(F("# STEP,번호,시작ms,지속ms,피크1~4(V),에너지1~4(uJ),첫접촉1~4(ms,-1=없음)"));
  Serial.println(F("# CAP,ms,Vcap(V),E=1/2CV^2(uJ)"));
  lastSample = micros();
}

void endStep(unsigned long ms) {
  stepCount++;
  Serial.print(F("STEP,")); Serial.print(stepCount); Serial.print(',');
  Serial.print(stepStart); Serial.print(','); Serial.print(ms - stepStart);
  for (int i = 0; i < 4; i++) { Serial.print(','); Serial.print(peakV[i], 2); }
  for (int i = 0; i < 4; i++) { Serial.print(','); Serial.print(energyJ[i] * 1e6, 3); }
  for (int i = 0; i < 4; i++) {
    Serial.print(',');
    if (firstHit[i] == NONE) Serial.print(-1); else Serial.print(firstHit[i]);
  }
  Serial.println();
  inStep = false;
  digitalWrite(LED_PIN, LOW);
}

void loop() {
  if (Serial.available()) { if (Serial.read() == 'r') rawMode = !rawMode; }

  unsigned long now = micros();
  if (now - lastSample < SAMPLE_US) return;
  lastSample += SAMPLE_US;
  if (now - lastSample > 10 * SAMPLE_US) lastSample = now;   // 밀리면 재동기화

  unsigned long ms = millis();
  float v[4], vmax = 0;
  for (int i = 0; i < 4; i++) {
    v[i] = analogRead(ROW_PIN[i]) * kRow;
    if (v[i] > vmax) vmax = v[i];
  }

  if (!inStep && vmax > TH_ON) {                 // 발걸음 시작
    inStep = true; stepStart = ms; quietSince = 0;
    for (int i = 0; i < 4; i++) { peakV[i] = 0; energyJ[i] = 0; firstHit[i] = NONE; }
    digitalWrite(LED_PIN, HIGH);
  }

  if (inStep) {
    for (int i = 0; i < 4; i++) {
      if (v[i] > peakV[i]) peakV[i] = v[i];
      energyJ[i] += v[i] * v[i] / (R1 + R2) * dt;   // 부하(R1+R2)에 전달된 에너지
      if (firstHit[i] == NONE && v[i] > TH_ON) firstHit[i] = ms - stepStart;
    }
    if (vmax < TH_OFF) {
      if (quietSince == 0) quietSince = ms;
      else if (ms - quietSince > 50) endStep(ms);
    } else quietSince = 0;
    if (inStep && ms - stepStart > 3000) endStep(ms);   // 3초 넘게 서 있으면 끊기
  }

  if (rawMode && ++rawDiv >= 4) {                // 250 Hz 파형 출력
    rawDiv = 0;
    Serial.print(F("RAW,")); Serial.print(ms);
    for (int i = 0; i < 4; i++) { Serial.print(','); Serial.print(v[i], 2); }
    Serial.println();
  }

  if (ms - lastCapPrint >= 1000) {               // 1초마다 저장 커패시터
    lastCapPrint = ms;
    float vc = analogRead(CAP_PIN) * kCap;
    Serial.print(F("CAP,")); Serial.print(ms); Serial.print(',');
    Serial.print(vc, 3); Serial.print(',');
    Serial.println(0.5 * C_STORE * vc * vc * 1e6, 2);
  }
}
