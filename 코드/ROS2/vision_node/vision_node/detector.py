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
    # 열림(open) 연산으로 점 노이즈 제거
    kernel = np.ones((5, 5), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)


def normalize_angle(rect_angle: float, width: float, height: float) -> int:
    """cv2.minAreaRect 각도를 '장축 기준 0~180'으로 정규화."""
    angle = rect_angle
    if width < height:      # 장축이 세로면 90도 보정
        angle += 90.0
    angle = angle % 180.0   # 0~180 범위로 래핑
    return int(round(angle))


def angle_to_wrist_roll(angle: int) -> int:
    """방위각 0~180 -> STS3215 Wrist Roll(ID5) 명령각 0~180 (clamp)."""
    return max(0, min(180, angle))


def detect(frame: np.ndarray, cfg: dict) -> list[Detection]:
    """프레임에서 빨강/노랑 물체를 검출해 Detection 리스트로 반환."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)   # BGR -> HSV
    min_area = float(cfg.get("min_area", 800))
    ar_thresh = float(cfg.get("aspect_ratio_threshold", 1.5))
    results: list[Detection] = []

    for color in ("red", "yellow"):
        mask = _color_mask(hsv, color, cfg)
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            if cv2.contourArea(cnt) < min_area:    # 면적 필터(노이즈 제거)
                continue
            (cx, cy), (w, h), rect_angle = cv2.minAreaRect(cnt)
            if w == 0 or h == 0:
                continue
            angle = normalize_angle(rect_angle, w, h)
            long_side, short_side = max(w, h), min(w, h)
            asymmetric = (long_side / short_side) > ar_thresh  # 종횡비 비대칭
            results.append(Detection(
                color=color, cx=int(cx), cy=int(cy),
                width=int(w), height=int(h),
                angle=angle, asymmetric=asymmetric,
            ))
    return results
