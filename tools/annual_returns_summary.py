"""Annual returns summary tool.

Reads annual_returns.csv files and prints:
- Year-by-year returns (single or multi-file comparison)
- Negative year count, worst/best year, median, annualized
- Consistency ratio (positive years / total years)
- Multi-file side-by-side comparison with PASS/WARN/FAIL verdicts
- Segment-aware statistics when used with --compare
"""

import argparse
import csv
import sys
from pathlib import Path


def load_annual_returns(path: str) -> dict[int, float]:
    result: dict[int, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return result
        return_column = (
            "strategy_return"
            if "strategy_return" in reader.fieldnames
            else "return"
        )
        for row in reader:
            year = int(row["year"])
            result[year] = float(row[return_column])
    return result


def summarize(annual_dict: dict[int, float]) -> dict:
    returns = list(annual_dict.values())
    if not returns:
        return {
            "years": [],
            "returns": [],
            "negative_years": 0,
            "worst_year": 0.0,
            "best_year": 0.0,
            "annualized": 0.0,
            "median_return": 0.0,
            "consistency_ratio": 1.0,
        }
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


def segment_stats(annual_dict: dict[int, float]) -> dict[int, dict]:
    segments = {}
    for year, ret in annual_dict.items():
        if year <= 2014:
            seg = 1
        elif year <= 2020:
            seg = 2
        else:
            seg = 3
        if seg not in segments:
            segments[seg] = {}
        segments[seg][year] = ret
    return segments


SEGMENT_NAMES = {1: "sw2000 (<=2014)", 2: "sw2014 (2015-2020)", 3: "sw2021 (2021+)"}


def print_summary(stats: dict, label: str = "") -> dict:
    print()
    header = f"=== Annual Returns Summary{' — ' + label if label else ''} ==="
    print(header)
    print()
    if not stats["years"]:
        print("  No data")
        return stats
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
    return stats


def print_segment_stats(annual_dict: dict[int, float]) -> None:
    segs = segment_stats(annual_dict)
    if len(segs) <= 1:
        return
    print()
    print("--- Segment Statistics ---")
    print()
    print(f"{'Segment':<28} {'Years':>5} {'Neg':>4} {'Worst':>8} {'Best':>8} {'Median':>8} {'Ann':>8} {'Cons':>6}")
    print("-" * 85)
    for seg_id in sorted(segs):
        seg_data = segs[seg_id]
        s = summarize(seg_data)
        print(
            f"{SEGMENT_NAMES.get(seg_id, f'S{seg_id}'):<28} "
            f"{len(s['years']):>5} "
            f"{s['negative_years']:>4} "
            f"{s['worst_year']:>+7.1%} "
            f"{s['best_year']:>+7.1%} "
            f"{s['median_return']:>+7.1%} "
            f"{s['annualized']:>+7.1%} "
            f"{s['consistency_ratio']:>5.1%}"
        )
    print()


def print_multi_comparison(file_stats: list[tuple[str, dict]]) -> None:
    if not file_stats:
        return
    all_years: set[int] = set()
    for _, s in file_stats:
        all_years.update(s["years"])
    year_list = sorted(all_years)
    if not year_list:
        return

    print()
    print("=== Multi-File Comparison ===")
    print()
    header = f"{'Year':>6}"
    for fname, _ in file_stats:
        short = fname[:14] if len(fname) > 15 else fname
        header += f"  {short:>9}"
    print(header)
    print("-" * (9 + 12 * len(file_stats)))

    for year in year_list:
        row = f"{year:>6}"
        for _, s in file_stats:
            if year in s["years"]:
                idx = s["years"].index(year)
                row += f"  {s['returns'][idx]:>+8.1%}"
            else:
                row += "         —"
        print(row)

    print("-" * (9 + 12 * len(file_stats)))
    print()
    print(f"{'':>6}  {'Neg':>3} {'Worst':>8} {'Best':>8} {'Median':>8} {'Ann':>8} {'Verdict':>8}")
    print("-" * 60)

    for fname, s in file_stats:
        short = fname[:14]
        if s["negative_years"] <= 1 and s["worst_year"] >= -0.10:
            verdict = "PASS"
        elif s["negative_years"] <= 2 and s["worst_year"] >= -0.15:
            verdict = "WARN"
        else:
            verdict = "FAIL"
        print(
            f"{short:>6}  "
            f"{s['negative_years']:>3} "
            f"{s['worst_year']:>+7.1%} "
            f"{s['best_year']:>+7.1%} "
            f"{s['median_return']:>+7.1%} "
            f"{s['annualized']:>+7.1%} "
            f"{verdict:>8}"
        )
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze annual returns CSV files")
    parser.add_argument(
        "paths", nargs="*", help="One or more annual_returns.csv paths"
    )
    parser.add_argument(
        "--compare", nargs="+", metavar="PATH",
        help="Compare multiple annual_returns.csv files side-by-side"
    )
    parser.add_argument("--segments", action="store_true", help="Show segment stats")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    all_paths: list[str] = list(args.paths or [])
    if args.compare:
        all_paths.extend(args.compare)

    if not all_paths:
        parser.print_help()
        return 1

    file_stats: list[tuple[str, dict]] = []
    for path in all_paths:
        if not Path(path).exists():
            print(f"File not found: {path}")
            continue
        annuals = load_annual_returns(path)
        if not annuals:
            print(f"No annual returns found in {path}")
            continue
        stats = summarize(annuals)
        label = Path(path).stem if len(all_paths) > 1 else ""
        print_summary(stats, label)
        if args.segments:
            print_segment_stats(annuals)
        file_stats.append((Path(path).name, stats))

    if len(file_stats) > 1:
        print_multi_comparison(file_stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())
