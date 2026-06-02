from __future__ import annotations

import csv
from pathlib import Path

from .models import BacktestResult


def write_reports(result: BacktestResult, output_dir: str | Path) -> None:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    _write_metrics(result, path / "metrics.csv")
    _write_equity_curve(result, path / "equity_curve.csv")
    _write_rebalances(result, path / "rebalances.csv")
    _write_annual_returns(result, path / "annual_returns.csv")


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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["year", "strategy_return"])
        for year, value in sorted(result.annual_returns.items()):
            writer.writerow([year, f"{value:.10f}"])
