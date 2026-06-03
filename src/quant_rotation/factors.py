from __future__ import annotations

from math import sqrt

from .models import BreadthData, FactorSnapshot, FactorWeights, PriceData


def simple_return(values: list[float], index: int, lookback: int) -> float:
    if index < lookback:
        raise ValueError("Not enough history for return calculation")
    previous = values[index - lookback]
    if previous <= 0:
        raise ValueError("Close values must be positive")
    return values[index] / previous - 1.0


def trailing_volatility(values: list[float], index: int, lookback: int) -> float:
    if index < lookback:
        raise ValueError("Not enough history for volatility calculation")
    returns = [
        values[i] / values[i - 1] - 1.0
        for i in range(index - lookback + 1, index + 1)
    ]
    mean_value = sum(returns) / len(returns)
    variance = sum((value - mean_value) ** 2 for value in returns) / len(returns)
    return sqrt(variance)


def trailing_mean(values: list[float], index: int, lookback: int) -> float:
    if index < lookback - 1:
        raise ValueError("Not enough history for mean calculation")
    window = values[index - lookback + 1 : index + 1]
    return sum(window) / len(window)


def zscore(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    mean_value = sum(values.values()) / len(values)
    variance = sum((value - mean_value) ** 2 for value in values.values()) / len(values)
    std = sqrt(variance)
    if std == 0:
        return {key: 0.0 for key in values}
    return {key: (value - mean_value) / std for key, value in values.items()}


def _validate_aligned_factor_data(
    name: str,
    factor_data: PriceData,
    data: PriceData,
) -> None:
    if data.dates != factor_data.dates:
        raise ValueError(f"{name} dates must match price data dates")
    if data.assets != factor_data.assets:
        raise ValueError(f"{name} assets must match price data assets")


def _breadth_value(values: list[float], index: int, name: str) -> float:
    value = values[index]
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} values must be between 0 and 1")
    return value


def compute_factor_snapshot(
    data: PriceData,
    index: int,
    weights: FactorWeights,
    amount_data: PriceData | None = None,
    breadth_data: BreadthData | None = None,
    valuation_data: PriceData | None = None,
    prosperity_data: PriceData | None = None,
) -> FactorSnapshot:
    if index < 120:
        raise ValueError("At least 120 observations are required for scoring")
    if amount_data is not None:
        _validate_aligned_factor_data("amount_data", amount_data, data)
    if breadth_data is not None:
        if breadth_data.breadth20 is not None:
            _validate_aligned_factor_data("breadth20 data", breadth_data.breadth20, data)
        if breadth_data.breadth60 is not None:
            _validate_aligned_factor_data("breadth60 data", breadth_data.breadth60, data)
    if valuation_data is not None:
        _validate_aligned_factor_data("valuation data", valuation_data, data)
    if prosperity_data is not None:
        _validate_aligned_factor_data("prosperity data", prosperity_data, data)

    ret20: dict[str, float] = {}
    ret60: dict[str, float] = {}
    ret120: dict[str, float] = {}
    amount_strength: dict[str, float] = {}
    breadth20: dict[str, float] = {}
    breadth60: dict[str, float] = {}
    valuation: dict[str, float] = {}
    valuation_score_input: dict[str, float] = {}
    prosperity: dict[str, float] = {}
    vol20: dict[str, float] = {}
    ret5: dict[str, float] = {}

    for asset, closes in data.closes.items():
        ret20[asset] = simple_return(closes, index, 20)
        ret60[asset] = simple_return(closes, index, 60)
        ret120[asset] = simple_return(closes, index, 120)
        vol20[asset] = trailing_volatility(closes, index, 20)
        ret5[asset] = simple_return(closes, index, 5)
        if amount_data is not None:
            amounts = amount_data.closes[asset]
            amount_ma120 = trailing_mean(amounts, index, 120)
            if amount_ma120 <= 0:
                raise ValueError("Amount values must have a positive 120-day mean")
            amount_strength[asset] = trailing_mean(amounts, index, 20) / amount_ma120
        if breadth_data is not None and breadth_data.breadth20 is not None:
            breadth20[asset] = _breadth_value(
                breadth_data.breadth20.closes[asset],
                index,
                "breadth20",
            )
        if breadth_data is not None and breadth_data.breadth60 is not None:
            breadth60[asset] = _breadth_value(
                breadth_data.breadth60.closes[asset],
                index,
                "breadth60",
            )
        if valuation_data is not None:
            value = valuation_data.closes[asset][index]
            if not 0.0 <= value <= 1.0:
                raise ValueError("valuation values must be between 0 and 1")
            valuation[asset] = value
            valuation_score_input[asset] = -value
        if prosperity_data is not None:
            prosperity[asset] = prosperity_data.closes[asset][index]

    z_ret20 = zscore(ret20)
    z_ret60 = zscore(ret60)
    z_ret120 = zscore(ret120)
    z_amount_strength = zscore(amount_strength)
    z_breadth20 = zscore(breadth20)
    z_breadth60 = zscore(breadth60)
    z_valuation = zscore(valuation_score_input)
    z_prosperity = zscore(prosperity)
    z_vol20 = zscore(vol20)
    z_ret5 = zscore(ret5)

    scores = {
        asset: (
            weights.ret20 * z_ret20[asset]
            + weights.ret60 * z_ret60[asset]
            + weights.ret120 * z_ret120[asset]
            + weights.amount_strength * z_amount_strength.get(asset, 0.0)
            + weights.breadth20 * z_breadth20.get(asset, 0.0)
            + weights.breadth60 * z_breadth60.get(asset, 0.0)
            + weights.valuation * z_valuation.get(asset, 0.0)
            + weights.prosperity * z_prosperity.get(asset, 0.0)
            + weights.vol20 * z_vol20[asset]
            + weights.ret5 * z_ret5[asset]
        )
        for asset in data.assets
    }

    fields = {
        "ret20": ret20,
        "ret60": ret60,
        "ret120": ret120,
        "vol20": vol20,
        "ret5": ret5,
        "score": scores,
    }
    if amount_strength:
        fields["amount_strength"] = amount_strength
    if breadth20:
        fields["breadth20"] = breadth20
    if breadth60:
        fields["breadth60"] = breadth60
    if valuation:
        fields["valuation"] = valuation
    if prosperity:
        fields["prosperity"] = prosperity
    return FactorSnapshot(data.dates[index], scores, fields)
