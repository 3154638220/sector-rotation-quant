from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path

from .metrics import annual_returns
from .models import BacktestResult


def write_reports(result: BacktestResult, output_dir: str | Path) -> None:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    _write_metrics(result, path / "metrics.csv")
    _write_equity_curve(result, path / "equity_curve.csv")
    _write_rebalances(result, path / "rebalances.csv")
    _write_annual_returns(result, path / "annual_returns.csv")
    _write_holding_period_returns(result, path / "holding_period_returns.csv")
    _write_holding_period_distribution(
        result,
        path / "holding_period_return_distribution.csv",
    )
    _write_industry_selection_frequency(
        result,
        path / "industry_selection_frequency.csv",
    )
    _write_risk_control_frequency(result, path / "risk_control_frequency.csv")


def _write_metrics(result: BacktestResult, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in sorted(result.metrics.items()):
            writer.writerow([key, f"{value:.10f}"])


def _write_equity_curve(result: BacktestResult, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = ["date", "strategy", "industry_equal_weight"]
        if result.benchmark_equity is not None:
            header.append("benchmark")
        writer.writerow(header)
        for i, day in enumerate(result.dates):
            row = [
                day.isoformat(),
                f"{result.strategy_equity[i]:.10f}",
                f"{result.equal_weight_equity[i]:.10f}",
            ]
            if result.benchmark_equity is not None:
                row.append(f"{result.benchmark_equity[i]:.10f}")
            writer.writerow(row)


def _write_rebalances(result: BacktestResult, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "signal_date",
                "selected_industries",
                "holdings",
                "exposure",
                "turnover",
                "cost",
                "market_trend",
                "market_score",
                "market_score_ok",
                "risk_on",
            ]
        )
        for event in result.rebalances:
            weights = [
                f"{asset}:{event.weights[asset]:.4f}" for asset in event.holdings
            ]
            writer.writerow(
                [
                    event.date.isoformat(),
                    event.signal_date.isoformat(),
                    ";".join(event.selected_industries),
                    ";".join(weights),
                    f"{event.exposure:.6f}",
                    f"{event.turnover:.6f}",
                    f"{event.cost:.8f}",
                    str(event.market_trend).lower(),
                    "" if event.market_score is None else f"{event.market_score:.8f}",
                    str(event.market_score_ok).lower(),
                    str(event.risk_on).lower(),
                ]
            )


def _write_annual_returns(result: BacktestResult, path: Path) -> None:
    benchmark_returns = (
        annual_returns(result.dates, result.benchmark_equity)
        if result.benchmark_equity is not None
        else {}
    )
    equal_weight_returns = annual_returns(result.dates, result.equal_weight_equity)
    years = sorted(
        set(result.annual_returns)
        | set(benchmark_returns)
        | set(equal_weight_returns)
    )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "year",
                "strategy_return",
                "benchmark_return",
                "industry_equal_weight_return",
                "excess_vs_benchmark",
                "excess_vs_equal_weight",
            ]
        )
        for year in years:
            strategy_value = result.annual_returns.get(year)
            benchmark_value = benchmark_returns.get(year)
            equal_weight_value = equal_weight_returns.get(year)
            writer.writerow(
                [
                    year,
                    "" if strategy_value is None else f"{strategy_value:.10f}",
                    "" if benchmark_value is None else f"{benchmark_value:.10f}",
                    "" if equal_weight_value is None else f"{equal_weight_value:.10f}",
                    ""
                    if strategy_value is None or benchmark_value is None
                    else f"{strategy_value - benchmark_value:.10f}",
                    ""
                    if strategy_value is None or equal_weight_value is None
                    else f"{strategy_value - equal_weight_value:.10f}",
                ]
            )


def _event_index_by_date(result: BacktestResult) -> dict[object, int]:
    return {day: index for index, day in enumerate(result.dates)}


def _series_return(values: list[float] | None, start_index: int, end_index: int) -> float | None:
    if values is None:
        return None
    start_value = values[start_index]
    if start_value == 0:
        return None
    return values[end_index] / start_value - 1.0


def _holding_period_rows(result: BacktestResult) -> list[dict[str, object]]:
    index_by_date = _event_index_by_date(result)
    rows: list[dict[str, object]] = []
    for event_index, event in enumerate(result.rebalances):
        start_index = index_by_date[event.date]
        if event_index + 1 < len(result.rebalances):
            next_start_index = index_by_date[result.rebalances[event_index + 1].date]
            end_index = max(start_index, next_start_index - 1)
        else:
            end_index = len(result.dates) - 1

        strategy_return = _series_return(result.strategy_equity, start_index, end_index)
        benchmark_return = _series_return(result.benchmark_equity, start_index, end_index)
        equal_weight_return = _series_return(
            result.equal_weight_equity,
            start_index,
            end_index,
        )
        rows.append(
            {
                "date": event.date.isoformat(),
                "signal_date": event.signal_date.isoformat(),
                "end_date": result.dates[end_index].isoformat(),
                "trading_days": end_index - start_index,
                "calendar_days": (result.dates[end_index] - event.date).days,
                "strategy_return": strategy_return,
                "benchmark_return": benchmark_return,
                "industry_equal_weight_return": equal_weight_return,
                "excess_vs_benchmark": (
                    None
                    if strategy_return is None or benchmark_return is None
                    else strategy_return - benchmark_return
                ),
                "excess_vs_equal_weight": (
                    None
                    if strategy_return is None or equal_weight_return is None
                    else strategy_return - equal_weight_return
                ),
                "exposure": event.exposure,
                "turnover": event.turnover,
                "cost": event.cost,
                "risk_on": event.risk_on,
                "market_trend": event.market_trend,
                "market_score": event.market_score,
                "market_score_ok": event.market_score_ok,
                "selected_industries": ";".join(event.selected_industries),
            }
        )
    return rows


def _format_optional(value: object, digits: int = 10) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _write_holding_period_returns(result: BacktestResult, path: Path) -> None:
    rows = _holding_period_rows(result)
    headers = [
        "date",
        "signal_date",
        "end_date",
        "trading_days",
        "calendar_days",
        "strategy_return",
        "benchmark_return",
        "industry_equal_weight_return",
        "excess_vs_benchmark",
        "excess_vs_equal_weight",
        "exposure",
        "turnover",
        "cost",
        "risk_on",
        "market_trend",
        "market_score",
        "market_score_ok",
        "selected_industries",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([_format_optional(row[header]) for header in headers])


def _return_bucket(value: float) -> str:
    buckets = [
        (-0.10, "< -10%"),
        (-0.05, "-10% to -5%"),
        (-0.02, "-5% to -2%"),
        (0.0, "-2% to 0%"),
        (0.02, "0% to 2%"),
        (0.05, "2% to 5%"),
        (0.10, "5% to 10%"),
    ]
    for upper_bound, label in buckets:
        if value < upper_bound:
            return label
    return ">= 10%"


def _write_holding_period_distribution(result: BacktestResult, path: Path) -> None:
    returns = [
        row["strategy_return"]
        for row in _holding_period_rows(result)
        if isinstance(row["strategy_return"], float)
    ]
    counts = Counter(_return_bucket(value) for value in returns)
    bucket_order = [
        "< -10%",
        "-10% to -5%",
        "-5% to -2%",
        "-2% to 0%",
        "0% to 2%",
        "2% to 5%",
        "5% to 10%",
        ">= 10%",
    ]
    total = len(returns)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["bucket", "count", "share"])
        for bucket in bucket_order:
            count = counts.get(bucket, 0)
            share = count / total if total else 0.0
            writer.writerow([bucket, count, f"{share:.10f}"])


def _write_industry_selection_frequency(result: BacktestResult, path: Path) -> None:
    selected_counts: Counter[str] = Counter()
    risk_on_counts: Counter[str] = Counter()
    risk_off_counts: Counter[str] = Counter()
    weight_totals: Counter[str] = Counter()

    for event in result.rebalances:
        for industry in event.selected_industries:
            selected_counts[industry] += 1
            if event.risk_on:
                risk_on_counts[industry] += 1
            else:
                risk_off_counts[industry] += 1
            weight_totals[industry] += event.weights.get(industry, 0.0)

    total_rebalances = len(result.rebalances)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "industry",
                "selected_count",
                "selected_share",
                "risk_on_count",
                "risk_off_count",
                "average_selected_weight",
            ]
        )
        for industry, count in sorted(
            selected_counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            writer.writerow(
                [
                    industry,
                    count,
                    f"{count / total_rebalances if total_rebalances else 0.0:.10f}",
                    risk_on_counts[industry],
                    risk_off_counts[industry],
                    f"{weight_totals[industry] / count if count else 0.0:.10f}",
                ]
            )


def _write_risk_control_frequency(result: BacktestResult, path: Path) -> None:
    total_rebalances = len(result.rebalances)
    risk_off_events = [event for event in result.rebalances if not event.risk_on]
    trend_failures = [event for event in result.rebalances if not event.market_trend]
    score_failures = [event for event in result.rebalances if not event.market_score_ok]
    months = {(event.date.year, event.date.month) for event in result.rebalances}
    risk_off_months = {(event.date.year, event.date.month) for event in risk_off_events}
    risk_on_exposures = [event.exposure for event in result.rebalances if event.risk_on]
    risk_off_exposures = [event.exposure for event in risk_off_events]

    rows = [
        ("total_rebalances", total_rebalances),
        ("risk_off_rebalances", len(risk_off_events)),
        (
            "risk_off_rebalance_share",
            len(risk_off_events) / total_rebalances if total_rebalances else 0.0,
        ),
        ("market_trend_failures", len(trend_failures)),
        (
            "market_trend_failure_share",
            len(trend_failures) / total_rebalances if total_rebalances else 0.0,
        ),
        ("market_score_failures", len(score_failures)),
        (
            "market_score_failure_share",
            len(score_failures) / total_rebalances if total_rebalances else 0.0,
        ),
        ("rebalance_months", len(months)),
        ("risk_off_months", len(risk_off_months)),
        (
            "risk_off_month_share",
            len(risk_off_months) / len(months) if months else 0.0,
        ),
        (
            "average_risk_on_exposure",
            sum(risk_on_exposures) / len(risk_on_exposures)
            if risk_on_exposures
            else 0.0,
        ),
        (
            "average_risk_off_exposure",
            sum(risk_off_exposures) / len(risk_off_exposures)
            if risk_off_exposures
            else 0.0,
        ),
    ]

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for metric, value in rows:
            writer.writerow([metric, _format_optional(value)])
