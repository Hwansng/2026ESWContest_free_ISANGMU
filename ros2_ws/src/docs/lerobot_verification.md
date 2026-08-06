# LeRobot 배포 검증 기록

- `~/lerobot-venv`에 격리 venv 설치 (`--system-site-packages` 미사용,
  ROS2의 opencv/cv_bridge와 충돌 방지 목적)
- `python rpi_check.py --skip-cameras` : 읽기 전용 테스트 전항목 통과
- `python rpi_check.py --skip-cameras --move-all` : 6축 실제 구동 확인
- arm_controller는 서보 버스를 직접 건드리지 않으므로 검증 중 ROS2 스택은
  계속 실행 상태로 두어도 무방 (단, arm_controller는 이 검증 동안 미실행)
