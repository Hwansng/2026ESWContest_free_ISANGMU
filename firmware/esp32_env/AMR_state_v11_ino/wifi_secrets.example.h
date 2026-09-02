#pragma once

// RPi5 AP 모드 접속 정보 — esp32_drive_tcp.ino와 동일한 AP를 쓴다.
const char* WIFI_SSID     = "여기에-AP-SSID";        // 🔴 실제 값으로 바꿀 것
const char* WIFI_PASSWORD = "여기에-AP-비밀번호";   // 🔴 실제 값으로 바꿀 것

// RPi mDNS 호스트명 (hazardbot.local). RPI_HOST를 쓰지 않고 mDNS로 찾는 방식이라
// AP 모드 IP(보통 192.168.4.1)가 바뀌어도 그대로 쓸 수 있다.
const char* RPI_MDNS_HOST = "hazardbot";

// sensor_bridge_node.py의 ENV_PORT (amr_v11_rpi_adaptive_gas_handoff_2026-08-29.md 참고).
// 🔴 DRIVE(5000)와 다르다 — 헷갈리지 말 것.
const uint16_t RPI_TCP_PORT = 8765;
