from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date
from pathlib import Path

from .backtest import run_backtest
from .config import load_config
from .data import (
    align_asset_data,
    align_benchmark,
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
)
from .reports import write_reports
from .sample_data import generate_sample_data
from .sweep import run_parameter_sweep, write_parameter_sweep_reports
from .sweep import (
    DEFAULT_FACTOR_SET_NAMES,
    DEFAULT_MARKET_SCORE_THRESHOLDS,
    DEFAULT_RISK_CONTROL_VALUES,
    DEFAULT_RISK_OFF_EXPOSURES,
    DEFAULT_TOP_K_VALUES,
)
from .validation import (
    DEFAULT_SELECTION_METRIC,
    run_walk_forward_validation,
    run_train_test_validation,
    selected_by_train,
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
        "--industry-indexes",
        default="",
        help=(
            "Optional comma-separated SW industry index list as NAME:CODE. "
            "Defaults to all detected SW level-1 industries."
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
        "--industry-indexes",
        default="",
        help=(
            "Optional comma-separated SW industry index list as NAME:CODE. "
            "Defaults to all detected SW level-1 industries."
        ),
    )

    run = subparsers.add_parser("run", help="Run a backtest")
    run.add_argument("--config", default="configs/default.toml", help="TOML config path")
    run.add_argument("--output-dir", default=None, help="Override report output directory")

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


def decompose_command(args: argparse.Namespace) -> int:
    (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
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


def _parse_market_index_list(value: str) -> list[IndexInfo]:
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
                "--market-indexes entries must use NAME:SYMBOL, "
                f"got {normalized!r}"
            )
        name, symbol = (part.strip() for part in normalized.split(":", 1))
        if not name or not symbol:
            raise ValueError(
                "--market-indexes entries must include both NAME and SYMBOL"
            )
        indexes.append(IndexInfo(symbol, name))
    if not indexes:
        raise ValueError("--market-indexes must contain at least one valid entry")
    return indexes


def sweep_command(args: argparse.Namespace) -> int:
    (
        app_config,
        industry_data,
        amount_data,
        breadth_data,
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
    runs = run_parameter_sweep(
        industry_data,
        benchmark_closes,
        strategy,
        amount_data=amount_data,
        breadth_data=breadth_data,
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
    if args.walk_forward:
        folds = run_walk_forward_validation(
            industry_data,
            benchmark_closes,
            strategy,
            amount_data=amount_data,
            breadth_data=breadth_data,
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
            selected_by_train(fold.runs, args.selection_metric) for fold in folds
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

    selected = selected_by_train(runs, args.selection_metric)
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


def sample_data_command(args: argparse.Namespace) -> int:
    generate_sample_data(args.output, days=args.days, seed=args.seed)
    print(f"Sample data written to: {Path(args.output).resolve()}")
    return 0


def fetch_real_data_command(args: argparse.Namespace) -> int:
    start = parse_date(args.start)
    end = parse_date(args.end)
    market_indices = _parse_market_index_list(args.market_indexes)
    summary = fetch_and_write_real_data(
        args.output,
        start,
        end,
        benchmark_symbol=args.benchmark,
        market_indices=market_indices,
        progress=print,
        request_interval=args.request_interval,
    )
    print(f"Real data written to: {summary.output_dir.resolve()}")
    print(f"Date range: {summary.start.isoformat()} to {summary.end.isoformat()}")
    print(f"Rows: {summary.rows}")
    print(f"Industries: {summary.industries}")
    print(f"Benchmark: {summary.benchmark_symbol}")
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
    summary = fetch_and_write_breadth_data(
        args.output,
        start,
        end,
        industries=industry_indexes,
        windows=windows,
        min_stocks=args.min_stocks,
        adjust=args.adjust,
        lookback_days=args.lookback_days,
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
    if summary.current_constituents:
        print(
            "Note: breadth uses current SW constituents; validate with historical "
            "constituent snapshots before production use."
        )
    return 0


def fetch_stock_data_command(args: argparse.Namespace) -> int:
    start = parse_date(args.start)
    end = parse_date(args.end)
    industry_indexes = (
        _parse_market_index_list(args.industry_indexes)
        if args.industry_indexes.strip()
        else None
    )
    summary = fetch_and_write_stock_data(
        args.output,
        start,
        end,
        industries=industry_indexes,
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
            "historical constituent snapshots before production use."
        )
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
    if args.command == "decompose":
        return decompose_command(args)
    if args.command == "sweep":
        return sweep_command(args)
    if args.command == "validate":
        return validate_command(args)
    parser.error(f"Unknown command: {args.command}")
    return 2
