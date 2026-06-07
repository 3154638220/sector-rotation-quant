"""Data integrity check tool.

Runs quality checks on configured research data files:
1. Coverage summary for every configured CSV
2. Outlier check: single-day price changes > threshold
3. Missing value check: consecutive non-numeric cells by asset
4. Date alignment across configured files
5. Metadata warnings for current-constituent stock data
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable


REPO = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


NumberSeries = dict[str, list[float | None]]


def _resolve_config_files(config_path: str) -> dict[str, str]:
    from quant_rotation.config import load_config

    app_config = load_config(config_path)
    candidates = {
        "industry_close": app_config.industry_close_path,
        "industry_amount": app_config.industry_amount_path,
        "industry_breadth20": app_config.industry_breadth20_path,
        "industry_breadth60": app_config.industry_breadth60_path,
        "industry_valuation": app_config.industry_valuation_path,
        "industry_prosperity": app_config.industry_prosperity_path,
        "market_close": app_config.market_close_path,
        "benchmark_close": app_config.benchmark_close_path,
        "stock_close": app_config.stock_close_path,
        "stock_amount": app_config.stock_amount_path,
        "stock_industry_map": app_config.stock_industry_map_path,
    }
    return {label: path for label, path in candidates.items() if path}


def _read_wide_data(path: str) -> tuple[list[date], NumberSeries]:
    dates: list[date] = []
    assets: NumberSeries = defaultdict(list)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "date" not in reader.fieldnames:
            raise ValueError(f"{path} must contain a date column")
        for row in reader:
            d = date.fromisoformat(row["date"])
            dates.append(d)
            for col, val in row.items():
                if col == "date":
                    continue
                value = (val or "").strip()
                if value == "":
                    assets[col].append(None)
                else:
                    assets[col].append(float(value))
    return dates, dict(assets)


def _is_price_file(label: str) -> bool:
    return label in {
        "industry_close",
        "benchmark_close",
        "market_close",
        "stock_close",
    }


def check_price_jumps(path: str, threshold: float = 0.20) -> list[str]:
    issues: list[str] = []
    dates, assets = _read_wide_data(path)
    for name, closes in assets.items():
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            curr = closes[i]
            if prev is None or curr is None or prev <= 0:
                continue
            change = abs(curr / prev - 1.0)
            if change > threshold:
                issues.append(
                    f"  {name} {dates[i]}: {change:.1%} jump"
                )
    return issues


def check_missing_values(
    dates: list[date],
    assets: NumberSeries,
    max_gap: int = 5,
) -> list[str]:
    issues: list[str] = []
    for name, values in assets.items():
        streak = 0
        streak_start: date | None = None
        for d, value in zip(dates, values):
            if value is None:
                if streak == 0:
                    streak_start = d
                streak += 1
                continue
            if streak > max_gap and streak_start is not None:
                issues.append(
                    f"  {name}: {streak} consecutive missing values "
                    f"from {streak_start} to {d}"
                )
            streak = 0
            streak_start = None
        if streak > max_gap and streak_start is not None:
            issues.append(
                f"  {name}: {streak} consecutive missing values "
                f"from {streak_start} to {dates[-1]}"
            )
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
    dates, assets = _read_wide_data(path)
    if not dates:
        return [
            f"  File: {os.path.basename(path)}",
            "  Date range: <empty>",
            "  Columns: 0",
        ]
    return [
        f"  File: {os.path.basename(path)}",
        f"  Date range: {dates[0]} ~ {dates[-1]} ({len(dates)} days)",
        f"  Columns: {len(assets)}",
    ]


def check_stock_map_summary(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return [f"  File: {os.path.basename(path)}", "  Rows: 0"]
        rows = list(reader)
    stocks = {row.get("stock", "").strip() for row in rows if row.get("stock")}
    industries = {
        row.get("industry", "").strip()
        for row in rows
        if row.get("industry")
    }
    snapshots = {
        (row.get("snapshot_date") or row.get("date") or row.get("as_of") or "").strip()
        for row in rows
        if row.get("snapshot_date") or row.get("date") or row.get("as_of")
    }
    lines = [
        f"  File: {os.path.basename(path)}",
        f"  Rows: {len(rows)}",
        f"  Stocks: {len(stocks)}",
        f"  Industries: {len(industries)}",
    ]
    if snapshots:
        lines.append(f"  Historical snapshots: {len(snapshots)}")
    else:
        lines.append("  Historical snapshots: none (static map)")
    return lines


def _nearby_manifest_paths(files: Iterable[str]) -> list[Path]:
    dirs = sorted({Path(path).parent for path in files})
    names = [
        "manifest.json",
        "stock_manifest.json",
        "breadth_manifest.json",
        "industry_prosperity_manifest.json",
        "industry_valuation_manifest.json",
    ]
    return [d / name for d in dirs for name in names if (d / name).exists()]


def _prosperity_manifest_path(prosperity_path: str) -> Path | None:
    path = Path(prosperity_path)
    candidates = [
        path.with_name("industry_prosperity_manifest.json"),
        path.with_name(f"{path.stem}_manifest.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _check_prosperity_metadata(path: str) -> list[str]:
    manifest_path = _prosperity_manifest_path(path)
    if manifest_path is None:
        return [
            "  industry_prosperity: no release-lag metadata found; "
            "treat as safe only if generated from same-day post-close amount "
            "and traded on the next rebalance"
        ]
    try:
        with manifest_path.open("r", encoding="utf-8-sig") as handle:
            manifest = json.load(handle)
    except json.JSONDecodeError as exc:
        return [f"  {manifest_path}: invalid JSON ({exc})"]

    warnings: list[str] = []
    if "source_file" not in manifest and "source" not in manifest:
        warnings.append(f"  {manifest_path}: prosperity source_file/source missing")
    if "release_lag_days" not in manifest:
        warnings.append(f"  {manifest_path}: release_lag_days missing")
    if "usable_from" not in manifest:
        warnings.append(f"  {manifest_path}: usable_from missing")
    return warnings


def _valuation_manifest_path(valuation_path: str) -> Path | None:
    path = Path(valuation_path)
    candidates = [
        path.with_name("industry_valuation_manifest.json"),
        path.with_name(f"{path.stem}_manifest.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _check_valuation_metadata(path: str) -> list[str]:
    manifest_path = _valuation_manifest_path(path)
    if manifest_path is None:
        return [
            "  industry_valuation: no manifest found; "
            "source and release-lag metadata are missing"
        ]
    try:
        with manifest_path.open("r", encoding="utf-8-sig") as handle:
            manifest = json.load(handle)
    except json.JSONDecodeError as exc:
        return [f"  {manifest_path}: invalid JSON ({exc})"]

    warnings: list[str] = []
    if "source_file" not in manifest and "source" not in manifest:
        warnings.append(f"  {manifest_path}: valuation source_file/source missing")
    if "release_lag_days" not in manifest:
        warnings.append(f"  {manifest_path}: release_lag_days missing")
    if "usable_from" not in manifest:
        warnings.append(f"  {manifest_path}: usable_from missing")
    return warnings


def check_metadata_warnings(files: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    seen: set[Path] = set()
    for manifest_path in _nearby_manifest_paths(files.values()):
        if manifest_path in seen:
            continue
        seen.add(manifest_path)
        with manifest_path.open("r", encoding="utf-8-sig") as handle:
            try:
                manifest = json.load(handle)
            except json.JSONDecodeError as exc:
                warnings.append(f"  {manifest_path}: invalid JSON ({exc})")
                continue
        if manifest.get("current_constituents") is True:
            warning = manifest.get(
                "survivor_bias_warning",
                "uses current constituents; historical snapshot validation required",
            )
            warnings.append(f"  {manifest_path}: {warning}")
        if (
            manifest.get("stock_source") == "sw_level1_current_constituents"
            or manifest.get("industry_source") == "sw_level1_current_constituents"
        ):
            warnings.append(
                f"  {manifest_path}: current SW constituents are not unbiased "
                "historical constituents"
            )
    if "industry_prosperity" in files:
        warnings.extend(_check_prosperity_metadata(files["industry_prosperity"]))
    if "industry_valuation" in files:
        warnings.extend(_check_valuation_metadata(files["industry_valuation"]))
    return warnings


def run_checks(
    config_path: str,
    jump_threshold: float = 0.20,
    *,
    production: bool = False,
) -> int:
    issues_found = 0
    files = _resolve_config_files(config_path)

    print("=== Data Integrity Check ===")
    print(f"Config: {config_path}")
    print()

    print("--- Coverage Summary ---")
    for label, path in files.items():
        if os.path.exists(path):
            print(f"[{label}]")
            summary = (
                check_stock_map_summary(path)
                if label == "stock_industry_map"
                else check_coverage_summary(path)
            )
            for line in summary:
                print(line)
        else:
            print(f"  {label}: file not found")
            issues_found += 1
    print()

    print(f"--- Outlier Check (> {jump_threshold:.0%} single-day price change) ---")
    for label, path in files.items():
        if not os.path.exists(path) or not _is_price_file(label):
            continue
        issues = check_price_jumps(path, threshold=jump_threshold)
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

    print("--- Missing Value Check ---")
    for label, path in files.items():
        if not os.path.exists(path) or label == "stock_industry_map":
            continue
        dates, values = _read_wide_data(path)
        issues = check_missing_values(dates, values)
        if issues:
            issues_found += len(issues)
            print(f"  {label}: {len(issues)} missing-value streaks")
            for issue in issues[:5]:
                print(issue)
            if len(issues) > 5:
                print(f"  ... and {len(issues) - 5} more")
        else:
            print(f"  {label}: OK")
    print()

    print("--- Date Alignment Check ---")
    alignment_files = {
        label: path
        for label, path in files.items()
        if os.path.exists(path) and label != "stock_industry_map"
    }
    alignment_issues = check_date_alignment(alignment_files)
    if alignment_issues:
        issues_found += len(alignment_issues)
        for issue in alignment_issues:
            print(issue)
    else:
        print("  All files aligned")
    print()

    print("--- Metadata Warnings ---")
    warnings = check_metadata_warnings(files)
    if warnings:
        for warning in warnings:
            print(warning)
        if production:
            issues_found += len(warnings)
    else:
        print("  No metadata warnings")
    print()

    if issues_found:
        print(f"Total issues found: {issues_found}")
    else:
        print("All checks passed.")
    return 1 if production and issues_found else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run data integrity checks")
    parser.add_argument(
        "--config",
        default="configs/real_sw2021.toml",
        help="TOML config path",
    )
    parser.add_argument(
        "--jump-threshold",
        type=float,
        default=0.20,
        help="Single-day price jump threshold",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Treat metadata warnings as failures",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(
        run_checks(
            args.config,
            jump_threshold=args.jump_threshold,
            production=args.production,
        )
    )
