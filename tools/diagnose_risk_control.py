"""G3: Risk Control Accuracy Diagnosis.

Analyzes rebalances.csv to classify each risk_off event by:
- TRUE_POSITIVE: benchmark dropped > 2% during the off period (effective)
- FALSE_POSITIVE: benchmark rose > 2% during the off period (missed gains)
- NEUTRAL: benchmark change within ±2%

Also analyzes events by cause (market_trend vs market_score) and by year.
"""

import csv
import os
from collections import defaultdict
from datetime import date

REPO = os.path.dirname(os.path.dirname(__file__))

def load_rebalances(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)

def load_benchmark(path: str) -> dict[date, float]:
    result = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[date.fromisoformat(row["date"])] = float(row["close"])
    return result

def classify_event(benchmark_return: float, threshold: float = 0.02) -> str:
    if benchmark_return <= -threshold:
        return "TRUE_POSITIVE"   # correctly avoided
    elif benchmark_return >= threshold:
        return "FALSE_POSITIVE"  # wrongly missed
    return "NEUTRAL"

def diagnose(rebalances_path: str, benchmark_path: str, output_path: str):
    rebalances = load_rebalances(rebalances_path)
    benchmarks = load_benchmark(benchmark_path)

    # Build list of event periods
    events = []
    for i, row in enumerate(rebalances):
        exposure = float(row["exposure"])
        if exposure >= 0.001 and row["holdings"].strip():
            continue  # risk_on period, skip

        # This is a risk_off entry; the period starts at this rebalance date
        start_date = date.fromisoformat(row["date"])
        # Find the next rebalance date as the end of the period
        if i + 1 < len(rebalances):
            end_date = date.fromisoformat(rebalances[i + 1]["date"])
        else:
            # Use last available benchmark date as end
            end_date = max(benchmarks.keys())

        # Get benchmark values
        if start_date not in benchmarks or end_date not in benchmarks:
            # Find nearest benchmark dates
            all_dates = sorted(benchmarks.keys())
            start_b = _find_nearest(all_dates, start_date, after=True)
            end_b = _find_nearest(all_dates, end_date, after=False)
        else:
            start_b, end_b = start_date, end_date

        if start_b not in benchmarks or end_b not in benchmarks:
            continue

        start_val = benchmarks[start_b]
        end_val = benchmarks[end_b]
        benchmark_return = (end_val / start_val) - 1.0

        # Determine cause
        market_trend = row.get("market_trend", "") == "true"
        market_score_ok = row.get("market_score_ok", "") == "true"
        risk_on_field = row.get("risk_on", "") == "true"

        # risk_on=false means risk_off event
        # We analyze why: market_trend=false or market_score_ok=false
        cause_parts = []
        if not market_trend:
            cause_parts.append("market_trend")
        if not market_score_ok:
            cause_parts.append("market_score")
        cause = "+".join(cause_parts) if cause_parts else "unknown"

        result_type = classify_event(benchmark_return)

        events.append({
            "signal_date": row["signal_date"],
            "date_start": start_date.isoformat(),
            "date_end": end_date.isoformat(),
            "benchmark_start": round(start_val, 2),
            "benchmark_end": round(end_val, 2),
            "benchmark_return": round(benchmark_return * 100, 2),
            "cause": cause,
            "result": result_type,
            "market_trend": market_trend,
            "market_score_ok": market_score_ok,
            "market_score": float(row["market_score"]) if row.get("market_score") and row["market_score"] else None,
        })

    # Write detailed CSV
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "signal_date", "date_start", "date_end",
            "benchmark_start", "benchmark_end", "benchmark_return",
            "cause", "result", "market_trend", "market_score_ok", "market_score",
        ])
        writer.writeheader()
        writer.writerows(events)

    # Summary statistics
    total = len(events)
    true_pos = sum(1 for e in events if e["result"] == "TRUE_POSITIVE")
    false_pos = sum(1 for e in events if e["result"] == "FALSE_POSITIVE")
    neutral = sum(1 for e in events if e["result"] == "NEUTRAL")

    hit_rate = (true_pos / total * 100) if total else 0
    false_alarm_rate = (false_pos / total * 100) if total else 0

    # By cause
    by_cause = defaultdict(lambda: {"total": 0, "TRUE_POSITIVE": 0, "FALSE_POSITIVE": 0, "NEUTRAL": 0})
    for e in events:
        by_cause[e["cause"]]["total"] += 1
        by_cause[e["cause"]][e["result"]] += 1

    # By year
    by_year = defaultdict(lambda: {"total": 0, "TRUE_POSITIVE": 0, "FALSE_POSITIVE": 0, "NEUTRAL": 0})
    for e in events:
        yr = e["date_start"][:4]
        by_year[yr]["total"] += 1
        by_year[yr][e["result"]] += 1

    # Print summary
    print("=" * 70)
    print("RISK CONTROL ACCURACY DIAGNOSIS (G3)")
    print("=" * 70)
    print(f"Total risk_off events: {total}")
    print(f"  TRUE_POSITIVE  (correctly avoided loss): {true_pos:3d} ({hit_rate:.1f}%)")
    print(f"  FALSE_POSITIVE (wrongly missed gains):  {false_pos:3d} ({false_alarm_rate:.1f}%)")
    print(f"  NEUTRAL        (market moved < ±2%):    {neutral:3d} ({neutral/total*100:.1f}%)" if total else "")
    print()

    avg_loss_avoided = sum(e["benchmark_return"] for e in events if e["result"] == "TRUE_POSITIVE")
    avg_loss_avoided = avg_loss_avoided / true_pos if true_pos else 0
    avg_gain_missed = sum(e["benchmark_return"] for e in events if e["result"] == "FALSE_POSITIVE")
    avg_gain_missed = avg_gain_missed / false_pos if false_pos else 0

    print(f"Avg loss avoided per true positive: {avg_loss_avoided:.2f}%")
    print(f"Avg gain missed per false positive:  {avg_gain_missed:.2f}%")
    print()

    # By cause breakdown
    print("--- By Cause ---")
    for cause in sorted(by_cause):
        stats = by_cause[cause]
        t = stats["total"]
        tp_pct = stats["TRUE_POSITIVE"] / t * 100 if t else 0
        fp_pct = stats["FALSE_POSITIVE"] / t * 100 if t else 0
        print(f"  {cause:30s}: total={t:2d}  TP={stats['TRUE_POSITIVE']:2d} ({tp_pct:.0f}%)  "
              f"FP={stats['FALSE_POSITIVE']:2d} ({fp_pct:.0f}%)  N={stats['NEUTRAL']:2d}")
    print()

    # By year breakdown
    print("--- By Year ---")
    for yr in sorted(by_year):
        stats = by_year[yr]
        t = stats["total"]
        tp_pct = stats["TRUE_POSITIVE"] / t * 100 if t else 0
        fp_pct = stats["FALSE_POSITIVE"] / t * 100 if t else 0
        print(f"  {yr}: total={t:2d}  TP={stats['TRUE_POSITIVE']:2d} ({tp_pct:.0f}%)  "
              f"FP={stats['FALSE_POSITIVE']:2d} ({fp_pct:.0f}%)  N={stats['NEUTRAL']:2d}")

    print()
    print(f"Detailed results written to: {output_path}")
    print()

    # Decision guidance
    if hit_rate < 50:
        print("VERDICT: hit_rate < 50% => risk control is more harmful than helpful.")
        print("  G1 (soft risk-off) and G2 (market state classifier) are HIGH PRIORITY.")
    else:
        print(f"VERDICT: hit_rate = {hit_rate:.1f}% => risk control provides net positive value.")
        print("  G1/G2 may still improve the false_alarm_rate.")

    return events


def _find_nearest(dates_sorted: list[date], target: date, after: bool = True) -> date | None:
    """Find nearest date >= target (after=True) or <= target (after=False)."""
    candidates = [d for d in dates_sorted if (d >= target if after else d <= target)]
    if not candidates:
        return None
    return min(candidates) if after else max(candidates)


if __name__ == "__main__":
    productions = [
        ("reports/production", "data/real"),
        ("reports/real_sw2000", "data/real_sw2000"),
        ("reports/real_sw2014", "data/real_sw2014"),
        ("reports/real_sw2021", "data/real_sw2021"),
    ]

    for report_dir, data_dir in productions:
        rebalances_path = os.path.join(REPO, report_dir, "rebalances.csv")
        benchmark_path = os.path.join(REPO, data_dir, "benchmark_close.csv")
        output_path = os.path.join(REPO, report_dir, "risk_control_accuracy.csv")

        if not os.path.exists(rebalances_path):
            print(f"SKIP: {rebalances_path} not found")
            continue
        if not os.path.exists(benchmark_path):
            print(f"SKIP: {benchmark_path} not found")
            continue

        print(f"\n>>> Analyzing: {report_dir}")
        diagnose(rebalances_path, benchmark_path, output_path)
