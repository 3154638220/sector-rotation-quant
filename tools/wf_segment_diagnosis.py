"""WF segment diagnosis tool.

Reads walk_forward_folds.csv from a walk-forward validation output and produces:
1. Per-segment statistics (sw2000, sw2014, sw2021) based on fold date ranges
2. Failure fold diagnostics: which folds failed, why (train->test degradation)
3. Train/test correlation analysis per metric
4. Summary verdict for production readiness

Usage:
    python tools/wf_segment_diagnosis.py reports/exp_full27_best_fixed
    python tools/wf_segment_diagnosis.py reports/exp_full27_best_fixed --segment-stats
    python tools/wf_segment_diagnosis.py reports/exp_full27_best_fixed --all
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median, pstdev


def _parse_date(val: str) -> date:
    return date.fromisoformat(val)


def _classify_segment(fold: dict) -> int:
    test_start = _parse_date(fold["test_start"])
    if test_start.year <= 2014:
        return 1
    elif test_start.year <= 2020:
        return 2
    else:
        return 3


SEGMENT_LABELS = {1: "sw2000 (<2015)", 2: "sw2014 (2015-2020)", 3: "sw2021 (2021+)"}


def load_folds(folds_path: Path) -> list[dict]:
    with folds_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _metric_fields(folds: list[dict]) -> list[str]:
    train_fields: set[str] = set()
    test_fields: set[str] = set()
    for fold in folds:
        for key in fold:
            if key.startswith("train_") and not key.startswith("train_start") and not key.startswith("train_end"):
                train_fields.add(key.removeprefix("train_"))
            if key.startswith("test_") and not key.startswith("test_start") and not key.startswith("test_end"):
                test_fields.add(key.removeprefix("test_"))
    return sorted(train_fields & test_fields)


def diagnose_folds(folds: list[dict]) -> dict:
    metrics = _metric_fields(folds)
    result: dict = {
        "total_folds": len(folds),
        "segment_counts": defaultdict(int),
        "segment_profitable": defaultdict(int),
        "segment_stats": defaultdict(lambda: defaultdict(list)),
        "failure_folds": [],
        "degradation_folds": [],
    }

    for fold in folds:
        seg = _classify_segment(fold)
        result["segment_counts"][seg] += 1

        test_return = float(fold.get("test_annualized_return", "0"))
        train_return = float(fold.get("train_annualized_return", "0"))
        fold_num = int(fold["fold"])

        for m in metrics:
            train_val = float(fold.get(f"train_{m}", "0") or "0")
            test_val = float(fold.get(f"test_{m}", "0") or "0")
            result["segment_stats"][seg][f"train_{m}"].append(train_val)
            result["segment_stats"][seg][f"test_{m}"].append(test_val)

        if test_return > 0:
            result["segment_profitable"][seg] += 1

        if test_return <= 0:
            result["failure_folds"].append({
                "fold": fold_num,
                "segment": seg,
                "test_start": fold["test_start"],
                "test_end": fold["test_end"],
                "train_return": train_return,
                "test_return": test_return,
                "train_sharpe": float(fold.get("train_sharpe_ratio", "0") or "0"),
                "test_sharpe": float(fold.get("test_sharpe_ratio", "0") or "0"),
                "selected_name": fold.get("selected_name", ""),
            })

        if test_return < train_return * 0.5:
            result["degradation_folds"].append({
                "fold": fold_num,
                "segment": seg,
                "train_return": train_return,
                "test_return": test_return,
                "degradation_ratio": test_return / train_return if train_return != 0 else float("inf"),
            })

    return result


def print_diagnosis(folds_path: Path, diagnosis: dict, show_segment_stats: bool = False,
                    show_failures: bool = False, show_degradation: bool = False) -> None:
    print()
    print(f"=== WF Segment Diagnosis: {folds_path.parent.name} ===")
    print()
    print(f"Total folds: {diagnosis['total_folds']}")
    print()

    print("--- Fold Count by Segment ---")
    for seg in sorted(diagnosis["segment_counts"]):
        total = diagnosis["segment_counts"][seg]
        prof = diagnosis["segment_profitable"].get(seg, 0)
        label = SEGMENT_LABELS.get(seg, f"Segment {seg}")
        pct = prof / total * 100 if total else 0
        print(f"  {label:<25}: {total:>2} folds  profitable: {prof:>2} ({pct:.0f}%)  "
              f"unprofitable: {total - prof:>2}")
    print()

    for seg in sorted(diagnosis["segment_stats"]):
        stats = diagnosis["segment_stats"][seg]
        train_returns = stats.get("train_annualized_return", [])
        test_returns = stats.get("test_annualized_return", [])
        if not test_returns:
            continue
        label = SEGMENT_LABELS.get(seg, f"Segment {seg}")
        print(f"--- {label}: Test Metrics ---")
        print(f"  folds:           {len(test_returns)}")
        print(f"  mean_return:     {mean(test_returns):>+8.1%}")
        print(f"  median_return:   {median(test_returns):>+8.1%}")
        print(f"  std_return:      {pstdev(test_returns):>8.1%}")
        if train_returns:
            print(f"  train_mean:      {mean(train_returns):>+8.1%}")
            print(f"  train_median:    {median(train_returns):>+8.1%}")
            degradation = mean(test_returns) - mean(train_returns)
            print(f"  degradation:     {degradation:>+8.1%}")
        print()

    if show_segment_stats:
        print("--- Per-Segment Performance Breakdown ---")
        metrics = ["annualized_return", "sharpe_ratio", "max_drawdown",
                   "calmar_ratio", "monthly_win_rate"]
        for seg in sorted(diagnosis["segment_stats"]):
            stats = diagnosis["segment_stats"][seg]
            label = SEGMENT_LABELS.get(seg, f"Segment {seg}")
            print(f"\n  [{label}]")
            for m in metrics:
                train_vals = stats.get(f"train_{m}", [])
                test_vals = stats.get(f"test_{m}", [])
                if test_vals:
                    print(f"    test_{m:<20}: mean={mean(test_vals):>+.4f}  "
                          f"median={median(test_vals):>+.4f}  std={pstdev(test_vals):.4f}")
                if train_vals:
                    print(f"    train_{m:<19}: mean={mean(train_vals):>+.4f}  "
                          f"median={median(train_vals):>+.4f}  std={pstdev(train_vals):.4f}")

    if show_failures:
        print()
        print("--- Failure Folds (test_return <= 0) ---")
        failures = diagnosis["failure_folds"]
        if failures:
            print(f"  Total: {len(failures)}/{diagnosis['total_folds']}")
            print(f"  {'Fold':>5} {'Seg':>4} {'Test Start':>12} {'Test End':>12} "
                  f"{'Train Ret':>10} {'Test Ret':>10} {'Train SR':>8} {'Test SR':>8} {'Candidate'}")
            print("  " + "-" * 85)
            for f in sorted(failures, key=lambda x: x["fold"]):
                print(f"  {f['fold']:>5} {f['segment']:>4} {f['test_start']:>12} {f['test_end']:>12} "
                      f"{f['train_return']:>+9.1%} {f['test_return']:>+9.1%} "
                      f"{f['train_sharpe']:>8.3f} {f['test_sharpe']:>8.3f} "
                      f"{f['selected_name'][:30]}")
        else:
            print("  None! All folds profitable.")
        print()

    if show_degradation:
        print("--- Top Degradation Folds (test < 50% train) ---")
        deg_folds = diagnosis["degradation_folds"]
        deg_folds.sort(key=lambda x: x["test_return"])
        for f in deg_folds[:10]:
            print(f"  Fold {f['fold']:>3} (seg={f['segment']}): "
                  f"train={f['train_return']:>+7.1%}  test={f['test_return']:>+7.1%}")
        print()

    total = diagnosis["total_folds"]
    failure_count = len(diagnosis["failure_folds"])
    profit_pct = (total - failure_count) / total * 100 if total else 0

    print("--- Verdict ---")
    issues: list[str] = []
    if profit_pct < 70:
        issues.append(f"OOS profitable folds {profit_pct:.0f}% < 70% threshold")
    else:
        print(f"  OOS profitable folds: {total - failure_count}/{total} ({profit_pct:.0f}%)")

    for seg in sorted(diagnosis["segment_counts"]):
        total_seg = diagnosis["segment_counts"][seg]
        prof = diagnosis["segment_profitable"].get(seg, 0)
        seg_pct = prof / total_seg * 100 if total_seg else 0
        if seg_pct < 60:
            label = SEGMENT_LABELS.get(seg, f"Segment {seg}")
            issues.append(f"{label}: only {seg_pct:.0f}% profitable ({prof}/{total_seg})")

    if issues:
        print("  Issues found:")
        for issue in issues:
            print(f"    - {issue}")
        print("  Verdict: NOT PRODUCTION READY")
    else:
        print("  No blocking issues detected.")
        print("  Verdict: MAY BE PRODUCTION READY (verify other checks)")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose WF folds by segment")
    parser.add_argument("wf_dir", help="Path to WF report directory")
    parser.add_argument("--all", action="store_true", help="Show all diagnostics")
    parser.add_argument("--segment-stats", action="store_true",
                        help="Show per-segment metric breakdowns")
    parser.add_argument("--failures", action="store_true",
                        help="Show detailed failure fold list")
    parser.add_argument("--degradation", action="store_true",
                        help="Show train->test degradation folds")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    wf_dir = Path(args.wf_dir)
    folds_path = wf_dir / "walk_forward_folds.csv"

    if not folds_path.exists():
        print(f"ERROR: {folds_path} not found")
        return 1

    folds = load_folds(folds_path)
    if not folds:
        print(f"No folds found in {folds_path}")
        return 1

    diagnosis = diagnose_folds(folds)
    print_diagnosis(
        folds_path,
        diagnosis,
        show_segment_stats=args.all or args.segment_stats,
        show_failures=args.all or args.failures,
        show_degradation=args.all or args.degradation,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
