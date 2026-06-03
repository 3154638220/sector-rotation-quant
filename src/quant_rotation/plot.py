from __future__ import annotations

import csv
import io
from base64 import b64encode
from datetime import date
from pathlib import Path
from typing import Callable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def plot_equity_curve(
    dates: list[date],
    strategy: list[float],
    equal_weight: list[float],
    benchmark: list[float] | None = None,
    title: str = "Equity Curve",
) -> bytes:
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(dates, strategy, linewidth=1.2, label="Strategy", color="#1f77b4")
    ax.plot(dates, equal_weight, linewidth=0.8, label="Equal Weight", color="#2ca02c")
    if benchmark:
        ax.plot(dates, benchmark, linewidth=0.8, label="Benchmark", color="#ff7f0e")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def plot_drawdown(
    dates: list[date],
    strategy_equity: list[float],
    title: str = "Drawdown",
) -> bytes:
    drawdown = _compute_drawdown_series(strategy_equity)
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.fill_between(dates, drawdown, 0, color="#d62728", alpha=0.5)
    ax.plot(dates, drawdown, linewidth=0.5, color="#d62728")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def plot_annual_returns(
    annual_returns: dict[int, float],
    title: str = "Annual Returns",
) -> bytes:
    years = sorted(annual_returns)
    values = [annual_returns[y] for y in years]
    colors = ["#2ca02c" if v > 0 else "#d62728" for v in values]
    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.bar([str(y) for y in years], values, color=colors, edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.5)
    for bar, val in zip(bars, values):
        y_pos = bar.get_height()
        va = "bottom" if y_pos >= 0 else "top"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y_pos,
            f"{val:.1%}",
            ha="center",
            va=va,
            fontsize=8,
        )
    ax.set_title(title)
    ax.set_xlabel("Year")
    ax.set_ylabel("Return")
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax.grid(True, alpha=0.3, axis="y")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def plot_holding_return_distribution(
    holding_returns_path: str | Path,
    title: str = "Holding Period Returns",
) -> bytes:
    buckets: list[str] = []
    counts: list[int] = []
    with open(holding_returns_path, "r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            buckets.append(row["bucket"])
            counts.append(int(row["count"]))
    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.bar(buckets, counts, color="#1f77b4", edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel("Return Range")
    ax.set_ylabel("Count")
    ax.grid(True, alpha=0.3, axis="y")
    for bar, count in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(count),
            ha="center",
            va="bottom",
            fontsize=8,
        )
    total = sum(counts)
    ax.text(
        0.95, 0.95,
        f"Total: {total}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def write_html_report(
    output_dir: str | Path,
    equity_curve_path: str | Path,
    benchmarks_curve_path: str | Path | None = None,
    annual_returns: dict[int, float] | None = None,
    holding_returns_path: str | Path | None = None,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    dates, strategy, equal_weight, benchmark = _load_equity_curve(equity_curve_path)

    equity_png = plot_equity_curve(dates, strategy, equal_weight, benchmark, "Strategy vs Benchmarks")
    drawdown_png = plot_drawdown(dates, strategy, "Drawdown")

    sections_html = ""
    sections_html += f'<h2>Equity Curve</h2><img src="data:image/png;base64,{b64encode(equity_png).decode()}">'
    sections_html += f'<h2>Drawdown</h2><img src="data:image/png;base64,{b64encode(drawdown_png).decode()}">'

    if annual_returns:
        annual_png = plot_annual_returns(annual_returns)
        sections_html += f'<h2>Annual Returns</h2><img src="data:image/png;base64,{b64encode(annual_png).decode()}">'

    if holding_returns_path and Path(holding_returns_path).exists():
        hist_png = plot_holding_return_distribution(holding_returns_path)
        sections_html += f'<h2>Holding Period Return Distribution</h2><img src="data:image/png;base64,{b64encode(hist_png).decode()}">'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Strategy Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
h1 {{ color: #333; }}
h2 {{ color: #555; margin-top: 30px; }}
img {{ width: 100%; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 10px 0; }}
</style></head>
<body>
<h1>Strategy Report</h1>
{sections_html}
</body></html>"""

    html_path = out / "report.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def _compute_drawdown_series(equity: list[float]) -> list[float]:
    peak = equity[0]
    result = [0.0]
    for value in equity[1:]:
        peak = max(peak, value)
        result.append(value / peak - 1.0 if peak > 0 else 0.0)
    return result


def _load_equity_curve(path: str | Path):
    dates = []
    strategy = []
    equal_weight = []
    benchmark: list[float] | None = None
    has_benchmark = False
    with open(path, "r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            dates.append(date.fromisoformat(row["date"]))
            strategy.append(float(row["strategy"]))
            equal_weight.append(float(row["industry_equal_weight"]))
            if "benchmark" in row:
                has_benchmark = True
                if benchmark is None:
                    benchmark = []
                benchmark.append(float(row["benchmark"]))
    if not has_benchmark:
        benchmark = None
    return dates, strategy, equal_weight, benchmark
