/*
 * wifi_task.h - Core 0 전담 WiFi TCP 태스크 진입점 선언
 */
#ifndef WIFI_TASK_H
#define WIFI_TASK_H

// Core 0에 고정 생성되는 FreeRTOS 태스크 함수
void wifiTask(void* pv);

#endif  // WIFI_TASK_H
