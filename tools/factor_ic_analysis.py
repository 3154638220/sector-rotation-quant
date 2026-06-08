"""Factor IC/ICIR Analysis — compute Information Coefficient for each factor.

Computes cross-sectional Spearman rank correlation between factor raw values
and forward returns across holding periods (5, 10, 20, 40, 60 trading days).

Outputs:
  - factor_ic.csv: IC time series per factor per holding period
  - factor_icir.csv: ICIR (mean IC / std IC) per factor, overall and by year
  - factor_decay.csv: IC decay curve (IC vs holding period) per factor
"""
from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quant_rotation.config import load_config
from quant_rotation.data import (
    align_asset_data,
    load_benchmark_csv,
    load_wide_asset_csv,
    load_wide_close_csv,
)
from quant_rotation.factors import compute_factor_snapshot
from quant_rotation.models import BreadthData, FactorWeights, PriceData


def spearman_rank_ic(
    values_a: dict[str, float],
    values_b: dict[str, float],
) -> float:
    """Spearman rank correlation between two cross-sectional value sets."""
    common = set(values_a) & set(values_b)
    if len(common) < 5:
        return 0.0
    a_vals = [values_a[k] for k in common]
    b_vals = [values_b[k] for k in common]
    n = len(a_vals)

    def rank_values(vals: list[float]) -> list[float]:
        indexed = sorted(enumerate(vals), key=lambda x: x[1])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rank_a = rank_values(a_vals)
    rank_b = rank_values(b_vals)

    n_f = float(n)
    sum_a = sum(rank_a)
    sum_b = sum(rank_b)
    sum_a_sq = sum(v * v for v in rank_a)
    sum_b_sq = sum(v * v for v in rank_b)
    sum_ab = sum(rank_a[i] * rank_b[i] for i in range(n))

    numerator = sum_ab - sum_a * sum_b / n_f
    denom = math.sqrt(
        (sum_a_sq - sum_a * sum_a / n_f) * (sum_b_sq - sum_b * sum_b / n_f)
    )
    if denom == 0:
        return 0.0
    return numerator / denom


@dataclass
class ICDecayPoint:
    hold_period: int
    mean_ic: float
    std_ic: float
    icir: float
    n_samples: int


@dataclass
class FactorICResult:
    factor_name: str
    hold_period: int
    ic_series: dict[date, float] = field(default_factory=dict)
    decay_points: list[ICDecayPoint] = field(default_factory=list)

    @property
    def mean_ic(self) -> float:
        vals = [v for v in self.ic_series.values() if v == v]
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    @property
    def ic_std(self) -> float:
        vals = [v for v in self.ic_series.values() if v == v]
        if len(vals) < 2:
            return 0.0
        m = self.mean_ic
        return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))

    @property
    def icir(self) -> float:
        std = self.ic_std
        if std == 0:
            return 0.0
        return self.mean_ic / std

    def icir_by_year(self, dates_map: dict[date, int]) -> dict[int, dict[str, float]]:
        """Compute ICIR broken down by year."""
        by_year: dict[int, list[float]] = {}
        for dt, ic in self.ic_series.items():
            year = dates_map.get(dt, dt.year)
            if ic == ic:
                by_year.setdefault(year, []).append(ic)

        result: dict[int, dict[str, float]] = {}
        for year, vals in sorted(by_year.items()):
            if len(vals) < 2:
                result[year] = {"mean_ic": sum(vals) / len(vals) if vals else 0.0, "icir": 0.0, "n": len(vals)}
                continue
            m = sum(vals) / len(vals)
            s = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
            result[year] = {
                "mean_ic": m,
                "icir": m / s if s != 0 else 0.0,
                "n": len(vals),
            }
        return result


def compute_forward_return(
    closes: list[float],
    index: int,
    hold_period: int,
) -> float | None:
    """Point-in-time forward return over hold_period days."""
    future_index = index + hold_period
    if future_index >= len(closes):
        return None
    if closes[index] <= 0:
        return None
    return closes[future_index] / closes[index] - 1.0


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Factor IC/ICIR analysis")
    parser.add_argument("--config", default="configs/real_sw2021.toml", help="Config path")
    parser.add_argument(
        "--factors",
        default="ret60,ret20,ret5,vol20,consistency60,amount_strength",
        help="Comma-separated factor names to analyze",
    )
    parser.add_argument(
        "--hold-periods",
        default="5,10,20,40,60",
        help="Comma-separated holding periods in trading days",
    )
    parser.add_argument(
        "--output",
        default="reports/factor_ic_audit",
        help="Output directory for IC reports",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=20,
        help="Evaluation step in trading days (default: 20 = monthly)",
    )
    args = parser.parse_args()

    config_path = args.config
    factor_names = [f.strip() for f in args.factors.split(",")]
    hold_periods = [int(h) for h in args.hold_periods.split(",")]
    output_dir = Path(args.output)

    print(f"=== Factor IC/ICIR Analysis ===")
    print(f"Config: {config_path}")
    print(f"Factors: {factor_names}")
    print(f"Holding periods: {hold_periods}")
    print()

    app_config = load_config(config_path)

    industry_data = load_wide_close_csv(app_config.industry_close_path)

    amount_data = None
    if app_config.industry_amount_path:
        raw_amount = load_wide_asset_csv(app_config.industry_amount_path, value_name="amount")
        amount_data = align_asset_data(
            industry_data.dates, industry_data.assets, raw_amount, value_name="amount"
        )

    breadth_data = BreadthData(breadth20=None, breadth60=None)
    if app_config.industry_breadth20_path:
        raw_b20 = load_wide_asset_csv(app_config.industry_breadth20_path, value_name="breadth20")
        breadth20 = align_asset_data(
            industry_data.dates, industry_data.assets, raw_b20, value_name="breadth20"
        )
        breadth_data = BreadthData(breadth20=breadth20, breadth60=None)
    if app_config.industry_breadth60_path:
        raw_b60 = load_wide_asset_csv(app_config.industry_breadth60_path, value_name="breadth60")
        breadth60 = align_asset_data(
            industry_data.dates, industry_data.assets, raw_b60, value_name="breadth60"
        )
        breadth_data = BreadthData(
            breadth20=breadth_data.breadth20, breadth60=breadth60
        )

    valuation_data = None
    if app_config.industry_valuation_path:
        raw_val = load_wide_asset_csv(app_config.industry_valuation_path, value_name="valuation")
        valuation_data = align_asset_data(
            industry_data.dates, industry_data.assets, raw_val, value_name="valuation"
        )

    prosperity_data = None
    if app_config.industry_prosperity_path:
        raw_pros = load_wide_asset_csv(
            app_config.industry_prosperity_path, value_name="prosperity"
        )
        prosperity_data = align_asset_data(
            industry_data.dates, industry_data.assets, raw_pros, value_name="prosperity"
        )

    market_data = None
    market_weights = app_config.market_weights or {}
    if app_config.market_close_path:
        raw_mkt = load_wide_close_csv(app_config.market_close_path)
        market_data = align_asset_data(
            industry_data.dates, raw_mkt.assets, raw_mkt, value_name="market close"
        )

    weights = FactorWeights(
        ret20=1.0,
        ret60=1.0,
        ret120=1.0,
        rel_ret60=1.0,
        rel_ret20=1.0,
        momentum_accel=1.0,
        consistency60=1.0,
        amount_strength=1.0,
        breadth20=1.0,
        breadth60=1.0,
        valuation=1.0,
        prosperity=1.0,
        vol20=1.0,
        ret5=1.0,
    )

    n_dates = len(industry_data.dates)
    warmup = 120
    step = args.step

    eval_indices = list(range(warmup, n_dates, step))

    all_factor_fields: dict[str, list[dict[date, float]]] = {}
    dates_map: dict[int, int] = {}
    for idx in eval_indices:
        try:
            snap = compute_factor_snapshot(
                industry_data,
                idx,
                weights,
                amount_data=amount_data,
                breadth_data=breadth_data if breadth_data.available else None,
                valuation_data=valuation_data,
                prosperity_data=prosperity_data,
                market_data=market_data,
                market_weights=market_weights if market_weights else None,
            )
        except (ValueError, IndexError):
            continue

        eval_date = industry_data.dates[idx]
        dates_map[hash(eval_date)] = eval_date.year

        for factor_name in factor_names:
            if factor_name not in snap.fields:
                continue
            raw_vals = {}
            for asset, val in snap.fields[factor_name].items():
                if not (math.isnan(val) or math.isinf(val)):
                    raw_vals[asset] = val
            all_factor_fields.setdefault(factor_name, []).append(raw_vals)

    results: dict[str, dict[int, FactorICResult]] = {}  # factor_name -> hold_period -> result

    for factor_name in factor_names:
        if factor_name not in all_factor_fields:
            print(f"  [SKIP] {factor_name}: no snapshots computed")
            continue
        factor_snapshots = all_factor_fields[factor_name]
        results[factor_name] = {}

        for hold in hold_periods:
            ic_result = FactorICResult(factor_name=factor_name, hold_period=hold)
            n_pairs = 0
            for i, raw_vals in enumerate(factor_snapshots):
                idx = eval_indices[i]
                if idx + hold >= n_dates:
                    continue
                eval_date = industry_data.dates[idx]

                fwd_returns: dict[str, float] = {}
                for asset in industry_data.assets:
                    fr = compute_forward_return(
                        industry_data.closes[asset], idx, hold
                    )
                    if fr is not None:
                        fwd_returns[asset] = fr

                if len(fwd_returns) < 5:
                    continue
                if len(raw_vals) < 5:
                    continue

                ic = spearman_rank_ic(raw_vals, fwd_returns)
                ic_result.ic_series[eval_date] = ic
                n_pairs += 1

            results[factor_name][hold] = ic_result
            print(
                f"  {factor_name:>20s}  hold={hold:>2d}d  "
                f"IC_mean={ic_result.mean_ic:+.4f}  "
                f"IC_std={ic_result.ic_std:.4f}  "
                f"ICIR={ic_result.icir:+.3f}  "
                f"N={n_pairs}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "factor_ic.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["date"]
        for fn in sorted(results):
            for hold in hold_periods:
                header.append(f"{fn}_hold{hold}d")
        writer.writerow(header)

        all_dates: set[date] = set()
        for fn_results in results.values():
            for ic_result in fn_results.values():
                all_dates.update(ic_result.ic_series.keys())
        sorted_dates = sorted(all_dates)

        for dt in sorted_dates:
            row = [dt.isoformat()]
            for fn in sorted(results):
                for hold in hold_periods:
                    val = results[fn][hold].ic_series.get(dt, "")
                    row.append(f"{val:.6f}" if val != "" else "")
            writer.writerow(row)

    with (output_dir / "factor_icir.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["factor", "hold_period", "section", "mean_ic", "icir", "n_samples"])
        for fn in sorted(results):
            for hold in hold_periods:
                ic_result = results[fn][hold]
                writer.writerow([
                    fn, hold, "overall",
                    f"{ic_result.mean_ic:.6f}",
                    f"{ic_result.icir:.6f}",
                    len(ic_result.ic_series),
                ])
                by_year = ic_result.icir_by_year(dates_map)
                for year, info in sorted(by_year.items()):
                    writer.writerow([
                        fn, hold, f"year_{year}",
                        f"{info['mean_ic']:.6f}",
                        f"{info['icir']:.6f}",
                        info["n"],
                    ])

    with (output_dir / "factor_decay.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["factor", "hold_period", "mean_ic", "icir"])
        for fn in sorted(results):
            for hold in hold_periods:
                ic_result = results[fn][hold]
                writer.writerow([
                    fn, hold,
                    f"{ic_result.mean_ic:.6f}",
                    f"{ic_result.icir:.6f}",
                ])

    print(f"\nReports written to {output_dir.resolve()}")
    print(f"  - factor_ic.csv")
    print(f"  - factor_icir.csv")
    print(f"  - factor_decay.csv")

    print("\n=== Summary ===")
    print(f"{'Factor':<20s} {'Hold':>5s} {'Mean IC':>9s} {'ICIR':>7s}")
    print("-" * 45)
    for fn in sorted(results):
        for hold in hold_periods:
            ic_result = results[fn][hold]
            print(
                f"{fn:<20s} {hold:>4d}d "
                f"{ic_result.mean_ic:>+8.4f} {ic_result.icir:>+7.3f}"
            )

    identified_strong = []
    identified_weak = []
    for fn in sorted(results):
        best_icir = max(
            (results[fn][hold].icir for hold in hold_periods if hold in results[fn]),
            default=0.0,
        )
        best_mean_ic = max(
            (results[fn][hold].mean_ic for hold in hold_periods if hold in results[fn]),
            default=0.0,
        )
        if abs(best_icir) > 0.12:
            identified_strong.append((fn, best_mean_ic, best_icir))
        if abs(best_icir) < 0.05:
            identified_weak.append((fn, best_mean_ic, best_icir))

    if identified_strong:
        print("\n--- Strong factors (|ICIR| > 0.12) ---")
        for name, mean_ic, icir in identified_strong:
            print(f"  {name}: mean_IC={mean_ic:+.4f}, ICIR={icir:+.3f}")
    if identified_weak:
        print("\n--- Weak factors (|ICIR| < 0.05) ---")
        for name, mean_ic, icir in identified_weak:
            print(f"  {name}: mean_IC={mean_ic:+.4f}, ICIR={icir:+.3f}")


if __name__ == "__main__":
    main()
