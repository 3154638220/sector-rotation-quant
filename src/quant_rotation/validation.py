from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from statistics import mean, median, pstdev, stdev
from pathlib import Path

from .metrics import annual_returns, summarize_performance
from .models import (
    BacktestResult,
    BreadthData,
    PriceData,
    StockIndustryMap,
    StrategyConfig,
)
from .sweep import (
    DEFAULT_FACTOR_SET_NAMES,
    DEFAULT_MARKET_SCORE_THRESHOLDS,
    DEFAULT_RISK_CONTROL_VALUES,
    DEFAULT_RISK_CONTROL_MODE_VALUES,
    DEFAULT_RISK_OFF_EXPOSURES,
    DEFAULT_SOFT_EXPOSURE_MIN_VALUES,
    DEFAULT_TOP_K_VALUES,
    METRIC_ORDER,
    ParameterSweepRun,
    run_parameter_sweep,
)


DEFAULT_SELECTION_METRIC = "composite"
SHARPE_PLUS_CALMAR_SELECTION_METRIC = "sharpe_plus_calmar"
RECENT_WEIGHTED_COMPOSITE_METRIC = "recent_weighted_composite"
REGIME_AWARE_SELECTION_METRIC = "regime_aware"
COMPOSITE_TURNOVER_PENALTY = 0.25
COMPOSITE_SELECTION_FIELDS = (
    "excess_return_vs_equal_weight",
    "calmar_ratio",
    "sharpe_ratio",
    "average_turnover",
    "max_drawdown",
)
LOWER_IS_BETTER_METRICS = {
    "average_turnover",
    "total_transaction_cost",
    "max_consecutive_losing_months",
}


@dataclass(frozen=True)
class TrainTestSplit:
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    train_start_index: int
    train_end_index: int
    test_start_index: int
    test_end_index: int


@dataclass(frozen=True)
class TrainTestValidationRun:
    sweep_run: ParameterSweepRun
    split: TrainTestSplit
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    train_annual_returns: dict[int, float]
    test_annual_returns: dict[int, float]


@dataclass(frozen=True)
class WalkForwardValidationFold:
    fold: int
    split: TrainTestSplit
    runs: list[TrainTestValidationRun]


def _last_index_on_or_before(dates: list[date], target: date) -> int:
    matches = [index for index, day in enumerate(dates) if day <= target]
    if not matches:
        raise ValueError(f"No observations on or before {target.isoformat()}")
    return matches[-1]


def _first_index_on_or_after(dates: list[date], target: date) -> int:
    for index, day in enumerate(dates):
        if day >= target:
            return index
    raise ValueError(f"No observations on or after {target.isoformat()}")


def resolve_train_test_split(
    dates: list[date],
    train_end: date | None = None,
    test_start: date | None = None,
    split_ratio: float = 0.70,
) -> TrainTestSplit:
    if len(dates) < 4:
        raise ValueError("Train/test validation requires at least four dates")
    if not 0.1 <= split_ratio <= 0.9:
        raise ValueError("split_ratio must be between 0.1 and 0.9")

    train_start_index = 0
    test_end_index = len(dates) - 1
    if train_end is None and test_start is None:
        train_end_index = int((len(dates) - 1) * split_ratio)
        train_end_index = max(1, min(train_end_index, len(dates) - 2))
        test_start_index = train_end_index + 1
    elif train_end is not None and test_start is None:
        train_end_index = _last_index_on_or_before(dates, train_end)
        if train_end_index >= len(dates) - 1:
            raise ValueError("train_end leaves no test observations")
        test_start_index = train_end_index + 1
    elif train_end is None and test_start is not None:
        test_start_index = _first_index_on_or_after(dates, test_start)
        if test_start_index <= 0:
            raise ValueError("test_start leaves no train observations")
        train_end_index = test_start_index - 1
    else:
        train_end_index = _last_index_on_or_before(dates, train_end or dates[0])
        test_start_index = _first_index_on_or_after(dates, test_start or dates[-1])
        if test_start_index <= train_end_index:
            raise ValueError("test_start must be after train_end")

    if train_end_index - train_start_index < 1:
        raise ValueError("Train segment must contain at least two observations")
    if test_end_index - test_start_index < 1:
        raise ValueError("Test segment must contain at least two observations")

    return TrainTestSplit(
        train_start=dates[train_start_index],
        train_end=dates[train_end_index],
        test_start=dates[test_start_index],
        test_end=dates[test_end_index],
        train_start_index=train_start_index,
        train_end_index=train_end_index,
        test_start_index=test_start_index,
        test_end_index=test_end_index,
    )


def resolve_walk_forward_splits(
    dates: list[date],
    train_window: int,
    test_window: int,
    step: int | None = None,
    include_partial_fold: bool = False,
) -> list[TrainTestSplit]:
    if train_window < 2:
        raise ValueError("train_window must contain at least two observations")
    if test_window < 2:
        raise ValueError("test_window must contain at least two observations")
    step_size = step if step is not None else test_window
    if step_size <= 0:
        raise ValueError("step must be positive")
    if len(dates) < train_window + 2:
        raise ValueError(
            f"Walk-forward validation requires at least {train_window + 2} dates"
        )

    splits: list[TrainTestSplit] = []
    train_start_index = 0
    while True:
        train_end_index = train_start_index + train_window - 1
        test_start_index = train_end_index + 1
        if test_start_index > len(dates) - 2:
            break

        test_end_index = test_start_index + test_window - 1
        if test_end_index >= len(dates):
            if not include_partial_fold:
                break
            test_end_index = len(dates) - 1
            if test_end_index - test_start_index < 1:
                break

        splits.append(
            TrainTestSplit(
                train_start=dates[train_start_index],
                train_end=dates[train_end_index],
                test_start=dates[test_start_index],
                test_end=dates[test_end_index],
                train_start_index=train_start_index,
                train_end_index=train_end_index,
                test_start_index=test_start_index,
                test_end_index=test_end_index,
            )
        )
        train_start_index += step_size

    if not splits:
        raise ValueError(
            "No walk-forward folds could be generated. "
            "Try smaller train/test windows or enable partial folds."
        )
    return splits


def _normalize(values: list[float]) -> list[float]:
    start = values[0]
    if start <= 0:
        raise ValueError("Cannot normalize an equity series that starts non-positive")
    return [value / start for value in values]


def _segment_equity(values: list[float], start_index: int, end_index: int) -> list[float]:
    return _normalize(values[start_index : end_index + 1])


def _segment_metrics(
    result: BacktestResult,
    start_index: int,
    end_index: int,
) -> tuple[dict[str, float], dict[int, float]]:
    dates = result.dates[start_index : end_index + 1]
    strategy_equity = _segment_equity(
        result.strategy_equity,
        start_index,
        end_index,
    )
    equal_weight_equity = _segment_equity(
        result.equal_weight_equity,
        start_index,
        end_index,
    )
    benchmark_equity = (
        _segment_equity(result.benchmark_equity, start_index, end_index)
        if result.benchmark_equity is not None
        else None
    )
    start_date = dates[0]
    end_date = dates[-1]
    events = [
        event
        for event in result.rebalances
        if start_date <= event.date <= end_date
    ]
    metrics = summarize_performance(
        dates,
        strategy_equity,
        benchmark_equity,
        equal_weight_equity,
        turnovers=[event.turnover for event in events],
        costs=[event.cost for event in events],
    )
    return metrics, annual_returns(dates, strategy_equity)


def _recent_weighted_score(
    metrics: dict[str, float],
    train_dates: list[date] | None,
    train_equity: list[float] | None,
) -> float:
    if train_dates is None or train_equity is None:
        return selection_score(metrics, DEFAULT_SELECTION_METRIC)
    if "sharpe_ratio" not in metrics:
        raise ValueError("recent_weighted_composite requires sharpe_ratio")
    recent_sharpe = _compute_recent_sharpe(train_dates, train_equity)
    overall_sharpe = metrics["sharpe_ratio"]
    weighted_sharpe = 0.6 * recent_sharpe + 0.4 * overall_sharpe
    return (
        metrics.get("excess_return_vs_equal_weight", 0.0)
        + metrics.get("calmar_ratio", 0.0)
        + weighted_sharpe
        - COMPOSITE_TURNOVER_PENALTY * metrics.get("average_turnover", 0.0)
        - abs(metrics.get("max_drawdown", 0.0))
    )


def _compute_recent_sharpe(
    train_dates: list[date],
    train_equity: list[float],
    lookback_days: int = 252,
) -> float:
    if len(train_equity) < 2:
        return 0.0
    start_idx = max(0, len(train_equity) - lookback_days - 1)
    recent_equity = train_equity[start_idx:]
    returns: list[float] = []
    for i in range(1, len(recent_equity)):
        if recent_equity[i - 1] != 0:
            returns.append(recent_equity[i] / recent_equity[i - 1] - 1.0)
    if not returns or stdev(returns) == 0:
        return 0.0
    daily_sr = mean(returns) / stdev(returns)
    return daily_sr * (252 ** 0.5)


def _classify_metrics_regime(metrics: dict[str, float]) -> str:
    monthly_win_rate = metrics.get("monthly_win_rate", 0.0)
    sharpe = metrics.get("sharpe_ratio", 0.0)
    dd = abs(metrics.get("max_drawdown", 0.0))
    if sharpe > 0.3 and monthly_win_rate > 0.45 and dd < 0.20:
        return "bull"
    elif sharpe < 0.0 and dd > 0.20:
        return "bear"
    return "sideways"


def _regime_aware_score(metrics: dict[str, float]) -> float:
    regime = _classify_metrics_regime(metrics)
    if regime == "bear":
        return metrics.get("calmar_ratio", 0.0)
    elif regime == "bull":
        return metrics.get("excess_return_vs_equal_weight", 0.0)
    else:
        return metrics.get("sharpe_ratio", 0.0) - abs(metrics.get("max_drawdown", 0.0))


def selection_score(
    metrics: dict[str, float],
    selection_metric: str = DEFAULT_SELECTION_METRIC,
    train_dates: list[date] | None = None,
    train_equity: list[float] | None = None,
) -> float:
    if train_dates is not None and train_equity is not None:
        _ = train_dates, train_equity
    if selection_metric == RECENT_WEIGHTED_COMPOSITE_METRIC:
        return _recent_weighted_score(
            metrics, train_dates, train_equity,
        )
    if selection_metric == REGIME_AWARE_SELECTION_METRIC:
        return selection_score(metrics, DEFAULT_SELECTION_METRIC)

    if selection_metric == DEFAULT_SELECTION_METRIC:
        missing = [
            metric
            for metric in COMPOSITE_SELECTION_FIELDS
            if metric not in metrics
        ]
        if missing:
            raise ValueError(
                "Composite selection metric requires: " + ", ".join(missing)
            )
        return (
            metrics["excess_return_vs_equal_weight"]
            + metrics["calmar_ratio"]
            + metrics["sharpe_ratio"]
            - COMPOSITE_TURNOVER_PENALTY * metrics["average_turnover"]
            - abs(metrics["max_drawdown"])
        )

    if selection_metric == SHARPE_PLUS_CALMAR_SELECTION_METRIC:
        return metrics["sharpe_ratio"] + metrics["calmar_ratio"]

    if selection_metric not in metrics:
        raise ValueError(f"Unknown selection metric: {selection_metric}")
    value = metrics[selection_metric]
    if selection_metric in LOWER_IS_BETTER_METRICS:
        return -value
    return value


def run_train_test_validation(
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
    train_end: date | None = None,
    test_start: date | None = None,
    split_ratio: float = 0.70,
) -> list[TrainTestValidationRun]:
    split = resolve_train_test_split(
        data.dates,
        train_end=train_end,
        test_start=test_start,
        split_ratio=split_ratio,
    )
    sweep_runs = run_parameter_sweep(
        data,
        benchmark_closes,
        config,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        market_data=market_data,
        market_weights=market_weights,
        stock_data=stock_data,
        stock_amount_data=stock_amount_data,
        stock_industry_map=stock_industry_map,
        factor_set_names=factor_set_names,
        top_k_values=top_k_values,
        risk_off_exposures=risk_off_exposures,
        risk_control_values=risk_control_values,
        market_score_control_values=market_score_control_values,
        market_score_threshold_values=market_score_threshold_values,
        risk_control_mode_values=risk_control_mode_values,
        soft_exposure_min_values=soft_exposure_min_values,
    )
    return _validation_runs_for_split(sweep_runs, split)


def _validation_runs_for_split(
    sweep_runs: list[ParameterSweepRun],
    split: TrainTestSplit,
) -> list[TrainTestValidationRun]:
    if not sweep_runs:
        raise ValueError("Validation requires at least one parameter sweep run")

    validation_runs: list[TrainTestValidationRun] = []
    for sweep_run in sweep_runs:
        train_metrics, train_years = _segment_metrics(
            sweep_run.result,
            split.train_start_index,
            split.train_end_index,
        )
        test_metrics, test_years = _segment_metrics(
            sweep_run.result,
            split.test_start_index,
            split.test_end_index,
        )
        validation_runs.append(
            TrainTestValidationRun(
                sweep_run=sweep_run,
                split=split,
                train_metrics=train_metrics,
                test_metrics=test_metrics,
                train_annual_returns=train_years,
                test_annual_returns=test_years,
            )
        )
    return validation_runs


def run_walk_forward_validation(
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
    train_window: int = 504,
    test_window: int = 126,
    step: int | None = None,
    include_partial_fold: bool = False,
) -> list[WalkForwardValidationFold]:
    splits = resolve_walk_forward_splits(
        data.dates,
        train_window=train_window,
        test_window=test_window,
        step=step,
        include_partial_fold=include_partial_fold,
    )
    sweep_runs = run_parameter_sweep(
        data,
        benchmark_closes,
        config,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        market_data=market_data,
        market_weights=market_weights,
        stock_data=stock_data,
        stock_amount_data=stock_amount_data,
        stock_industry_map=stock_industry_map,
        factor_set_names=factor_set_names,
        top_k_values=top_k_values,
        risk_off_exposures=risk_off_exposures,
        risk_control_values=risk_control_values,
        market_score_control_values=market_score_control_values,
        market_score_threshold_values=market_score_threshold_values,
        risk_control_mode_values=risk_control_mode_values,
        soft_exposure_min_values=soft_exposure_min_values,
    )

    return [
        WalkForwardValidationFold(
            fold=index,
            split=split,
            runs=_validation_runs_for_split(sweep_runs, split),
        )
        for index, split in enumerate(splits, start=1)
    ]


def _rank_key(
    metrics: dict[str, float],
    name: str,
    selection_metric: str,
) -> tuple[float, float, str]:
    score = selection_score(metrics, selection_metric)
    return (
        -score,
        abs(metrics["max_drawdown"]),
        name,
    )


def _ranked_by_train(
    runs: list[TrainTestValidationRun],
    selection_metric: str = DEFAULT_SELECTION_METRIC,
) -> list[TrainTestValidationRun]:
    return sorted(
        runs,
        key=lambda run: _rank_key(
            run.train_metrics,
            run.sweep_run.spec.name,
            selection_metric,
        ),
    )


def _ranked_by_test(
    runs: list[TrainTestValidationRun],
    selection_metric: str = DEFAULT_SELECTION_METRIC,
) -> list[TrainTestValidationRun]:
    return sorted(
        runs,
        key=lambda run: _rank_key(
            run.test_metrics,
            run.sweep_run.spec.name,
            selection_metric,
        ),
    )


def selected_by_train(
    runs: list[TrainTestValidationRun],
    selection_metric: str = DEFAULT_SELECTION_METRIC,
) -> TrainTestValidationRun:
    if not runs:
        raise ValueError("Train/test validation requires at least one run")
    return _ranked_by_train(runs, selection_metric)[0]


def selected_by_train_with_data(
    runs: list[TrainTestValidationRun],
    selection_metric: str = DEFAULT_SELECTION_METRIC,
) -> TrainTestValidationRun:
    if not runs:
        raise ValueError("Train/test validation requires at least one run")
    if selection_metric not in (
        RECENT_WEIGHTED_COMPOSITE_METRIC,
        REGIME_AWARE_SELECTION_METRIC,
    ):
        return selected_by_train(runs, selection_metric)

    def _score(run: TrainTestValidationRun) -> float:
        result = run.sweep_run.result
        train_equity = result.strategy_equity[
            run.split.train_start_index : run.split.train_end_index + 1
        ]
        train_dates = result.dates[
            run.split.train_start_index : run.split.train_end_index + 1
        ]
        if selection_metric == RECENT_WEIGHTED_COMPOSITE_METRIC:
            return _recent_weighted_score(
                run.train_metrics,
                train_dates,
                train_equity,
            )
        elif selection_metric == REGIME_AWARE_SELECTION_METRIC:
            return _regime_aware_score(run.train_metrics)
        return selection_score(run.train_metrics, selection_metric)

    best = max(runs, key=_score)
    return best


def write_train_test_validation_reports(
    runs: list[TrainTestValidationRun],
    output_dir: str | Path,
    selection_metric: str = DEFAULT_SELECTION_METRIC,
) -> None:
    if not runs:
        raise ValueError("Train/test validation requires at least one run")
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    ranked_train = _ranked_by_train(runs, selection_metric)
    ranked_test = _ranked_by_test(runs, selection_metric)
    test_rank_by_name = {
        run.sweep_run.spec.name: rank
        for rank, run in enumerate(ranked_test, start=1)
    }
    selected = ranked_train[0]
    _write_validation_summary(
        ranked_train,
        test_rank_by_name,
        selected.sweep_run.spec.name,
        path / "train_test_validation.csv",
        selection_metric,
    )
    _write_selected_equity(selected, path / "train_test_selected_equity.csv")
    _write_annual_returns(ranked_train, path / "train_test_annual_returns.csv")


def write_walk_forward_validation_reports(
    folds: list[WalkForwardValidationFold],
    output_dir: str | Path,
    selection_metric: str = DEFAULT_SELECTION_METRIC,
) -> None:
    if not folds:
        raise ValueError("Walk-forward validation requires at least one fold")
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    for fold in folds:
        if not fold.runs:
            raise ValueError("Each walk-forward fold requires at least one run")

    _write_walk_forward_candidates(
        folds,
        path / "walk_forward_candidates.csv",
        selection_metric,
    )
    _write_walk_forward_folds(
        folds,
        path / "walk_forward_folds.csv",
        selection_metric,
    )
    _write_walk_forward_selected_equity(
        folds,
        path / "walk_forward_selected_equity.csv",
        selection_metric,
    )
    _write_walk_forward_oos_equity(
        folds,
        path / "walk_forward_oos_equity.csv",
        selection_metric,
    )
    _write_fixed_candidate_summary(folds, path / "fixed_candidate_summary.csv")
    _write_walk_forward_summary(
        folds,
        path / "walk_forward_summary.csv",
        selection_metric,
    )


def _metric_columns(runs: list[TrainTestValidationRun]) -> list[str]:
    available = set()
    for run in runs:
        available.update(run.train_metrics)
        available.update(run.test_metrics)
    ordered = [metric for metric in METRIC_ORDER if metric in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _write_validation_summary(
    ranked_runs: list[TrainTestValidationRun],
    test_rank_by_name: dict[str, int],
    selected_name: str,
    path: Path,
    selection_metric: str,
) -> None:
    metric_columns = _metric_columns(ranked_runs)
    split = ranked_runs[0].split
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank_by_train",
                "rank_by_test",
                "selected_by_train",
                "selection_metric",
                "train_selection_score",
                "test_selection_score",
                "name",
                "factor_set",
                "enabled_factors",
                "top_k",
                "risk_off_exposure",
                "risk_control",
                "market_score_control",
                "market_score_threshold",
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                *[f"train_{metric}" for metric in metric_columns],
                *[f"test_{metric}" for metric in metric_columns],
            ]
        )
        for rank, run in enumerate(ranked_runs, start=1):
            spec = run.sweep_run.spec
            writer.writerow(
                [
                    rank,
                    test_rank_by_name[spec.name],
                    str(spec.name == selected_name).lower(),
                    selection_metric,
                    f"{selection_score(run.train_metrics, selection_metric):.10f}",
                    f"{selection_score(run.test_metrics, selection_metric):.10f}",
                    spec.name,
                    spec.factor_set,
                    ";".join(spec.factors),
                    spec.top_k,
                    f"{spec.risk_off_exposure:.6f}",
                    str(spec.risk_control).lower(),
                    str(spec.market_score_control).lower(),
                    f"{spec.market_score_threshold:.6f}",
                    split.train_start.isoformat(),
                    split.train_end.isoformat(),
                    split.test_start.isoformat(),
                    split.test_end.isoformat(),
                    *[
                        f"{run.train_metrics[metric]:.10f}"
                        if metric in run.train_metrics
                        else ""
                        for metric in metric_columns
                    ],
                    *[
                        f"{run.test_metrics[metric]:.10f}"
                        if metric in run.test_metrics
                        else ""
                        for metric in metric_columns
                    ],
                ]
            )


def _write_selected_equity(run: TrainTestValidationRun, path: Path) -> None:
    result = run.sweep_run.result
    split = run.split
    has_benchmark = result.benchmark_equity is not None
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = ["date", "segment", "strategy", "equal_weight"]
        if has_benchmark:
            header.append("benchmark")
        writer.writerow(header)
        for segment, start_index, end_index in (
            ("train", split.train_start_index, split.train_end_index),
            ("test", split.test_start_index, split.test_end_index),
        ):
            strategy_equity = _segment_equity(
                result.strategy_equity,
                start_index,
                end_index,
            )
            equal_weight_equity = _segment_equity(
                result.equal_weight_equity,
                start_index,
                end_index,
            )
            benchmark_equity = (
                _segment_equity(result.benchmark_equity, start_index, end_index)
                if result.benchmark_equity is not None
                else None
            )
            for offset, day in enumerate(result.dates[start_index : end_index + 1]):
                row = [
                    day.isoformat(),
                    segment,
                    f"{strategy_equity[offset]:.10f}",
                    f"{equal_weight_equity[offset]:.10f}",
                ]
                if benchmark_equity is not None:
                    row.append(f"{benchmark_equity[offset]:.10f}")
                writer.writerow(row)


def _write_annual_returns(
    ranked_runs: list[TrainTestValidationRun],
    path: Path,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank_by_train", "name", "segment", "year", "annual_return"])
        for rank, run in enumerate(ranked_runs, start=1):
            for year, value in sorted(run.train_annual_returns.items()):
                writer.writerow([rank, run.sweep_run.spec.name, "train", year, f"{value:.10f}"])
            for year, value in sorted(run.test_annual_returns.items()):
                writer.writerow([rank, run.sweep_run.spec.name, "test", year, f"{value:.10f}"])


def _walk_forward_metric_columns(
    folds: list[WalkForwardValidationFold],
) -> list[str]:
    runs = [run for fold in folds for run in fold.runs]
    return _metric_columns(runs)


def _write_walk_forward_candidates(
    folds: list[WalkForwardValidationFold],
    path: Path,
    selection_metric: str,
) -> None:
    metric_columns = _walk_forward_metric_columns(folds)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "fold",
                "rank_by_train",
                "rank_by_test",
                "selected_by_train",
                "selection_metric",
                "train_selection_score",
                "test_selection_score",
                "name",
                "factor_set",
                "enabled_factors",
                "top_k",
                "risk_off_exposure",
                "risk_control",
                "market_score_control",
                "market_score_threshold",
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                *[f"train_{metric}" for metric in metric_columns],
                *[f"test_{metric}" for metric in metric_columns],
            ]
        )
        for fold in folds:
            ranked_train = _ranked_by_train(fold.runs, selection_metric)
            ranked_test = _ranked_by_test(fold.runs, selection_metric)
            test_rank_by_name = {
                run.sweep_run.spec.name: rank
                for rank, run in enumerate(ranked_test, start=1)
            }
            selected_name = ranked_train[0].sweep_run.spec.name
            split = fold.split
            for rank, run in enumerate(ranked_train, start=1):
                spec = run.sweep_run.spec
                writer.writerow(
                    [
                        fold.fold,
                        rank,
                        test_rank_by_name[spec.name],
                        str(spec.name == selected_name).lower(),
                        selection_metric,
                        f"{selection_score(run.train_metrics, selection_metric):.10f}",
                        f"{selection_score(run.test_metrics, selection_metric):.10f}",
                        spec.name,
                        spec.factor_set,
                        ";".join(spec.factors),
                        spec.top_k,
                        f"{spec.risk_off_exposure:.6f}",
                        str(spec.risk_control).lower(),
                        str(spec.market_score_control).lower(),
                        f"{spec.market_score_threshold:.6f}",
                        split.train_start.isoformat(),
                        split.train_end.isoformat(),
                        split.test_start.isoformat(),
                        split.test_end.isoformat(),
                        *[
                            f"{run.train_metrics[metric]:.10f}"
                            if metric in run.train_metrics
                            else ""
                            for metric in metric_columns
                        ],
                        *[
                            f"{run.test_metrics[metric]:.10f}"
                            if metric in run.test_metrics
                            else ""
                            for metric in metric_columns
                        ],
                    ]
                )


def _write_walk_forward_folds(
    folds: list[WalkForwardValidationFold],
    path: Path,
    selection_metric: str,
) -> None:
    selected_runs = [selected_by_train_with_data(fold.runs, selection_metric) for fold in folds]
    metric_columns = _metric_columns(selected_runs)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "fold",
                "test_rank",
                "selection_metric",
                "train_selection_score",
                "test_selection_score",
                "selected_name",
                "factor_set",
                "enabled_factors",
                "top_k",
                "risk_off_exposure",
                "risk_control",
                "market_score_control",
                "market_score_threshold",
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                *[f"train_{metric}" for metric in metric_columns],
                *[f"test_{metric}" for metric in metric_columns],
            ]
        )
        for fold, run in zip(folds, selected_runs, strict=True):
            ranked_test = _ranked_by_test(fold.runs, selection_metric)
            test_rank_by_name = {
                candidate.sweep_run.spec.name: rank
                for rank, candidate in enumerate(ranked_test, start=1)
            }
            spec = run.sweep_run.spec
            split = fold.split
            writer.writerow(
                [
                    fold.fold,
                    test_rank_by_name[spec.name],
                    selection_metric,
                    f"{selection_score(run.train_metrics, selection_metric):.10f}",
                    f"{selection_score(run.test_metrics, selection_metric):.10f}",
                    spec.name,
                    spec.factor_set,
                    ";".join(spec.factors),
                    spec.top_k,
                    f"{spec.risk_off_exposure:.6f}",
                    str(spec.risk_control).lower(),
                    str(spec.market_score_control).lower(),
                    f"{spec.market_score_threshold:.6f}",
                    split.train_start.isoformat(),
                    split.train_end.isoformat(),
                    split.test_start.isoformat(),
                    split.test_end.isoformat(),
                    *[
                        f"{run.train_metrics[metric]:.10f}"
                        if metric in run.train_metrics
                        else ""
                        for metric in metric_columns
                    ],
                    *[
                        f"{run.test_metrics[metric]:.10f}"
                        if metric in run.test_metrics
                        else ""
                        for metric in metric_columns
                    ],
                ]
            )


def _write_walk_forward_selected_equity(
    folds: list[WalkForwardValidationFold],
    path: Path,
    selection_metric: str,
) -> None:
    first_selected = selected_by_train(folds[0].runs, selection_metric)
    has_benchmark = first_selected.sweep_run.result.benchmark_equity is not None
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = [
            "fold",
            "date",
            "segment",
            "selected_name",
            "strategy",
            "equal_weight",
        ]
        if has_benchmark:
            header.append("benchmark")
        writer.writerow(header)
        for fold in folds:
            selected = selected_by_train_with_data(fold.runs, selection_metric)
            result = selected.sweep_run.result
            split = selected.split
            for segment, start_index, end_index in (
                ("train", split.train_start_index, split.train_end_index),
                ("test", split.test_start_index, split.test_end_index),
            ):
                strategy_equity = _segment_equity(
                    result.strategy_equity,
                    start_index,
                    end_index,
                )
                equal_weight_equity = _segment_equity(
                    result.equal_weight_equity,
                    start_index,
                    end_index,
                )
                benchmark_equity = (
                    _segment_equity(result.benchmark_equity, start_index, end_index)
                    if result.benchmark_equity is not None
                    else None
                )
                for offset, day in enumerate(result.dates[start_index : end_index + 1]):
                    row = [
                        fold.fold,
                        day.isoformat(),
                        segment,
                        selected.sweep_run.spec.name,
                        f"{strategy_equity[offset]:.10f}",
                        f"{equal_weight_equity[offset]:.10f}",
                    ]
                    if benchmark_equity is not None:
                        row.append(f"{benchmark_equity[offset]:.10f}")
                    writer.writerow(row)


def _write_walk_forward_oos_equity(
    folds: list[WalkForwardValidationFold],
    path: Path,
    selection_metric: str,
) -> None:
    first_selected = selected_by_train(folds[0].runs, selection_metric)
    has_benchmark = first_selected.sweep_run.result.benchmark_equity is not None
    strategy_base = 1.0
    equal_weight_base = 1.0
    benchmark_base = 1.0

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = ["date", "fold", "selected_name", "strategy", "equal_weight"]
        if has_benchmark:
            header.append("benchmark")
        writer.writerow(header)

        for fold in folds:
            selected = selected_by_train_with_data(fold.runs, selection_metric)
            result = selected.sweep_run.result
            split = selected.split
            strategy_equity = _segment_equity(
                result.strategy_equity,
                split.test_start_index,
                split.test_end_index,
            )
            equal_weight_equity = _segment_equity(
                result.equal_weight_equity,
                split.test_start_index,
                split.test_end_index,
            )
            benchmark_equity = (
                _segment_equity(
                    result.benchmark_equity,
                    split.test_start_index,
                    split.test_end_index,
                )
                if result.benchmark_equity is not None
                else None
            )
            for offset, day in enumerate(
                result.dates[split.test_start_index : split.test_end_index + 1]
            ):
                row = [
                    day.isoformat(),
                    fold.fold,
                    selected.sweep_run.spec.name,
                    f"{strategy_base * strategy_equity[offset]:.10f}",
                    f"{equal_weight_base * equal_weight_equity[offset]:.10f}",
                ]
                if benchmark_equity is not None:
                    row.append(f"{benchmark_base * benchmark_equity[offset]:.10f}")
                writer.writerow(row)

            strategy_base *= strategy_equity[-1]
            equal_weight_base *= equal_weight_equity[-1]
            if benchmark_equity is not None:
                benchmark_base *= benchmark_equity[-1]


def _write_fixed_candidate_summary(
    folds: list[WalkForwardValidationFold],
    path: Path,
) -> None:
    first_names = [run.sweep_run.spec.name for run in folds[0].runs]
    fold_runs_by_name: list[dict[str, TrainTestValidationRun]] = []
    for fold in folds:
        runs_by_name = {run.sweep_run.spec.name: run for run in fold.runs}
        if set(runs_by_name) != set(first_names):
            raise ValueError("All walk-forward folds must share candidate names")
        fold_runs_by_name.append(runs_by_name)

    has_benchmark = (
        folds[0].runs[0].sweep_run.result.benchmark_equity is not None
    )
    rows: list[tuple[float, str, TrainTestValidationRun, float, float | None]] = []
    for name in first_names:
        strategy_base = 1.0
        equal_weight_base = 1.0
        benchmark_base: float | None = 1.0 if has_benchmark else None
        first_run = fold_runs_by_name[0][name]

        for fold_runs in fold_runs_by_name:
            run = fold_runs[name]
            result = run.sweep_run.result
            split = run.split
            strategy_equity = _segment_equity(
                result.strategy_equity,
                split.test_start_index,
                split.test_end_index,
            )
            equal_weight_equity = _segment_equity(
                result.equal_weight_equity,
                split.test_start_index,
                split.test_end_index,
            )
            strategy_base *= strategy_equity[-1]
            equal_weight_base *= equal_weight_equity[-1]
            if benchmark_base is not None and result.benchmark_equity is not None:
                benchmark_equity = _segment_equity(
                    result.benchmark_equity,
                    split.test_start_index,
                    split.test_end_index,
                )
                benchmark_base *= benchmark_equity[-1]

        rows.append(
            (
                strategy_base,
                name,
                first_run,
                equal_weight_base,
                benchmark_base,
            )
        )

    rows.sort(key=lambda row: (-row[0], row[1]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = [
            "rank_by_oos_final_equity",
            "name",
            "factor_set",
            "enabled_factors",
            "top_k",
            "risk_off_exposure",
            "risk_control",
            "market_score_control",
            "market_score_threshold",
            "folds",
            "first_test_start",
            "last_test_end",
            "oos_final_equity",
            "equal_weight_final_equity",
            "oos_excess_vs_equal_weight",
        ]
        if has_benchmark:
            header.extend(["benchmark_final_equity", "oos_excess_vs_benchmark"])
        writer.writerow(header)
        for rank, (
            final_equity,
            _name,
            run,
            equal_weight_final,
            benchmark_final,
        ) in enumerate(rows, start=1):
            spec = run.sweep_run.spec
            row = [
                rank,
                spec.name,
                spec.factor_set,
                ";".join(spec.factors),
                spec.top_k,
                f"{spec.risk_off_exposure:.6f}",
                str(spec.risk_control).lower(),
                str(spec.market_score_control).lower(),
                f"{spec.market_score_threshold:.6f}",
                len(folds),
                folds[0].split.test_start.isoformat(),
                folds[-1].split.test_end.isoformat(),
                f"{final_equity:.10f}",
                f"{equal_weight_final:.10f}",
                f"{final_equity / equal_weight_final - 1.0:.10f}",
            ]
            if has_benchmark:
                value = benchmark_final if benchmark_final is not None else 0.0
                row.extend(
                    [
                        f"{value:.10f}",
                        f"{final_equity / value - 1.0:.10f}" if value > 0 else "",
                    ]
                )
            writer.writerow(row)


def _write_walk_forward_summary(
    folds: list[WalkForwardValidationFold],
    path: Path,
    selection_metric: str,
) -> None:
    selected_runs = [selected_by_train_with_data(fold.runs, selection_metric) for fold in folds]
    metric_columns = _metric_columns(selected_runs)
    selection_counts: dict[str, int] = {}
    for run in selected_runs:
        name = run.sweep_run.spec.name
        selection_counts[name] = selection_counts.get(name, 0) + 1

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "name", "value"])
        writer.writerow(["summary", "folds", len(folds)])
        writer.writerow(["summary", "selection_metric", selection_metric])
        writer.writerow(["summary", "first_train_start", folds[0].split.train_start.isoformat()])
        writer.writerow(["summary", "last_test_end", folds[-1].split.test_end.isoformat()])
        for metric in metric_columns:
            test_values = [
                run.test_metrics[metric]
                for run in selected_runs
                if metric in run.test_metrics
            ]
            train_values = [
                run.train_metrics[metric]
                for run in selected_runs
                if metric in run.train_metrics
            ]
            if test_values:
                writer.writerow(["test_mean", metric, f"{mean(test_values):.10f}"])
                writer.writerow(["test_median", metric, f"{median(test_values):.10f}"])
                writer.writerow(["test_std", metric, f"{pstdev(test_values):.10f}"])
            if train_values:
                writer.writerow(["train_mean", metric, f"{mean(train_values):.10f}"])
                writer.writerow(["train_median", metric, f"{median(train_values):.10f}"])
                writer.writerow(["train_std", metric, f"{pstdev(train_values):.10f}"])
        for name, count in sorted(
            selection_counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            writer.writerow(["selection_count", name, count])
