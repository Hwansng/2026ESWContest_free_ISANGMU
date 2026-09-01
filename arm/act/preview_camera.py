"""손목 카메라를 브라우저로 실시간 확인한다 (읽기 전용 — 캡처만, 서보는 건드리지 않는다).

check_cameras.py 는 스냅샷 한 장만 찍는다. 이 도구는 팔을 손으로 움직이면서
화각을 눈으로 바로바로 확인할 때 쓴다 — 캘리브레이션 재조정 중 화각 중심을 잡을 때.

🔴 이 conda 환경의 opencv 는 headless 빌드라 cv2.imshow 가 동작하지 않는다
   (namedWindow: "The function is not implemented"). 대신 프레임을 JPEG 로 인코딩해
   로컬 HTTP 서버로 서빙하고 브라우저에서 새로고침하며 본다. 새 패키지 설치가 필요 없다.

카메라는 COM 포트(서보 버스)와 별개의 USB 장치라 팔 쪽 스크립트와 동시에 실행해도 충돌하지 않는다.

사용법:
    python tools/preview_camera.py --index 0
    브라우저가 자동으로 뜬다. 터미널에서 Ctrl+C 로 종료.
"""

import argparse
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

CAP_W, CAP_H, CAP_FPS = 640, 480, 30  # 데이터 수집과 같은 조건 (check_cameras.py 와 동일)
PORT = 8642

_lock = threading.Lock()
_latest_jpeg: bytes | None = None

PAGE = b"""<!doctype html>
<html><head><meta charset="utf-8"><title>wrist camera preview</title>
<style>body{margin:0;background:#111;display:flex;justify-content:center;align-items:center;height:100vh}
img{max-width:100vw;max-height:100vh}</style></head>
<body><img id="f" src="/frame.jpg"></body>
<script>
setInterval(() => {
  document.getElementById("f").src = "/frame.jpg?t=" + Date.now();
}, 150);
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 콘솔에 요청 로그를 찍지 않는다

    def do_GET(self):
        if self.path.startswith("/frame.jpg"):
            with _lock:
                data = _latest_jpeg
            if data is None:
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, required=True, help="카메라 인덱스 (check_cameras.py --list 로 확인)")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.index, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_H)
    cap.set(cv2.CAP_PROP_FPS, CAP_FPS)

    if not cap.isOpened():
        print(f"❌ 인덱스 {args.index} 를 열 수 없다.")
        return 1

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{PORT}/"
    print(f"브라우저에서 {url} 를 연다. 창이 안 뜨면 직접 접속할 것.")
    print("종료: 이 터미널에서 Ctrl+C.")
    webbrowser.open(url)

    global _latest_jpeg
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("⚠ 프레임을 못 받았다.")
                time.sleep(0.1)
                continue

            h, w = frame.shape[:2]
            cv2.line(frame, (w // 2, 0), (w // 2, h), (0, 255, 0), 1)
            cv2.line(frame, (0, h // 2), (w, h // 2), (0, 255, 0), 1)

            ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok2:
                with _lock:
                    _latest_jpeg = buf.tobytes()
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        server.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
