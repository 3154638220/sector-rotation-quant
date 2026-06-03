from __future__ import annotations

import tomllib
from pathlib import Path

from .models import AppConfig, FactorWeights, StockSelectionConfig, StrategyConfig


def _resolve_path(base_dir: Path, value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    base_dir = config_path.parent
    data = raw.get("data", {})
    strategy = raw.get("strategy", {})
    factors = raw.get("factors", {})
    reports = raw.get("reports", {})
    market_weights = {
        str(key): float(value) for key, value in raw.get("market_weights", {}).items()
    }

    factor_weights = FactorWeights(
        ret20=float(factors.get("ret20_weight", 0.40)),
        ret60=float(factors.get("ret60_weight", 0.40)),
        ret120=float(factors.get("ret120_weight", 0.20)),
        amount_strength=float(factors.get("amount_strength_weight", 0.25)),
        breadth20=float(factors.get("breadth20_weight", 0.12)),
        breadth60=float(factors.get("breadth60_weight", 0.08)),
        valuation=float(factors.get("valuation_weight", 0.00)),
        prosperity=float(factors.get("prosperity_weight", 0.00)),
        vol20=float(factors.get("vol20_weight", -0.30)),
        ret5=float(factors.get("ret5_weight", -0.20)),
    )
    stock_selection = StockSelectionConfig(
        enabled=bool(strategy.get("stock_selection", False)),
        top_n_per_industry=int(strategy.get("stock_top_n_per_industry", 5)),
        min_stocks_per_industry=int(strategy.get("stock_min_stocks_per_industry", 1)),
        max_stock_weight=float(strategy.get("stock_max_weight", 0.10)),
        ret20=float(factors.get("stock_ret20_weight", 0.45)),
        ret60=float(factors.get("stock_ret60_weight", 0.25)),
        amount_strength=float(factors.get("stock_amount_strength_weight", 0.10)),
        vol20=float(factors.get("stock_vol20_weight", -0.20)),
        ret5=float(factors.get("stock_ret5_weight", -0.10)),
    )
    strategy_config = StrategyConfig(
        rebalance_every=int(strategy.get("rebalance_every", 20)),
        top_k=int(strategy.get("top_k", 5)),
        max_industry_weight=float(strategy.get("max_industry_weight", 0.30)),
        transaction_cost=float(strategy.get("transaction_cost", 0.001)),
        risk_control=bool(strategy.get("risk_control", True)),
        market_ma_window=int(strategy.get("market_ma_window", 120)),
        market_score_control=bool(strategy.get("market_score_control", False)),
        market_score_window=int(strategy.get("market_score_window", 60)),
        market_score_threshold=float(strategy.get("market_score_threshold", 0.0)),
        risk_off_exposure=float(strategy.get("risk_off_exposure", 0.50)),
        factor_weights=factor_weights,
        stock_selection=stock_selection,
    )
    return AppConfig(
        industry_close_path=_resolve_path(base_dir, data["industry_close"]) or "",
        industry_amount_path=_resolve_path(base_dir, data.get("industry_amount")),
        industry_breadth20_path=_resolve_path(base_dir, data.get("industry_breadth20")),
        industry_breadth60_path=_resolve_path(base_dir, data.get("industry_breadth60")),
        industry_valuation_path=_resolve_path(base_dir, data.get("industry_valuation")),
        industry_prosperity_path=_resolve_path(base_dir, data.get("industry_prosperity")),
        market_close_path=_resolve_path(base_dir, data.get("market_close")),
        stock_close_path=_resolve_path(base_dir, data.get("stock_close")),
        stock_amount_path=_resolve_path(base_dir, data.get("stock_amount")),
        stock_industry_map_path=_resolve_path(base_dir, data.get("stock_industry_map")),
        benchmark_close_path=_resolve_path(base_dir, data.get("benchmark_close")),
        output_dir=_resolve_path(base_dir, reports.get("output_dir", "../reports"))
        or "reports",
        market_weights=market_weights,
        strategy=strategy_config,
    )
