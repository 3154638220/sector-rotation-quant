"""Tests for the three-state market regime classifier."""
import math

from quant_rotation.regime import (
    MarketState,
    MarketStateConfig,
    _trend_score,
    _dispersion_score,
    _momentum_quality_score,
    _breadth_score,
    classify_market_state,
)


class TestTrendScore:
    def test_insufficient_history_returns_zero(self):
        closes = [100.0] * 50
        assert _trend_score(closes, 49) == 0.0

    def test_above_all_mas_returns_positive(self):
        closes = [100.0] * 120 + [105.0]
        idx = len(closes) - 1
        score = _trend_score(closes, idx)
        assert score > 0.0

    def test_below_all_mas_returns_negative(self):
        closes = [110.0] * 120 + [100.0]
        idx = len(closes) - 1
        score = _trend_score(closes, idx)
        assert score < 0.0

    def test_clamped_to_range(self):
        closes = [100.0] * 120 + [200.0]
        idx = len(closes) - 1
        score = _trend_score(closes, idx)
        assert -1.0 <= score <= 1.0


class TestDispersionScore:
    def test_empty_returns_zero(self):
        assert _dispersion_score({}) == 0.0

    def test_too_few_returns_zero(self):
        assert _dispersion_score({"a": 0.01, "b": 0.02}) == 0.0

    def test_high_dispersion_yields_positive(self):
        returns = {f"ind{i}": 0.05 * (i - 5) for i in range(11)}
        score = _dispersion_score(returns)
        assert score > 0.0

    def test_low_dispersion_yields_negative(self):
        returns = {f"ind{i}": 0.01 for i in range(10)}
        score = _dispersion_score(returns)
        assert score < 0.0


class TestMomentumQualityScore:
    def test_insufficient_history_returns_zero(self):
        closes = [100.0] * 50
        assert _momentum_quality_score(closes, 49) == 0.0

    def test_strong_momentum_no_overheat(self):
        closes = [100.0] * 55 + [115.0] * 10 + [116.0]
        idx = len(closes) - 1
        score = _momentum_quality_score(closes, idx)
        assert score > 0.0

    def test_overheat_penalized(self):
        closes = [100.0] * 55 + [115.0] * 9 + [130.0]
        idx_before = len(closes) - 2
        idx_now = len(closes) - 1
        score_before = _momentum_quality_score(closes, idx_before)
        score_now = _momentum_quality_score(closes, idx_now)
        assert score_now < score_before


class TestBreadthScore:
    def test_none_returns_zero(self):
        assert _breadth_score(None) == 0.0

    def test_empty_returns_zero(self):
        assert _breadth_score({}) == 0.0

    def test_high_breadth_positive(self):
        score = _breadth_score({"a": 0.9, "b": 0.9})
        assert score > 0.0

    def test_low_breadth_negative(self):
        score = _breadth_score({"a": 0.1, "b": 0.1})
        assert score < 0.0

    def test_mid_breadth_near_zero(self):
        score = _breadth_score({"a": 0.5, "b": 0.5})
        assert abs(score) < 0.1


class TestClassifyMarketState:
    def test_strong_state_with_breadth(self):
        closes = [100.0] * 120 + [105.0]
        idx = len(closes) - 1
        config = MarketStateConfig(strong_threshold=0.10, weak_threshold=-0.15)
        state, exposure = classify_market_state(
            closes, idx, config,
            breadth_values={"a": 0.7, "b": 0.8},
        )
        assert state == MarketState.STRONG
        assert exposure == config.strong_exposure

    def test_weak_state(self):
        closes = [110.0] * 120 + [95.0]
        idx = len(closes) - 1
        config = MarketStateConfig(strong_threshold=0.25, weak_threshold=-0.10)
        state, exposure = classify_market_state(closes, idx, config)
        assert state == MarketState.WEAK
        assert exposure == config.weak_exposure

    def test_neutral_state(self):
        closes = [100.0] * 121
        idx = len(closes) - 1
        config = MarketStateConfig(strong_threshold=0.50, weak_threshold=-0.50)
        state, exposure = classify_market_state(closes, idx, config)
        assert state == MarketState.NEUTRAL

    def test_custom_exposures_strong(self):
        closes = [100.0] * 121
        idx = len(closes) - 1
        config = MarketStateConfig(
            strong_threshold=-0.50,
            weak_threshold=-0.80,
            strong_exposure=0.90,
            neutral_exposure=0.50,
            weak_exposure=0.10,
        )
        _state, exposure = classify_market_state(closes, idx, config)
        assert exposure == 0.90
