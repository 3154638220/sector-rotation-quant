"""Annual returns summary tool.

Reads an annual_returns.csv (or computes from backtest result) and prints:
- Year-by-year returns
- Negative year count
- Worst single year
- Mean and median annual return
- Consistency ratio (positive years / total years)
"""

import csv
import os
import sys
from collections import OrderedDict
from datetime import date


def load_annual_returns(path: str) -> dict[int, float]:
    result: dict[int, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row["year"])
            result[year] = float(row["return"])
    return result


def summarize(annual_dict: dict[int, float]) -> dict:
    returns = list(annual_dict.values())
    years = sorted(annual_dict)
    negative_years = sum(1 for r in returns if r < 0)
    worst_year = min(returns)
    best_year = max(returns)
    total_return = 1.0
    for r in returns:
        total_return *= 1.0 + r
    n_years = len(returns)
    annualized = total_return ** (1.0 / n_years) - 1.0 if n_years > 0 else 0.0
    sorted_r = sorted(returns)
    median_return = sorted_r[n_years // 2] if n_years > 0 else 0.0
    consistency = (n_years - negative_years) / n_years if n_years > 0 else 1.0
    return {
        "years": years,
        "returns": returns,
        "negative_years": negative_years,
        "worst_year": worst_year,
        "best_year": best_year,
        "annualized": annualized,
        "median_return": median_return,
        "consistency_ratio": consistency,
    }


def print_summary(stats: dict) -> None:
    print()
    print("=== Annual Returns Summary ===")
    print()
    print(f"{'Year':>6}  {'Return':>8}")
    print("-" * 17)
    for year, ret in zip(stats["years"], stats["returns"]):
        print(f"{year:>6}  {ret:>+7.1%}")
    print("-" * 17)
    print()
    print(f"Years analyzed:       {len(stats['years'])}")
    print(f"Negative years:       {stats['negative_years']}")
    print(f"Consistency ratio:    {stats['consistency_ratio']:.1%}")
    print(f"Worst single year:    {stats['worst_year']:>+.1%}")
    print(f"Best single year:     {stats['best_year']:>+.1%}")
    print(f"Median annual return: {stats['median_return']:>+.1%}")
    print(f"Annualized return:    {stats['annualized']:>+.1%}")
    print()

    if stats["negative_years"] <= 1 and stats["worst_year"] >= -0.10:
        print("Annual consistency: PASS (neg <= 1, worst >= -10%)")
    elif stats["negative_years"] <= 2 and stats["worst_year"] >= -0.15:
        print("Annual consistency: WARN (neg <= 2, worst >= -15%)")
    else:
        print("Annual consistency: FAIL")


def main(path: str) -> int:
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return 1
    annuals = load_annual_returns(path)
    if not annuals:
        print(f"No annual returns found in {path}")
        return 1
    stats = summarize(annuals)
    print_summary(stats)
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path is None:
        print("Usage: python tools/annual_returns_summary.py <annual_returns.csv>")
        sys.exit(1)
    sys.exit(main(path))
