"""Probe whether AKShare exposes historical SW constituent snapshots.

This is a diagnostic helper for Phase I.2. It first checks the local function
signature, then optionally attempts a dated call such as:

    ak.index_component_sw(symbol="801010", date="20220101")

If AKShare rejects the date keyword, Phase D stock-level results should remain
marked as current-constituent research approximations.
"""

from __future__ import annotations

import argparse
import inspect
import sys


def probe(symbol: str, snapshot_date: str, skip_network: bool = False) -> int:
    try:
        import akshare as ak
    except ImportError:
        print("AKShare import: FAIL")
        print("Install optional dependency first: pip install 'quant-rotation[real-data]'")
        return 1

    func = getattr(ak, "index_component_sw", None)
    if func is None:
        print("ak.index_component_sw: MISSING")
        return 1

    signature = inspect.signature(func)
    print("AKShare import: OK")
    print(f"index_component_sw signature: {signature}")

    supports_date = (
        "date" in signature.parameters
        or any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
    )
    print(f"Date keyword supported by signature: {supports_date}")
    if skip_network:
        return 0 if supports_date else 1

    try:
        frame = func(symbol=symbol, date=snapshot_date)
    except TypeError as exc:
        print(f"Dated call: FAIL ({exc})")
        return 1
    except Exception as exc:
        print(f"Dated call: ERROR ({type(exc).__name__}: {exc})")
        print("Signature appears compatible, but network/provider access failed.")
        return 2

    rows = len(frame) if hasattr(frame, "__len__") else "unknown"
    print(f"Dated call: OK ({rows} rows)")
    if hasattr(frame, "head"):
        print(frame.head())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check AKShare historical SW constituent support",
    )
    parser.add_argument("--symbol", default="801010", help="SW industry index code")
    parser.add_argument(
        "--date",
        default="20220101",
        help="Snapshot date in AKShare format, e.g. 20220101",
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="Only inspect the local function signature",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(probe(args.symbol, args.date, skip_network=args.skip_network))
