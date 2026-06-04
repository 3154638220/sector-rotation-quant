from __future__ import annotations

import math


def select_top_k(scores: dict[str, float], top_k: int) -> list[str]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [asset for asset, _score in ranked[:top_k]]


def equal_weight_target(
    scores: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
) -> dict[str, float]:
    if not 0 <= exposure <= 1:
        raise ValueError("exposure must be between 0 and 1")
    if max_weight <= 0:
        raise ValueError("max_weight must be positive")

    holdings = select_top_k(scores, top_k)
    if not holdings or exposure == 0:
        return {}

    per_asset = min(exposure / len(holdings), max_weight)
    return {asset: per_asset for asset in holdings}


def _clamp_and_renormalize(
    weights: dict[str, float],
    max_weight: float,
) -> dict[str, float]:
    result = dict(weights)
    for _ in range(10):
        excess = sum(
            result[k] - max_weight for k in result if result[k] > max_weight
        )
        if excess < 1e-10:
            break
        clamped = {k: min(v, max_weight) for k, v in result.items()}
        below_max = [k for k, v in result.items() if v < max_weight]
        if not below_max:
            break
        per_asset = excess / len(below_max)
        result = {
            k: clamped[k] + (per_asset if k in below_max else 0.0)
            for k in result
        }
    return {k: min(v, max_weight) for k, v in result.items()}


def softmax_weight_target(
    scores: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
    temperature: float = 1.0,
) -> dict[str, float]:
    if not 0 <= exposure <= 1:
        raise ValueError("exposure must be between 0 and 1")
    if temperature <= 0:
        raise ValueError("temperature must be positive")

    holdings = select_top_k(scores, top_k)
    if not holdings or exposure == 0:
        return {}

    top_scores = {asset: scores[asset] for asset in holdings}
    max_score = max(top_scores.values())
    exp_scores = {
        asset: math.exp((s - max_score) / temperature)
        for asset, s in top_scores.items()
    }
    total = sum(exp_scores.values())
    raw_weights = {asset: (v / total) * exposure for asset, v in exp_scores.items()}

    return _clamp_and_renormalize(raw_weights, max_weight)


def vol_parity_target(
    scores: dict[str, float],
    vol_data: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
) -> dict[str, float]:
    holdings = select_top_k(scores, top_k)
    if not holdings or exposure == 0:
        return {}

    inv_vols = {
        asset: 1.0 / max(vol_data.get(asset, 0.02), 0.001)
        for asset in holdings
    }
    total = sum(inv_vols.values())
    raw_weights = {asset: (v / total) * exposure for asset, v in inv_vols.items()}
    return _clamp_and_renormalize(raw_weights, max_weight)


def adaptive_top_k(
    scores: dict[str, float],
    base_k: int = 5,
    concentration_threshold: float = 1.5,
) -> int:
    if not scores:
        return base_k
    ranked = sorted(scores.values(), reverse=True)
    if len(ranked) < base_k:
        return len(ranked)
    top_mean = sum(ranked[:base_k]) / base_k
    if top_mean > 0 and ranked[0] / top_mean > concentration_threshold:
        return max(3, base_k - 2)
    elif top_mean <= 0 or ranked[0] / max(top_mean, 0.01) < 0.8:
        return min(7, base_k + 2)
    return base_k


def turnover(previous: dict[str, float], target: dict[str, float]) -> float:
    assets = set(previous) | set(target)
    return sum(abs(target.get(asset, 0.0) - previous.get(asset, 0.0)) for asset in assets)
