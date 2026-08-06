/*
 * File: AMR_state_v8_wifi.ino  (참고용 - Arduino 저장소는 별도)
 * Target: ESP32 #1 (AMR) - MQ135 가스 + KY-026 화염 감지, WiFi TCP로
 * RPi5 amr_bridge(포트5000)에 <SENS,gas,flame,battCv,stateCode,
 * actionCode,faultCode,checksum> 형식 전송.
 * 원본 AMR_state_v8.ino(USB Serial)를 WiFiClient 기반으로 변환.
 * 상세 구현은 팀원(강희) 저장소 참조.
 */
