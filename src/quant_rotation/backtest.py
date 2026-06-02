from __future__ import annotations

from .factors import compute_factor_snapshot, simple_return
from .metrics import annual_returns, summarize_performance
from .models import (
    BacktestResult,
    BreadthData,
    PriceData,
    RebalanceEvent,
    StrategyConfig,
)
from .portfolio import equal_weight_target, turnover
from .stock_selection import stock_target_weights


def _asset_returns(data: PriceData, index: int) -> dict[str, float]:
    return {
        asset: closes[index] / closes[index - 1] - 1.0
        for asset, closes in data.closes.items()
    }


def _weighted_return(weights: dict[str, float], returns: dict[str, float]) -> float:
    return sum(weight * returns.get(asset, 0.0) for asset, weight in weights.items())


def _benchmark_equity(benchmark_closes: list[float] | None) -> list[float] | None:
    if benchmark_closes is None:
        return None
    equity = [1.0]
    for i in range(1, len(benchmark_closes)):
        equity.append(equity[-1] * (benchmark_closes[i] / benchmark_closes[i - 1]))
    return equity


def _equal_weight_equity(data: PriceData) -> list[float]:
    equity = [1.0]
    for i in range(1, len(data.dates)):
        returns = _asset_returns(data, i)
        day_return = sum(returns.values()) / len(returns)
        equity.append(equity[-1] * (1.0 + day_return))
    return equity


def _market_trend(
    benchmark_closes: list[float] | None,
    signal_index: int,
    ma_window: int,
) -> bool:
    if benchmark_closes is None:
        return True
    if signal_index < ma_window:
        return True
    window = benchmark_closes[signal_index - ma_window + 1 : signal_index + 1]
    moving_average = sum(window) / len(window)
    return benchmark_closes[signal_index] > moving_average


def _normalized_market_weights(
    assets: list[str],
    market_weights: dict[str, float],
) -> dict[str, float]:
    if not assets:
        return {}
    unknown = sorted(set(market_weights) - set(assets))
    if unknown:
        preview = ", ".join(unknown[:5])
        raise ValueError(f"market_weights contains unknown market assets: {preview}")
    if any(weight < 0 for weight in market_weights.values()):
        raise ValueError("market_weights must be non-negative")

    if market_weights:
        total = sum(market_weights.values())
        if total <= 0:
            raise ValueError("market_weights must sum to a positive value")
        return {asset: market_weights.get(asset, 0.0) / total for asset in assets}

    equal_weight = 1.0 / len(assets)
    return {asset: equal_weight for asset in assets}


def _market_score(
    market_data: PriceData | None,
    benchmark_closes: list[float] | None,
    signal_index: int,
    window: int,
    market_weights: dict[str, float],
) -> float | None:
    if signal_index < window:
        return None
    if market_data is not None:
        weights = _normalized_market_weights(market_data.assets, market_weights)
        return sum(
            weights[asset] * simple_return(market_data.closes[asset], signal_index, window)
            for asset in market_data.assets
        )
    if benchmark_closes is not None:
        return simple_return(benchmark_closes, signal_index, window)
    return None


def run_backtest(
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
) -> BacktestResult:
    if benchmark_closes is not None and len(benchmark_closes) != len(data.dates):
        raise ValueError("benchmark_closes length must match data dates")
    if market_data is not None and market_data.dates != data.dates:
        raise ValueError("market_data dates must match price data dates")
    if config.market_score_control and market_data is None and benchmark_closes is None:
        raise ValueError(
            "market_score_control requires market_data or benchmark_closes"
        )
    stock_mode = config.stock_selection.enabled
    if stock_mode:
        if stock_data is None or stock_industry_map is None:
            raise ValueError(
                "stock_selection requires stock_data and stock_industry_map"
            )
        if stock_data.dates != data.dates:
            raise ValueError("stock_data dates must match price data dates")
        if not any(stock in stock_data.closes for stock in stock_industry_map):
            raise ValueError("stock_industry_map has no stocks in stock_data")
    if stock_amount_data is not None:
        if stock_data is None:
            raise ValueError("stock_amount_data requires stock_data")
        if stock_amount_data.dates != stock_data.dates:
            raise ValueError("stock_amount_data dates must match stock data dates")
        if stock_amount_data.assets != stock_data.assets:
            raise ValueError("stock_amount_data assets must match stock data assets")
    if amount_data is not None:
        if amount_data.dates != data.dates:
            raise ValueError("amount_data dates must match price data dates")
        if amount_data.assets != data.assets:
            raise ValueError("amount_data assets must match price data assets")
    if breadth_data is not None:
        for name, value in (
            ("breadth20", breadth_data.breadth20),
            ("breadth60", breadth_data.breadth60),
        ):
            if value is None:
                continue
            if value.dates != data.dates:
                raise ValueError(f"{name} dates must match price data dates")
            if value.assets != data.assets:
                raise ValueError(f"{name} assets must match price data assets")
    if config.rebalance_every <= 0:
        raise ValueError("rebalance_every must be positive")
    if config.market_score_window <= 0:
        raise ValueError("market_score_window must be positive")

    return_data = stock_data if stock_mode and stock_data is not None else data
    min_history = max(
        120,
        config.market_ma_window if config.risk_control else 0,
        config.market_score_window if config.market_score_control else 0,
    )
    if len(data.dates) <= min_history + 2:
        raise ValueError(
            f"Need more than {min_history + 2} observations, got {len(data.dates)}"
        )

    current_weights: dict[str, float] = {}
    strategy_equity = [1.0]
    rebalances: list[RebalanceEvent] = []
    daily_returns = [0.0]
    rebalance_by_execution_index = {
        signal_index + 1: signal_index
        for signal_index in range(min_history, len(data.dates) - 1, config.rebalance_every)
    }

    for index in range(1, len(data.dates)):
        day_return = _weighted_return(current_weights, _asset_returns(return_data, index))
        next_equity = strategy_equity[-1] * (1.0 + day_return)

        signal_index = rebalance_by_execution_index.get(index)
        if signal_index is not None:
            snapshot = compute_factor_snapshot(
                data,
                signal_index,
                config.factor_weights,
                amount_data=amount_data,
                breadth_data=breadth_data,
            )
            trend_ok = (
                _market_trend(benchmark_closes, signal_index, config.market_ma_window)
                if config.risk_control
                else True
            )
            score = (
                _market_score(
                    market_data,
                    benchmark_closes,
                    signal_index,
                    config.market_score_window,
                    market_weights or {},
                )
                if config.market_score_control
                else None
            )
            score_ok = score is None or score >= config.market_score_threshold
            risk_on = trend_ok and score_ok
            exposure = 1.0 if risk_on else config.risk_off_exposure
            industry_target_weights = equal_weight_target(
                snapshot.scores,
                top_k=config.top_k,
                exposure=exposure,
                max_weight=config.max_industry_weight,
            )
            target_weights = (
                stock_target_weights(
                    industry_target_weights,
                    stock_data,
                    stock_industry_map or {},
                    signal_index,
                    config.stock_selection,
                    stock_amount_data=stock_amount_data,
                )
                if stock_mode and stock_data is not None
                else industry_target_weights
            )
            trade_turnover = turnover(current_weights, target_weights)
            cost = trade_turnover * config.transaction_cost
            next_equity *= 1.0 - cost
            current_weights = target_weights
            rebalances.append(
                RebalanceEvent(
                    date=data.dates[index],
                    signal_date=snapshot.signal_date,
                    holdings=list(target_weights),
                    weights=target_weights,
                    exposure=sum(target_weights.values()),
                    turnover=trade_turnover,
                    cost=cost,
                    market_trend=trend_ok,
                    market_score=score,
                    market_score_ok=score_ok,
                    risk_on=risk_on,
                    selected_industries=list(industry_target_weights),
                )
            )

        daily_returns.append(next_equity / strategy_equity[-1] - 1.0)
        strategy_equity.append(next_equity)

    benchmark_equity = _benchmark_equity(benchmark_closes)
    equal_weight_equity = _equal_weight_equity(return_data)
    metrics = summarize_performance(
        data.dates,
        strategy_equity,
        benchmark_equity,
        equal_weight_equity,
        turnovers=[event.turnover for event in rebalances],
        costs=[event.cost for event in rebalances],
    )
    return BacktestResult(
        dates=data.dates,
        strategy_equity=strategy_equity,
        benchmark_equity=benchmark_equity,
        equal_weight_equity=equal_weight_equity,
        daily_returns=daily_returns,
        rebalances=rebalances,
        metrics=metrics,
        annual_returns=annual_returns(data.dates, strategy_equity),
    )
