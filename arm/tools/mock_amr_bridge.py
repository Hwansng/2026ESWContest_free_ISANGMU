"""RPi 없이 DRIVE 펌웨어를 시험하는 목업 amr_bridge.

노트북에서 이걸 띄우고 ESP32 의 RPI_HOST 를 노트북 IP 로 두면,
`esp32_drive_tcp.ino` 의 TCP·체크섬·<SENS>·<MOVE>/<STOP>/<HB>·RPI_TIMEOUT 을
RPi 가 준비되기 전에 전부 확인할 수 있다.

프로토콜은 `ros2_ws/src/amr_bridge/amr_bridge/amr_bridge_node.py` 와 같다 —
프레이밍 `<payload,CS>\n`, 체크섬은 payload 각 문자의 ASCII 합 % 256.

    python tools/mock_amr_bridge.py

명령 (엔터로 실행):
    m 120 120   <MOVE,120,120> 송신
    s           <STOP> 송신
    g           <GO> 송신 (ESTOP 해제 — 펌웨어에만 있고 진짜 amr_bridge 엔 아직 없다)
    h           하트비트 중단/재개 토글  ← 🔴 RPI_TIMEOUT 검증이 이것이다
    q           종료
"""
import socket
import threading
import time
import sys

# 🔴 Windows 콘솔 기본 인코딩이 cp949 라 이모지·em대시를 그냥 print 하면
#    UnicodeEncodeError 로 죽는다 (실제로 겪었다). 출력 스트림을 UTF-8 로 돌린다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

HELP = """명령 (엔터로 실행):
    m 120 120   <MOVE,120,120> 송신
    s           <STOP> 송신
    g           <GO> 송신 (ESTOP 해제)
    h           하트비트 중단/재개 토글  <- RPI_TIMEOUT 검증이 이것이다
    q           종료
"""

HOST = '0.0.0.0'
PORT = 5000
HB_PERIOD = 0.3          # 8/25 확정 하트비트 주기

STATE_NAMES  = ['SAFE', 'WARNING', 'DANGER', 'STOP', 'SENSOR_ERROR']
ACTION_NAMES = ['NORMAL_MOTION', 'LIMITED_MOTION', 'STOP_MOTION']
FAULT_NAMES  = ['OK', 'ESTOP', 'LIPO', 'SENSOR', 'RPI_TIMEOUT', 'HAZARD']

conn = None
conn_lock = threading.Lock()
hb_enabled = True
running = True
last_sens = 0.0


def checksum(payload: str) -> int:
    return sum(ord(c) for c in payload) % 256


def send(*fields):
    payload = ','.join(str(f) for f in fields)
    frame = f'<{payload},{checksum(payload)}>\n'
    with conn_lock:
        if conn:
            try:
                conn.sendall(frame.encode())
            except OSError as e:
                print(f'  송신 실패: {e}')
        else:
            print('  ESP32 미연결 — 송신 안 됨')


def parse(line: str):
    """ESP32 가 보낸 <SENS,...> 를 amr_bridge 와 같은 방식으로 해석한다."""
    global last_sens
    if not (line.startswith('<') and line.endswith('>')):
        print(f'  프레이밍 아님: {line!r}')
        return
    parts = line[1:-1].split(',')
    if len(parts) < 2:
        return

    body = ','.join(parts[:-1])
    if checksum(body) != int(parts[-1]):
        print(f'  🔴 체크섬 불일치: {line}')
        return

    if parts[0] != 'SENS' or len(parts) < 8:
        print(f'  알 수 없는 CMD: {parts[0]}')
        return

    gas, flame, batt_cv = int(parts[1]), int(parts[2]), int(parts[3])
    st, ac, ft = int(parts[4]), int(parts[5]), int(parts[6])
    dist = int(parts[7]) if len(parts) >= 9 else None      # 덧붙인 필드
    sidx = int(parts[8]) if len(parts) >= 10 else None

    now = time.time()
    gap = f'{(now - last_sens) * 1000:5.0f}ms' if last_sens else '   —  '
    last_sens = now

    extra = ''
    if dist is not None:
        extra += f' dist={dist:>5}mm' + ('  🔴장애물' if 0 <= dist <= 300 else '')
    if sidx is not None:
        extra += f' stopIdx={sidx}'

    print(f'  [{gap}] batt={batt_cv/100:5.2f}V  {STATE_NAMES[st]:<12} '
          f'{ACTION_NAMES[ac]:<14} {FAULT_NAMES[ft]:<11}{extra}'
          + ('' if (gas == 0 and flame == 0) else f'  ⚠ gas={gas} flame={flame}'))


def recv_loop(sock):
    buf = ''
    while running:
        try:
            raw = sock.recv(256)
            if not raw:
                break
            buf += raw.decode('utf-8', errors='ignore')
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                line = line.strip()
                if line:
                    parse(line)
        except OSError:
            break
    print('\n  ESP32 연결 종료. 재접속 대기 중...\n')


def hb_loop():
    while running:
        if hb_enabled:
            with conn_lock:
                alive = conn is not None
            if alive:
                send('HB')
        time.sleep(HB_PERIOD)


def accept_loop():
    global conn
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(1)
        srv.settimeout(1.0)
        print(f'포트 {PORT} 에서 ESP32(DRIVE) 접속 대기 중...')
        print('🔴 ESP32 의 RPI_HOST 를 이 컴퓨터 IP 로 바꿔서 업로드해야 붙는다.')
        print(f'   이 컴퓨터: {socket.gethostbyname(socket.gethostname())}\n')
        while running:
            try:
                c, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f'🔵 ESP32 연결됨: {addr[0]}\n')
            with conn_lock:
                conn = c
            recv_loop(c)
            with conn_lock:
                conn = None


def main():
    global running, hb_enabled
    threading.Thread(target=accept_loop, daemon=True).start()
    threading.Thread(target=hb_loop, daemon=True).start()

    print(HELP)
    if not sys.stdin.isatty():
        # 콘솔 없이 띄운 경우(런처·리다이렉션) stdin 이 즉시 EOF 라 바로 끝나버린다.
        # 그때는 명령 입력을 포기하고 수신만 계속한다 — Ctrl+C 로 끝낸다.
        print('  (stdin 없음 — 수신 전용 모드. Ctrl+C 로 종료)')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            globals()['running'] = False
        return

    try:
        for line in sys.stdin:
            cmd = line.strip().split()
            if not cmd:
                continue
            if cmd[0] == 'q':
                break
            elif cmd[0] == 'm' and len(cmd) == 3:
                send('MOVE', int(cmd[1]), int(cmd[2]))
                print(f'  → MOVE {cmd[1]} {cmd[2]}')
            elif cmd[0] == 's':
                send('STOP')
                print('  → STOP')
            elif cmd[0] == 'g':
                send('GO')
                print('  → GO')
            elif cmd[0] == 'h':
                hb_enabled = not hb_enabled
                print(f'  → 하트비트 {"재개" if hb_enabled else "🔴 중단 — 1초 뒤 ESP32 가 서야 정상"}')
            else:
                print('  m <L> <R> / s / g / h / q')
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        print('\n종료.')


if __name__ == '__main__':
    main()
