from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .metrics import annual_returns, summarize_performance
from .models import BacktestResult
from .reports import write_reports
from .sweep import METRIC_ORDER, ParameterSweepRun, write_parameter_sweep_reports


@dataclass(frozen=True)
class SegmentBacktestRun:
    name: str
    result: BacktestResult
    industries: int


@dataclass(frozen=True)
class SegmentedBacktestResult:
    segments: list[SegmentBacktestRun]
    stitched: BacktestResult


@dataclass(frozen=True)
class SegmentParameterSweepRuns:
    name: str
    industries: int
    runs: list[ParameterSweepRun]


@dataclass(frozen=True)
class SegmentedParameterSweepRun:
    spec_name: str
    run: ParameterSweepRun
    segments: list[SegmentBacktestRun]


def stitch_backtest_segments(
    segments: list[SegmentBacktestRun],
) -> SegmentedBacktestResult:
    if not segments:
        raise ValueError("At least one segment is required")

    has_benchmark = segments[0].result.benchmark_equity is not None
    dates = []
    strategy_equity = []
    equal_weight_equity = []
    benchmark_equity = [] if has_benchmark else None
    rebalances = []
    segment_base = {
        "strategy": 1.0,
        "equal_weight": 1.0,
        "benchmark": 1.0,
    }
    previous_date = None

    for segment in segments:
        result = segment.result
        if previous_date is not None and result.dates[0] <= previous_date:
            raise ValueError("Segment dates must be strictly increasing")
        if has_benchmark and result.benchmark_equity is None:
            raise ValueError("All segments must include benchmark equity")
        if not has_benchmark and result.benchmark_equity is not None:
            raise ValueError("All segments must share benchmark availability")

        dates.extend(result.dates)
        strategy_equity.extend(
            segment_base["strategy"] * value for value in result.strategy_equity
        )
        equal_weight_equity.extend(
            segment_base["equal_weight"] * value for value in result.equal_weight_equity
        )
        if benchmark_equity is not None and result.benchmark_equity is not None:
            benchmark_equity.extend(
                segment_base["benchmark"] * value for value in result.benchmark_equity
            )
            segment_base["benchmark"] *= result.benchmark_equity[-1]

        rebalances.extend(result.rebalances)
        segment_base["strategy"] *= result.strategy_equity[-1]
        segment_base["equal_weight"] *= result.equal_weight_equity[-1]
        previous_date = result.dates[-1]

    daily_returns = [0.0]
    for index in range(1, len(strategy_equity)):
        daily_returns.append(strategy_equity[index] / strategy_equity[index - 1] - 1.0)

    metrics = summarize_performance(
        dates,
        strategy_equity,
        benchmark_equity,
        equal_weight_equity,
        turnovers=[event.turnover for event in rebalances],
        costs=[event.cost for event in rebalances],
    )
    stitched = BacktestResult(
        dates=dates,
        strategy_equity=strategy_equity,
        benchmark_equity=benchmark_equity,
        equal_weight_equity=equal_weight_equity,
        daily_returns=daily_returns,
        rebalances=rebalances,
        metrics=metrics,
        annual_returns=annual_returns(dates, strategy_equity),
    )
    return SegmentedBacktestResult(segments=segments, stitched=stitched)


def stitch_parameter_sweep_segments(
    segments: list[SegmentParameterSweepRuns],
) -> list[SegmentedParameterSweepRun]:
    if not segments:
        raise ValueError("At least one parameter sweep segment is required")
    first_names = [run.spec.name for run in segments[0].runs]
    if not first_names:
        raise ValueError("Parameter sweep segments require at least one run")

    for segment in segments:
        names = [run.spec.name for run in segment.runs]
        if names != first_names:
            raise ValueError(
                "All parameter sweep segments must share candidate names and order"
            )

    stitched_runs: list[SegmentedParameterSweepRun] = []
    for candidate_index, candidate_name in enumerate(first_names):
        candidate_segments = [
            SegmentBacktestRun(
                name=segment.name,
                result=segment.runs[candidate_index].result,
                industries=segment.industries,
            )
            for segment in segments
        ]
        stitched = stitch_backtest_segments(candidate_segments)
        first_run = segments[0].runs[candidate_index]
        stitched_run = ParameterSweepRun(
            spec=first_run.spec,
            result=stitched.stitched,
        )
        stitched_runs.append(
            SegmentedParameterSweepRun(
                spec_name=candidate_name,
                run=stitched_run,
                segments=candidate_segments,
            )
        )
    return stitched_runs


def write_segmented_backtest_reports(
    result: SegmentedBacktestResult,
    output_dir: str | Path,
) -> None:
    path = Path(output_dir)
    write_reports(result.stitched, path)
    _write_segment_summary(result, path / "segment_summary.csv")
    _write_segmented_equity_curve(result, path / "segmented_equity_curve.csv")


def write_segmented_parameter_sweep_reports(
    runs: list[SegmentedParameterSweepRun],
    output_dir: str | Path,
    top_n_equity: int = 10,
) -> None:
    if not runs:
        raise ValueError("Segmented parameter sweep requires at least one run")
    path = Path(output_dir)
    write_parameter_sweep_reports(
        [run.run for run in runs],
        path,
        top_n_equity=top_n_equity,
    )
    _write_segmented_sweep_segments(
        runs,
        path / "parameter_sweep_segments.csv",
    )


def _metric_columns(result: SegmentedBacktestResult) -> list[str]:
    available = set(result.stitched.metrics)
    for segment in result.segments:
        available.update(segment.result.metrics)
    ordered = [metric for metric in METRIC_ORDER if metric in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _sweep_metric_columns(runs: list[SegmentedParameterSweepRun]) -> list[str]:
    available = set()
    for run in runs:
        available.update(run.run.result.metrics)
        for segment in run.segments:
            available.update(segment.result.metrics)
    ordered = [metric for metric in METRIC_ORDER if metric in available]
    ordered.extend(sorted(available - set(ordered)))
    return ordered


def _write_segment_summary(
    result: SegmentedBacktestResult,
    path: Path,
) -> None:
    metric_columns = _metric_columns(result)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "segment",
                "start",
                "end",
                "rows",
                "industries",
                "rebalances",
                *metric_columns,
            ]
        )
        for segment in result.segments:
            segment_result = segment.result
            writer.writerow(
                [
                    segment.name,
                    segment_result.dates[0].isoformat(),
                    segment_result.dates[-1].isoformat(),
                    len(segment_result.dates),
                    segment.industries,
                    len(segment_result.rebalances),
                    *[
                        f"{segment_result.metrics[metric]:.10f}"
                        if metric in segment_result.metrics
                        else ""
                        for metric in metric_columns
                    ],
                ]
            )
        writer.writerow(
            [
                "stitched",
                result.stitched.dates[0].isoformat(),
                result.stitched.dates[-1].isoformat(),
                len(result.stitched.dates),
                "",
                len(result.stitched.rebalances),
                *[
                    f"{result.stitched.metrics[metric]:.10f}"
                    if metric in result.stitched.metrics
                    else ""
                    for metric in metric_columns
                ],
            ]
        )


def _write_segmented_equity_curve(
    result: SegmentedBacktestResult,
    path: Path,
) -> None:
    has_benchmark = result.stitched.benchmark_equity is not None
    segment_by_date = {
        day: segment.name
        for segment in result.segments
        for day in segment.result.dates
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = ["date", "segment", "strategy", "industry_equal_weight"]
        if has_benchmark:
            header.append("benchmark")
        writer.writerow(header)
        for index, day in enumerate(result.stitched.dates):
            row = [
                day.isoformat(),
                segment_by_date[day],
                f"{result.stitched.strategy_equity[index]:.10f}",
                f"{result.stitched.equal_weight_equity[index]:.10f}",
            ]
            if result.stitched.benchmark_equity is not None:
                row.append(f"{result.stitched.benchmark_equity[index]:.10f}")
            writer.writerow(row)


def _write_segmented_sweep_segments(
    runs: list[SegmentedParameterSweepRun],
    path: Path,
) -> None:
    metric_columns = _sweep_metric_columns(runs)
    ranked = sorted(
        runs,
        key=lambda run: (
            -run.run.result.metrics["annualized_return"],
            run.run.result.metrics["max_drawdown"],
            run.run.spec.name,
        ),
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "name",
                "segment",
                "start",
                "end",
                "rows",
                "industries",
                "rebalances",
                *metric_columns,
            ]
        )
        for rank, run in enumerate(ranked, start=1):
            for segment in run.segments:
                segment_result = segment.result
                writer.writerow(
                    [
                        rank,
                        run.run.spec.name,
                        segment.name,
                        segment_result.dates[0].isoformat(),
                        segment_result.dates[-1].isoformat(),
                        len(segment_result.dates),
                        segment.industries,
                        len(segment_result.rebalances),
                        *[
                            f"{segment_result.metrics[metric]:.10f}"
                            if metric in segment_result.metrics
                            else ""
                            for metric in metric_columns
                        ],
                    ]
                )
            stitched_result = run.run.result
            writer.writerow(
                [
                    rank,
                    run.run.spec.name,
                    "stitched",
                    stitched_result.dates[0].isoformat(),
                    stitched_result.dates[-1].isoformat(),
                    len(stitched_result.dates),
                    "",
                    len(stitched_result.rebalances),
                    *[
                        f"{stitched_result.metrics[metric]:.10f}"
                        if metric in stitched_result.metrics
                        else ""
                        for metric in metric_columns
                    ],
                ]
            )
