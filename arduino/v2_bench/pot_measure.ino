// [저장소 메모] 2026-09-18 보조 스케치(멀티미터가 없을 때 가변저항 값을 읽기). 실행 기록 없음.

// pot_measure (2026-09-18)
// 가변저항(10kΩ)이 지금 몇 옴인지 아두이노로 읽는 보조 스케치.
// 멀티미터가 없을 때, 부하저항 조건을 숫자로 기록하기 위해 쓴다.
//
// 배선 (측정할 때만 이렇게 꽂는다):
//   가변저항 왼쪽 핀   -> 5V
//   가변저항 가운데 핀 -> A1
//   가변저항 오른쪽 핀 -> GND
//
// 읽는 값의 의미:
//   fraction = A1전압 / 5V
//   R(가운데-오른쪽) = fraction x 10000 Ω      <- 이 값이 부하저항 R_load
//   R(가운데-왼쪽)   = (1 - fraction) x 10000 Ω
//
// 사용 순서:
//   1) 위 배선으로 꽂고 이 스케치를 올린다.
//   2) 손잡이를 원하는 위치로 돌리고, 시리얼에 찍힌 R_ohm 값을 적는다.
//   3) 손잡이를 건드리지 말고 5V 점퍼만 뽑는다.
//   4) 가운데 핀 -> 압전 노드, 오른쪽 핀 -> GND 로 바꿔 꽂으면
//      방금 적은 값이 그대로 부하저항이 된다.
//   5) 회로 A 스케치를 다시 올리고 'L<값>' 으로 그 숫자를 기록한다.
//
// ※ 손잡이를 돌리면 값이 바뀐다. 한 조건을 다 재기 전에는 건드리지 말 것.
// ※ 공칭 10kΩ의 오차(보통 ±20%)가 그대로 실린다. 멀티미터가 있으면 그쪽이 정확하다.

const int   POT_PIN  = A1;
const float VREF     = 5.0;
const float POT_FULL = 10000.0;   // 가변저항 전체 저항 (제품 표기값)

void setup() {
  Serial.begin(9600);
  while (!Serial) { }
  Serial.println(F("adc,fraction,R_ohm"));
  Serial.println(F("# 손잡이를 돌린 뒤 값이 안정되면 R_ohm 을 적으세요."));
}

void loop() {
  // 잡음을 줄이려고 32회 평균
  uint32_t sum = 0;
  for (int i = 0; i < 32; i++) {
    analogRead(POT_PIN);            // 첫 변환은 버린다
    sum += analogRead(POT_PIN);
    delay(2);
  }
  float adc  = sum / 32.0;
  float frac = adc / 1023.0;

  Serial.print(adc, 1);               Serial.print(',');
  Serial.print(frac, 4);              Serial.print(',');
  Serial.println(frac * POT_FULL, 0);

  delay(400);
}
