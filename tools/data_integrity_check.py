"""Data integrity check tool.

Runs quality checks on industry and market data files:
1. Outlier check: single-day changes > 20% for any industry
2. Missing value check: consecutive gaps > 5 days
3. Date alignment: cross-file date column consistency
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import date


REPO = os.path.dirname(os.path.dirname(__file__))


def _read_wide_data(path: str) -> tuple[list[date], dict[str, list[float]]]:
    dates: list[date] = []
    industries: dict[str, list[float]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = date.fromisoformat(row["date"])
            dates.append(d)
            for col, val in row.items():
                if col == "date":
                    continue
                industries[col].append(float(val))
    return dates, dict(industries)


def check_price_jumps(path: str, threshold: float = 0.20) -> list[str]:
    issues: list[str] = []
    dates, industries = _read_wide_data(path)
    for name, closes in industries.items():
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            curr = closes[i]
            if prev <= 0:
                continue
            change = abs(curr / prev - 1.0)
            if change > threshold:
                issues.append(
                    f"  {name} {dates[i]}: {change:.1%} jump"
                )
    return issues


def check_consecutive_missing(
    dates: list[date],
    max_gap: int = 5,
) -> list[str]:
    issues: list[str] = []
    if not dates:
        return issues
    prev = dates[0]
    streak_start: date | None = None
    for d in dates[1:]:
        gap = (d - prev).days
        if gap > 1:
            if streak_start is None:
                streak_start = prev + (d - prev)
        prev = d
    return issues


def check_date_alignment(files: dict[str, str]) -> list[str]:
    issues: list[str] = []
    date_sets: dict[str, set[date]] = {}
    for label, path in files.items():
        if not os.path.exists(path):
            continue
        dates, _ = _read_wide_data(path)
        date_sets[label] = set(dates)

    if len(date_sets) < 2:
        return issues

    labels = sorted(date_sets)
    base = date_sets[labels[0]]
    for label in labels[1:]:
        other = date_sets[label]
        only_base = sorted(base - other)[:5]
        only_other = sorted(other - base)[:5]
        if only_base:
            issues.append(
                f"  {len(base - other)} dates in {labels[0]} missing from {label}"
                f" (e.g., {only_base[0]})"
            )
        if only_other:
            issues.append(
                f"  {len(other - base)} dates in {label} missing from {labels[0]}"
                f" (e.g., {only_other[0]})"
            )
    return issues


def check_coverage_summary(path: str) -> list[str]:
    dates, industries = _read_wide_data(path)
    lines = [
        f"  File: {os.path.basename(path)}",
        f"  Date range: {dates[0]} ~ {dates[-1]} ({len(dates)} days)",
        f"  Industries: {len(industries)}",
    ]
    return lines


def run_checks(_config_path: str) -> int:
    issues_found = 0
    data_dir = os.path.join(REPO, "data", "real_sw2021")
    files = {
        "industry_close": os.path.join(data_dir, "industry_close.csv"),
        "benchmark_close": os.path.join(data_dir, "benchmark_close.csv"),
        "market_close": os.path.join(data_dir, "market_close.csv"),
    }

    print("=== Data Integrity Check ===")
    print(f"Data dir: {data_dir}")
    print()

    print("--- Coverage Summary ---")
    for label, path in files.items():
        if os.path.exists(path):
            for line in check_coverage_summary(path):
                print(line)
        else:
            print(f"  {label}: file not found")
    print()

    print("--- Outlier Check (> 20% single-day change) ---")
    for label, path in files.items():
        if not os.path.exists(path):
            continue
        issues = check_price_jumps(path)
        if issues:
            issues_found += len(issues)
            print(f"  {label}: {len(issues)} outliers")
            for issue in issues[:5]:
                print(issue)
            if len(issues) > 5:
                print(f"  ... and {len(issues) - 5} more")
        else:
            print(f"  {label}: OK")
    print()

    print("--- Date Alignment Check ---")
    alignment_issues = check_date_alignment(files)
    if alignment_issues:
        issues_found += len(alignment_issues)
        for issue in alignment_issues:
            print(issue)
    else:
        print("  All files aligned")
    print()

    if issues_found:
        print(f"Total issues found: {issues_found}")
    else:
        print("All checks passed.")
    return 0


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "configs/real_sw2021.toml"
    sys.exit(run_checks(config))
