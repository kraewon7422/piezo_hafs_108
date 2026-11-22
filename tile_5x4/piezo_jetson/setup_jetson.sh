#!/usr/bin/env bash
# 압전 발판 젯슨 버전 — 처음 한 번만 실행 (젯슨 오린 나노, JetPack / Ubuntu 22.04)
#   chmod +x setup_jetson.sh run_jetson.sh && ./setup_jetson.sh
set -e
echo "== 1. 한글 글꼴·I2C 도구 설치"
sudo apt-get update
sudo apt-get install -y python3-pip fonts-noto-cjk i2c-tools
echo "== 2. 파이썬 패키지 (pyserial: 아두이노, pygame-ce: 화면, smbus2: 키트 I2C 장치)"
python3 -m pip install --user pyserial pygame-ce smbus2
echo "== 3. OpenCV·Jetson.GPIO 확인 (JetPack 에 기본으로 들어 있음)"
python3 -c "import cv2; print('OpenCV', cv2.__version__)" || echo "※ OpenCV 가 없습니다: sudo apt-get install -y python3-opencv"
python3 -c "import Jetson.GPIO; print('Jetson.GPIO OK')" || python3 -m pip install --user Jetson.GPIO
echo "== 4. 권한: 시리얼(dialout)·I2C(i2c)·GPIO(gpio)"
sudo groupadd -f -r gpio
sudo groupadd -f -r i2c
sudo usermod -aG dialout,i2c,gpio "$USER"
echo "== 5. Jetson.GPIO 권한 규칙(udev) — 일반 사용자로 GPIO 쓰기"
rules=""
for f in /opt/nvidia/jetson-gpio/etc/99-gpio.rules $(python3 -c "import Jetson.GPIO, os; print(os.path.join(os.path.dirname(Jetson.GPIO.__file__), '99-gpio.rules'))" 2>/dev/null); do
  if [ -f "$f" ]; then rules="$f"; break; fi
done
if [ -n "$rules" ]; then
  sudo cp "$rules" /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger
  echo "규칙 적용: $rules"
else
  echo "※ 99-gpio.rules 를 찾지 못했습니다 — 초음파·LED 가 '없음'이면 sudo 로 실행해 보세요"
fi
echo "== 6. OpenCV 의 GStreamer 지원 (CSI 리본 카메라에 필요)"
python3 -c "import cv2,re,sys; b=cv2.getBuildInformation(); sys.exit(0 if re.search(r'GStreamer:\s*YES', b) else 1)" \
  && echo "GStreamer: YES" \
  || echo "※ 이 OpenCV 는 GStreamer 가 없습니다 → CSI 카메라 대신 USB 카메라만 됩니다 (pip 로 opencv-python 이 깔렸으면 지우기: python3 -m pip uninstall opencv-python)"
echo
echo "끝. 권한을 적용하려면 로그아웃 후 다시 로그인(또는 재부팅)하세요."
echo "확인: 아두이노를 꽂고  ls /dev/ttyUSB* /dev/ttyACM*   ·   키트 I2C 장치  i2cdetect -y -r 7"
