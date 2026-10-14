"""启动/停止六个本地演示服务（控制面、三个园区、两个计算节点）。

用法：
    python backend/scripts/manage_services.py start
    python backend/scripts/manage_services.py stop

服务以 detached 方式在后台运行（不占用当前终端），日志写入 backend/logs/，
PID 列表写入 backend/logs/service_pids.txt。
"""

import os
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
LOG_DIR = BACKEND_DIR / "logs"
PID_FILE = LOG_DIR / "service_pids.txt"

SERVICES = [
    ("control", "control_plane.main:app", 8000, {}),
    ("party-a", "party_node.main:app", 8101, {"PARTY_ID": "ORG_A"}),
    ("party-b", "party_node.main:app", 8102, {"PARTY_ID": "ORG_B"}),
    ("party-c", "party_node.main:app", 8103, {"PARTY_ID": "ORG_C"}),
    ("compute-s1", "compute_node.main:app", 8201, {"COMPUTE_NODE_ID": "S1"}),
    ("compute-s2", "compute_node.main:app", 8202, {"COMPUTE_NODE_ID": "S2"}),
]


def start() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    python = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    pids = []
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    for name, module, port, extra in SERVICES:
        child_env = dict(env)
        child_env.update(extra)
        stdout = open(LOG_DIR / f"{name}.log", "a", encoding="utf-8")
        stderr = open(LOG_DIR / f"{name}.err.log", "a", encoding="utf-8")
        proc = subprocess.Popen(
            [python, "-m", "uvicorn", module, "--port", str(port)],
            cwd=str(BACKEND_DIR),
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=flags,
        )
        stdout.close()
        stderr.close()
        pids.append(proc.pid)
        print(f"{name} started pid={proc.pid} port={port}")
    PID_FILE.write_text("\n".join(str(pid) for pid in pids) + "\n", encoding="utf-8")
    print(f"pids written to {PID_FILE}")


def stop() -> None:
    if not PID_FILE.exists():
        print("未找到 PID 文件，可能服务未启动")
        return
    for line in PID_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            # venv 的 python.exe 是转发器，会派生真实解释器子进程；
            # 必须按进程树停止，避免子进程成为孤儿继续占用端口。
            subprocess.run(
                ["taskkill", "/PID", str(int(line)), "/T", "/F"],
                capture_output=True,
                timeout=15,
            )
            print(f"stopped pid={line}")
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"pid={line} 已退出或无法停止: {exc}")
    PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "start":
        start()
    elif action == "stop":
        stop()
    else:
        print(__doc__)
        sys.exit(2)
