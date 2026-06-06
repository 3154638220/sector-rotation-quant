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


def _parse_factor_weights(section: dict) -> FactorWeights:
    return FactorWeights(
        ret20=float(section.get("ret20_weight", 0.40)),
        ret60=float(section.get("ret60_weight", 0.40)),
        ret120=float(section.get("ret120_weight", 0.20)),
        rel_ret60=float(section.get("rel_ret60_weight", 0.00)),
        rel_ret20=float(section.get("rel_ret20_weight", 0.00)),
        momentum_accel=float(section.get("momentum_accel_weight", 0.00)),
        consistency60=float(section.get("consistency60_weight", 0.00)),
        amount_strength=float(section.get("amount_strength_weight", 0.25)),
        breadth20=float(section.get("breadth20_weight", 0.12)),
        breadth60=float(section.get("breadth60_weight", 0.08)),
        valuation=float(section.get("valuation_weight", 0.00)),
        prosperity=float(section.get("prosperity_weight", 0.00)),
        vol20=float(section.get("vol20_weight", -0.30)),
        ret5=float(section.get("ret5_weight", -0.20)),
    )


def _parse_regime_factors(section: dict) -> FactorWeights:
    return FactorWeights(
        ret20=float(section.get("ret20_weight", 0.00)),
        ret60=float(section.get("ret60_weight", 0.00)),
        ret120=float(section.get("ret120_weight", 0.00)),
        rel_ret60=float(section.get("rel_ret60_weight", 0.00)),
        rel_ret20=float(section.get("rel_ret20_weight", 0.00)),
        momentum_accel=float(section.get("momentum_accel_weight", 0.00)),
        consistency60=float(section.get("consistency60_weight", 0.00)),
        amount_strength=float(section.get("amount_strength_weight", 0.00)),
        breadth20=float(section.get("breadth20_weight", 0.00)),
        breadth60=float(section.get("breadth60_weight", 0.00)),
        valuation=float(section.get("valuation_weight", 0.00)),
        prosperity=float(section.get("prosperity_weight", 0.00)),
        vol20=float(section.get("vol20_weight", 0.00)),
        ret5=float(section.get("ret5_weight", 0.00)),
    )


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

    factor_weights = _parse_factor_weights(factors)
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
        rel_ret60=float(factors.get("stock_rel_ret60_weight", 0.00)),
        consistency20=float(factors.get("stock_consistency20_weight", 0.00)),
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
        risk_control_mode=str(strategy.get("risk_control_mode", "hard")),
        soft_exposure_min=float(strategy.get("soft_exposure_min", 0.20)),
        soft_exposure_max=float(strategy.get("soft_exposure_max", 1.00)),
        soft_exposure_center=float(strategy.get("soft_exposure_center", 0.00)),
        soft_exposure_steepness=float(strategy.get("soft_exposure_steepness", 20.0)),
        state_aware_risk_control=bool(strategy.get("state_aware_risk_control", False)),
        bull_exposure=float(strategy.get("bull_exposure", 1.00)),
        sideways_exposure=float(strategy.get("sideways_exposure", 0.50)),
        bear_exposure=float(strategy.get("bear_exposure", 0.10)),
        regime_aware_factors=bool(strategy.get("regime_aware_factors", False)),
        bull_factor_weights=_parse_regime_factors(strategy.get("bull_factors", {})),
        sideways_factor_weights=_parse_regime_factors(strategy.get("sideways_factors", {})),
        bear_factor_weights=_parse_regime_factors(strategy.get("bear_factors", {})),
        portfolio_mode=str(strategy.get("portfolio_mode", "equal")),
        softmax_temperature=float(strategy.get("softmax_temperature", 1.0)),
        adaptive_top_k=bool(strategy.get("adaptive_top_k", False)),
        adaptive_top_k_base=int(strategy.get("adaptive_top_k_base", 5)),
        adaptive_top_k_concentration=float(strategy.get("adaptive_top_k_concentration", 1.5)),
        risk_control_dual_ma=bool(strategy.get("risk_control_dual_ma", False)),
        state_aware_bull_threshold=float(strategy.get("state_aware_bull_threshold", 1.5)),
        state_aware_bear_threshold=float(strategy.get("state_aware_bear_threshold", 0.0)),
        factor_weights=factor_weights,
        stock_selection=stock_selection,
        annual_budget_control=bool(strategy.get("annual_budget_control", False)),
        annual_budget_target=float(strategy.get("annual_budget_target", 0.12)),
        annual_budget_lock_trigger=float(strategy.get("annual_budget_lock_trigger", 0.10)),
        annual_budget_min_exposure=float(strategy.get("annual_budget_min_exposure", 0.50)),
        vol_targeting=bool(strategy.get("vol_targeting", False)),
        vol_target_level=float(strategy.get("vol_target_level", 0.15)),
        vol_target_window=int(strategy.get("vol_target_window", 20)),
        vol_target_min_exposure=float(strategy.get("vol_target_min_exposure", 0.30)),
        defensive_mode=bool(strategy.get("defensive_mode", False)),
        defensive_top_k=int(strategy.get("defensive_top_k", 3)),
        defensive_exposure_threshold=float(strategy.get("defensive_exposure_threshold", 0.50)),
        strategy_mode=str(strategy.get("mode", "absolute")),
        defensive_sector_filter=bool(strategy.get("defensive_sector_filter", False)),
        defensive_sector_cap=float(strategy.get("defensive_sector_cap", 0.50)),
        relative_excess_target=float(strategy.get("relative_excess_target", 0.05)),
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
