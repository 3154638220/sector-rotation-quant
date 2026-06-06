"""7.2 Factor independence check — cross-sectional correlations between factors.

Computes cross-sectional correlations between all factor pairs at regular
intervals across the dataset, then reports the average absolute correlation.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quant_rotation.config import load_config
from quant_rotation.data import (
    align_asset_data,
    align_benchmark,
    load_benchmark_csv,
    load_wide_asset_csv,
    load_wide_close_csv,
)
from quant_rotation.factors import compute_factor_snapshot
from quant_rotation.models import (
    BreadthData,
    FactorWeights,
    PriceData,
)


def cross_sectional_correlation(
    values_a: dict[str, float],
    values_b: dict[str, float],
) -> float:
    """Pearson correlation across assets at a single point in time."""
    common = values_a.keys() & values_b.keys()
    if len(common) < 5:
        return 0.0
    a_vals = [values_a[k] for k in common]
    b_vals = [values_b[k] for k in common]

    n = len(a_vals)
    mean_a = sum(a_vals) / n
    mean_b = sum(b_vals) / n
    num = sum((a_vals[i] - mean_a) * (b_vals[i] - mean_b) for i in range(n))
    den_a = (sum((v - mean_a) ** 2 for v in a_vals)) ** 0.5
    den_b = (sum((v - mean_b) ** 2 for v in b_vals)) ** 0.5
    if den_a == 0 or den_b == 0:
        return 0.0
    return num / (den_a * den_b)


def main():
    config_path = "configs/exp_valuation.toml"
    app_config = load_config(config_path)

    industry_data = load_wide_close_csv(app_config.industry_close_path)
    amount_data = None
    if app_config.industry_amount_path:
        raw_amount = load_wide_asset_csv(app_config.industry_amount_path, value_name="amount")
        amount_data = align_asset_data(industry_data.dates, industry_data.assets, raw_amount, value_name="amount")

    breadth_data = BreadthData(breadth20=None, breadth60=None)
    if app_config.industry_breadth20_path:
        raw_b20 = load_wide_asset_csv(app_config.industry_breadth20_path, value_name="breadth20")
        breadth20 = align_asset_data(industry_data.dates, industry_data.assets, raw_b20, value_name="breadth20")
        breadth_data = BreadthData(breadth20=breadth20, breadth60=None)

    valuation_data = None
    if app_config.industry_valuation_path:
        raw_val = load_wide_asset_csv(app_config.industry_valuation_path, value_name="valuation")
        valuation_data = align_asset_data(industry_data.dates, industry_data.assets, raw_val, value_name="valuation")

    prosperity_data = None
    if app_config.industry_prosperity_path:
        raw_pros = load_wide_asset_csv(app_config.industry_prosperity_path, value_name="prosperity")
        prosperity_data = align_asset_data(industry_data.dates, industry_data.assets, raw_pros, value_name="prosperity")

    market_data = None
    market_weights = app_config.market_weights or {}
    if app_config.market_close_path:
        raw_mkt = load_wide_close_csv(app_config.market_close_path)
        market_data = align_asset_data(industry_data.dates, raw_mkt.assets, raw_mkt, value_name="market close")

    weights = FactorWeights(
        ret20=1.0, ret60=1.0, ret120=1.0,
        rel_ret60=1.0, rel_ret20=1.0, momentum_accel=1.0,
        consistency60=1.0, amount_strength=1.0,
        breadth20=1.0, breadth60=1.0,
        valuation=1.0, prosperity=1.0,
        vol20=1.0, ret5=1.0,
    )

    n_dates = len(industry_data.dates)
    warmup = 120
    step = max(1, (n_dates - warmup) // 100)

    factor_names = [
        "ret20", "ret60", "ret120",
        "rel_ret60", "rel_ret20", "momentum_accel",
        "consistency60", "amount_strength",
        "breadth20", "breadth60",
        "valuation", "prosperity",
        "vol20", "ret5",
    ]

    all_corrs: dict[tuple[str, str], list[float]] = {(a, b): [] for a in factor_names for b in factor_names if a < b}

    sample_count = 0
    for idx in range(warmup, n_dates, step):
        try:
            snap = compute_factor_snapshot(
                industry_data, idx, weights,
                amount_data=amount_data,
                breadth_data=breadth_data if breadth_data.available else None,
                valuation_data=valuation_data,
                prosperity_data=prosperity_data,
                market_data=market_data,
                market_weights=market_weights if market_weights else None,
            )
        except (ValueError, IndexError):
            continue

        sample_count += 1
        for a in factor_names:
            for b in factor_names:
                if a >= b:
                    continue
                a_vals = snap.fields.get(a, {})
                b_vals = snap.fields.get(b, {})
                if not a_vals or not b_vals:
                    continue
                corr = cross_sectional_correlation(a_vals, b_vals)
                all_corrs[(a, b)].append(corr)

    print(f"Factor Cross-Sectional Correlations (avg |r| over {sample_count} snapshots)")
    print("=" * 80)

    avg_corrs = {}
    for (a, b), corrs in sorted(all_corrs.items()):
        if not corrs:
            continue
        avg = sum(abs(c) for c in corrs) / len(corrs)
        avg_corrs[(a, b)] = avg

    sorted_pairs = sorted(avg_corrs.items(), key=lambda x: -x[1])

    print(f"{'Factor A':<18} {'Factor B':<18} {'Avg |r|':>8}  {'Warning'}")
    print("-" * 60)
    high_corr_count = 0
    for (a, b), avg in sorted_pairs:
        warn = " *** HIGH ***" if avg > 0.7 else ""
        if avg > 0.7:
            high_corr_count += 1
        print(f"{a:<18} {b:<18} {avg:>8.3f}  {warn}")

    print(f"\nHigh correlations (>0.7): {high_corr_count} pairs")
    print(f"Total factor pairs analyzed: {len(avg_corrs)}")

    if high_corr_count > 0:
        print("\nWARNING: Some factor pairs have high cross-sectional correlation.")
        print("Consider removing redundant factors or combining them.")
    else:
        print("\nAll factor pairs have acceptably low cross-sectional correlation.")


if __name__ == "__main__":
    main()
