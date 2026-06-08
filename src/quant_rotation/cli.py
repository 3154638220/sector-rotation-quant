from __future__ import annotations

import argparse
from base64 import b64encode
from dataclasses import replace
from datetime import date
from pathlib import Path

from .backtest import run_backtest
from .config import load_config
from .data import (
    align_asset_data,
    align_benchmark,
    filter_benchmark_by_date_range,
    filter_price_data_by_date_range,
    load_benchmark_csv,
    load_stock_industry_map_csv,
    load_wide_asset_csv,
    load_wide_close_csv,
)
from .decomposition import run_factor_decomposition, write_factor_decomposition_reports
from .models import BreadthData
from .real_data import (
    DEFAULT_MARKET_INDICES,
    IndexInfo,
    fetch_and_write_breadth_data,
    fetch_and_write_real_data,
    fetch_and_write_stock_data,
    parse_date,
    sw_level1_universe_names,
)
from .reports import write_reports
from .plot import write_html_report
from .sample_data import generate_sample_data
from .segments import (
    SegmentParameterSweepRuns,
    SegmentBacktestRun,
    stitch_parameter_sweep_segments,
    stitch_backtest_segments,
    write_segmented_backtest_reports,
    write_segmented_parameter_sweep_reports,
    merge_segment_price_data,
    merge_benchmark_closes,
)
from .sweep import run_parameter_sweep, write_parameter_sweep_reports
from .sweep import (
    DEFAULT_FACTOR_SET_NAMES,
    DEFAULT_MARKET_SCORE_THRESHOLDS,
    DEFAULT_RISK_CONTROL_VALUES,
    DEFAULT_RISK_OFF_EXPOSURES,
    DEFAULT_RISK_CONTROL_MODE_VALUES,
    DEFAULT_SOFT_EXPOSURE_MIN_VALUES,
    DEFAULT_SOFTMAX_TEMPERATURES,
    DEFAULT_TOP_K_VALUES,
)
from .validation import (
    DEFAULT_SELECTION_METRIC,
    run_walk_forward_validation,
    run_train_test_validation,
    selected_by_train,
    selected_by_train_with_data,
    write_walk_forward_validation_reports,
    write_train_test_validation_reports,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quant-rotation",
        description="Industry momentum rotation research CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser("sample-data", help="Generate deterministic CSV data")
    sample.add_argument("--output", default="data/sample", help="Output directory")
    sample.add_argument("--days", type=int, default=520, help="Number of business days")
    sample.add_argument("--seed", type=int, default=7, help="Random seed")

    fetch = subparsers.add_parser(
        "fetch-real-data",
        help="Fetch AKShare SW level-1 industry index data",
    )
    fetch.add_argument("--output", default="data/real", help="Output directory")
    fetch.add_argument(
        "--start",
        default="2021-01-01",
        help="Start date, YYYY-MM-DD or YYYYMMDD",
    )
    fetch.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date, YYYY-MM-DD or YYYYMMDD",
    )
    fetch.add_argument(
        "--benchmark",
        default="sh000300",
        help="Benchmark index symbol for AKShare stock_zh_index_daily_tx",
    )
    fetch.add_argument(
        "--request-interval",
        type=float,
        default=0.0,
        help="Seconds to wait between industry index requests",
    )
    fetch.add_argument(
        "--market-indexes",
        default=",".join(
            f"{info.name}:{info.code}" for info in DEFAULT_MARKET_INDICES
        ),
        help=(
            "Comma-separated market index list as NAME:SYMBOL. "
            "Use an empty string to skip market_close.csv."
        ),
    )
    fetch.add_argument(
        "--industry-universe",
        default="current",
        choices=sw_level1_universe_names(),
        help=(
            "Predefined SW level-1 industry universe. Use sw2000 for "
            "1999-2014, sw2014 for 2014-2021, sw2021 for 2021+, or current "
            "to detect the latest universe from AKShare."
        ),
    )
    fetch.add_argument(
        "--industry-indexes",
        default="",
        help=(
            "Optional comma-separated SW industry index list as NAME:CODE. "
            "Overrides --industry-universe when provided."
        ),
    )
    fetch.add_argument(
        "--update-mode",
        default="replace",
        choices=("replace", "append"),
        help=(
            "Update mode. replace overwrites all files; append fetches only "
            "new data after the last date in manifest.json."
        ),
    )

    breadth = subparsers.add_parser(
        "fetch-breadth-data",
        help="Fetch current SW constituent stock data and compute industry breadth",
    )
    breadth.add_argument("--output", default="data/real", help="Output directory")
    breadth.add_argument(
        "--start",
        default="2021-01-01",
        help="Start date, YYYY-MM-DD or YYYYMMDD",
    )
    breadth.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date, YYYY-MM-DD or YYYYMMDD",
    )
    breadth.add_argument(
        "--windows",
        default="20,60",
        help="Comma-separated moving-average windows, e.g. 20,60",
    )
    breadth.add_argument(
        "--min-stocks",
        type=int,
        default=1,
        help="Minimum stocks with enough data required for an industry/date",
    )
    breadth.add_argument(
        "--adjust",
        default="",
        help="AKShare stock_zh_a_hist adjustment: empty, qfq, or hfq",
    )
    breadth.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Calendar days fetched before start for MA warm-up; defaults to max(window)*3",
    )
    breadth.add_argument(
        "--request-interval",
        type=float,
        default=0.0,
        help="Seconds to wait between AKShare requests",
    )
    breadth.add_argument(
        "--constituent-snapshots",
        default=None,
        help=(
            "Historical snapshot CSV with snapshot_date, stock, industry columns. "
            "When provided, breadth is computed with point-in-time constituents."
        ),
    )
    breadth.add_argument(
        "--max-stocks-per-industry",
        type=int,
        default=None,
        help="Optional cap for smoke tests when using historical snapshots",
    )
    breadth.add_argument(
        "--industry-indexes",
        default="",
        help=(
            "Optional comma-separated SW industry index list as NAME:CODE. "
            "Defaults to all detected SW level-1 industries."
        ),
    )
    breadth.add_argument(
        "--update-mode",
        default="replace",
        choices=("replace", "append"),
        help=(
            "Update mode. replace overwrites all files; append fetches only "
            "new data after the last date in breadth_manifest.json."
        ),
    )

    stock = subparsers.add_parser(
        "fetch-stock-data",
        help="Fetch current SW constituent A-share stock data",
    )
    stock.add_argument("--output", default="data/real", help="Output directory")
    stock.add_argument(
        "--start",
        default="2021-01-01",
        help="Start date, YYYY-MM-DD or YYYYMMDD",
    )
    stock.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date, YYYY-MM-DD or YYYYMMDD",
    )
    stock.add_argument(
        "--adjust",
        default="",
        help="AKShare stock_zh_a_hist adjustment: empty, qfq, or hfq",
    )
    stock.add_argument(
        "--max-stocks-per-industry",
        type=int,
        default=None,
        help="Optional cap for smoke tests before fetching full constituent sets",
    )
    stock.add_argument(
        "--request-interval",
        type=float,
        default=0.0,
        help="Seconds to wait between AKShare requests",
    )
    stock.add_argument(
        "--constituent-snapshots",
        default=None,
        help=(
            "Historical snapshot CSV with snapshot_date, stock, industry columns. "
            "When provided, stock data is fetched for the snapshot union."
        ),
    )
    stock.add_argument(
        "--industry-indexes",
        default="",
        help=(
            "Optional comma-separated SW industry index list as NAME:CODE. "
            "Defaults to all detected SW level-1 industries."
        ),
    )
    stock.add_argument(
        "--update-mode",
        default="replace",
        choices=("replace", "append"),
        help=(
            "Update mode. replace overwrites all files; append fetches only "
            "new data after the last date in stock_manifest.json."
        ),
    )

    run = subparsers.add_parser("run", help="Run a backtest")
    run.add_argument("--config", default="configs/default.toml", help="TOML config path")
    run.add_argument("--output-dir", default=None, help="Override report output directory")
    run.add_argument("--start", default=None, help="Start date (YYYY-MM-DD) for data filtering")
    run.add_argument("--end", default=None, help="End date (YYYY-MM-DD) for data filtering")

    run_segments = subparsers.add_parser(
        "run-segments",
        help="Run multiple dated backtest segments and stitch their equity curves",
    )
    run_segments.add_argument(
        "--configs",
        nargs="+",
        required=True,
        help="Ordered segment config paths, e.g. configs/real_sw2000.toml configs/real_sw2014.toml",
    )
    run_segments.add_argument(
        "--output-dir",
        default="reports/segmented_history",
        help="Output directory for stitched segment reports",
    )

    sweep_segments = subparsers.add_parser(
        "sweep-segments",
        help="Run parameter sweeps over dated segments and stitch matching candidates",
    )
    sweep_segments.add_argument(
        "--configs",
        nargs="+",
        required=True,
        help="Ordered segment config paths, e.g. configs/real_sw2000.toml configs/real_sw2014.toml",
    )
    sweep_segments.add_argument(
        "--output-dir",
        default="reports/segmented_parameter_sweep",
        help="Output directory for stitched parameter sweep reports",
    )
    sweep_segments.add_argument(
        "--industry-only",
        action="store_true",
        help="Disable configured stock selection for cleaner industry-factor attribution",
    )
    sweep_segments.add_argument(
        "--top-k",
        default=",".join(str(value) for value in DEFAULT_TOP_K_VALUES),
        help="Comma-separated top_k values, e.g. 5",
    )
    sweep_segments.add_argument(
        "--factor-set",
        default=",".join(DEFAULT_FACTOR_SET_NAMES),
        help="Comma-separated factor sets, e.g. ret60,ret60_ret5",
    )
    sweep_segments.add_argument(
        "--risk-off-exposure",
        default=",".join(str(value) for value in DEFAULT_RISK_OFF_EXPOSURES),
        help="Comma-separated risk-off exposure values, e.g. 0,0.3,0.5",
    )
    sweep_segments.add_argument(
        "--risk-control",
        default=",".join("true" if value else "false" for value in DEFAULT_RISK_CONTROL_VALUES),
        help="Comma-separated risk_control values, e.g. false,true",
    )
    sweep_segments.add_argument(
        "--market-score-control",
        default="auto",
        help=(
            "Comma-separated market_score_control values, e.g. false,true. "
            "Use auto to include true only when market data or benchmark exists."
        ),
    )
    sweep_segments.add_argument(
        "--market-score-threshold",
        default=",".join(str(value) for value in DEFAULT_MARKET_SCORE_THRESHOLDS),
        help=(
            "Comma-separated market score threshold values, e.g. "
            "-0.05,-0.02,0,0.02,0.05. Values only expand candidates where "
            "market_score_control is true."
        ),
    )
    sweep_segments.add_argument(
        "--risk-control-mode",
        default=",".join(DEFAULT_RISK_CONTROL_MODE_VALUES),
        help="Comma-separated risk control modes: hard, soft",
    )
    sweep_segments.add_argument(
        "--soft-exposure-min",
        default=",".join(str(v) for v in DEFAULT_SOFT_EXPOSURE_MIN_VALUES),
        help=(
            "Comma-separated soft exposure min values, e.g. 0.1,0.2,0.3. "
            "Only used when risk-control-mode includes soft."
        ),
    )
    sweep_segments.add_argument(
        "--top-n-equity",
        type=int,
        default=10,
        help="Number of top-ranked stitched equity curves to write",
    )

    decompose = subparsers.add_parser(
        "decompose",
        help="Run factor decomposition backtests",
    )
    decompose.add_argument(
        "--config",
        default="configs/default.toml",
        help="TOML config path",
    )
    decompose.add_argument(
        "--output-dir",
        default=None,
        help="Override factor decomposition report output directory",
    )
    decompose.add_argument(
        "--industry-only",
        action="store_true",
        help="Disable configured stock selection for cleaner industry-factor attribution",
    )

    sweep = subparsers.add_parser(
        "sweep",
        help="Run a small parameter sweep around candidate factor models",
    )
    sweep.add_argument(
        "--config",
        default="configs/default.toml",
        help="TOML config path",
    )
    sweep.add_argument(
        "--output-dir",
        default=None,
        help="Override parameter sweep report output directory",
    )
    sweep.add_argument(
        "--industry-only",
        action="store_true",
        help="Disable configured stock selection for cleaner industry-factor attribution",
    )
    sweep.add_argument(
        "--top-k",
        default=",".join(str(value) for value in DEFAULT_TOP_K_VALUES),
        help="Comma-separated top_k values, e.g. 5",
    )
    sweep.add_argument(
        "--factor-set",
        default=",".join(DEFAULT_FACTOR_SET_NAMES),
        help="Comma-separated factor sets, e.g. ret60,ret60_ret5",
    )
    sweep.add_argument(
        "--risk-off-exposure",
        default=",".join(str(value) for value in DEFAULT_RISK_OFF_EXPOSURES),
        help="Comma-separated risk-off exposure values, e.g. 0,0.3,0.5",
    )
    sweep.add_argument(
        "--risk-control",
        default=",".join("true" if value else "false" for value in DEFAULT_RISK_CONTROL_VALUES),
        help="Comma-separated risk_control values, e.g. false,true",
    )
    sweep.add_argument(
        "--market-score-control",
        default="auto",
        help=(
            "Comma-separated market_score_control values, e.g. false,true. "
            "Use auto to include true only when market data or benchmark exists."
        ),
    )
    sweep.add_argument(
        "--market-score-threshold",
        default=",".join(str(value) for value in DEFAULT_MARKET_SCORE_THRESHOLDS),
        help=(
            "Comma-separated market score threshold values, e.g. "
            "-0.05,-0.02,0,0.02,0.05. Values only expand candidates where "
            "market_score_control is true."
        ),
    )
    sweep.add_argument(
        "--risk-control-mode",
        default=",".join(DEFAULT_RISK_CONTROL_MODE_VALUES),
        help="Comma-separated risk control modes: hard, soft",
    )
    sweep.add_argument(
        "--soft-exposure-min",
        default=",".join(str(v) for v in DEFAULT_SOFT_EXPOSURE_MIN_VALUES),
        help=(
            "Comma-separated soft exposure min values, e.g. 0.1,0.2,0.3. "
            "Only used when risk-control-mode includes soft."
        ),
    )
    sweep.add_argument(
        "--state-aware-risk-control",
        default="false",
        help="Comma-separated state_aware_risk_control values, e.g. false,true",
    )
    sweep.add_argument(
        "--portfolio-mode",
        default="equal",
        help="Comma-separated portfolio_mode values, e.g. equal,softmax,vol_parity",
    )
    sweep.add_argument(
        "--softmax-temperature",
        default="1.0",
        help="Comma-separated softmax_temperature values, e.g. 0.5,0.75,1.0,1.5,2.0",
    )
    sweep.add_argument(
        "--adaptive-top-k",
        default="false",
        help="Comma-separated adaptive_top_k values, e.g. false,true",
    )
    sweep.add_argument(
        "--risk-control-dual-ma",
        default="false",
        help="Comma-separated risk_control_dual_ma values, e.g. false,true",
    )
    sweep.add_argument(
        "--regime-aware-factors",
        default="false",
        help="Comma-separated regime_aware_factors values, e.g. false,true",
    )
    sweep.add_argument(
        "--bull-exposure",
        default="1.0",
        help="Comma-separated bull_exposure values for state_aware, e.g. 1.0",
    )
    sweep.add_argument(
        "--sideways-exposure",
        default="0.5",
        help="Comma-separated sideways_exposure values for state_aware, e.g. 0.5,0.7,0.9",
    )
    sweep.add_argument(
        "--bear-exposure",
        default="0.1",
        help="Comma-separated bear_exposure values for state_aware, e.g. 0.0,0.1,0.2",
    )
    sweep.add_argument(
        "--bull-threshold",
        default="1.5",
        help="Comma-separated bull vote thresholds for state_aware, e.g. 0.5,1.0,1.5",
    )
    sweep.add_argument(
        "--bear-threshold",
        default="0.0",
        help="Comma-separated bear vote thresholds for state_aware, e.g. -1.0,-0.5,0.0",
    )
    sweep.add_argument(
        "--top-n-equity",
        type=int,
        default=10,
        help="Number of top-ranked equity curves to write",
    )

    validate = subparsers.add_parser(
        "validate",
        help="Run train/test or walk-forward validation over candidate factor models",
    )
    validate.add_argument(
        "--config",
        default="configs/default.toml",
        help="TOML config path",
    )
    validate.add_argument(
        "--output-dir",
        default=None,
        help="Override validation report output directory",
    )
    validate.add_argument(
        "--industry-only",
        action="store_true",
        help="Disable configured stock selection for cleaner industry-factor attribution",
    )
    validate.add_argument(
        "--top-k",
        default=",".join(str(value) for value in DEFAULT_TOP_K_VALUES),
        help="Comma-separated top_k values, e.g. 5",
    )
    validate.add_argument(
        "--factor-set",
        default=",".join(DEFAULT_FACTOR_SET_NAMES),
        help="Comma-separated factor sets, e.g. ret60,ret60_ret5",
    )
    validate.add_argument(
        "--risk-off-exposure",
        default=",".join(str(value) for value in DEFAULT_RISK_OFF_EXPOSURES),
        help="Comma-separated risk-off exposure values, e.g. 0,0.3,0.5",
    )
    validate.add_argument(
        "--risk-control",
        default=",".join("true" if value else "false" for value in DEFAULT_RISK_CONTROL_VALUES),
        help="Comma-separated risk_control values, e.g. false,true",
    )
    validate.add_argument(
        "--market-score-control",
        default="auto",
        help=(
            "Comma-separated market_score_control values, e.g. false,true. "
            "Use auto to include true only when market data or benchmark exists."
        ),
    )
    validate.add_argument(
        "--market-score-threshold",
        default=",".join(str(value) for value in DEFAULT_MARKET_SCORE_THRESHOLDS),
        help=(
            "Comma-separated market score threshold values, e.g. "
            "-0.05,-0.02,0,0.02,0.05. Values only expand candidates where "
            "market_score_control is true."
        ),
    )
    validate.add_argument(
        "--risk-control-mode",
        default=",".join(DEFAULT_RISK_CONTROL_MODE_VALUES),
        help="Comma-separated risk control modes: hard, soft",
    )
    validate.add_argument(
        "--soft-exposure-min",
        default=",".join(str(v) for v in DEFAULT_SOFT_EXPOSURE_MIN_VALUES),
        help=(
            "Comma-separated soft exposure min values, e.g. 0.1,0.2,0.3. "
            "Only used when risk-control-mode includes soft."
        ),
    )
    validate.add_argument(
        "--selection-metric",
        default=DEFAULT_SELECTION_METRIC,
        help=(
            "Metric used to rank train folds. Use composite for "
            "excess+Calmar+Sharpe-turnover-drawdown, or a metric column name "
            "such as annualized_return."
        ),
    )
    validate.add_argument(
        "--train-end",
        default=None,
        help="Last train date, YYYY-MM-DD or YYYYMMDD. Defaults to split-ratio.",
    )
    validate.add_argument(
        "--test-start",
        default=None,
        help="First test date, YYYY-MM-DD or YYYYMMDD. Defaults to after train-end.",
    )
    validate.add_argument(
        "--split-ratio",
        type=float,
        default=0.70,
        help="Train ratio used when train/test dates are omitted",
    )
    validate.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run rolling walk-forward multi-fold validation",
    )
    validate.add_argument(
        "--train-window",
        type=int,
        default=504,
        help="Walk-forward train window length in observations",
    )
    validate.add_argument(
        "--test-window",
        type=int,
        default=126,
        help="Walk-forward test window length in observations",
    )
    validate.add_argument(
        "--step",
        type=int,
        default=None,
        help="Walk-forward step length in observations. Defaults to test-window.",
    )
    validate.add_argument(
        "--include-partial-fold",
        action="store_true",
        help="Include a final shorter test fold when enough observations remain",
    )
    validate.add_argument(
        "--portfolio-mode",
        default="equal",
        help="Comma-separated portfolio_mode values, e.g. equal,softmax,vol_parity",
    )
    validate.add_argument(
        "--softmax-temperature",
        default="1.0",
        help="Comma-separated softmax_temperature values, e.g. 0.5,0.75,1.0,1.5,2.0",
    )
    validate_segments = subparsers.add_parser(
        "validate-segments",
        help="Run walk-forward validation over merged segment data",
    )
    validate_segments.add_argument(
        "--configs",
        nargs="+",
        required=True,
        help="Ordered segment config paths, e.g. configs/real_sw2000.toml configs/real_sw2014.toml",
    )
    validate_segments.add_argument(
        "--output-dir",
        default="reports/cross_segment_walk_forward",
        help="Output directory for cross-segment validation reports",
    )
    validate_segments.add_argument(
        "--industry-only",
        action="store_true",
        help="Disable configured stock selection for cleaner industry-factor attribution",
    )
    validate_segments.add_argument(
        "--top-k",
        default=",".join(str(value) for value in DEFAULT_TOP_K_VALUES),
        help="Comma-separated top_k values, e.g. 5",
    )
    validate_segments.add_argument(
        "--factor-set",
        default=",".join(DEFAULT_FACTOR_SET_NAMES),
        help="Comma-separated factor sets, e.g. ret60,ret60_ret5",
    )
    validate_segments.add_argument(
        "--risk-off-exposure",
        default=",".join(str(value) for value in DEFAULT_RISK_OFF_EXPOSURES),
        help="Comma-separated risk-off exposure values, e.g. 0,0.3,0.5",
    )
    validate_segments.add_argument(
        "--risk-control",
        default=",".join("true" if value else "false" for value in DEFAULT_RISK_CONTROL_VALUES),
        help="Comma-separated risk_control values, e.g. false,true",
    )
    validate_segments.add_argument(
        "--market-score-control",
        default="auto",
        help=(
            "Comma-separated market_score_control values, e.g. false,true. "
            "Use auto to include true only when market data or benchmark exists."
        ),
    )
    validate_segments.add_argument(
        "--market-score-threshold",
        default=",".join(str(value) for value in DEFAULT_MARKET_SCORE_THRESHOLDS),
        help=(
            "Comma-separated market score threshold values, e.g. "
            "-0.05,-0.02,0,0.02,0.05. Values only expand candidates where "
            "market_score_control is true."
        ),
    )
    validate_segments.add_argument(
        "--risk-control-mode",
        default=",".join(DEFAULT_RISK_CONTROL_MODE_VALUES),
        help="Comma-separated risk control modes: hard, soft",
    )
    validate_segments.add_argument(
        "--soft-exposure-min",
        default=",".join(str(v) for v in DEFAULT_SOFT_EXPOSURE_MIN_VALUES),
        help=(
            "Comma-separated soft exposure min values, e.g. 0.1,0.2,0.3. "
            "Only used when risk-control-mode includes soft."
        ),
    )
    validate_segments.add_argument(
        "--selection-metric",
        default=DEFAULT_SELECTION_METRIC,
        help=(
            "Metric used to rank train folds. Use composite for "
            "excess+Calmar+Sharpe-turnover-drawdown, or a metric column name "
            "such as annualized_return."
        ),
    )
    validate_segments.add_argument(
        "--walk-forward",
        action="store_true",
        default=True,
        help="Run rolling walk-forward multi-fold validation (always on for this command)",
    )
    validate_segments.add_argument(
        "--train-window",
        type=int,
        default=504,
        help="Walk-forward train window length in observations",
    )
    validate_segments.add_argument(
        "--test-window",
        type=int,
        default=126,
        help="Walk-forward test window length in observations",
    )
    validate_segments.add_argument(
        "--step",
        type=int,
        default=None,
        help="Walk-forward step length in observations. Defaults to test-window.",
    )
    validate_segments.add_argument(
        "--include-partial-fold",
        action="store_true",
        help="Include a final shorter test fold when enough observations remain",
    )
    validate_segments.add_argument(
        "--portfolio-mode",
        default="equal",
        help="Comma-separated portfolio_mode values, e.g. equal,softmax,vol_parity",
    )
    validate_segments.add_argument(
        "--softmax-temperature",
        default="1.0",
        help="Comma-separated softmax_temperature values, e.g. 0.5,0.75,1.0,1.5,2.0",
    )
    validate_segments.add_argument(
        "--purged-gap",
        type=int,
        default=0,
        help="Number of days to purge between train and test windows (0 = no purge)",
    )
    validate_segments.add_argument(
        "--config-override",
        default=None,
        help="Path to a TOML config that overrides the base strategy (fixes params, no sweep)",
    )

    plot_cmd = subparsers.add_parser(
        "plot",
        help="Generate HTML report with charts from backtest output",
    )
    plot_cmd.add_argument(
        "--report-dir",
        default="reports/production",
        help="Directory containing backtest output CSVs",
    )
    plot_cmd.add_argument(
        "--output",
        default=None,
        help="Output directory for HTML report. Defaults to report-dir.",
    )
    plot_cmd.add_argument(
        "--wf-dir",
        default=None,
        help="Explicit path to walk-forward output directory "
        "(default: probe report-dir and common subdirectories)",
    )

    signal = subparsers.add_parser(
        "signal",
        help="Generate next rebalance signal JSON",
    )
    signal.add_argument("--config", required=True, help="TOML config path")
    signal.add_argument(
        "--output", default=None, help="Output JSON path (default: reports/signals/signal_<date>.json)"
    )

    compute_pros = subparsers.add_parser(
        "compute-prosperity",
        help="Compute prosperity proxy from amount data (z-score)",
    )
    compute_pros.add_argument("--amount-csv", required=True,
                             help="Path to industry_amount.csv")
    compute_pros.add_argument("--output", required=True,
                             help="Output CSV path for industry_prosperity.csv")
    compute_pros.add_argument("--window", type=int, default=60,
                             help="Rolling window for z-score (default: 60)")
    compute_pros.add_argument("--release-lag-days", type=int, default=1,
                             help="Days after source date before the signal is usable")
    compute_pros.add_argument("--metadata-output", default=None,
                             help="Output JSON metadata path (default: sibling manifest)")

    compute_val = subparsers.add_parser(
        "compute-valuation",
        help="Compute valuation proxy from industry close data (price percentile)",
    )
    compute_val.add_argument("--close-csv", required=True,
                            help="Path to industry_close.csv")
    compute_val.add_argument("--output", required=True,
                            help="Output CSV path for industry_valuation.csv")
    compute_val.add_argument("--window", type=int, default=252,
                            help="Rolling window for percentile (default: 252)")

    hist_const = subparsers.add_parser(
        "fetch-historical-constituents",
        help="Fetch, convert, or import historical SW constituent snapshots",
    )
    hist_const.add_argument(
        "--source",
        default="csv-snapshots",
        choices=("csv-snapshots", "csv-intervals", "sws", "tushare", "joinquant"),
        help=(
            "Source type. csv-snapshots validates/imports ready snapshots; "
            "csv-intervals expands stock/industry start/end intervals; sws, "
            "tushare, and joinquant fetch external sources."
        ),
    )
    hist_const.add_argument(
        "--input",
        default=None,
        help=(
            "Input CSV. For csv-snapshots: snapshot_date, stock, industry. "
            "For csv-intervals: stock, industry, start_date/in_date, end_date/out_date."
        ),
    )
    hist_const.add_argument("--output", required=True,
                           help="Target path for validated snapshot CSV")
    hist_const.add_argument("--start", default=None,
                           help="Snapshot start date, YYYY-MM-DD or YYYYMMDD")
    hist_const.add_argument("--end", default=None,
                           help="Snapshot end date, YYYY-MM-DD or YYYYMMDD")
    hist_const.add_argument(
        "--snapshot-frequency",
        default="event",
        choices=("event", "daily", "month-end", "quarter-end"),
        help="Snapshot dates when expanding interval sources",
    )
    hist_const.add_argument(
        "--industries",
        default="",
        help="Optional comma-separated industry names for SWS",
    )
    hist_const.add_argument(
        "--request-interval",
        type=float,
        default=0.0,
        help="Seconds to wait between external source requests",
    )
    hist_const.add_argument(
        "--no-ssl-verify",
        action="store_true",
        help="Disable SSL certificate verification for SWS download probing",
    )
    hist_const.add_argument("--tushare-token", default=None,
                           help="Tushare token (default: TUSHARE_TOKEN or TS_TOKEN)")
    hist_const.add_argument("--tushare-src", default="SW2021",
                           help="Tushare SW source, e.g. SW2021")
    hist_const.add_argument("--jq-user", default=None,
                           help="JoinQuant username (default: JQDATA_USER)")
    hist_const.add_argument("--jq-password", default=None,
                           help="JoinQuant password (default: JQDATA_PASSWORD)")
    hist_const.add_argument("--overwrite", action="store_true",
                           help="Overwrite existing target file")
    hist_const.add_argument("--validate-only", action="store_true",
                           help="Only validate the input CSV without copying")

    align_sse = subparsers.add_parser(
        "align-sse-benchmark",
        help="Fetch SSE Composite Index and align to existing equity curve",
    )
    align_sse.add_argument("--report-dir", required=True,
                          help="Directory containing equity_curve.csv")
    align_sse.add_argument("--output", default=None,
                          help="Output CSV path (default: <report-dir>/sse_composite.csv)")

    combine = subparsers.add_parser(
        "combine",
        help="Combine multiple strategy equity curves into a weighted aggregate",
    )
    combine.add_argument(
        "--equity-paths",
        nargs="+",
        required=True,
        help="Paths to equity_curve.csv files from multiple backtests",
    )
    combine.add_argument(
        "--weights",
        nargs="+",
        type=float,
        required=True,
        help="Weights for each strategy (must match number of equity-paths)",
    )
    combine.add_argument(
        "--output",
        default="reports/combined/combined_equity.csv",
        help="Output path for combined equity curve",
    )
    return parser


def _load_inputs(config_path: str):
    app_config = load_config(config_path)
    industry_data = load_wide_close_csv(app_config.industry_close_path)
    amount_data = None
    if app_config.industry_amount_path:
        raw_amount_data = load_wide_asset_csv(
            app_config.industry_amount_path,
            value_name="amount",
        )
        amount_data = align_asset_data(
            industry_data.dates,
            industry_data.assets,
            raw_amount_data,
            value_name="amount",
        )
    breadth20_data = None
    if app_config.industry_breadth20_path:
        raw_breadth20_data = load_wide_asset_csv(
            app_config.industry_breadth20_path,
            value_name="breadth20",
        )
        breadth20_data = align_asset_data(
            industry_data.dates,
            industry_data.assets,
            raw_breadth20_data,
            value_name="breadth20",
        )
    breadth60_data = None
    if app_config.industry_breadth60_path:
        raw_breadth60_data = load_wide_asset_csv(
            app_config.industry_breadth60_path,
            value_name="breadth60",
        )
        breadth60_data = align_asset_data(
            industry_data.dates,
            industry_data.assets,
            raw_breadth60_data,
            value_name="breadth60",
        )
    breadth_data = BreadthData(breadth20=breadth20_data, breadth60=breadth60_data)
    valuation_data = None
    if app_config.industry_valuation_path:
        raw_valuation_data = load_wide_asset_csv(
            app_config.industry_valuation_path,
            value_name="valuation",
        )
        valuation_data = align_asset_data(
            industry_data.dates,
            industry_data.assets,
            raw_valuation_data,
            value_name="valuation",
        )
    prosperity_data = None
    if app_config.industry_prosperity_path:
        raw_prosperity_data = load_wide_asset_csv(
            app_config.industry_prosperity_path,
            value_name="prosperity",
        )
        prosperity_data = align_asset_data(
            industry_data.dates,
            industry_data.assets,
            raw_prosperity_data,
            value_name="prosperity",
        )
    market_data = None
    if app_config.market_close_path:
        raw_market_data = load_wide_close_csv(app_config.market_close_path)
        market_data = align_asset_data(
            industry_data.dates,
            raw_market_data.assets,
            raw_market_data,
            value_name="market close",
        )
    stock_data = None
    if app_config.stock_close_path:
        raw_stock_data = load_wide_close_csv(app_config.stock_close_path)
        stock_data = align_asset_data(
            industry_data.dates,
            raw_stock_data.assets,
            raw_stock_data,
            value_name="stock close",
        )
    stock_amount_data = None
    if app_config.stock_amount_path:
        raw_stock_amount_data = load_wide_asset_csv(
            app_config.stock_amount_path,
            value_name="stock amount",
        )
        stock_amount_data = align_asset_data(
            industry_data.dates,
            raw_stock_amount_data.assets,
            raw_stock_amount_data,
            value_name="stock amount",
        )
    stock_industry_map = (
        load_stock_industry_map_csv(app_config.stock_industry_map_path)
        if app_config.stock_industry_map_path
        else None
    )
    benchmark_closes = None
    if app_config.benchmark_close_path:
        benchmark_dates, raw_benchmark = load_benchmark_csv(app_config.benchmark_close_path)
        benchmark_closes = align_benchmark(industry_data.dates, benchmark_dates, raw_benchmark)
    return (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
        valuation_data,
        prosperity_data,
        market_data,
        stock_data,
        stock_amount_data,
        stock_industry_map,
        benchmark_closes,
    )


def run_command(args: argparse.Namespace) -> int:
    (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
        valuation_data,
        prosperity_data,
        market_data,
        stock_data,
        stock_amount_data,
        stock_industry_map,
        benchmark_closes,
    ) = _load_inputs(args.config)

    start_date = date.fromisoformat(args.start) if getattr(args, "start", None) else None
    end_date = date.fromisoformat(args.end) if getattr(args, "end", None) else None
    if start_date or end_date:
        orig_dates = list(industry_data.dates)
        industry_data = filter_price_data_by_date_range(industry_data, start_date, end_date)
        keep_indices = {i for i, d in enumerate(orig_dates) if d in industry_data.dates}
        if amount_data is not None:
            amount_data = filter_price_data_by_date_range(amount_data, start_date, end_date)
        if breadth_data is not None:
            breadth_data = BreadthData(
                breadth20=filter_price_data_by_date_range(breadth_data.breadth20, start_date, end_date) if breadth_data.breadth20 else None,
                breadth60=filter_price_data_by_date_range(breadth_data.breadth60, start_date, end_date) if breadth_data.breadth60 else None,
            )
        if valuation_data is not None:
            valuation_data = filter_price_data_by_date_range(valuation_data, start_date, end_date)
        if prosperity_data is not None:
            prosperity_data = filter_price_data_by_date_range(prosperity_data, start_date, end_date)
        if market_data is not None:
            market_data = filter_price_data_by_date_range(market_data, start_date, end_date)
        if stock_data is not None:
            stock_data = filter_price_data_by_date_range(stock_data, start_date, end_date)
            if stock_amount_data is not None:
                stock_amount_data = filter_price_data_by_date_range(stock_amount_data, start_date, end_date)
        if benchmark_closes is not None:
            benchmark_closes = [c for i, c in enumerate(benchmark_closes) if i in keep_indices]

    result = run_backtest(
        industry_data,
        benchmark_closes,
        app_config.strategy,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        market_data=market_data,
        market_weights=app_config.market_weights,
        stock_data=stock_data,
        stock_amount_data=stock_amount_data,
        stock_industry_map=stock_industry_map,
    )
    output_dir = args.output_dir or app_config.output_dir
    write_reports(result, output_dir)

    print(f"Backtest complete. Reports written to: {Path(output_dir).resolve()}")
    print(f"Final equity: {result.metrics['final_equity']:.4f}")
    print(f"Annualized return: {result.metrics['annualized_return']:.2%}")
    print(f"Max drawdown: {result.metrics['max_drawdown']:.2%}")
    print(f"Sharpe ratio: {result.metrics['sharpe_ratio']:.2f}")
    print(f"Rebalances: {len(result.rebalances)}")
    return 0


def run_segments_command(args: argparse.Namespace) -> int:
    segments: list[SegmentBacktestRun] = []
    for config_path in args.configs:
        (
            app_config,
            industry_data,
            amount_data,
            breadth_data,
            valuation_data,
            prosperity_data,
            market_data,
            stock_data,
            stock_amount_data,
            stock_industry_map,
            benchmark_closes,
        ) = _load_inputs(config_path)
        result = run_backtest(
            industry_data,
            benchmark_closes,
            app_config.strategy,
            amount_data=amount_data,
            breadth_data=breadth_data,
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
            market_data=market_data,
            market_weights=app_config.market_weights,
            stock_data=stock_data,
            stock_amount_data=stock_amount_data,
            stock_industry_map=stock_industry_map,
        )
        segments.append(
            SegmentBacktestRun(
                name=Path(config_path).stem,
                result=result,
                industries=len(industry_data.assets),
            )
        )

    segmented_result = stitch_backtest_segments(segments)
    write_segmented_backtest_reports(segmented_result, args.output_dir)

    print(
        "Segmented backtest complete. "
        f"Reports written to: {Path(args.output_dir).resolve()}"
    )
    print(f"Segments: {len(segments)}")
    print(
        "Date range: "
        f"{segmented_result.stitched.dates[0].isoformat()} to "
        f"{segmented_result.stitched.dates[-1].isoformat()}"
    )
    print(f"Final equity: {segmented_result.stitched.metrics['final_equity']:.4f}")
    print(
        "Annualized return: "
        f"{segmented_result.stitched.metrics['annualized_return']:.2%}"
    )
    print(f"Max drawdown: {segmented_result.stitched.metrics['max_drawdown']:.2%}")
    print(f"Sharpe ratio: {segmented_result.stitched.metrics['sharpe_ratio']:.2f}")
    return 0


def sweep_segments_command(args: argparse.Namespace) -> int:
    top_k_values = _parse_int_tuple(args.top_k, "--top-k")
    factor_set_names = _parse_str_tuple(args.factor_set, "--factor-set")
    risk_off_exposures = _parse_float_tuple(
        args.risk_off_exposure,
        "--risk-off-exposure",
    )
    risk_control_values = _parse_bool_tuple(args.risk_control, "--risk-control")
    market_score_control_values = _parse_bool_tuple_or_auto(
        args.market_score_control,
        "--market-score-control",
    )
    market_score_threshold_values = _parse_float_tuple(
        args.market_score_threshold,
        "--market-score-threshold",
    )
    risk_control_mode_values = _parse_str_tuple(
        args.risk_control_mode,
        "--risk-control-mode",
    )
    soft_exposure_min_values = _parse_float_tuple(
        args.soft_exposure_min,
        "--soft-exposure-min",
    )

    segments: list[SegmentParameterSweepRuns] = []
    for config_path in args.configs:
        (
            app_config,
            industry_data,
            amount_data,
            breadth_data,
            valuation_data,
            prosperity_data,
            market_data,
            stock_data,
            stock_amount_data,
            stock_industry_map,
            benchmark_closes,
        ) = _load_inputs(config_path)
        strategy = app_config.strategy
        if args.industry_only:
            strategy = replace(
                strategy,
                stock_selection=replace(strategy.stock_selection, enabled=False),
            )
            stock_data = None
            stock_amount_data = None
            stock_industry_map = None

        runs = run_parameter_sweep(
            industry_data,
            benchmark_closes,
            strategy,
            amount_data=amount_data,
            breadth_data=breadth_data,
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
            market_data=market_data,
            market_weights=app_config.market_weights,
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
        segments.append(
            SegmentParameterSweepRuns(
                name=Path(config_path).stem,
                industries=len(industry_data.assets),
                runs=runs,
            )
        )

    stitched_runs = stitch_parameter_sweep_segments(segments)
    write_segmented_parameter_sweep_reports(
        stitched_runs,
        args.output_dir,
        top_n_equity=args.top_n_equity,
    )

    best = max(
        stitched_runs,
        key=lambda run: run.run.result.metrics["annualized_return"],
    )
    print(
        "Segmented parameter sweep complete. "
        f"Reports written to: {Path(args.output_dir).resolve()}"
    )
    print(f"Segments: {len(segments)}")
    print(f"Runs: {len(stitched_runs)}")
    print(f"Best: {best.run.spec.name}")
    print(
        "Best annualized return: "
        f"{best.run.result.metrics['annualized_return']:.2%}"
    )
    print(f"Best max drawdown: {best.run.result.metrics['max_drawdown']:.2%}")
    print(f"Best Sharpe ratio: {best.run.result.metrics['sharpe_ratio']:.2f}")
    return 0


def decompose_command(args: argparse.Namespace) -> int:
    (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
        valuation_data,
        prosperity_data,
        market_data,
        stock_data,
        stock_amount_data,
        stock_industry_map,
        benchmark_closes,
    ) = _load_inputs(args.config)
    strategy = app_config.strategy
    if args.industry_only:
        strategy = replace(
            strategy,
            stock_selection=replace(strategy.stock_selection, enabled=False),
        )
        stock_data = None
        stock_amount_data = None
        stock_industry_map = None

    runs = run_factor_decomposition(
        industry_data,
        benchmark_closes,
        strategy,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        market_data=market_data,
        market_weights=app_config.market_weights,
        stock_data=stock_data,
        stock_amount_data=stock_amount_data,
        stock_industry_map=stock_industry_map,
    )
    output_dir = args.output_dir or str(Path(app_config.output_dir) / "factor_decomposition")
    write_factor_decomposition_reports(runs, output_dir)

    best = max(runs, key=lambda run: run.result.metrics["annualized_return"])
    print(f"Factor decomposition complete. Reports written to: {Path(output_dir).resolve()}")
    print(f"Runs: {len(runs)}")
    print(
        "Best annualized return: "
        f"{best.spec.name} ({best.result.metrics['annualized_return']:.2%})"
    )
    print(f"Best final equity: {best.result.metrics['final_equity']:.4f}")
    return 0


def _parse_int_tuple(value: str, name: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a comma-separated list of integers") from exc
    if not result:
        raise ValueError(f"{name} must contain at least one value")
    return result


def _parse_str_tuple(value: str, name: str) -> tuple[str, ...]:
    result = tuple(item.strip() for item in value.split(",") if item.strip())
    if not result:
        raise ValueError(f"{name} must contain at least one value")
    return result


def _parse_bool_tuple(value: str, name: str) -> tuple[bool, ...]:
    true_values = {"1", "true", "t", "yes", "y", "on"}
    false_values = {"0", "false", "f", "no", "n", "off"}
    result: list[bool] = []
    for item in value.split(","):
        normalized = item.strip().lower()
        if not normalized:
            continue
        if normalized in true_values:
            result.append(True)
        elif normalized in false_values:
            result.append(False)
        else:
            raise ValueError(
                f"{name} must be a comma-separated list of booleans"
            )
    if not result:
        raise ValueError(f"{name} must contain at least one value")
    return tuple(result)


def _parse_bool_tuple_or_auto(value: str, name: str) -> tuple[bool, ...] | None:
    if value.strip().lower() == "auto":
        return None
    return _parse_bool_tuple(value, name)


def _parse_float_tuple(value: str, name: str) -> tuple[float, ...]:
    try:
        result = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a comma-separated list of numbers") from exc
    if not result:
        raise ValueError(f"{name} must contain at least one value")
    return result


def _parse_index_info_list(value: str, option_name: str) -> list[IndexInfo]:
    indexes: list[IndexInfo] = []
    raw = value.strip()
    if not raw:
        return indexes
    for item in raw.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        if ":" not in normalized:
            raise ValueError(
                f"{option_name} entries must use NAME:SYMBOL, "
                f"got {normalized!r}"
            )
        name, symbol = (part.strip() for part in normalized.split(":", 1))
        if not name or not symbol:
            raise ValueError(
                f"{option_name} entries must include both NAME and SYMBOL"
            )
        indexes.append(IndexInfo(symbol, name))
    if not indexes:
        raise ValueError(f"{option_name} must contain at least one valid entry")
    return indexes


def _parse_market_index_list(value: str) -> list[IndexInfo]:
    return _parse_index_info_list(value, "--market-indexes")


def _parse_industry_index_list(value: str) -> list[IndexInfo]:
    return _parse_index_info_list(value, "--industry-indexes")


def sweep_command(args: argparse.Namespace) -> int:
    (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
        valuation_data,
        prosperity_data,
        market_data,
        stock_data,
        stock_amount_data,
        stock_industry_map,
        benchmark_closes,
    ) = _load_inputs(args.config)
    strategy = app_config.strategy
    if args.industry_only:
        strategy = replace(
            strategy,
            stock_selection=replace(strategy.stock_selection, enabled=False),
        )
        stock_data = None
        stock_amount_data = None
        stock_industry_map = None

    top_k_values = _parse_int_tuple(args.top_k, "--top-k")
    factor_set_names = _parse_str_tuple(args.factor_set, "--factor-set")
    risk_off_exposures = _parse_float_tuple(
        args.risk_off_exposure,
        "--risk-off-exposure",
    )
    risk_control_values = _parse_bool_tuple(args.risk_control, "--risk-control")
    market_score_control_values = _parse_bool_tuple_or_auto(
        args.market_score_control,
        "--market-score-control",
    )
    market_score_threshold_values = _parse_float_tuple(
        args.market_score_threshold,
        "--market-score-threshold",
    )
    risk_control_mode_values = _parse_str_tuple(
        args.risk_control_mode,
        "--risk-control-mode",
    )
    soft_exposure_min_values = _parse_float_tuple(
        args.soft_exposure_min,
        "--soft-exposure-min",
    )
    state_aware_risk_control_values = _parse_bool_tuple(
        args.state_aware_risk_control,
        "--state-aware-risk-control",
    )
    portfolio_mode_values = _parse_str_tuple(
        args.portfolio_mode,
        "--portfolio-mode",
    )
    softmax_temperature_values = _parse_float_tuple(
        args.softmax_temperature,
        "--softmax-temperature",
    )
    adaptive_top_k_values = _parse_bool_tuple(
        args.adaptive_top_k,
        "--adaptive-top-k",
    )
    risk_control_dual_ma_values = _parse_bool_tuple(
        args.risk_control_dual_ma,
        "--risk-control-dual-ma",
    )
    regime_aware_factors_values = _parse_bool_tuple(
        args.regime_aware_factors,
        "--regime-aware-factors",
    )
    bull_exposures = _parse_float_tuple(
        args.bull_exposure,
        "--bull-exposure",
    )
    sideways_exposures = _parse_float_tuple(
        args.sideways_exposure,
        "--sideways-exposure",
    )
    bear_exposures = _parse_float_tuple(
        args.bear_exposure,
        "--bear-exposure",
    )
    bull_thresholds = _parse_float_tuple(
        args.bull_threshold,
        "--bull-threshold",
    )
    bear_thresholds = _parse_float_tuple(
        args.bear_threshold,
        "--bear-threshold",
    )
    runs = run_parameter_sweep(
        industry_data,
        benchmark_closes,
        strategy,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        market_data=market_data,
        market_weights=app_config.market_weights,
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
        state_aware_risk_control_values=state_aware_risk_control_values,
        portfolio_mode_values=portfolio_mode_values,
        softmax_temperature_values=softmax_temperature_values,
        adaptive_top_k_values=adaptive_top_k_values,
        risk_control_dual_ma_values=risk_control_dual_ma_values,
        regime_aware_factors_values=regime_aware_factors_values,
        bull_exposures=bull_exposures,
        sideways_exposures=sideways_exposures,
        bear_exposures=bear_exposures,
        bull_thresholds=bull_thresholds,
        bear_thresholds=bear_thresholds,
    )
    output_dir = args.output_dir or str(Path(app_config.output_dir) / "parameter_sweep")
    write_parameter_sweep_reports(
        runs,
        output_dir,
        top_n_equity=args.top_n_equity,
    )

    best = max(runs, key=lambda run: run.result.metrics["annualized_return"])
    print(f"Parameter sweep complete. Reports written to: {Path(output_dir).resolve()}")
    print(f"Runs: {len(runs)}")
    print(f"Best: {best.spec.name}")
    print(f"Best annualized return: {best.result.metrics['annualized_return']:.2%}")
    print(f"Best max drawdown: {best.result.metrics['max_drawdown']:.2%}")
    print(f"Best Sharpe ratio: {best.result.metrics['sharpe_ratio']:.2f}")
    return 0


def validate_command(args: argparse.Namespace) -> int:
    (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
        valuation_data,
        prosperity_data,
        market_data,
        stock_data,
        stock_amount_data,
        stock_industry_map,
        benchmark_closes,
    ) = _load_inputs(args.config)
    strategy = app_config.strategy
    if args.industry_only:
        strategy = replace(
            strategy,
            stock_selection=replace(strategy.stock_selection, enabled=False),
        )
        stock_data = None
        stock_amount_data = None
        stock_industry_map = None

    top_k_values = _parse_int_tuple(args.top_k, "--top-k")
    factor_set_names = _parse_str_tuple(args.factor_set, "--factor-set")
    risk_off_exposures = _parse_float_tuple(
        args.risk_off_exposure,
        "--risk-off-exposure",
    )
    risk_control_values = _parse_bool_tuple(args.risk_control, "--risk-control")
    market_score_control_values = _parse_bool_tuple_or_auto(
        args.market_score_control,
        "--market-score-control",
    )
    market_score_threshold_values = _parse_float_tuple(
        args.market_score_threshold,
        "--market-score-threshold",
    )
    risk_control_mode_values = _parse_str_tuple(
        args.risk_control_mode,
        "--risk-control-mode",
    )
    soft_exposure_min_values = _parse_float_tuple(
        args.soft_exposure_min,
        "--soft-exposure-min",
    )
    portfolio_mode_values = _parse_str_tuple(
        args.portfolio_mode,
        "--portfolio-mode",
    )
    softmax_temperature_values = _parse_float_tuple(
        args.softmax_temperature,
        "--softmax-temperature",
    )
    if args.walk_forward:
        folds = run_walk_forward_validation(
            industry_data,
            benchmark_closes,
            strategy,
            amount_data=amount_data,
            breadth_data=breadth_data,
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
            market_data=market_data,
            market_weights=app_config.market_weights,
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
            portfolio_mode_values=portfolio_mode_values,
            softmax_temperature_values=softmax_temperature_values,
            train_window=args.train_window,
            test_window=args.test_window,
            step=args.step,
            include_partial_fold=args.include_partial_fold,
        )
        output_dir = args.output_dir or str(Path(app_config.output_dir) / "walk_forward")
        write_walk_forward_validation_reports(
            folds,
            output_dir,
            selection_metric=args.selection_metric,
        )

        selected_runs = [
            selected_by_train_with_data(fold.runs, args.selection_metric) for fold in folds
        ]
        selection_counts: dict[str, int] = {}
        for selected in selected_runs:
            name = selected.sweep_run.spec.name
            selection_counts[name] = selection_counts.get(name, 0) + 1
        most_selected, most_selected_count = sorted(
            selection_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0]
        mean_test_return = sum(
            run.test_metrics["annualized_return"] for run in selected_runs
        ) / len(selected_runs)
        mean_test_drawdown = sum(
            run.test_metrics["max_drawdown"] for run in selected_runs
        ) / len(selected_runs)
        step = args.step if args.step is not None else args.test_window
        print(
            "Walk-forward validation complete. "
            f"Reports written to: {Path(output_dir).resolve()}"
        )
        print(
            "Folds: "
            f"{len(folds)} "
            f"(train_window={args.train_window}, test_window={args.test_window}, "
            f"step={step})"
        )
        print(
            "Date range: "
            f"{folds[0].split.train_start.isoformat()} to "
            f"{folds[-1].split.test_end.isoformat()}"
        )
        print(
            "Most selected: "
            f"{most_selected} ({most_selected_count}/{len(folds)} folds)"
        )
        print(f"Selection metric: {args.selection_metric}")
        print(f"Mean test annualized return: {mean_test_return:.2%}")
        print(f"Mean test max drawdown: {mean_test_drawdown:.2%}")
        return 0

    train_end = parse_date(args.train_end) if args.train_end else None
    test_start = parse_date(args.test_start) if args.test_start else None
    runs = run_train_test_validation(
        industry_data,
        benchmark_closes,
        strategy,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        market_data=market_data,
        market_weights=app_config.market_weights,
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
        portfolio_mode_values=portfolio_mode_values,
        softmax_temperature_values=softmax_temperature_values,
        train_end=train_end,
        test_start=test_start,
        split_ratio=args.split_ratio,
    )
    output_dir = args.output_dir or str(Path(app_config.output_dir) / "validation")
    write_train_test_validation_reports(
        runs,
        output_dir,
        selection_metric=args.selection_metric,
    )

    selected = selected_by_train_with_data(runs, args.selection_metric)
    spec = selected.sweep_run.spec
    print(f"Train/test validation complete. Reports written to: {Path(output_dir).resolve()}")
    print(
        "Split: "
        f"{selected.split.train_start.isoformat()} to {selected.split.train_end.isoformat()} "
        f"train, {selected.split.test_start.isoformat()} to "
        f"{selected.split.test_end.isoformat()} test"
    )
    print(f"Selected by train ({args.selection_metric}): {spec.name}")
    print(f"Train annualized return: {selected.train_metrics['annualized_return']:.2%}")
    print(f"Test annualized return: {selected.test_metrics['annualized_return']:.2%}")
    print(f"Test max drawdown: {selected.test_metrics['max_drawdown']:.2%}")
    print(f"Test Sharpe ratio: {selected.test_metrics['sharpe_ratio']:.2f}")
    return 0


def validate_segments_command(args: argparse.Namespace) -> int:
    segment_price_data: list[tuple] = []
    segment_benchmark_data: list[tuple] = []

    base_strategy = None
    market_weights = {}

    for config_path in args.configs:
        app_config = load_config(config_path)
        industry_data = load_wide_close_csv(app_config.industry_close_path)
        benchmark_dates, benchmark_closes_raw = (
            load_benchmark_csv(app_config.benchmark_close_path)
            if app_config.benchmark_close_path
            else (None, None)
        )

        segment_price_data.append((industry_data, Path(config_path).stem))
        segment_benchmark_data.append(
            (benchmark_dates, benchmark_closes_raw, Path(config_path).stem)
        )

        if base_strategy is None:
            base_strategy = app_config.strategy
            market_weights = app_config.market_weights

    if base_strategy is None:
        raise ValueError("At least one config is required")

    strategy = base_strategy
    if args.industry_only:
        strategy = replace(
            strategy,
            stock_selection=replace(strategy.stock_selection, enabled=False),
        )
    if args.config_override:
        import tomllib as _toml
        with open(args.config_override, "rb") as _fh:
            _override_raw = _toml.load(_fh)
        _override_strategy = _override_raw.get("strategy", {})
        strategy = replace(
            strategy,
            rebalance_every=int(_override_strategy.get("rebalance_every", strategy.rebalance_every)),
            top_k=int(_override_strategy.get("top_k", strategy.top_k)),
            max_industry_weight=float(_override_strategy.get("max_industry_weight", strategy.max_industry_weight)),
            transaction_cost=float(_override_strategy.get("transaction_cost", strategy.transaction_cost)),
            risk_control=bool(_override_strategy.get("risk_control", strategy.risk_control)),
            market_ma_window=int(_override_strategy.get("market_ma_window", strategy.market_ma_window)),
            market_score_control=bool(_override_strategy.get("market_score_control", strategy.market_score_control)),
            market_score_window=int(_override_strategy.get("market_score_window", strategy.market_score_window)),
            market_score_threshold=float(_override_strategy.get("market_score_threshold", strategy.market_score_threshold)),
            risk_off_exposure=float(_override_strategy.get("risk_off_exposure", strategy.risk_off_exposure)),
            portfolio_mode=str(_override_strategy.get("portfolio_mode", strategy.portfolio_mode)),
            softmax_temperature=float(_override_strategy.get("softmax_temperature", strategy.softmax_temperature)),
            cluster_constraint=bool(_override_strategy.get("cluster_constraint", strategy.cluster_constraint)),
            max_per_cluster=int(_override_strategy.get("max_per_cluster", strategy.max_per_cluster)),
            market_state_mode=str(_override_strategy.get("market_state_mode", strategy.market_state_mode)),
            three_state_strong_exposure=float(_override_strategy.get("three_state_strong_exposure", strategy.three_state_strong_exposure)),
            three_state_neutral_exposure=float(_override_strategy.get("three_state_neutral_exposure", strategy.three_state_neutral_exposure)),
            three_state_weak_exposure=float(_override_strategy.get("three_state_weak_exposure", strategy.three_state_weak_exposure)),
            three_state_trend_weight=float(_override_strategy.get("three_state_trend_weight", strategy.three_state_trend_weight)),
            three_state_dispersion_weight=float(_override_strategy.get("three_state_dispersion_weight", strategy.three_state_dispersion_weight)),
            three_state_momentum_weight=float(_override_strategy.get("three_state_momentum_weight", strategy.three_state_momentum_weight)),
            three_state_breadth_weight=float(_override_strategy.get("three_state_breadth_weight", strategy.three_state_breadth_weight)),
            three_state_strong_threshold=float(_override_strategy.get("three_state_strong_threshold", strategy.three_state_strong_threshold)),
            three_state_weak_threshold=float(_override_strategy.get("three_state_weak_threshold", strategy.three_state_weak_threshold)),
            dynamic_top_k=bool(_override_strategy.get("dynamic_top_k", strategy.dynamic_top_k)),
            dynamic_top_k_min=int(_override_strategy.get("dynamic_top_k_min", strategy.dynamic_top_k_min)),
            dynamic_top_k_max=int(_override_strategy.get("dynamic_top_k_max", strategy.dynamic_top_k_max)),
            dynamic_top_k_disp_low=float(_override_strategy.get("dynamic_top_k_disp_low", strategy.dynamic_top_k_disp_low)),
            dynamic_top_k_disp_high=float(_override_strategy.get("dynamic_top_k_disp_high", strategy.dynamic_top_k_disp_high)),
            turnover_budget=float(_override_strategy["turnover_budget"]) if "turnover_budget" in _override_strategy else strategy.turnover_budget,
            turnover_budget_window=int(_override_strategy.get("turnover_budget_window", strategy.turnover_budget_window)),
            staggered_rebalance=bool(_override_strategy.get("staggered_rebalance", strategy.staggered_rebalance)),
            staggered_n_tranches=int(_override_strategy.get("staggered_n_tranches", strategy.staggered_n_tranches)),
        )

        _override_factors = _override_raw.get("factors", {})
        if _override_factors:
            _existing = strategy.factor_weights
            strategy = replace(
                strategy,
                factor_weights=replace(
                    _existing,
                    ret20=float(_override_factors.get("ret20_weight", _existing.ret20)),
                    ret60=float(_override_factors.get("ret60_weight", _existing.ret60)),
                    ret120=float(_override_factors.get("ret120_weight", _existing.ret120)),
                    ret5=float(_override_factors.get("ret5_weight", _existing.ret5)),
                    consistency60=float(_override_factors.get("consistency60_weight", _existing.consistency60)),
                    vol20=float(_override_factors.get("vol20_weight", _existing.vol20)),
                    amount_strength=float(_override_factors.get("amount_strength_weight", _existing.amount_strength)),
                    rel_ret60=float(_override_factors.get("rel_ret60_weight", _existing.rel_ret60)),
                    rel_ret20=float(_override_factors.get("rel_ret20_weight", _existing.rel_ret20)),
                    momentum_accel=float(_override_factors.get("momentum_accel_weight", _existing.momentum_accel)),
                    breadth20=float(_override_factors.get("breadth20_weight", _existing.breadth20)),
                    breadth60=float(_override_factors.get("breadth60_weight", _existing.breadth60)),
                    valuation=float(_override_factors.get("valuation_weight", _existing.valuation)),
                    prosperity=float(_override_factors.get("prosperity_weight", _existing.prosperity)),
                ),
            )

    merged_prices = merge_segment_price_data(segment_price_data, fill_missing=True)
    merged_benchmark = merge_benchmark_closes(segment_benchmark_data)

    top_k_values = _parse_int_tuple(args.top_k, "--top-k")
    factor_set_names = _parse_str_tuple(args.factor_set, "--factor-set")
    risk_off_exposures = _parse_float_tuple(
        args.risk_off_exposure,
        "--risk-off-exposure",
    )
    risk_control_values = _parse_bool_tuple(args.risk_control, "--risk-control")
    market_score_control_values = _parse_bool_tuple_or_auto(
        args.market_score_control,
        "--market-score-control",
    )
    market_score_threshold_values = _parse_float_tuple(
        args.market_score_threshold,
        "--market-score-threshold",
    )
    risk_control_mode_values = _parse_str_tuple(
        args.risk_control_mode,
        "--risk-control-mode",
    )
    soft_exposure_min_values = _parse_float_tuple(
        args.soft_exposure_min,
        "--soft-exposure-min",
    )
    portfolio_mode_values = _parse_str_tuple(
        args.portfolio_mode,
        "--portfolio-mode",
    )
    softmax_temperature_values = _parse_float_tuple(
        args.softmax_temperature,
        "--softmax-temperature",
    )

    folds = run_walk_forward_validation(
        merged_prices,
        merged_benchmark,
        strategy,
        factor_set_names=factor_set_names,
        top_k_values=top_k_values,
        risk_off_exposures=risk_off_exposures,
        risk_control_values=risk_control_values,
        market_score_control_values=market_score_control_values,
        market_score_threshold_values=market_score_threshold_values,
        risk_control_mode_values=risk_control_mode_values,
        soft_exposure_min_values=soft_exposure_min_values,
        portfolio_mode_values=portfolio_mode_values,
        softmax_temperature_values=softmax_temperature_values,
        market_weights=market_weights,
        train_window=args.train_window,
        test_window=args.test_window,
        step=args.step,
        include_partial_fold=args.include_partial_fold,
        purged_gap=args.purged_gap,
    )

    write_walk_forward_validation_reports(
        folds,
        args.output_dir,
        selection_metric=args.selection_metric,
    )

    selected_runs = [
        selected_by_train_with_data(fold.runs, args.selection_metric) for fold in folds
    ]
    selection_counts: dict[str, int] = {}
    for selected in selected_runs:
        name = selected.sweep_run.spec.name
        selection_counts[name] = selection_counts.get(name, 0) + 1
    most_selected, most_selected_count = sorted(
        selection_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )[0]
    mean_test_return = sum(
        run.test_metrics["annualized_return"] for run in selected_runs
    ) / len(selected_runs)
    mean_test_drawdown = sum(
        run.test_metrics["max_drawdown"] for run in selected_runs
    ) / len(selected_runs)
    step = args.step if args.step is not None else args.test_window
    print(
        "Cross-segment walk-forward validation complete. "
        f"Reports written to: {Path(args.output_dir).resolve()}"
    )
    print(
        f"Folds: {len(folds)} "
        f"(train_window={args.train_window}, test_window={args.test_window}, "
        f"step={step})"
    )
    print(
        "Date range: "
        f"{folds[0].split.train_start.isoformat()} to "
        f"{folds[-1].split.test_end.isoformat()}"
    )
    print(
        "Most selected: "
        f"{most_selected} ({most_selected_count}/{len(folds)} folds)"
    )
    print(f"Selection metric: {args.selection_metric}")
    print(f"Mean test annualized return: {mean_test_return:.2%}")
    print(f"Mean test max drawdown: {mean_test_drawdown:.2%}")
    return 0


def sample_data_command(args: argparse.Namespace) -> int:
    generate_sample_data(args.output, days=args.days, seed=args.seed)
    print(f"Sample data written to: {Path(args.output).resolve()}")
    return 0


def fetch_real_data_command(args: argparse.Namespace) -> int:
    start = parse_date(args.start)
    end = parse_date(args.end)
    market_indices = _parse_market_index_list(args.market_indexes)
    industry_indexes = (
        _parse_industry_index_list(args.industry_indexes)
        if args.industry_indexes.strip()
        else None
    )
    summary = fetch_and_write_real_data(
        args.output,
        start,
        end,
        benchmark_symbol=args.benchmark,
        industries=industry_indexes,
        industry_universe=args.industry_universe,
        market_indices=market_indices,
        progress=print,
        request_interval=args.request_interval,
        update_mode=args.update_mode,
    )
    print(f"Real data written to: {summary.output_dir.resolve()}")
    print(f"Date range: {summary.start.isoformat()} to {summary.end.isoformat()}")
    print(f"Rows: {summary.rows}")
    print(f"Industries: {summary.industries}")
    print(f"Benchmark: {summary.benchmark_symbol}")
    print(
        "Industry universe: "
        f"{'custom' if industry_indexes is not None else args.industry_universe}"
    )
    if summary.market_close_path:
        print(f"Market close: {summary.market_close_path.resolve()}")
    print(f"Manifest: {summary.manifest_path.resolve()}")
    return 0


def fetch_breadth_data_command(args: argparse.Namespace) -> int:
    start = parse_date(args.start)
    end = parse_date(args.end)
    windows = _parse_int_tuple(args.windows, "--windows")
    if args.lookback_days is not None and args.lookback_days < max(windows):
        raise ValueError("--lookback-days should be at least the largest MA window")
    industry_indexes = (
        _parse_market_index_list(args.industry_indexes)
        if args.industry_indexes.strip()
        else None
    )
    constituent_snapshots = (
        load_stock_industry_map_csv(args.constituent_snapshots)
        if args.constituent_snapshots
        else None
    )
    summary = fetch_and_write_breadth_data(
        args.output,
        start,
        end,
        industries=industry_indexes,
        constituent_snapshots=constituent_snapshots,
        windows=windows,
        min_stocks=args.min_stocks,
        adjust=args.adjust,
        lookback_days=args.lookback_days,
        max_stocks_per_industry=args.max_stocks_per_industry,
        progress=print,
        request_interval=args.request_interval,
    )
    print(f"Breadth data written to: {summary.output_dir.resolve()}")
    print(f"Date range: {summary.start.isoformat()} to {summary.end.isoformat()}")
    print(f"Rows: {summary.rows}")
    print(f"Industries: {summary.industries}")
    print(f"Windows: {', '.join(str(window) for window in summary.windows)}")
    for window, path in summary.breadth_paths.items():
        print(f"MA{window} breadth: {path.resolve()}")
    print(f"Manifest: {summary.manifest_path.resolve()}")
    return 0


def fetch_stock_data_command(args: argparse.Namespace) -> int:
    start = parse_date(args.start)
    end = parse_date(args.end)
    industry_indexes = (
        _parse_market_index_list(args.industry_indexes)
        if args.industry_indexes.strip()
        else None
    )
    constituent_snapshots = (
        load_stock_industry_map_csv(args.constituent_snapshots)
        if args.constituent_snapshots
        else None
    )
    summary = fetch_and_write_stock_data(
        args.output,
        start,
        end,
        industries=industry_indexes,
        constituent_snapshots=constituent_snapshots,
        adjust=args.adjust,
        max_stocks_per_industry=args.max_stocks_per_industry,
        progress=print,
        request_interval=args.request_interval,
    )
    print(f"Stock data written to: {summary.output_dir.resolve()}")
    print(f"Date range: {summary.start.isoformat()} to {summary.end.isoformat()}")
    print(f"Rows: {summary.rows}")
    print(f"Stocks: {summary.stocks}")
    print(f"Industries: {summary.industries}")
    print(f"Stock close: {summary.stock_close_path.resolve()}")
    if summary.stock_amount_path:
        print(f"Stock amount: {summary.stock_amount_path.resolve()}")
    print(f"Stock industry map: {summary.stock_industry_map_path.resolve()}")
    print(f"Manifest: {summary.manifest_path.resolve()}")
    if summary.current_constituents:
        print(
            "Note: stock data uses current SW constituents; validate with "
            "historical snapshots for backtest use."
        )
    return 0


WF_SUBDIRS = [
    "walk_forward",
    "walk_forward_ret60_ret5",
    "walk_forward_qtr",
    "walk_forward_partial",
]


def _find_wf_csvs(
    report_dir: Path, explicit_wf_dir: str | None
) -> tuple[Path | None, Path | None]:
    if explicit_wf_dir:
        d = Path(explicit_wf_dir)
        oos = d / "walk_forward_oos_equity.csv"
        folds = d / "walk_forward_folds.csv"
        return (oos if oos.exists() else None, folds if folds.exists() else None)

    for candidate in [report_dir] + [report_dir / d for d in WF_SUBDIRS]:
        oos = candidate / "walk_forward_oos_equity.csv"
        folds = candidate / "walk_forward_folds.csv"
        if oos.exists() and folds.exists():
            return oos, folds
    return None, None


def plot_command(args: argparse.Namespace) -> int:
    report_dir = Path(args.report_dir)
    equity_path = report_dir / "equity_curve.csv"
    holding_path = report_dir / "holding_period_return_distribution.csv"
    annual_path = report_dir / "annual_returns.csv"

    from quant_rotation.plot import (
        plot_walk_forward_folds,
        plot_risk_control_accuracy,
        plot_parameter_heatmap,
        plot_holding_history,
    )

    extra_sections = ""
    has_base_plots = equity_path.exists()

    wf_oos_path, wf_folds_path = _find_wf_csvs(report_dir, getattr(args, "wf_dir", None))
    if wf_oos_path and wf_folds_path:
        try:
            eq_png, bar_png = plot_walk_forward_folds(wf_oos_path, wf_folds_path)
            extra_sections += (
                f'<h2>WF Fold OOS Equity</h2>'
                f'<img src="data:image/png;base64,{b64encode(eq_png).decode()}">'
            )
            extra_sections += (
                f'<h2>WF Fold Returns</h2>'
                f'<img src="data:image/png;base64,{b64encode(bar_png).decode()}">'
            )
            wf_summary_csv = wf_folds_path.parent / "walk_forward_summary.csv"
            if wf_summary_csv.exists():
                from quant_rotation.plot import render_wf_summary_table
                extra_sections += render_wf_summary_table(wf_summary_csv)
        except Exception as exc:
            print(f"Warning: WF fold plot skipped ({exc})")

    accuracy_path = report_dir / "risk_control_accuracy.csv"
    if accuracy_path.exists():
        try:
            acc_png = plot_risk_control_accuracy(accuracy_path)
            extra_sections += (
                f'<h2>Risk Control Accuracy</h2>'
                f'<img src="data:image/png;base64,{b64encode(acc_png).decode()}">'
            )
        except Exception as exc:
            print(f"Warning: risk control plot skipped ({exc})")

    sweep_path = report_dir / "parameter_sweep.csv"
    if sweep_path.exists():
        try:
            heatmap_png = plot_parameter_heatmap(sweep_path)
            extra_sections += (
                f'<h2>Parameter Heatmap</h2>'
                f'<img src="data:image/png;base64,{b64encode(heatmap_png).decode()}">'
            )
        except Exception as exc:
            print(f"Warning: parameter heatmap skipped ({exc})")

    rebalances_path = report_dir / "rebalances.csv"
    if rebalances_path.exists():
        try:
            holdings_png = plot_holding_history(rebalances_path)
            extra_sections += (
                f'<h2>Holding History</h2>'
                f'<img src="data:image/png;base64,{b64encode(holdings_png).decode()}">'
            )
        except Exception as exc:
            print(f"Warning: holding history skipped ({exc})")

    if not has_base_plots and not extra_sections:
        print(f"Error: no plot data found in {report_dir}")
        return 1

    output_dir = args.output or str(report_dir)

    extra_benchmarks = None
    sse_path = report_dir / "sse_composite.csv"
    if sse_path.exists():
        try:
            import csv
            with sse_path.open("r", encoding="utf-8-sig") as h:
                reader = csv.DictReader(h)
                extra_benchmarks = [("上证指数", [float(r["close"]) for r in reader])]
        except Exception:
            pass

    if has_base_plots:
        annual_returns = {}
        if annual_path.exists():
            import csv as _csv
            with annual_path.open("r", encoding="utf-8-sig") as handle:
                reader = _csv.DictReader(handle)
                for row in reader:
                    annual_returns[int(row["year"])] = float(row["strategy_return"])

        html_path = write_html_report(
            output_dir,
            equity_path,
            annual_returns=annual_returns if annual_returns else None,
            holding_returns_path=holding_path if holding_path.exists() else None,
            extra_sections=extra_sections,
            extra_benchmarks=extra_benchmarks,
        )
    else:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>WF Validation Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
h1 {{ color: #333; }}
h2 {{ color: #555; margin-top: 30px; }}
img {{ width: 100%; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 10px 0; }}
</style></head>
<body>
<h1>Walk-Forward Validation Report</h1>
{extra_sections}
</body></html>"""
        html_path = out / "report.html"
        html_path.write_text(html, encoding="utf-8")

    print(f"HTML report written to: {html_path.resolve()}")
    return 0


def signal_command(args: argparse.Namespace) -> int:
    import json

    (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
        valuation_data,
        prosperity_data,
        market_data,
        stock_data,
        stock_amount_data,
        stock_industry_map,
        benchmark_closes,
    ) = _load_inputs(args.config)

    result = run_backtest(
        industry_data,
        benchmark_closes,
        app_config.strategy,
        amount_data=amount_data,
        breadth_data=breadth_data,
        valuation_data=valuation_data,
        prosperity_data=prosperity_data,
        market_data=market_data,
        market_weights=app_config.market_weights,
        stock_data=stock_data,
        stock_amount_data=stock_amount_data,
        stock_industry_map=stock_industry_map,
    )

    if not result.rebalances:
        print("Error: backtest produced no rebalances")
        return 1

    last = result.rebalances[-1]

    signal_data = {
        "signal_date": last.signal_date.isoformat(),
        "next_rebalance_date": last.date.isoformat(),
        "holdings": last.holdings,
        "weights": last.weights,
        "exposure": last.exposure,
        "market_trend": last.market_trend,
        "market_score": last.market_score,
        "market_score_ok": last.market_score_ok,
        "config": args.config,
        "generated_at": date.today().isoformat(),
    }

    output_path = Path(args.output) if args.output else (
        Path("reports/signals") / f"signal_{last.signal_date.isoformat()}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(signal_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Signal written to: {output_path.resolve()}")
    print(f"Signal date: {last.signal_date}")
    print(f"Next rebalance: {last.date}")
    print(f"Holdings ({len(last.holdings)}): {', '.join(last.holdings)}")
    print(f"Exposure: {last.exposure:.0%}")
    return 0


def compute_prosperity_command(args: argparse.Namespace) -> int:
    import csv
    import json
    from datetime import datetime
    from quant_rotation.data import load_wide_asset_csv
    from quant_rotation.real_data import compute_industry_amount_zscore

    if args.release_lag_days < 0:
        raise ValueError("--release-lag-days must be non-negative")
    raw_amount = load_wide_asset_csv(args.amount_csv, value_name="amount")
    zscore_data = compute_industry_amount_zscore(raw_amount, window=args.window)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", *zscore_data.assets])
        for i, day in enumerate(zscore_data.dates):
            writer.writerow([
                day.isoformat(),
                *[f"{zscore_data.closes[asset][i]:.6f}" for asset in zscore_data.assets],
            ])

    metadata_path = (
        Path(args.metadata_output)
        if args.metadata_output
        else output_path.with_name("industry_prosperity_manifest.json")
    )
    metadata = {
        "provider": "derived",
        "source_file": str(Path(args.amount_csv).resolve()),
        "source_factor": "industry_amount",
        "method": "rolling_amount_zscore",
        "window": args.window,
        "release_lag_days": args.release_lag_days,
        "available_time": "post_close",
        "usable_from": "next_rebalance",
        "start": zscore_data.dates[0].isoformat(),
        "end": zscore_data.dates[-1].isoformat(),
        "rows": len(zscore_data.dates),
        "industries": len(zscore_data.assets),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": {
            "industry_prosperity": output_path.name,
        },
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Prosperity proxy written to: {output_path.resolve()}")
    print(f"Prosperity metadata written to: {metadata_path.resolve()}")
    print(f"Dates: {len(zscore_data.dates)}, Industries: {len(zscore_data.assets)}")
    return 0


def compute_valuation_command(args: argparse.Namespace) -> int:
    import csv
    import json
    from datetime import datetime
    from quant_rotation.data import load_wide_close_csv
    from quant_rotation.real_data import compute_industry_valuation_proxy

    close_data = load_wide_close_csv(args.close_csv)
    valuation_data = compute_industry_valuation_proxy(close_data, window=args.window)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", *valuation_data.assets])
        for i, day in enumerate(valuation_data.dates):
            writer.writerow([
                day.isoformat(),
                *[f"{valuation_data.closes[asset][i]:.6f}" for asset in valuation_data.assets],
            ])

    metadata_path = output_path.with_name("industry_valuation_manifest.json")
    metadata = {
        "provider": "derived",
        "source_file": str(Path(args.close_csv).resolve()),
        "source_factor": "industry_close",
        "method": "rolling_price_percentile",
        "window": args.window,
        "release_lag_days": 1,
        "available_time": "post_close",
        "usable_from": "next_rebalance",
        "start": valuation_data.dates[0].isoformat(),
        "end": valuation_data.dates[-1].isoformat(),
        "rows": len(valuation_data.dates),
        "industries": len(valuation_data.assets),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": {
            "industry_valuation": output_path.name,
        },
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Valuation proxy written to: {output_path.resolve()}")
    print(f"Valuation metadata written to: {metadata_path.resolve()}")
    print(f"Dates: {len(valuation_data.dates)}, Industries: {len(valuation_data.assets)}")
    return 0


def fetch_historical_constituents_command(args: argparse.Namespace) -> int:
    import os
    from quant_rotation.real_data import (
        build_constituent_snapshots_from_intervals,
        fetch_joinquant_sw_level1_constituent_intervals,
        fetch_sws_level1_constituent_intervals,
        fetch_tushare_sw_level1_constituent_intervals,
        import_constituent_snapshot,
        read_constituent_interval_csv,
        validate_constituent_snapshot_csv,
        write_constituent_snapshot_csv,
    )

    if args.source == "csv-snapshots":
        if not args.input:
            print("Error: --input is required for --source csv-snapshots")
            return 1
        source = Path(args.input)
        issues = validate_constituent_snapshot_csv(source)
        if issues:
            print(f"Validation found {len(issues)} issue(s):")
            for issue in issues:
                print(f"  [FAIL] {issue}")
            if not args.validate_only:
                return 1
        else:
            print("Validation passed.")

        if args.validate_only:
            return 0 if not issues else 1

        target = Path(args.output)
        try:
            rows = import_constituent_snapshot(source, target, overwrite=args.overwrite)
            print(f"Imported {rows} rows to: {target.resolve()}")
            return 0
        except (ValueError, FileExistsError) as exc:
            print(f"Error: {exc}")
            return 1

    if not args.start or not args.end:
        print(f"Error: --start and --end are required for --source {args.source}")
        return 1
    start = parse_date(args.start)
    end = parse_date(args.end)

    try:
        if args.source == "csv-intervals":
            if not args.input:
                print("Error: --input is required for --source csv-intervals")
                return 1
            intervals = read_constituent_interval_csv(Path(args.input))
        elif args.source == "sws":
            industries = [
                item.strip()
                for item in args.industries.split(",")
                if item.strip()
            ] or None
            intervals = fetch_sws_level1_constituent_intervals(
                industries=industries,
                verify_ssl=not args.no_ssl_verify,
                request_interval=args.request_interval,
                progress=print,
            )
        elif args.source == "tushare":
            token = (
                args.tushare_token
                or os.environ.get("TUSHARE_TOKEN")
                or os.environ.get("TS_TOKEN")
            )
            if not token:
                print(
                    "Error: Tushare token is required. Pass --tushare-token "
                    "or set TUSHARE_TOKEN/TS_TOKEN."
                )
                return 1
            intervals = fetch_tushare_sw_level1_constituent_intervals(
                token=token,
                src=args.tushare_src,
                progress=print,
            )
        elif args.source == "joinquant":
            username = args.jq_user or os.environ.get("JQDATA_USER")
            password = args.jq_password or os.environ.get("JQDATA_PASSWORD")
            if not username or not password:
                print(
                    "Error: JoinQuant credentials are required. Pass --jq-user "
                    "and --jq-password or set JQDATA_USER/JQDATA_PASSWORD."
                )
                return 1
            intervals = fetch_joinquant_sw_level1_constituent_intervals(
                username=username,
                password=password,
                progress=print,
            )
        else:
            print(f"Error: unsupported source {args.source}")
            return 1

        stock_map = build_constituent_snapshots_from_intervals(
            intervals,
            start,
            end,
            snapshot_frequency=args.snapshot_frequency,
        )
        snapshot_dates = sorted(stock_map.snapshots)
        row_count = sum(len(mapping) for mapping in stock_map.snapshots.values())
        print(
            "Built historical snapshots: "
            f"{len(snapshot_dates)} dates, {row_count} rows, "
            f"{len(stock_map.all_stocks)} stocks"
        )
        print(
            "Snapshot range: "
            f"{snapshot_dates[0].isoformat()} to {snapshot_dates[-1].isoformat()}"
        )
        if args.validate_only:
            return 0

        target = Path(args.output)
        rows = write_constituent_snapshot_csv(
            stock_map,
            target,
            overwrite=args.overwrite,
        )
        issues = validate_constituent_snapshot_csv(target)
        if issues:
            print(f"Written file failed validation with {len(issues)} issue(s):")
            for issue in issues:
                print(f"  [FAIL] {issue}")
            return 1
        print(f"Historical constituent snapshots written to: {target.resolve()}")
        print(f"Rows: {rows}")
        return 0
    except (RuntimeError, ValueError, FileExistsError) as exc:
        print(f"Error: {exc}")
        return 1


def align_sse_benchmark_command(args: argparse.Namespace) -> int:
    import csv
    import pandas as pd
    try:
        import akshare as ak
    except ImportError:
        print("Error: akshare is required. Install with: pip install akshare")
        return 1

    report_dir = Path(args.report_dir)
    equity_path = report_dir / "equity_curve.csv"
    if not equity_path.exists():
        print(f"Error: equity_curve.csv not found in {report_dir}")
        return 1

    eq = pd.read_csv(equity_path)
    start = eq["date"].iloc[0]
    end = eq["date"].iloc[-1]

    sz = ak.stock_zh_index_daily(symbol="sh000001")
    sz["date"] = pd.to_datetime(sz["date"])
    sz = sz.set_index("date").sort_index()
    sz_aligned = sz.loc[start:end, "close"]

    from datetime import date as dt_date
    first_val = sz_aligned.iloc[0]
    normalized = [float(sz_aligned.loc[d] / first_val) for d in eq["date"]]

    output_path = Path(args.output) if args.output else (report_dir / "sse_composite.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "close"])
        for d, v in zip(eq["date"], normalized):
            writer.writerow([d, f"{v:.6f}"])

    print(f"SSE Composite aligned to: {output_path.resolve()}")
    print(f"Dates: {len(normalized)}, Period: {start} ~ {end}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "sample-data":
        return sample_data_command(args)
    if args.command == "fetch-real-data":
        return fetch_real_data_command(args)
    if args.command == "fetch-breadth-data":
        return fetch_breadth_data_command(args)
    if args.command == "fetch-stock-data":
        return fetch_stock_data_command(args)
    if args.command == "run":
        return run_command(args)
    if args.command == "run-segments":
        return run_segments_command(args)
    if args.command == "sweep-segments":
        return sweep_segments_command(args)
    if args.command == "decompose":
        return decompose_command(args)
    if args.command == "sweep":
        return sweep_command(args)
    if args.command == "validate":
        return validate_command(args)
    if args.command == "validate-segments":
        return validate_segments_command(args)
    if args.command == "plot":
        return plot_command(args)
    if args.command == "signal":
        return signal_command(args)
    if args.command == "compute-prosperity":
        return compute_prosperity_command(args)
    if args.command == "compute-valuation":
        return compute_valuation_command(args)
    if args.command == "fetch-historical-constituents":
        return fetch_historical_constituents_command(args)
    if args.command == "align-sse-benchmark":
        return align_sse_benchmark_command(args)
    if args.command == "combine":
        return combine_command(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


def combine_command(args: argparse.Namespace) -> int:
    import csv
    from datetime import date as dt_date

    def _read_equity_csv(path: str) -> tuple[list[dt_date], list[float]]:
        dates: list[dt_date] = []
        equity: list[float] = []
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                dates.append(dt_date.fromisoformat(row["date"]))
                equity.append(float(row["strategy_equity"]))
        return dates, equity

    base = Path(__file__).resolve().parent.parent.parent
    equity_paths = [str(Path(p) if Path(p).is_absolute() else base / p) for p in args.equity_paths]
    output = str(Path(args.output) if Path(args.output).is_absolute() else base / args.output)
    weights = args.weights

    if len(equity_paths) < 2:
        print("Need at least 2 strategy equity curves to combine")
        return 1
    if len(equity_paths) != len(weights):
        print("Number of equity-paths must match number of weights")
        return 1

    total_weight = sum(weights)
    if total_weight <= 0:
        print("Weights must sum to a positive value")
        return 1
    normalized = [w / total_weight for w in weights]

    equity_data = [_read_equity_csv(p) for p in equity_paths]

    first_dates = equity_data[0][0]
    for i in range(1, len(equity_data)):
        if equity_data[i][0] != first_dates:
            print(f"Date mismatch: {equity_paths[0]} and {equity_paths[i]}")
            return 1

    combined = [1.0]
    for t in range(1, len(first_dates)):
        day_return = sum(
            normalized[i] * (equity_data[i][1][t] / equity_data[i][1][t - 1] - 1.0)
            for i in range(len(equity_paths))
        )
        combined.append(combined[-1] * (1.0 + day_return))

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "combined_equity"])
        for i, d in enumerate(first_dates):
            writer.writerow([d.isoformat(), f"{combined[i]:.6f}"])

    final_return = combined[-1] - 1.0
    years = (first_dates[-1] - first_dates[0]).days / 365.25
    annualized = (combined[-1] ** (1.0 / years)) - 1.0 if years > 0 else 0.0

    peak = combined[0]
    max_drawdown = 0.0
    for v in combined:
        if v > peak:
            peak = v
        dd = (v / peak - 1.0) if peak > 0 else 0.0
        if dd < max_drawdown:
            max_drawdown = dd

    print(f"Combined equity written to: {output_path}")
    print(f"Strategies: {len(equity_paths)}")
    print(f"Weights: {[f'{w:.1%}' for w in normalized]}")
    print(f"Date range: {first_dates[0]} to {first_dates[-1]}")
    print(f"Final equity: {combined[-1]:.4f}")
    print(f"Total return: {final_return:.2%}")
    print(f"Annualized return: {annualized:.2%}")
    print(f"Max drawdown: {max_drawdown:.2%}")
    return 0
