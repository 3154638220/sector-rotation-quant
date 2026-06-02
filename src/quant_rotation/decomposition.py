from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from .backtest import run_backtest
from .models import BacktestResult, BreadthData, FactorWeights, PriceData, StrategyConfig


FACTOR_FIELDS = (
    "ret20",
    "ret60",
    "ret120",
    "amount_strength",
    "breadth20",
    "breadth60",
    "vol20",
    "ret5",
)

METRIC_ORDER = (
    "final_equity",
    "annualized_return",
    "max_drawdown",
    "sharpe_ratio",
    "calmar_ratio",
    "monthly_win_rate",
    "max_consecutive_losing_months",
    "average_turnover",
    "total_transaction_cost",
    "equal_weight_final_equity",
    "excess_return_vs_equal_weight",
    "benchmark_final_equity",
    "excess_return_vs_benchmark",
)


@dataclass(frozen=True)
class FactorDecompositionSpec:
    name: str
    description: str
    factors: tuple[str, ...]
    weights: FactorWeights
    kind: str = "factor"


@dataclass(frozen=True)
class FactorDecompositionRun:
    spec: FactorDecompositionSpec
    result: BacktestResult


def _empty_weights() -> dict[str, float]:
    return {field: 0.0 for field in FACTOR_FIELDS}


def _weights_from_fields(
    base_weights: FactorWeights,
    fields: tuple[str, ...],
) -> FactorWeights:
    values = _empty_weights()
    for field in fields:
        values[field] = getattr(base_weights, field)
    return FactorWeights(**values)


def _factor_available(
    field: str,
    amount_data: PriceData | None,
    breadth_data: BreadthData | None,
) -> bool:
    if field == "amount_strength":
        return amount_data is not None
    if field == "breadth20":
        return breadth_data is not None and breadth_data.breadth20 is not None
    if field == "breadth60":
        return breadth_data is not None and breadth_data.breadth60 is not None
    return True


def _configured_fields(
    base_weights: FactorWeights,
    fields: tuple[str, ...],
    amount_data: PriceData | None,
    breadth_data: BreadthData | None,
) -> tuple[str, ...]:
    return tuple(
        field
        for field in fields
        if getattr(base_weights, field) != 0.0
        and _factor_available(field, amount_data, breadth_data)
    )


def build_factor_decomposition_specs(
    base_weights: FactorWeights,
    amount_data: PriceData | None = None,
    breadth_data: BreadthData | None = None,
) -> list[FactorDecompositionSpec]:
    specs: list[FactorDecompositionSpec] = []
    all_active_fields = _configured_fields(
        base_weights,
        FACTOR_FIELDS,
        amount_data,
        breadth_data,
    )

    def add(
        name: str,
        description: str,
        fields: tuple[str, ...],
        kind: str = "factor",
    ) -> None:
        active_fields = _configured_fields(
            base_weights,
            fields,
            amount_data,
            breadth_data,
        )
        if not active_fields:
            return
        specs.append(
            FactorDecompositionSpec(
                name=name,
                description=description,
                factors=active_fields,
                weights=_weights_from_fields(base_weights, active_fields),
                kind=kind,
            )
        )

    add("all_factors", "configured full industry factor model", FACTOR_FIELDS)
    add("price_momentum", "20/60/120-day industry momentum", ("ret20", "ret60", "ret120"))
    add("ret20", "20-day industry momentum", ("ret20",))
    add("ret60", "60-day industry momentum", ("ret60",))
    add("ret120", "120-day industry momentum", ("ret120",))
    add("amount_strength", "20-day versus 120-day amount strength", ("amount_strength",))
    add("breadth", "industry breadth composite", ("breadth20", "breadth60"))
    add("breadth20", "industry MA20 breadth", ("breadth20",))
    add("breadth60", "industry MA60 breadth", ("breadth60",))
    add("risk_penalty", "volatility and short-term overheating penalties", ("vol20", "ret5"))
    add("vol20", "20-day volatility factor using configured sign", ("vol20",))
    add("ret5", "5-day return factor using configured sign", ("ret5",))
    for removed_field in all_active_fields:
        remaining_fields = tuple(
            field for field in all_active_fields if field != removed_field
        )
        if not remaining_fields:
            continue
        add(
            f"without_{removed_field}",
            f"full model without {removed_field}",
            remaining_fields,
            kind="ablation",
        )

    return specs


def run_factor_decomposition(
    data: PriceData,
    benchmark_closes: list[float] | None,
    config: StrategyConfig,
    amount_data: PriceData | None = None,
    breadth_data: BreadthData | None = None,
    market_data: PriceData | None = None,
    market_weights: dict[str, float] | None = None,
    stock_data: PriceData | None = None,
    stock_amount_data: PriceData | None = None,
    stock_industry_map: dict[str, str] | None = None,
) -> list[FactorDecompositionRun]:
    specs = build_factor_decomposition_specs(
        config.factor_weights,
        amount_data=amount_data,
        breadth_data=breadth_data,
    )
    if not specs:
        raise ValueError("No configured and available factors to decompose")

    runs: list[FactorDecompositionRun] = []
    for spec in specs:
        strategy = replace(config, factor_weights=spec.weights)
        result = run_backtest(
            data,
            benchmark_closes,
            strategy,
            amount_data=amount_data,
            breadth_data=breadth_data,
            market_data=market_data,
            market_weights=market_weights,
            stock_data=stock_data,
            stock_amount_data=stock_amount_data,
            stock_industry_map=stock_industry_map,
        )
        runs.append(FactorDecompositionRun(spec=spec, result=result))
    return runs


def write_factor_decomposition_reports(
    runs: list[FactorDecompositionRun],
    output_dir: str | Path,
) -> None:
    if not runs:
        raise ValueError("Factor decomposition requires at least one run")

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    _validate_run_dates(runs)
    _write_decomposition_metrics(runs, path / "factor_decomposition.csv")
    _write_decomposition_equity(runs, path / "factor_equity_curves.csv")
    _write_decomposition_annual_returns(runs, path / "factor_annual_returns.csv")
    _write_ablation_report(runs, path / "factor_ablation.csv")


def _validate_run_dates(runs: list[FactorDecompositionRun]) -> None:
    dates = runs[0].result.dates
    for run in runs[1:]:
        if run.result.dates != dates:
            raise ValueError("All factor decomposition runs must share dates")


def _metric_columns(runs: list[FactorDecompositionRun]) -> list[str]:
    available = set()
    for run in runs:
        available.update(run.result.metrics)
    ordered = [metric for metric in METRIC_ORDER if metric in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _write_decomposition_metrics(
    runs: list[FactorDecompositionRun],
    path: Path,
) -> None:
    metric_columns = _metric_columns(runs)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "factor",
                "kind",
                "description",
                "enabled_factors",
                "rebalances",
                *metric_columns,
            ]
        )
        for run in runs:
            writer.writerow(
                [
                    run.spec.name,
                    run.spec.kind,
                    run.spec.description,
                    ";".join(run.spec.factors),
                    len(run.result.rebalances),
                    *[
                        f"{run.result.metrics[metric]:.10f}"
                        if metric in run.result.metrics
                        else ""
                        for metric in metric_columns
                    ],
                ]
            )


def _write_decomposition_equity(
    runs: list[FactorDecompositionRun],
    path: Path,
) -> None:
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


def _write_decomposition_annual_returns(
    runs: list[FactorDecompositionRun],
    path: Path,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["factor", "year", "annual_return"])
        for run in runs:
            for year, value in sorted(run.result.annual_returns.items()):
                writer.writerow([run.spec.name, year, f"{value:.10f}"])


def _write_ablation_report(
    runs: list[FactorDecompositionRun],
    path: Path,
) -> None:
    baseline = next((run for run in runs if run.spec.name == "all_factors"), None)
    ablations = [run for run in runs if run.spec.kind == "ablation"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "removed_factor",
                "enabled_factors",
                "final_equity",
                "annualized_return",
                "max_drawdown",
                "sharpe_ratio",
                "delta_final_equity_vs_all",
                "delta_annualized_return_vs_all",
                "delta_max_drawdown_vs_all",
                "delta_sharpe_ratio_vs_all",
            ]
        )
        if baseline is None:
            return
        base_metrics = baseline.result.metrics
        for run in ablations:
            removed_factor = run.spec.name.removeprefix("without_")
            metrics = run.result.metrics
            writer.writerow(
                [
                    removed_factor,
                    ";".join(run.spec.factors),
                    f"{metrics['final_equity']:.10f}",
                    f"{metrics['annualized_return']:.10f}",
                    f"{metrics['max_drawdown']:.10f}",
                    f"{metrics['sharpe_ratio']:.10f}",
                    f"{metrics['final_equity'] - base_metrics['final_equity']:.10f}",
                    f"{metrics['annualized_return'] - base_metrics['annualized_return']:.10f}",
                    f"{metrics['max_drawdown'] - base_metrics['max_drawdown']:.10f}",
                    f"{metrics['sharpe_ratio'] - base_metrics['sharpe_ratio']:.10f}",
                ]
            )
