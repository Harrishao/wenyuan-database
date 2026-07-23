import argparse
import subprocess
import sys
import time
from pathlib import Path

import httpx


def wait_for_health(url: str, process: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"验证服务提前退出，退出码 {process.returncode}")
        try:
            if httpx.get(url, timeout=2).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise RuntimeError("验证服务启动超时")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--port", type=int, default=4397)
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    api_root = f"http://127.0.0.1:{args.port}"
    python = Path(sys.executable)
    server_stdout = (artifacts / "server-stdout.log").open("w", encoding="utf-8")
    server_stderr = (artifacts / "server-stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
        ],
        stdout=server_stdout,
        stderr=server_stderr,
    )
    (artifacts / "server.pid").write_text(str(process.pid), encoding="utf-8")
    try:
        wait_for_health(f"{api_root}/api/v1/health/ready", process)
        commands = [
            [
                str(python),
                "scripts/validate_llm_mvp4.py",
                "--base-url",
                f"{api_root}/api/v1",
                "--artifacts",
                str(artifacts / "mvp4-admin"),
            ],
            [
                str(python),
                "scripts/validate_llm_mvp2_mvp3.py",
                "--base-url",
                f"{api_root}/api/v1",
                "--artifacts",
                str(artifacts / "mvp2-mvp3-regression"),
            ],
        ]
        for command in commands:
            completed = subprocess.run(command, check=False)
            if completed.returncode != 0:
                return completed.returncode
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        server_stdout.close()
        server_stderr.close()


if __name__ == "__main__":
    sys.exit(main())
