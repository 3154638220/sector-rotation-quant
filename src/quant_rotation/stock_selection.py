from __future__ import annotations

from datetime import date

from .factors import simple_return, trailing_mean, trailing_volatility, trend_consistency, zscore
from .models import PriceData, StockIndustryMap, StockSelectionConfig
from .portfolio import select_top_k

StockIndustryMapLike = StockIndustryMap | dict[str, str]


def _resolve_stock_industry_map(
    stock_industry_map: StockIndustryMapLike,
    as_of: date | None,
) -> dict[str, str]:
    if isinstance(stock_industry_map, StockIndustryMap):
        if as_of is None:
            as_of = max(stock_industry_map.snapshots)
        return stock_industry_map.get_map_at(as_of)
    return stock_industry_map


def stocks_by_industry(
    stock_industry_map: StockIndustryMapLike,
    available_stocks: list[str],
    *,
    as_of: date | None = None,
) -> dict[str, list[str]]:
    mapping = _resolve_stock_industry_map(stock_industry_map, as_of)
    available = set(available_stocks)
    grouped: dict[str, list[str]] = {}
    for stock, industry in mapping.items():
        if stock not in available:
            continue
        grouped.setdefault(industry, []).append(stock)
    return {industry: sorted(stocks) for industry, stocks in grouped.items()}


def compute_stock_scores(
    stock_data: PriceData,
    index: int,
    candidates: list[str],
    config: StockSelectionConfig,
    stock_amount_data: PriceData | None = None,
) -> dict[str, float]:
    if not candidates:
        return {}
    if index < 60:
        raise ValueError("At least 60 observations are required for stock scoring")
    if stock_amount_data is not None:
        if stock_amount_data.dates != stock_data.dates:
            raise ValueError("stock_amount_data dates must match stock data dates")
        if stock_amount_data.assets != stock_data.assets:
            raise ValueError("stock_amount_data assets must match stock data assets")

    ret20: dict[str, float] = {}
    ret60: dict[str, float] = {}
    amount_strength: dict[str, float] = {}
    vol20: dict[str, float] = {}
    ret5: dict[str, float] = {}
    rel_ret60_raw: dict[str, float] = {}
    consistency20_raw: dict[str, float] = {}

    for stock in candidates:
        closes = stock_data.closes[stock]
        # Skip stocks with no real price movement (forward-fill artifact)
        if index >= 20:
            moved = any(closes[i] != closes[i-1] for i in range(index - 19, index + 1))
            if not moved:
                continue
        ret20[stock] = simple_return(closes, index, 20)
        ret60[stock] = simple_return(closes, index, 60)
        vol20[stock] = trailing_volatility(closes, index, 20)
        ret5[stock] = simple_return(closes, index, 5)
        if stock_amount_data is not None:
            amounts = stock_amount_data.closes[stock]
            amount_ma60 = trailing_mean(amounts, index, 60)
            if amount_ma60 > 0:
                amount_strength[stock] = trailing_mean(amounts, index, 20) / amount_ma60
        if config.rel_ret60 != 0:
            rel_ret60_raw[stock] = ret60[stock]
        if config.consistency20 != 0:
            consistency20_raw[stock] = trend_consistency(closes, index, 20)

    z_ret20 = zscore(ret20)
    z_ret60 = zscore(ret60)
    z_amount_strength = zscore(amount_strength)
    z_vol20 = zscore(vol20)
    z_ret5 = zscore(ret5)
    z_rel_ret60 = zscore(rel_ret60_raw)
    z_consistency20 = zscore(consistency20_raw)

    return {
        stock: (
            config.ret20 * z_ret20[stock]
            + config.ret60 * z_ret60[stock]
            + config.amount_strength * z_amount_strength.get(stock, 0.0)
            + config.vol20 * z_vol20[stock]
            + config.ret5 * z_ret5[stock]
            + config.rel_ret60 * z_rel_ret60.get(stock, 0.0)
            + config.consistency20 * z_consistency20.get(stock, 0.0)
        )
        for stock in candidates
    }


def stock_target_weights(
    industry_weights: dict[str, float],
    stock_data: PriceData,
    stock_industry_map: StockIndustryMapLike,
    index: int,
    config: StockSelectionConfig,
    stock_amount_data: PriceData | None = None,
    signal_date: date | None = None,
) -> dict[str, float]:
    if config.top_n_per_industry <= 0:
        raise ValueError("stock_top_n_per_industry must be positive")
    if config.min_stocks_per_industry <= 0:
        raise ValueError("stock_min_stocks_per_industry must be positive")
    if config.max_stock_weight <= 0:
        raise ValueError("stock_max_weight must be positive")

    grouped = stocks_by_industry(
        stock_industry_map,
        stock_data.assets,
        as_of=signal_date or stock_data.dates[index],
    )
    selected_industries = {ind for ind, w in industry_weights.items() if w > 0}
    all_candidates = [
        stock
        for ind, stocks in grouped.items()
        if ind in selected_industries
        for stock in stocks
    ]
    all_scores = compute_stock_scores(
        stock_data,
        index,
        all_candidates,
        config,
        stock_amount_data=stock_amount_data,
    )
    target: dict[str, float] = {}
    for industry, industry_weight in industry_weights.items():
        candidates = grouped.get(industry, [])
        if len(candidates) < config.min_stocks_per_industry:
            continue
        industry_scores = {
            stock: score
            for stock, score in all_scores.items()
            if stock in candidates
        }
        selected = select_top_k(
            industry_scores,
            min(config.top_n_per_industry, len(industry_scores)),
        )
        if not selected:
            continue
        per_stock = min(industry_weight / len(selected), config.max_stock_weight)
        for stock in selected:
            target[stock] = per_stock
    return target
