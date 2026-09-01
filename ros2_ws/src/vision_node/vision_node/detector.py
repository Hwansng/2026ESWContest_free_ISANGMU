"""
[레거시 — 현재 사용 안 함]
초기 개발 단계에서 만든 순수 함수 버전 물체 검출 로직임. ROS 의존 없이
단위 테스트하려고 분리했던 것인데, 지금 실제로 돌아가는 vision_node.py는
이 모듈을 import하지 않고 자체적으로 HSV 판정 로직을 갖고 있음.
vision_node.py가 최신본이니 로직 수정은 거기서 해야 함. 이 파일은 참고용으로만 남겨둠.
"""
"""물체 검출 핵심 로직 (ROS 의존 없음 - 정지 이미지로 단독/단위 테스트 가능).

처리 흐름: HSV 색상 분류 -> 컨투어 면적 필터 -> minAreaRect로
중심/폭/높이/방위각 추출 -> 종횡비 비대칭 판정 -> 방위각 0~180 정규화 ->
STS3215 Wrist Roll 매핑.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Detection:
    """검출 결과 한 건."""
    color: str        # "red" / "yellow"
    cx: int           # 중심 x [px]
    cy: int           # 중심 y [px]
    width: int        # minAreaRect 폭 [px]
    height: int       # minAreaRect 높이 [px]
    angle: int        # 0~180 정규화 방위각 [deg]
    asymmetric: bool  # 종횡비 > 임계값 여부


def _color_mask(hsv: np.ndarray, color: str, cfg: dict) -> np.ndarray:
    """설정된 HSV 범위로 색상 마스크 생성. 빨강은 두 구간을 합친다."""
    c = cfg[color]
    if color == "red":
        m1 = cv2.inRange(hsv, np.array(c["lower1"]), np.array(c["upper1"]))
        m2 = cv2.inRange(hsv, np.array(c["lower2"]), np.array(c["upper2"]))
        mask = cv2.bitwise_or(m1, m2)
    else:
        mask = cv2.inRange(hsv, np.array(c["lower"]), np.array(c["upper"]))
    kernel = np.ones((5, 5), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)


def normalize_angle(rect_angle: float, width: float, height: float) -> int:
    """cv2.minAreaRect 각도를 '장축 기준 0~180'으로 정규화."""
    angle = rect_angle
    if width < height:
        angle += 90.0
    angle = angle % 180.0
    return int(round(angle))


de