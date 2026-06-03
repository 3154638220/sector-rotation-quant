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

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def plot_equity_curve(
    dates: list[date],
    strategy: list[float],
    equal_weight: list[float],
    benchmark: list[float] | None = None,
    title: str = "Equity Curve",
    extra_benchmarks: list[tuple[str, list[float]]] | None = None,
) -> bytes:
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(dates, strategy, linewidth=1.2, label="Strategy", color="#1f77b4")
    ax.plot(dates, equal_weight, linewidth=0.8, label="Equal Weight", color="#2ca02c")
    if benchmark:
        ax.plot(dates, benchmark, linewidth=0.8, label="CSI 300", color="#ff7f0e")
    extra_colors = ["#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]
    if extra_benchmarks:
        for i, (label, values) in enumerate(extra_benchmarks):
            ax.plot(dates, values, linewidth=0.8, label=label,
                    color=extra_colors[i % len(extra_colors)])
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
    extra_sections: str = "",
    extra_benchmarks: list[tuple[str, list[float]]] | None = None,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    dates, strategy, equal_weight, benchmark = _load_equity_curve(equity_curve_path)

    equity_png = plot_equity_curve(dates, strategy, equal_weight, benchmark, "Strategy vs Benchmarks", extra_benchmarks=extra_benchmarks)
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
{extra_sections}
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


def plot_walk_forward_folds(
    oos_equity_csv: str | Path,
    folds_csv: str | Path,
) -> tuple[bytes, bytes]:
    import pandas as pd

    eq = pd.read_csv(oos_equity_csv, parse_dates=["date"])
    folds_df = pd.read_csv(folds_csv)

    folds_sorted = sorted(eq["fold"].unique())
    cmap = plt.cm.tab20

    fig, ax = plt.subplots(figsize=(14, 6))
    for idx, fold_id in enumerate(folds_sorted):
        fold_eq = eq[eq["fold"] == fold_id]
        color = cmap(idx % 20)
        ax.plot(fold_eq["date"], fold_eq["strategy"], linewidth=0.8,
                color=color, alpha=0.7, label=f"Fold {fold_id}")
    ax.set_title("Walk-Forward Fold OOS Equity Curves")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity")
    ax.axhline(1.0, color="black", linewidth=0.5, linestyle="--", alpha=0.3)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    fig.autofmt_xdate()
    if len(folds_sorted) <= 20:
        ax.legend(loc="upper left", fontsize=7, ncol=2)
    equity_buf = io.BytesIO()
    fig.savefig(equity_buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    returns = [float(r) for r in folds_df["test_annualized_return"].tolist()]
    fold_labels = [f"F{int(f)}" for f in folds_df["fold"].tolist()]
    colors_bar = ["#2ca02c" if v > 0 else "#d62728" for v in returns]

    fig2, ax2 = plt.subplots(figsize=(14, 4))
    bars = ax2.bar(fold_labels, returns, color=colors_bar, edgecolor="white")
    ax2.axhline(0, color="black", linewidth=0.5)
    for bar, val in zip(bars, returns):
        y_pos = bar.get_height()
        va = "bottom" if y_pos >= 0 else "top"
        ax2.text(bar.get_x() + bar.get_width() / 2, y_pos,
                 f"{val:.1%}", ha="center", va=va, fontsize=7, rotation=90)
    pos_count = sum(1 for v in returns if v > 0)
    ax2.set_title(f"Per-Fold OOS Annualized Return  ({pos_count}/{len(returns)} profitable)")
    ax2.set_xlabel("Fold")
    ax2.set_ylabel("Annualized Return")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax2.grid(True, alpha=0.3, axis="y")

    median = sorted(returns)[len(returns) // 2]
    mean_v = sum(returns) / len(returns)
    ax2.axhline(median, color="#9467bd", linewidth=1, linestyle="--",
                label=f"Median {median:.1%}")
    ax2.axhline(mean_v, color="#ff7f0e", linewidth=1, linestyle="--",
                label=f"Mean {mean_v:.1%}")
    ax2.legend(loc="upper left", fontsize=8)
    bar_buf = io.BytesIO()
    fig2.savefig(bar_buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig2)

    return equity_buf.getvalue(), bar_buf.getvalue()


def plot_risk_control_accuracy(
    accuracy_csv: str | Path,
) -> bytes:
    import pandas as pd
    df = pd.read_csv(accuracy_csv, parse_dates=["signal_date"])
    df["year"] = df["signal_date"].dt.year

    years = sorted(df["year"].unique())
    tp_counts = []
    fp_counts = []
    neutral_counts = []
    hit_rates = []
    for y in years:
        ydf = df[df["year"] == y]
        tp = (ydf["result"] == "TRUE_POSITIVE").sum()
        fp = (ydf["result"] == "FALSE_POSITIVE").sum()
        ne = (ydf["result"] == "NEUTRAL").sum()
        total = tp + fp + ne
        tp_counts.append(tp)
        fp_counts.append(fp)
        neutral_counts.append(ne)
        hit_rates.append(tp / (tp + fp) if (tp + fp) > 0 else float("nan"))

    fig, ax1 = plt.subplots(figsize=(12, 5))
    x = range(len(years))
    width = 0.5
    ax1.bar(x, tp_counts, width, label="True Positive", color="#2ca02c", edgecolor="white")
    ax1.bar(x, fp_counts, width, bottom=tp_counts, label="False Positive",
            color="#d62728", edgecolor="white")
    neutral_bottom = [tp + fp for tp, fp in zip(tp_counts, fp_counts)]
    ax1.bar(x, neutral_counts, width, bottom=neutral_bottom, label="Neutral",
            color="#7f7f7f", edgecolor="white")

    ax1.set_xlabel("Year")
    ax1.set_ylabel("Count")
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(y) for y in years])
    ax1.set_title("Risk Control Accuracy by Year")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3, axis="y")

    ax2 = ax1.twinx()
    ax2.plot(x, hit_rates, "o-", color="#1f77b4", linewidth=2, markersize=6, label="Hit Rate")
    ax2.set_ylabel("Hit Rate (TP / (TP+FP))")
    ax2.set_ylim(-0.05, 1.05)
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter(1.0))
    ax2.axhline(0.5, color="red", linewidth=0.5, linestyle="--", alpha=0.5, label="Random (50%)")
    ax2.legend(loc="upper right")

    for i, hr in enumerate(hit_rates):
        if not (hr != hr):
            ax2.annotate(f"{hr:.0%}", (i, hr), textcoords="offset points",
                         xytext=(0, 8), ha="center", fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def plot_parameter_heatmap(
    sweep_csv: str | Path,
    x_param: str = "top_k",
    y_param: str = "risk_off_exposure",
    metric: str = "sharpe_ratio",
) -> bytes:
    import pandas as pd
    import numpy as np
    df = pd.read_csv(sweep_csv)

    if x_param not in df.columns or y_param not in df.columns:
        raise ValueError(f"Parameters {x_param} or {y_param} not found in sweep CSV")

    pivot = df.pivot_table(values=metric, index=y_param, columns=x_param, aggfunc="max")

    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", origin="lower")

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([str(c) for c in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(i) for i in pivot.index])
    ax.set_xlabel(x_param)
    ax.set_ylabel(y_param)
    ax.set_title(f"Parameter Heatmap: {metric} by {y_param} x {x_param}")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label(metric)

    for yi in range(len(pivot.index)):
        for xi in range(len(pivot.columns)):
            val = pivot.values[yi, xi]
            if not np.isnan(val):
                ax.text(xi, yi, f"{val:.3f}", ha="center", va="center",
                        fontsize=9, color="black" if 0.2 < abs(val) < 0.8 else "white")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def render_wf_summary_table(summary_csv: str | Path) -> str:
    from collections import defaultdict
    sections: dict[str, dict[str, str]] = defaultdict(dict)
    with open(summary_csv, "r", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            section = row.get("section", "")
            name = row.get("name", "")
            value = row.get("value", "")
            if section and name:
                sections[section][name] = value

    metric_labels = {
        "annualized_return": "OOS Annualized Return",
        "sharpe_ratio": "OOS Sharpe",
        "max_drawdown": "OOS Max Drawdown",
        "final_equity": "OOS Final Equity",
        "calmar_ratio": "OOS Calmar",
    }
    stats = ["test_mean", "test_median", "test_std"]

    rows = ""
    for metric_key, label in metric_labels.items():
        cells = f"<td>{label}</td>"
        for stat in stats:
            val = sections.get(stat, {}).get(metric_key, "—")
            try:
                if "return" in metric_key or "drawdown" in metric_key:
                    cells += f"<td>{float(val):.2%}</td>"
                else:
                    cells += f"<td>{float(val):.3f}</td>"
            except (ValueError, TypeError):
                cells += f"<td>{val}</td>"
        rows += f"<tr>{cells}</tr>"

    bootstrap_key = None
    for name_key in sections.get("test_mean", {}):
        if "bootstrap_p_positive" in name_key:
            bootstrap_key = name_key
            break
    bootstrap_p = sections.get("test_mean", {}).get(bootstrap_key or "", "") if bootstrap_key else ""

    folds = sections.get("summary", {}).get("folds", "—")
    selection = sections.get("summary", {}).get("selection_metric", "—")

    bootstrap_row = ""
    if bootstrap_p:
        try:
            bp_val = float(bootstrap_p)
            bootstrap_row = (
                f'<tr><td>Bootstrap p_positive</td>'
                f'<td colspan="3" style="text-align:center">{bp_val:.2%}</td></tr>'
            )
        except (ValueError, TypeError):
            pass

    return f"""<h2>Walk-Forward Summary</h2>
<table style="border-collapse:collapse;width:100%;max-width:700px;margin:10px 0;">
<tr style="background:#f0f0f0;"><td>Folds</td><td colspan="3" style="text-align:center">{folds}</td></tr>
<tr style="background:#f0f0f0;"><td>Selection</td><td colspan="3" style="text-align:center">{selection}</td></tr>
<tr style="background:#e8e8e8;"><th style="text-align:left">Metric</th><th>Mean</th><th>Median</th><th>Std</th></tr>
{rows}
{bootstrap_row}
</table>"""


def plot_holding_history(
    rebalances_csv: str | Path,
) -> bytes:
    import numpy as np
    import pandas as pd

    df = pd.read_csv(rebalances_csv, parse_dates=["date"])
    df = df[df["exposure"] > 0.001].copy()
    if df.empty:
        fig, ax = plt.subplots(figsize=(12, 2))
        ax.text(0.5, 0.5, "No holdings (always risk-off)", ha="center", va="center",
                transform=ax.transAxes, fontsize=14, color="gray")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()

    all_industries: set[str] = set()
    holdings_matrix: list[tuple[pd.Timestamp, set[str], float]] = []
    for _, row in df.iterrows():
        if pd.isna(row.get("holdings")) or not str(row["holdings"]).strip():
            continue
        parts = str(row["holdings"]).split(";")
        held = set()
        for part in parts:
            if ":" in part:
                ind = part.split(":")[0]
                if ind:
                    held.add(ind)
            elif part.strip():
                held.add(part.strip())
        if held:
            holdings_matrix.append((row["date"], held, float(row["exposure"])))
        all_industries.update(held)

    if not holdings_matrix:
        fig, ax = plt.subplots(figsize=(12, 2))
        ax.text(0.5, 0.5, "No valid holdings data", ha="center", va="center",
                transform=ax.transAxes, fontsize=14, color="gray")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()

    industries = sorted(all_industries)
    n_ind = len(industries)
    n_periods = len(holdings_matrix)

    grid = np.zeros((n_ind, n_periods))
    for j, (_, held, _) in enumerate(holdings_matrix):
        for i, ind in enumerate(industries):
            if ind in held:
                grid[i, j] = 1.0

    date_labels = [d.strftime("%Y-%m-%d") for d, _, _ in holdings_matrix]
    fig_height = max(3, n_ind * 0.4)

    fig, ax = plt.subplots(figsize=(max(12, n_periods * 0.4), fig_height))
    ax.imshow(grid, aspect="auto", cmap=plt.cm.Greens, vmin=0, vmax=1, origin="upper")

    ax.set_yticks(range(n_ind))
    ax.set_yticklabels(industries, fontsize=8)

    tick_step = max(1, n_periods // 15)
    ax.set_xticks(range(n_periods))
    ax.set_xticklabels(date_labels, rotation=45, ha="right", fontsize=7)
    for i in range(n_periods):
        if i % tick_step != 0:
            ax.xaxis.get_ticklabels()[i].set_visible(False)

    for j in range(n_periods):
        for i in range(n_ind):
            if grid[i, j] > 0:
                ax.text(j, i, "■", ha="center", va="center",
                        fontsize=10, color="#1a5631", alpha=0.9)

    ax.set_title("Holding History (green = held)")
    ax.set_xlabel("Rebalance Date")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()

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
