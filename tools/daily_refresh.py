#!/usr/bin/env python
"""每日运营脚本：数据追加 + 信号生成

用法：
    python tools/daily_refresh.py

配置可通过顶部常量或环境变量覆盖：

    $env:PRODUCTION_CONFIG="configs/production.toml"
    $env:REAL_DATA_DIR="data/real_sw2021"
    $env:SIGNAL_OUTPUT_DIR="reports/signals"
    python tools/daily_refresh.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

PRODUCTION_CONFIG = os.environ.get("PRODUCTION_CONFIG", "configs/production.toml")
REAL_DATA_DIR = os.environ.get("REAL_DATA_DIR", "data/real_sw2021")
SIGNAL_OUTPUT_DIR = os.environ.get("SIGNAL_OUTPUT_DIR", "reports/signals")
REQUEST_INTERVAL = os.environ.get("REQUEST_INTERVAL", "0.3")
PYTHON_CMD = sys.executable

TODAY = date.today().isoformat()


def run_step(step_name: str, cmd: list[str]) -> None:
    print(f"[{step_name}] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent)
    if result.returncode != 0:
        print(f"[{step_name}] FAILED with exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"[{step_name}] OK")


def main() -> None:
    print(f"=== Daily Refresh {TODAY} ===")

    run_step(
        "append-data",
        [
            PYTHON_CMD, "-m", "quant_rotation", "fetch-real-data",
            "--output", REAL_DATA_DIR,
            "--end", TODAY,
            "--update-mode", "append",
            "--request-interval", REQUEST_INTERVAL,
        ],
    )

    run_step(
        "signal",
        [
            PYTHON_CMD, "-m", "quant_rotation", "signal",
            "--config", PRODUCTION_CONFIG,
            "--output", str(Path(SIGNAL_OUTPUT_DIR) / f"signal_{TODAY}.json"),
        ],
    )

    print(f"=== Daily Refresh {TODAY} done ===")
    recent_signal = sorted(
        Path(SIGNAL_OUTPUT_DIR).glob("signal_*.json"),
        key=lambda p: p.stat().st_mtime,
    )[-1]
    print(f"Latest signal: {recent_signal.resolve()}")


if __name__ == "__main__":
    main()
