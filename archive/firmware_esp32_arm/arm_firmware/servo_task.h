/*
 * servo_task.h - Core 1 전담 서보 태스크 진입점 선언
 */
#ifndef SERVO_TASK_H
#define SERVO_TASK_H

// Core 1에 고정 생성되는 FreeRTOS 태스크 함수
void servoTask(void* pv);

#endif  // SERVO_TASK_H
