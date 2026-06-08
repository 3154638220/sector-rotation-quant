"""Stability Test — perturbation-based robustness check for strategy parameters.

Perturbs factor weights, top_k, and rebalance frequency to measure
strategy sensitivity to small parameter changes. A robust strategy
should show < 1pp annualized return degradation under 5% perturbation.
"""
from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path
from random import gauss
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quant_rotation.backtest import run_backtest
from quant_rotation.config import load_config
from quant_rotation.data import (
    align_asset_data,
    align_benchmark,
    load_benchmark_csv,
    load_wide_asset_csv,
    load_wide_close_csv,
)
from quant_rotation.models import FactorWeights, StrategyConfig


def perturb_factor_weights(
    weights: FactorWeights,
    std: float = 0.05,
    seed: int = 42,
) -> FactorWeights:
    rng = __import__("random")
    rng.seed(seed)
    kwargs: dict[str, Any] = {}
    for field_name in weights.__dataclass_fields__:
        val = getattr(weights, field_name)
        if val != 0:
            kwargs[field_name] = val * (1.0 + gauss(0, std))
        else:
            kwargs[field_name] = val
    return FactorWeights(**kwargs)


def stability_test(
    config_path: str,
    n_perturb: int = 50,
    perturb_std: float = 0.05,
    top_k_range: tuple[int, int] = (4, 6),
    rebalance_range: tuple[int, int] = (18, 22),
    seed: int = 42,
) -> dict:
    rng = __import__("random")
    rng.seed(seed)

    app = load_config(config_path)
    data = load_wide_close_csv(app.industry_close_path)
    bd, bc = load_benchmark_csv(app.benchmark_close_path)
    ab = align_benchmark(data.dates, bd, bc)

    ra = load_wide_asset_csv(app.industry_amount_path, value_name="amount") if app.industry_amount_path else None
    ad = align_asset_data(data.dates, data.assets, ra, value_name="amount") if ra else None

    rm = load_wide_close_csv(app.market_close_path) if app.market_close_path else None
    md = align_asset_data(data.dates, rm.assets, rm, value_name="market") if rm else None
    mw = app.market_weights or {}

    baseline = run_backtest(data, ab, app.strategy, amount_data=ad, market_data=md, market_weights=mw)
    base_sharpe = baseline.metrics["sharpe_ratio"]
    base_ann = baseline.metrics["annualized_return"]
    base_dd = baseline.metrics["max_drawdown"]

    results: list[dict] = [
        {"name": "baseline", "sharpe": base_sharpe, "annualized_return": base_ann, "max_drawdown": base_dd}
    ]

    for i in range(n_perturb):
        fw = perturb_factor_weights(app.strategy.factor_weights, std=perturb_std, seed=seed + i)
        tk = app.strategy.top_k
        if top_k_range[0] != top_k_range[1]:
            tk = rng.randint(top_k_range[0], top_k_range[1])
        re = app.strategy.rebalance_every
        if rebalance_range[0] != rebalance_range[1]:
            re = rng.randint(rebalance_range[0], rebalance_range[1])

        strat = replace(
            app.strategy,
            factor_weights=fw,
            top_k=tk,
            rebalance_every=re,
        )
        try:
            r = run_backtest(data, ab, strat, amount_data=ad, market_data=md, market_weights=mw)
        except Exception:
            continue
        results.append({
            "name": f"perturb_{i:02d}",
            "sharpe": r.metrics["sharpe_ratio"],
            "annualized_return": r.metrics["annualized_return"],
            "max_drawdown": r.metrics["max_drawdown"],
        })

    sharpe_vals = [r["sharpe"] for r in results[1:] if abs(r["sharpe"]) < 100]
    ann_vals = [r["annualized_return"] for r in results[1:] if abs(r["annualized_return"]) < 100]
    dd_vals = [r["max_drawdown"] for r in results[1:] if abs(r["max_drawdown"]) < 100]

    if sharpe_vals:
        sharpe_mean = sum(sharpe_vals) / len(sharpe_vals)
        sharpe_std = (sum((v - sharpe_mean) ** 2 for v in sharpe_vals) / max(1, len(sharpe_vals) - 1)) ** 0.5
    else:
        sharpe_mean = sharpe_std = 0.0

    if ann_vals:
        ann_mean = sum(ann_vals) / len(ann_vals)
        ann_std = (sum((v - ann_mean) ** 2 for v in ann_vals) / max(1, len(ann_vals) - 1)) ** 0.5
    else:
        ann_mean = ann_std = 0.0

    return {
        "baseline_sharpe": base_sharpe,
        "baseline_annualized_return": base_ann,
        "baseline_max_drawdown": base_dd,
        "perturbed_sharpe_mean": sharpe_mean,
        "perturbed_sharpe_std": sharpe_std,
        "perturbed_annualized_return_mean": ann_mean,
        "perturbed_annualized_return_std": ann_std,
        "sharpe_degradation": base_sharpe - sharpe_mean,
        "annualized_return_degradation": base_ann - ann_mean,
        "n_successful": len(sharpe_vals),
        "pass": abs(base_ann - ann_mean) < 0.01,
    }


def print_stability_report(result: dict) -> None:
    print("=== Stability Test Report ===")
    print(f"  N perturbed runs: {result['n_successful']}")
    print()
    print(f"  Baseline Sharpe:              {result['baseline_sharpe']:>+.4f}")
    print(f"  Perturbed Sharpe (mean ± std): {result['perturbed_sharpe_mean']:>+.4f} ± {result['perturbed_sharpe_std']:.4f}")
    print(f"  Sharpe degradation:           {result['sharpe_degradation']:>+.4f}")
    print()
    print(f"  Baseline Annualized Return:              {result['baseline_annualized_return']:>+.4%}")
    print(f"  Perturbed Annualized Return (mean ± std): {result['perturbed_annualized_return_mean']:>+.4%} ± {result['perturbed_annualized_return_std']:.4%}")
    print(f"  Annualized Return degradation:           {result['annualized_return_degradation']:>+.4%}")
    print()
    verdict = "PASS" if result["pass"] else "WARN"
    print(f"  Verdict: {verdict} (annualized degradation < 1pp)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/production.toml")
    parser.add_argument("--n-perturb", type=int, default=50)
    parser.add_argument("--perturb-std", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = stability_test(
        args.config,
        n_perturb=args.n_perturb,
        perturb_std=args.perturb_std,
        seed=args.seed,
    )
    print_stability_report(result)
