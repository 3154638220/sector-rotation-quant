#!/usr/bin/env python
"""持仓追踪工具：对比目标信号与实际持仓，输出换仓差异。

用法：
    python tools/position_tracker.py \\
        --signal reports/signals/signal_2026-06-03.json \\
        --positions '{"综合":0.15, "通信":0.20, "电子":0.25, "电力设备":0.20}' \\
        --output reports/signals/rebalance_diff.json

或从文件读取当前持仓：
    python tools/position_tracker.py \\
        --signal reports/signals/signal_2026-06-03.json \\
        --positions-file data/current_positions.json \\
        --output reports/signals/rebalance_diff.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def compute_rebalance_diff(
    target_signal: dict,
    current_positions: dict[str, float],
) -> dict:
    target_weights = target_signal.get("weights", {})
    target_holdings = set(target_weights)
    current_holdings = set(current_positions)

    buy = sorted(target_holdings - current_holdings)
    sell = sorted(current_holdings - target_holdings)
    hold = sorted(target_holdings & current_holdings)

    drift: dict[str, float] = {}
    for industry in hold:
        target_w = float(target_weights.get(industry, 0.0))
        current_w = float(current_positions.get(industry, 0.0))
        diff = target_w - current_w
        if abs(diff) > 0.001:
            drift[industry] = round(diff, 6)

    current_exposure = sum(float(v) for v in current_positions.values())

    return {
        "signal_date": target_signal.get("signal_date"),
        "buy": buy,
        "sell": sell,
        "hold": hold,
        "drift": drift,
        "target_exposure": float(target_signal.get("exposure", 0)),
        "current_exposure": current_exposure,
        "num_changes": len(buy) + len(sell) + len(drift),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute rebalance diff")
    parser.add_argument("--signal", required=True, help="Path to signal JSON file")
    parser.add_argument(
        "--positions",
        default=None,
        help='Current positions as JSON string, e.g. \'{"A":0.2,"B":0.3}\'',
    )
    parser.add_argument(
        "--positions-file",
        default=None,
        help="Path to file containing current positions JSON",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path for rebalance diff",
    )

    args = parser.parse_args()

    with open(args.signal, "r", encoding="utf-8") as f:
        signal = json.load(f)

    if args.positions:
        current = json.loads(args.positions)
    elif args.positions_file:
        with open(args.positions_file, "r", encoding="utf-8") as f:
            current = json.load(f)
    else:
        print("Error: either --positions or --positions-file is required")
        raise SystemExit(1)

    diff = compute_rebalance_diff(signal, current)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Rebalance diff written to: {out_path.resolve()}")

    print(f"Signal date: {diff['signal_date']}")
    print(f"Buy ({len(diff['buy'])}): {', '.join(diff['buy']) or '(none)'}")
    print(f"Sell ({len(diff['sell'])}): {', '.join(diff['sell']) or '(none)'}")
    print(f"Hold ({len(diff['hold'])}): {', '.join(diff['hold']) or '(none)'}")
    print(f"Weight adjustments: {len(diff['drift'])}")
    for ind, d in diff["drift"].items():
        direction = "+" if d > 0 else ""
        print(f"  {ind}: {direction}{d:.4f}")


if __name__ == "__main__":
    main()
