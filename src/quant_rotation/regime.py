"""Three-state market regime classifier.

Replaces the binary (risk-on/risk-off) risk control with a multi-signal
classifier that emits one of three states: STRONG, NEUTRAL, WEAK.
Each state maps to a configurable exposure level.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MarketState(Enum):
    STRONG = "strong"
    NEUTRAL = "neutral"
    WEAK = "weak"


@dataclass(frozen=True)
class MarketStateConfig:
    trend_weight: float = 0.35
    dispersion_weight: float = 0.25
    momentum_weight: float = 0.25
    breadth_weight: float = 0.15
    strong_threshold: float = 0.25
    weak_threshold: float = -0.10
    strong_exposure: float = 1.00
    neutral_exposure: float = 0.60
    weak_exposure: float = 0.25


def _clamp_score(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _trend_score(benchmark_closes: list[float], signal_index: int) -> float:
    """Multi-MA trend composite score, range -1.0 to +1.0."""
    if signal_index < 120:
        return 0.0
    closes = benchmark_closes[: signal_index + 1]
    ma20 = sum(closes[-20:]) / 20.0
    ma60 = sum(closes[-60:]) / 60.0
    ma120 = sum(closes[-120:]) / 120.0
    current = closes[-1]
    score = 0.0
    score += 0.4 if current > ma20 else -0.4
    score += 0.4 if current > ma60 else -0.4
    score += 0.2 if current > ma120 else -0.2
    return _clamp_score(score)


def _dispersion_score(industry_returns_20d: dict[str, float]) -> float:
    """Cross-sectional dispersion of 20-day industry returns."""
    returns = list(industry_returns_20d.values())
    if len(returns) < 3:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    dispersion = variance ** 0.5
    return _clamp_score((dispersion - 0.07) / 0.05)


def _momentum_quality_score(
    benchmark_closes: list[float], signal_index: int
) -> float:
    """Market momentum quality: 60-day return penalized by recent overheating."""
    if signal_index < 60:
        return 0.0
    closes = benchmark_closes[: signal_index + 1]
    ret60 = closes[-1] / closes[-60] - 1.0
    ret5 = closes[-1] / closes[-5] - 1.0
    momentum_quality = ret60 - max(0.0, ret5 * 3.0)
    return _clamp_score(momentum_quality / 0.15)


def _breadth_score(breadth_values: dict[str, float] | None) -> float:
    """Average industry breadth centered and scaled to [-1, 1]."""
    if not breadth_values:
        return 0.0
    avg = sum(breadth_values.values()) / len(breadth_values)
    return _clamp_score((avg - 0.50) * 4.0)


def classify_market_state(
    benchmark_closes: list[float],
    signal_index: int,
    config: MarketStateConfig,
    industry_returns_20d: dict[str, float] | None = None,
    breadth_values: dict[str, float] | None = None,
) -> tuple[MarketState, float]:
    """Classify market into STRONG/NEUTRAL/WEAK and return target exposure.

    Signal weights are configurable; defaults favour trend strength (35%)
    and give equal weight to dispersion and momentum quality (25% each).
    """
    t_score = _trend_score(benchmark_closes, signal_index)
    d_score = _dispersion_score(industry_returns_20d or {})
    m_score = _momentum_quality_score(benchmark_closes, signal_index)
    b_score = _breadth_score(breadth_values)

    composite = (
        config.trend_weight * t_score
        + config.dispersion_weight * d_score
        + config.momentum_weight * m_score
        + config.breadth_weight * b_score
    )

    if composite >= config.strong_threshold:
        return MarketState.STRONG, config.strong_exposure
    elif composite > config.weak_threshold:
        return MarketState.NEUTRAL, config.neutral_exposure
    else:
        return MarketState.WEAK, config.weak_exposure
