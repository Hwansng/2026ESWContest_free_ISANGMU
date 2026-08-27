# vision_node 의존성 트러블슈팅 기록 (2026-07-13)

vision_node를 camera_ros 토픽 구독 방식으로 바꾸는 과정에서 만난
환경 의존성 문제와 해결법. `.py` 코드 변경이 아니라 시스템 패키지
설치라 diff로는 안 남아서 별도 기록.

## 1. libcamera 자체가 카메라를 못 잡던 문제 (근본 원인)
```
ros-jazzy-libcamera(0.7.1) 패키지가 미디어 엔티티 이름을 하이픈
(rp1-cfe-fe-image0)으로 하드코딩한 구버전 소스로 빌드되어 있었음.
실제 Ubuntu 24.04 커널의 rp1-cfe 드라이버는 언더스코어
(rp1-cfe-fe_image0)로 엔티티를 등록 -> 이름이 절대 일치하지 않아
CFE acquire가 항상 실패.

해결: GitHub 최신 libcamera 소스 직접 빌드 후 LD_PRELOAD로 강제 로드.
~/.bashrc에 영구 등록:
  export LD_PRELOAD=$HOME/libcamera/build/src/libcamera/libcamera.so.0.7.1:$HOME/libcamera/build/src/libcamera/base/libcamera-base.so.0.7.1
  export LIBCAMERA_IPA_MODULE_PATH=$HOME/libcamera/build/src/ipa/rpi/pisp:$HOME/libcamera/build/src/ipa/rpi/vc4
검증: camera_ros의 /camera/image_raw가 30fps 안정 스트리밍 확인
  (ros2 topic hz /camera/image_raw)
```

## 2. cv_bridge 자체가 시스템에 없던 문제
```
vision_node가 cv2.VideoCapture(0) 직접 오픈 대신
/camera/image_raw 토픽을 구독하는 방식으로 바뀌면서 cv_bridge 필요.

해결:
  sudo apt install -y ros-jazzy-cv-bridge ros-jazzy-vision-opencv
```

## 3. numpy 2.x ↔ cv_bridge(numpy 1.x 컴파일) ABI 불일치
```
증상: dashboard_node/vision_node가 image_cb에서 세그폴트
  (ImportError: numpy 2.x cannot be run with modules compiled for numpy 1.x
   -> exit code -11)

원인: pip으로 설치된 numpy 2.5.1이 apt로 설치된 cv_bridge(numpy 1.x로
컴파일됨)와 ABI 불일치.

해결:
  pip3 install "numpy<2" --break-system-packages --force-reinstall
```

## 4. (HSV 캘리브레이션 도구 관련) opencv GUI 미지원 문제
```
증상: cv2.namedWindow() 호출 시
  "The function is not implemented. Rebuild library with GTK+..."

원인: numpy 충돌 해결 과정에서 opencv-python-headless가 설치되어
  있었음 (cv2.imshow 등 GUI 함수 미지원).

해결: 캘리브레이션 도구는 로컬 GUI creo 대신 Flask 웹 스트리밍
  방식으로 전환 (SSH 원격 작업 환경에 더 적합하기도 함).
```
