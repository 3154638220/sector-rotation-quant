from __future__ import annotations

import math

from .factors import compute_factor_snapshot, simple_return, trailing_volatility
from .metrics import annual_returns, summarize_performance
from .models import (
    BacktestResult,
    BreadthData,
    FactorWeights,
    PriceData,
    RebalanceEvent,
    StockIndustryMap,
    StrategyConfig,
)
from .portfolio import adaptive_top_k, equal_weight_target, softmax_weight_target, turnover, vol_parity_target
from .stock_selection import stock_target_weights


def _classify_regime_for_factors(
    benchmark_closes: list[float] | None,
    signal_index: int,
    ma_window: int,
    market_score: float | None = None,
) -> str:
    if benchmark_closes is None or signal_index < ma_window:
        return "sideways"

    ma_val = sum(benchmark_closes[signal_index - ma_window + 1 : signal_index + 1]) / ma_window
    current = benchmark_closes[signal_index]
    trend_up = current > ma_val

    if trend_up and (market_score is None or market_score > 0):
        return "bull"
    elif not trend_up:
        return "bear"
    return "sideways"


def _select_regime_weights(config: StrategyConfig, regime: str) -> FactorWeights:
    if regime == "bull":
        return config.bull_factor_weights
    elif regime == "bear":
        return config.bear_factor_weights
    return config.sideways_factor_weights


def soft_risk_exposure(
    market_score: float,
    center: float = 0.0,
    steepness: float = 20.0,
    min_exp: float = 0.2,
    max_exp: float = 1.0,
) -> float:
    raw = 1.0 / (1.0 + math.exp(-steepness * (market_score - center)))
    return min_exp + (max_exp - min_exp) * raw


def _rolling_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def classify_market_state(
    market_score: float,
    benchmark_closes: list[float] | None,
    signal_index: int,
    ma_window: int,
    vol_hist: list[float] | None = None,
    bull_threshold: float = 1.5,
    bear_threshold: float = 0.0,
) -> str:
    votes = 0.0

    if benchmark_closes is not None and signal_index >= 60:
        ma20 = sum(benchmark_closes[signal_index - 19 : signal_index + 1]) / 20.0
        ma60 = sum(benchmark_closes[signal_index - 59 : signal_index + 1]) / 60.0
        votes += 1.0 if ma20 > ma60 else -1.0

    if vol_hist is not None and signal_index >= 60:
        daily_rets = [
            vol_hist[i] / vol_hist[i - 1] - 1.0
            for i in range(signal_index - 59, signal_index + 1)
        ]
        recent_vol = _rolling_std(daily_rets[-20:])
        hist_vol = _rolling_std(daily_rets)
        votes += 0.0 if recent_vol > 1.5 * hist_vol else 0.5

    if market_score > 0.03:
        votes += 1.0
    elif market_score < -0.03:
        votes += -1.0

    if votes >= bull_threshold:
        return "bull"
    elif votes >= bear_threshold:
        return "sideways"
    return "bear"


def _state_aware_exposure(
    market_score: float,
    benchmark_closes: list[float] | None,
    signal_index: int,
    ma_window: int,
    trend_ok: bool,
    bull_exposure: float = 1.0,
    sideways_exposure: float = 0.5,
    bear_exposure: float = 0.1,
    bull_threshold: float = 1.5,
    bear_threshold: float = 0.0,
) -> float:
    state = classify_market_state(
        market_score, benchmark_closes, signal_index, ma_window,
        vol_hist=benchmark_closes,
        bull_threshold=bull_threshold,
        bear_threshold=bear_threshold,
    )
    if state == "bull":
        return bull_exposure
    elif state == "bear":
        return bear_exposure
    else:
        return sideways_exposure


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


def _dual_ma_trend(
    benchmark_closes: list[float] | None,
    signal_index: int,
) -> bool:
    if benchmark_closes is None or signal_index < 60:
        return True
    ma20 = sum(benchmark_closes[signal_index - 19 : signal_index + 1]) / 20.0
    ma60 = sum(benchmark_closes[signal_index - 59 : signal_index + 1]) / 60.0
    return ma20 > ma60


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


def _stock_map_symbols(stock_industry_map: StockIndustryMap | dict[str, str]) -> set[str]:
    if isinstance(stock_industry_map, StockIndustryMap):
        return stock_industry_map.all_stocks
    return set(stock_industry_map)


def run_backtest(
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
        if not any(
            stock in stock_data.closes
            for stock in _stock_map_symbols(stock_industry_map)
        ):
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
    for name, value in (
        ("valuation_data", valuation_data),
        ("prosperity_data", prosperity_data),
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
            if config.risk_control_dual_ma:
                trend_ok = _dual_ma_trend(benchmark_closes, signal_index)
            elif config.risk_control:
                trend_ok = _market_trend(
                    benchmark_closes, signal_index, config.market_ma_window
                )
            else:
                trend_ok = True

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
            if config.regime_aware_factors:
                regime = _classify_regime_for_factors(
                    benchmark_closes, signal_index,
                    config.market_ma_window, score,
                )
                active_weights = _select_regime_weights(config, regime)
            else:
                active_weights = config.factor_weights
            snapshot = compute_factor_snapshot(
                data,
                signal_index,
                active_weights,
                amount_data=amount_data,
                breadth_data=breadth_data,
                valuation_data=valuation_data,
                prosperity_data=prosperity_data,
                market_data=market_data,
                market_weights=market_weights,
            )
            score_ok = score is None or score >= config.market_score_threshold
            risk_on = trend_ok and score_ok

            effective_top_k = config.top_k
            if config.adaptive_top_k:
                effective_top_k = adaptive_top_k(
                    snapshot.scores,
                    base_k=config.adaptive_top_k_base,
                    concentration_threshold=config.adaptive_top_k_concentration,
                )

            if (
                config.risk_control_mode == "soft"
                and config.market_score_control
                and score is not None
            ):
                exposure = soft_risk_exposure(
                    score,
                    center=config.soft_exposure_center,
                    steepness=config.soft_exposure_steepness,
                    min_exp=config.soft_exposure_min,
                    max_exp=config.soft_exposure_max,
                )
                if config.risk_control and not trend_ok:
                    exposure = min(exposure, config.soft_exposure_min)
            elif (
                config.state_aware_risk_control
                and config.market_score_control
                and score is not None
                and config.risk_control
            ):
                exposure = _state_aware_exposure(
                    score,
                    benchmark_closes,
                    signal_index,
                    config.market_ma_window,
                    trend_ok,
                    bull_exposure=config.bull_exposure,
                    sideways_exposure=config.sideways_exposure,
                    bear_exposure=config.bear_exposure,
                    bull_threshold=config.state_aware_bull_threshold,
                    bear_threshold=config.state_aware_bear_threshold,
                )
            else:
                exposure = 1.0 if risk_on else config.risk_off_exposure
            if config.portfolio_mode == "softmax":
                industry_target_weights = softmax_weight_target(
                    snapshot.scores,
                    top_k=effective_top_k,
                    exposure=exposure,
                    max_weight=config.max_industry_weight,
                    temperature=config.softmax_temperature,
                )
            elif config.portfolio_mode == "vol_parity":
                vol_snapshot = {
                    asset: trailing_volatility(closes, signal_index, 20)
                    for asset, closes in data.closes.items()
                }
                industry_target_weights = vol_parity_target(
                    snapshot.scores,
                    vol_snapshot,
                    top_k=effective_top_k,
                    exposure=exposure,
                    max_weight=config.max_industry_weight,
                )
            else:
                industry_target_weights = equal_weight_target(
                    snapshot.scores,
                    top_k=effective_top_k,
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
                    signal_date=snapshot.signal_date,
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
