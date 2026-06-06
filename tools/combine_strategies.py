from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path


def _read_equity_csv(path: str) -> tuple[list[date], list[float]]:
    dates: list[date] = []
    equity: list[float] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            dates.append(date.fromisoformat(row["date"]))
            equity.append(float(row["strategy_equity"]))
    return dates, equity


def combine_strategies(
    equity_paths: list[str],
    weights: list[float],
    output: str,
) -> None:
    if len(equity_paths) < 2:
        raise ValueError("Need at least 2 strategy equity curves to combine")
    if len(equity_paths) != len(weights):
        raise ValueError("Number of equity_paths must match number of weights")

    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("Weights must sum to a positive value")
    normalized = [w / total_weight for w in weights]

    equity_data: list[tuple[list[date], list[float]]] = []
    for path in equity_paths:
        equity_data.append(_read_equity_csv(path))

    first_dates = equity_data[0][0]
    for i in range(1, len(equity_data)):
        if equity_data[i][0] != first_dates:
            raise ValueError(
                f"Date mismatch: {equity_paths[0]} and {equity_paths[i]} "
                "have different date ranges. All strategies must run on "
                "the same date range."
            )

    combined = [1.0]
    for t in range(1, len(first_dates)):
        day_return = sum(
            normalized[i] * (equity_data[i][1][t] / equity_data[i][1][t - 1] - 1.0)
            for i in range(len(equity_paths))
        )
        combined.append(combined[-1] * (1.0 + day_return))

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "combined_equity"])
        for i, d in enumerate(first_dates):
            writer.writerow([d.isoformat(), f"{combined[i]:.6f}"])

    final_return = combined[-1] - 1.0
    years = (first_dates[-1] - first_dates[0]).days / 365.25
    annualized = (combined[-1] ** (1.0 / years)) - 1.0 if years > 0 else 0.0

    peak = combined[0]
    max_drawdown = 0.0
    for v in combined:
        if v > peak:
            peak = v
        dd = (v / peak - 1.0) if peak > 0 else 0.0
        if dd < max_drawdown:
            max_drawdown = dd

    print(f"Combined equity written to: {output_path}")
    print(f"Strategies: {len(equity_paths)}")
    print(f"Weights: {[f'{w:.1%}' for w in normalized]}")
    print(f"Date range: {first_dates[0]} to {first_dates[-1]}")
    print(f"Final equity: {combined[-1]:.4f}")
    print(f"Total return: {final_return:.2%}")
    print(f"Annualized return: {annualized:.2%}")
    print(f"Max drawdown: {max_drawdown:.2%}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine multiple strategy equity curves",
    )
    parser.add_argument(
        "--equity-paths",
        nargs="+",
        required=True,
        help="Paths to equity_curve.csv files",
    )
    parser.add_argument(
        "--weights",
        nargs="+",
        type=float,
        required=True,
        help="Weights for each strategy (must match number of equity-paths)",
    )
    parser.add_argument(
        "--output",
        default="reports/combined/combined_equity.csv",
        help="Output path for combined equity curve",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    combine_strategies(args.equity_paths, args.weights, args.output)
