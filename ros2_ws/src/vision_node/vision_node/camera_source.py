"""카메라 캡처 인터페이스 (PC USB 웹캠 <-> RPi CSI picamera2 교체용).

캡처 소스를 추상화해 소스만 바꾸면 동일 코드가 PC/RPi 양쪽에서 동작한다.
PC 단독 개발 단계에서는 WebcamSource를, RPi 통합 시 Picamera2Source를 사용한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import cv2
import numpy as np


class CameraSource(ABC):
    """프레임을 BGR ndarray로 제공하는 캡처 소스 공통 인터페이스."""

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """한 프레임 캡처. 실패 시 None."""

    @abstractmethod
    def release(self) -> None:
        """자원 해제."""


class WebcamSource(CameraSource):
    """PC 개발용 USB 웹캠 (cv2.VideoCapture)."""

    def __init__(self, device: int = 0, width: int = 640, height: int = 480) -> None:
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        self._cap.release()


class Picamera2Source(CameraSource):
    """RPi 통합용 CSI 카메라 (picamera2). RPi 환경에서만 import 가능 - 골격 제공."""

    def __init__(self, width: int = 640, height: int = 480) -> None:
        from picamera2 import Picamera2  # RPi에서만 설치되는 모듈
        self._cam = Picamera2()
        config = self._cam.create_preview_configuration(
            main={"format": "RGB888", "size": (width, height)})
        self._cam.configure(config)
        self._cam.start()

    def read(self) -> np.ndarray | None:
        rgb = self._cam.capture_array()                 # picamera2는 RGB 반환
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)     # OpenCV 기준 BGR로 변환

    def release(self) -> None:
        self._cam.stop()


def create_camera(source: str, **kwargs) -> CameraSource:
    """설정 문자열로 캡처 소스를 생성. 'picamera2' 또는 그 외(기본 webcam)."""
    if source == "picamera2":
        return Picamera2Source(**kwargs)
    return WebcamSource(**kwargs)
