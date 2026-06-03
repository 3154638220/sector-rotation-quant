from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from .backtest import run_backtest
from .decomposition import FACTOR_FIELDS, METRIC_ORDER
from .models import (
    BacktestResult,
    BreadthData,
    FactorWeights,
    PriceData,
    StockIndustryMap,
    StrategyConfig,
)


DEFAULT_FACTOR_SET_NAMES = (
    "ret60",
    "ret60_ret5",
    "ret60_ret120",
    "ret60_ret120_ret5",
)
DEFAULT_TOP_K_VALUES = (3, 5, 8)
DEFAULT_RISK_OFF_EXPOSURES = (0.0, 0.2, 0.3, 0.5)
DEFAULT_RISK_CONTROL_VALUES = (False, True)
DEFAULT_MARKET_SCORE_CONTROL_VALUES = (False, True)
DEFAULT_MARKET_SCORE_THRESHOLDS = (0.0,)
DEFAULT_RISK_CONTROL_MODE_VALUES = ("hard",)
DEFAULT_SOFT_EXPOSURE_MIN_VALUES = (0.1, 0.2, 0.3)
DEFAULT_STATE_AWARE_RISK_CONTROL_VALUES = (False,)


@dataclass(frozen=True)
class ParameterSweepSpec:
    name: str
    factor_set: str
    description: str
    factors: tuple[str, ...]
    factor_weights: FactorWeights
    top_k: int
    risk_off_exposure: float
    risk_control: bool
    market_score_control: bool
    market_score_threshold: float
    risk_control_mode: str = "hard"
    soft_exposure_min: float = 0.20
    soft_exposure_max: float = 1.00
    soft_exposure_center: float = 0.00
    soft_exposure_steepness: float = 20.0
    state_aware_risk_control: bool = False


@dataclass(frozen=True)
class ParameterSweepRun:
    spec: ParameterSweepSpec
    result: BacktestResult


def _factor_available(
    field: str,
    amount_data: PriceData | None,
    breadth_data: BreadthData | None,
    valuation_data: PriceData | None = None,
    prosperity_data: PriceData | None = None,
) -> bool:
    if field == "amount_strength":
        return amount_data is not None
    if field == "breadth20":
        return breadth_data is not None and breadth_data.breadth20 is not None
    if field == "breadth60":
        return breadth_data is not None and breadth_data.breadth60 is not None
    if field == "valuation":
        return valuation_data is not None
    if field == "prosperity":
        return prosperity_data is not None
    return True


def _active_fields(
    fields: tuple[str, ...],
    amount_data: PriceData | None,
    breadth_data: BreadthData | None,
    valuation_data: PriceData | None = None,
    prosperity_data: PriceData | None = None,
) -> tuple[str, ...]:
    return tuple(
        field
        for field in fields
        if _factor_available(
            field,
            amount_data,
            breadth_data,
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
        )
    )


def _empty_weights() -> dict[str, float]:
    return {field: 0.0 for field in FACTOR_FIELDS}


def _factor_weights(values: dict[str, float]) -> FactorWeights:
    weights = _empty_weights()
    weights.update(values)
    return FactorWeights(**weights)


def _configured_weights(
    base_weights: FactorWeights,
    amount_data: PriceData | None,
    breadth_data: BreadthData | None,
    valuation_data: PriceData | None = None,
    prosperity_data: PriceData | None = None,
) -> tuple[tuple[str, ...], FactorWeights]:
    fields = tuple(
        field
        for field in FACTOR_FIELDS
        if getattr(base_weights, field) != 0.0
        and _factor_available(
            field,
            amount_data,
            breadth_data,
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
        )
    )
    values = {field: getattr(base_weights, field) for field in fields}
    return fields, _factor_weights(values)


def _format_exposure(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def _format_bool(value: bool) -> str:
    return "1" if value else "0"


def _format_threshold(value: float) -> str:
    text = f"{value:g}".replace("-", "neg").replace(".", "p")
    return text if text != "neg0" else "0"


def _candidate_factor_sets(
    base_weights: FactorWeights,
    amount_data: PriceData | None,
    breadth_data: BreadthData | None,
    valuation_data: PriceData | None = None,
    prosperity_data: PriceData | None = None,
) -> list[tuple[str, str, tuple[str, ...], FactorWeights]]:
    candidates: list[tuple[str, str, tuple[str, ...], FactorWeights]] = []
    configured_fields, configured_weight_values = _configured_weights(
        base_weights,
        amount_data,
        breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
    )
    if configured_fields:
        candidates.append(
            (
                "all_factors",
                "configured full industry factor model",
                configured_fields,
                configured_weight_values,
            )
        )

    raw_candidates = [
        (
            "ret60",
            "60-day industry momentum",
            {"ret60": 1.0},
        ),
        (
            "ret60_ret5",
            "60-day momentum with 5-day overheating penalty",
            {"ret60": 1.0, "ret5": -0.5},
        ),
        (
            "ret60_ret120",
            "60/120-day industry momentum",
            {"ret60": 1.0, "ret120": 0.5},
        ),
        (
            "ret60_ret120_ret5",
            "60/120-day momentum with 5-day overheating penalty",
            {"ret60": 1.0, "ret120": 0.5, "ret5": -0.5},
        ),
        (
            "ret60_breadth20",
            "60-day momentum with industry breadth",
            {"ret60": 1.0, "breadth20": 0.15},
        ),
        (
            "ret60_ret5_breadth20",
            "60-day momentum, 5-day overheating penalty, and industry breadth",
            {"ret60": 1.0, "ret5": -0.5, "breadth20": 0.15},
        ),
        (
            "ret60_valuation",
            "60-day momentum with valuation percentile filter",
            {"ret60": 1.0, "valuation": 0.20},
        ),
        (
            "ret60_ret5_valuation",
            "60-day momentum, 5-day overheating penalty, and valuation",
            {"ret60": 1.0, "ret5": -0.5, "valuation": 0.20},
        ),
        (
            "ret60_prosperity",
            "60-day momentum with prosperity proxy",
            {"ret60": 1.0, "prosperity": 0.20},
        ),
        (
            "ret60_ret5_fundamental",
            "60-day momentum, 5-day overheating penalty, valuation, and prosperity",
            {"ret60": 1.0, "ret5": -0.5, "valuation": 0.15, "prosperity": 0.15},
        ),
        (
            "price_momentum",
            "20/60/120-day industry momentum",
            {"ret20": 1.0, "ret60": 1.0, "ret120": 0.5},
        ),
    ]
    for name, description, values in raw_candidates:
        fields = _active_fields(
            tuple(values),
            amount_data,
            breadth_data,
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
        )
        if len(fields) != len(values):
            continue
        available_values = {field: values[field] for field in fields}
        candidates.append((name, description, fields, _factor_weights(available_values)))

    deduped: list[tuple[str, str, tuple[str, ...], FactorWeights]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for name, description, fields, weights in candidates:
        key = (name, fields)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((name, description, fields, weights))
    return deduped


def build_parameter_sweep_specs(
    config: StrategyConfig,
    amount_data: PriceData | None = None,
    breadth_data: BreadthData | None = None,
    valuation_data: PriceData | None = None,
    prosperity_data: PriceData | None = None,
    factor_set_names: tuple[str, ...] = DEFAULT_FACTOR_SET_NAMES,
    top_k_values: tuple[int, ...] = DEFAULT_TOP_K_VALUES,
    risk_off_exposures: tuple[float, ...] = DEFAULT_RISK_OFF_EXPOSURES,
    risk_control_values: tuple[bool, ...] = DEFAULT_RISK_CONTROL_VALUES,
    market_score_control_values: tuple[bool, ...] = DEFAULT_MARKET_SCORE_CONTROL_VALUES,
    market_score_threshold_values: tuple[float, ...] = DEFAULT_MARKET_SCORE_THRESHOLDS,
    risk_control_mode_values: tuple[str, ...] = DEFAULT_RISK_CONTROL_MODE_VALUES,
    soft_exposure_min_values: tuple[float, ...] = DEFAULT_SOFT_EXPOSURE_MIN_VALUES,
    state_aware_risk_control_values: tuple[bool, ...] = DEFAULT_STATE_AWARE_RISK_CONTROL_VALUES,
) -> list[ParameterSweepSpec]:
    if not factor_set_names:
        raise ValueError("Parameter sweep requires at least one factor_set value")
    if not top_k_values:
        raise ValueError("Parameter sweep requires at least one top_k value")
    if not risk_off_exposures:
        raise ValueError("Parameter sweep requires at least one risk_off_exposure value")
    if not risk_control_values:
        raise ValueError("Parameter sweep requires at least one risk_control value")
    if not market_score_control_values:
        raise ValueError(
            "Parameter sweep requires at least one market_score_control value"
        )
    if not market_score_threshold_values:
        raise ValueError(
            "Parameter sweep requires at least one market_score_threshold value"
        )
    for top_k in top_k_values:
        if top_k <= 0:
            raise ValueError("top_k values must be positive")
    for exposure in risk_off_exposures:
        if not 0.0 <= exposure <= 1.0:
            raise ValueError("risk_off_exposure values must be between 0 and 1")
    for exp_min in soft_exposure_min_values:
        if not 0.0 <= exp_min <= 1.0:
            raise ValueError("soft_exposure_min values must be between 0 and 1")
    for mode in risk_control_mode_values:
        if mode not in ("hard", "soft"):
            raise ValueError(
                f"risk_control_mode must be 'hard' or 'soft', got {mode!r}"
            )

    candidate_sets = _candidate_factor_sets(
        config.factor_weights,
        amount_data,
        breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
    )
    available_names = {factor_set for factor_set, *_ in candidate_sets}
    unknown_names = sorted(set(factor_set_names) - available_names)
    if unknown_names:
        raise ValueError(
            "Unknown factor_set values: " + ", ".join(unknown_names)
        )
    requested_names = set(factor_set_names)
    include_mode_suffix = len(risk_control_mode_values) > 1
    include_control_suffix = (
        len(risk_control_values) > 1 or len(market_score_control_values) > 1
    )
    include_threshold_suffix = (
        len(market_score_threshold_values) > 1
        or market_score_threshold_values[0] != config.market_score_threshold
    )

    specs: list[ParameterSweepSpec] = []
    for factor_set, description, fields, weights in candidate_sets:
        if factor_set not in requested_names:
            continue
        for top_k in top_k_values:
            for risk_control_mode in risk_control_mode_values:
                if risk_control_mode == "soft":
                    exposure_iter = soft_exposure_min_values
                    mode_label = "softoff"
                else:
                    exposure_iter = risk_off_exposures
                    mode_label = "riskoff"
                for exp_val in exposure_iter:
                    for risk_control in risk_control_values:
                        for market_score_control in market_score_control_values:
                            thresholds = (
                                market_score_threshold_values
                                if market_score_control
                                else (config.market_score_threshold,)
                            )
                            for threshold in thresholds:
                                name = (
                                    f"{factor_set}_top{top_k}_"
                                    f"{mode_label}"
                                    f"{_format_exposure(exp_val)}"
                                )
                                if include_mode_suffix:
                                    name = f"{name}_mode{risk_control_mode[:1]}"
                                if include_control_suffix:
                                    name = (
                                        f"{name}"
                                        f"_riskctrl{_format_bool(risk_control)}"
                                        f"_mscore{_format_bool(market_score_control)}"
                                    )
                                if market_score_control and include_threshold_suffix:
                                    name = (
                                        f"{name}_mthr"
                                        f"{_format_threshold(threshold)}"
                                    )
                                if risk_control_mode == "soft":
                                    spec = ParameterSweepSpec(
                                        name=name,
                                        factor_set=factor_set,
                                        description=description,
                                        factors=fields,
                                        factor_weights=weights,
                                        top_k=top_k,
                                        risk_off_exposure=0.0,
                                        risk_control=risk_control,
                                        market_score_control=market_score_control,
                                        market_score_threshold=threshold,
                                        risk_control_mode="soft",
                                        soft_exposure_min=exp_val,
                                        soft_exposure_max=config.soft_exposure_max,
                                        soft_exposure_center=config.soft_exposure_center,
                                        soft_exposure_steepness=config.soft_exposure_steepness,
                                    )
                                else:
                                    spec = ParameterSweepSpec(
                                        name=name,
                                        factor_set=factor_set,
                                        description=description,
                                        factors=fields,
                                        factor_weights=weights,
                                        top_k=top_k,
                                        risk_off_exposure=exp_val,
                                        risk_control=risk_control,
                                        market_score_control=market_score_control,
                                        market_score_threshold=threshold,
                                    )
                                specs.append(spec)
    if not specs:
        raise ValueError("No parameter sweep candidates were generated")

    if True in state_aware_risk_control_values:
        state_aware_specs: list[ParameterSweepSpec] = []
        for factor_set, description, fields, weights in candidate_sets:
            if factor_set not in requested_names:
                continue
            for top_k in top_k_values:
                for risk_control in risk_control_values:
                    for market_score_control in market_score_control_values:
                        if not risk_control or not market_score_control:
                            continue
                        for threshold in (
                            market_score_threshold_values
                            if market_score_control
                            else (config.market_score_threshold,)
                        ):
                            name = f"{factor_set}_top{top_k}_stateaware"
                            if include_control_suffix:
                                name = (
                                    f"{name}"
                                    f"_riskctrl{_format_bool(risk_control)}"
                                    f"_mscore{_format_bool(market_score_control)}"
                                )
                            if include_threshold_suffix:
                                name = f"{name}_mthr{_format_threshold(threshold)}"
                            spec = ParameterSweepSpec(
                                name=name,
                                factor_set=factor_set,
                                description=f"{description} (state-aware risk control)",
                                factors=fields,
                                factor_weights=weights,
                                top_k=top_k,
                                risk_off_exposure=0.0,
                                risk_control=risk_control,
                                market_score_control=market_score_control,
                                market_score_threshold=threshold,
                                state_aware_risk_control=True,
                            )
                            state_aware_specs.append(spec)
        specs.extend(state_aware_specs)
    return specs


def run_parameter_sweep(
    data: PriceData,
    benchmark_closes: list[float] | None,
    config: StrategyConfig,
    amount_data: PriceData | None = None,
    breadth_data: BreadthData | None = None,
    valuation_data: PriceData | None = None,
    prosperity_data: PriceData | None = None,
    market_data: PriceData | None = None,
    market_weights: dict[str, float] | None = None,
    stock_data: PriceData | None = None,
    stock_amount_data: PriceData | None = None,
    stock_industry_map: StockIndustryMap | dict[str, str] | None = None,
    factor_set_names: tuple[str, ...] = DEFAULT_FACTOR_SET_NAMES,
    top_k_values: tuple[int, ...] = DEFAULT_TOP_K_VALUES,
    risk_off_exposures: tuple[float, ...] = DEFAULT_RISK_OFF_EXPOSURES,
    risk_control_values: tuple[bool, ...] = DEFAULT_RISK_CONTROL_VALUES,
    market_score_control_values: tuple[bool, ...] | None = None,
    market_score_threshold_values: tuple[float, ...] = DEFAULT_MARKET_SCORE_THRESHOLDS,
    risk_control_mode_values: tuple[str, ...] = DEFAULT_RISK_CONTROL_MODE_VALUES,
    soft_exposure_min_values: tuple[float, ...] = DEFAULT_SOFT_EXPOSURE_MIN_VALUES,
    state_aware_risk_control_values: tuple[bool, ...] = DEFAULT_STATE_AWARE_RISK_CONTROL_VALUES,
) -> list[ParameterSweepRun]:
    resolved_market_score_control_values = (
        DEFAULT_MARKET_SCORE_CONTROL_VALUES
        if market_score_control_values is None
        and (market_data is not None or benchmark_closes is not None)
        else market_score_control_values
    )
    if resolved_market_score_control_values is None:
        resolved_market_score_control_values = (False,)
    if (
        True in resolved_market_score_control_values
        and market_data is None
        and benchmark_closes is None
    ):
        raise ValueError(
            "market_score_control sweep requires market_data or benchmark_closes"
        )
    specs = build_parameter_sweep_specs(
        config,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        factor_set_names=factor_set_names,
        top_k_values=top_k_values,
        risk_off_exposures=risk_off_exposures,
        risk_control_values=risk_control_values,
        market_score_control_values=resolved_market_score_control_values,
        market_score_threshold_values=market_score_threshold_values,
        risk_control_mode_values=risk_control_mode_values,
        soft_exposure_min_values=soft_exposure_min_values,
        state_aware_risk_control_values=state_aware_risk_control_values,
    )
    runs: list[ParameterSweepRun] = []
    for spec in specs:
        strategy = replace(
            config,
            factor_weights=spec.factor_weights,
            top_k=spec.top_k,
            risk_off_exposure=spec.risk_off_exposure,
            risk_control=spec.risk_control,
            market_score_control=spec.market_score_control,
            market_score_threshold=spec.market_score_threshold,
            risk_control_mode=spec.risk_control_mode,
            soft_exposure_min=spec.soft_exposure_min,
            soft_exposure_max=spec.soft_exposure_max,
            soft_exposure_center=spec.soft_exposure_center,
            soft_exposure_steepness=spec.soft_exposure_steepness,
            state_aware_risk_control=spec.state_aware_risk_control,
            bull_exposure=config.bull_exposure,
            sideways_exposure=config.sideways_exposure,
            bear_exposure=config.bear_exposure,
        )
        result = run_backtest(
            data,
            benchmark_closes,
            strategy,
            amount_data=amount_data,
            breadth_data=breadth_data,
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
            market_data=market_data,
            market_weights=market_weights,
            stock_data=stock_data,
            stock_amount_data=stock_amount_data,
            stock_industry_map=stock_industry_map,
        )
        runs.append(ParameterSweepRun(spec=spec, result=result))
    return runs


def write_parameter_sweep_reports(
    runs: list[ParameterSweepRun],
    output_dir: str | Path,
    top_n_equity: int = 10,
) -> None:
    if not runs:
        raise ValueError("Parameter sweep requires at least one run")
    if top_n_equity <= 0:
        raise ValueError("top_n_equity must be positive")

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    _validate_run_dates(runs)
    ranked = sorted(
        runs,
        key=lambda run: (
            -run.result.metrics["annualized_return"],
            run.result.metrics["max_drawdown"],
            run.spec.name,
        ),
    )
    _write_sweep_metrics(ranked, path / "parameter_sweep.csv")
    _write_sweep_equity(ranked[:top_n_equity], path / "parameter_sweep_equity_top.csv")
    _write_sweep_annual_returns(ranked, path / "parameter_sweep_annual_returns.csv")


def _validate_run_dates(runs: list[ParameterSweepRun]) -> None:
    dates = runs[0].result.dates
    for run in runs[1:]:
        if run.result.dates != dates:
            raise ValueError("All parameter sweep runs must share dates")


def _metric_columns(runs: list[ParameterSweepRun]) -> list[str]:
    available = set()
    for run in runs:
        available.update(run.result.metrics)
    ordered = [metric for metric in METRIC_ORDER if metric in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _write_sweep_metrics(runs: list[ParameterSweepRun], path: Path) -> None:
    metric_columns = _metric_columns(runs)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "name",
                "factor_set",
                "description",
                "enabled_factors",
                "top_k",
                "risk_off_exposure",
                "risk_control",
                "market_score_control",
                "market_score_threshold",
                "risk_control_mode",
                "soft_exposure_min",
                "state_aware_risk_control",
                "rebalances",
                *metric_columns,
            ]
        )
        for rank, run in enumerate(runs, start=1):
            writer.writerow(
                [
                    rank,
                    run.spec.name,
                    run.spec.factor_set,
                    run.spec.description,
                    ";".join(run.spec.factors),
                    run.spec.top_k,
                    f"{run.spec.risk_off_exposure:.6f}",
                    str(run.spec.risk_control).lower(),
                    str(run.spec.market_score_control).lower(),
                    f"{run.spec.market_score_threshold:.6f}",
                    run.spec.risk_control_mode,
                    f"{run.spec.soft_exposure_min:.6f}",
                    str(run.spec.state_aware_risk_control).lower(),
                    len(run.result.rebalances),
                    *[
                        f"{run.result.metrics[metric]:.10f}"
                        if metric in run.result.metrics
                        else ""
                        for metric in metric_columns
                    ],
                ]
            )


def _write_sweep_equity(runs: list[ParameterSweepRun], path: Path) -> None:
    first = runs[0].result
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = ["date", *[run.spec.name for run in runs], "equal_weight"]
        if first.benchmark_equity is not None:
            header.append("benchmark")
        writer.writerow(header)
        for index, day in enumerate(first.dates):
            row = [
                day.isoformat(),
                *[f"{run.result.strategy_equity[index]:.10f}" for run in runs],
                f"{first.equal_weight_equity[index]:.10f}",
            ]
            if first.benchmark_equity is not None:
                row.append(f"{first.benchmark_equity[index]:.10f}")
            writer.writerow(row)


def _write_sweep_annual_returns(runs: list[ParameterSweepRun], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "name", "factor_set", "year", "annual_return"])
        for rank, run in enumerate(runs, start=1):
            for year, value in sorted(run.result.annual_returns.items()):
                writer.writerow(
                    [rank, run.spec.name, run.spec.factor_set, year, f"{value:.10f}"]
                )
