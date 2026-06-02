from __future__ import annotations


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


def turnover(previous: dict[str, float], target: dict[str, float]) -> float:
    assets = set(previous) | set(target)
    return sum(abs(target.get(asset, 0.0) - previous.get(asset, 0.0)) for asset in assets)
