"""lerobot 모듈을 이 파이썬의 conda Scripts 폴더를 PATH에 넣은 채로 실행한다.

`lerobot.scripts.lerobot_record`/`lerobot_teleoperate`는 시각화를 위해 `rerun`을
서브프로세스로 호출한다. `rerun.exe`는 conda 환경의 `Scripts` 폴더에 콘솔 스크립트로
설치되는데, 일부 실행 경로(예: PowerShell에서 절대경로로 python.exe를 직접 호출)에서는
이 폴더가 PATH에 없어 `rerun`을 못 찾고 실패한다. 이 런처는 대상 모듈을 실행하기 전에
그 Scripts 폴더를 PATH 맨 앞에 붙여준다.

사용: python run_lerobot_module.py <module> [args...]
      (python -m <module> [args...] 와 동일하게 동작하되 PATH만 보정한다)
"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_lerobot_module.py <module> [args...]", file=sys.stderr)
        return 2

    module = sys.argv[1]
    module_args = sys.argv[2:]

    scripts_dir = str(Path(sys.executable).parent / "Scripts")
    env = os.environ.copy()
    env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")

    result = subprocess.run([sys.executable, "-m", module, *module_args], env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
