// 유리프 압전 타일 측정 코드 v3 — Arduino Uno
// 회로: ROWn+ → 1MΩ → 측정점(A0~A3) → 100kΩ → GND, 1N4148 클램프(측정점↔5V, GND↔측정점)
// 시리얼 250000 baud (Arduino IDE 시리얼 모니터 오른쪽 아래도 250000으로)
//
// 출력 줄 종류 (맨 앞 글자로 구분, 쉼표 구분)
//   M  : 설정값 (시작할 때 1번)          M,버전,VREF,R1,R2,샘플주기us,TH_ON_V,TH_OFF_V
//   B  : 잡음 기준선 (시작 후 2초 측정)  B,ms,평균1~4(V),최대1~4(V)
//   R  : 원자료 (2 ms마다, ADC 값 0~1023)  R,ms,a0,a1,a2,a3
//   P  : 펄스 1개 요약 (디딜 때·뗄 때 각각 1줄) — 아래 P_HEADER 참고
//   S  : 상태 (10초마다)                 S,ms,펄스수,놓친샘플수,잡음최대1~4(V)
// 명령: r = 원자료(R) 켜기/끄기,  z = 잡음 기준선 다시 측정,  m = 설정값(M) 다시 출력

const char VERSION[] = "v3.1";
const float VREF = 5.00;                  // ★ 멀티미터로 잰 우노 5V 핀 전압
const float R1 = 1000000.0;               // ★ 잰 1MΩ 값
const float R2 = 100000.0;                // ★ 잰 100kΩ 값

const int ROW_PIN[4] = {A0, A1, A2, A3};
const int LED_PIN = 13;
const unsigned long SAMPLE_US = 2000;     // 2 ms (행당 500 Hz)
const float TH_ON_V  = 1.0;               // 펄스 시작: 어느 행이든 1.0 V 초과
const float TH_OFF_V = 0.3;               // 펄스 끝: 모든 행 0.3 V 미만이 QUIET_MS 동안
const unsigned long QUIET_MS = 30;
const unsigned long MAX_PULSE_MS = 3000;
const int CLIP_ADC = 1015;                // 이 값 이상이면 클램프에 걸림(약 54 V 이상) → 값이 잘렸음
const unsigned long NONE = 0xFFFFFFFFUL;

float kRow;                // ADC 1칸 → 행 전압(V)
int thOn, thOff;           // 문턱값(ADC 칸)
bool rawMode = true;

// 펄스 상태
bool inPulse = false;
unsigned long pStart, quietSince, prevEnd = 0, pulseCount = 0;
int   peakA[4];
unsigned long tFirst[4], tPeak[4], aboveSamples[4];
float eJ[4], qC[4];
bool  clip[4];

// 잡음·상태
bool calibrating = true;
unsigned long calStart, lastStatus = 0, dropped = 0, lastSample;
long  calSum[4]; unsigned long calN = 0;
int   calMax[4], idleMax[4];
float baseA[4] = {0, 0, 0, 0};   // 잡음 기준선 평균(ADC 칸) — 에너지·전하 계산 때 뺌

void resetCal() {
  calibrating = true; calStart = millis(); calN = 0;
  for (int i = 0; i < 4; i++) { calSum[i] = 0; calMax[i] = 0; }
}

int readPin(int pin) {        // 채널 전환 직후 첫 값은 버림 (분압 저항이 커서 앞 채널 값이 남음)
  analogRead(pin);
  return analogRead(pin);
}

void printV(float v) { Serial.print(','); Serial.print(v, 3); }

void printMeta() {
  Serial.print(F("M,")); Serial.print(VERSION);
  printV(VREF); Serial.print(','); Serial.print((unsigned long)R1); Serial.print(',');
  Serial.print((unsigned long)R2); Serial.print(','); Serial.print(SAMPLE_US);
  printV(TH_ON_V); printV(TH_OFF_V); Serial.println();
}

void setup() {
  Serial.begin(250000);
  pinMode(LED_PIN, OUTPUT);
  kRow  = VREF / 1023.0 * (R1 + R2) / R2;
  thOn  = (int)(TH_ON_V / kRow + 0.5);
  thOff = (int)(TH_OFF_V / kRow + 0.5);
  printMeta();
  for (int i = 0; i < 4; i++) idleMax[i] = 0;
  resetCal();
  lastSample = micros();
}

void endPulse(unsigned long ms) {
  pulseCount++;
  // 첫 접촉 순서 (예: "12" = 1행 다음 2행)
  char order[5]; int n = 0;
  bool used[4] = {false, false, false, false};
  for (int k = 0; k < 4; k++) {
    int best = -1;
    for (int i = 0; i < 4; i++)
      if (!used[i] && tFirst[i] != NONE && (best < 0 || tFirst[i] < tFirst[best])) best = i;
    if (best < 0) break;
    used[best] = true; order[n++] = '1' + best;
  }
  order[n] = '\0';
  unsigned long gap = (prevEnd == 0) ? 0 : (pStart - prevEnd);

  Serial.print(F("P,")); Serial.print(pulseCount); Serial.print(',');
  Serial.print(pStart); Serial.print(','); Serial.print(ms - pStart); Serial.print(',');
  Serial.print(gap); Serial.print(','); Serial.print(n); Serial.print(',');
  Serial.print(n ? order : "0");
  float sampleSec = SAMPLE_US * 1e-6;
  for (int i = 0; i < 4; i++) {
    printV(peakA[i] * kRow);
    Serial.print(','); if (tFirst[i] == NONE) Serial.print(-1); else Serial.print(tFirst[i]);
    Serial.print(','); if (tFirst[i] == NONE) Serial.print(-1); else Serial.print(tPeak[i]);
    Serial.print(','); Serial.print((unsigned long)(aboveSamples[i] * sampleSec * 1000.0 + 0.5));
    Serial.print(','); Serial.print(eJ[i] * 1e6, 4);     // µJ
    Serial.print(','); Serial.print(qC[i] * 1e9, 2);     // nC
    Serial.print(','); Serial.print(clip[i] ? 1 : 0);
  }
  Serial.println();
  prevEnd = ms;
  inPulse = false;
  digitalWrite(LED_PIN, LOW);
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'r') rawMode = !rawMode;
    if (c == 'z') resetCal();
    if (c == 'm') printMeta();
  }

  unsigned long now = micros();
  if (now - lastSample < SAMPLE_US) return;
  unsigned long el = now - lastSample;
  if (el > SAMPLE_US + SAMPLE_US / 2) dropped += el / SAMPLE_US - 1;   // 밀려서 놓친 샘플 수
  float dt = el * 1e-6;
  lastSample = now;
  unsigned long ms = millis();

  int a[4], amax = 0;
  for (int i = 0; i < 4; i++) { a[i] = readPin(ROW_PIN[i]); if (a[i] > amax) amax = a[i]; }

  if (rawMode) {
    Serial.print(F("R,")); Serial.print(ms);
    for (int i = 0; i < 4; i++) { Serial.print(','); Serial.print(a[i]); }
    Serial.println();
  }

  // 시작 2초: 아무도 밟지 않은 상태의 잡음 측정
  if (calibrating) {
    for (int i = 0; i < 4; i++) { calSum[i] += a[i]; if (a[i] > calMax[i]) calMax[i] = a[i]; }
    calN++;
    if (ms - calStart >= 2000) {
      calibrating = false;
      Serial.print(F("B,")); Serial.print(ms);
      for (int i = 0; i < 4; i++) { baseA[i] = calN ? (float)calSum[i] / calN : 0; printV(baseA[i] * kRow); }
      for (int i = 0; i < 4; i++) printV(calMax[i] * kRow);
      Serial.println();
    }
  }

  if (!inPulse && amax > thOn) {
    inPulse = true; pStart = ms; quietSince = 0;
    for (int i = 0; i < 4; i++) {
      peakA[i] = 0; tFirst[i] = NONE; tPeak[i] = 0; aboveSamples[i] = 0;
      eJ[i] = 0; qC[i] = 0; clip[i] = false;
    }
    digitalWrite(LED_PIN, HIGH);
  }

  if (inPulse) {
    for (int i = 0; i < 4; i++) {
      float v = (a[i] - baseA[i]) * kRow;   // 기준선을 뺀 전압
      if (v < 0) v = 0;
      unsigned long rel = ms - pStart;
      if (a[i] > peakA[i]) { peakA[i] = a[i]; tPeak[i] = rel; }
      if (a[i] > thOn) { aboveSamples[i]++; if (tFirst[i] == NONE) tFirst[i] = rel; }
      if (a[i] >= CLIP_ADC) clip[i] = true;
      eJ[i] += v * v / (R1 + R2) * dt;      // 부하에 전달된 에너지  E = ∫V²/R dt
      qC[i] += v / (R1 + R2) * dt;          // 부하로 흐른 전하      Q = ∫V/R dt
    }
    if (amax < thOff) {
      if (quietSince == 0) quietSince = ms;
      else if (ms - quietSince >= QUIET_MS) endPulse(ms);
    } else quietSince = 0;
    if (inPulse && ms - pStart > MAX_PULSE_MS) endPulse(ms);
  } else {
    for (int i = 0; i < 4; i++) if (a[i] > idleMax[i]) idleMax[i] = a[i];
  }

  if (ms - lastStatus >= 10000) {
    lastStatus = ms;
    Serial.print(F("S,")); Serial.print(ms); Serial.print(',');
    Serial.print(pulseCount); Serial.print(','); Serial.print(dropped);
    for (int i = 0; i < 4; i++) { printV(idleMax[i] * kRow); idleMax[i] = 0; }
    Serial.println();
  }
}
