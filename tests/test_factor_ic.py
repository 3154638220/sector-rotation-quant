"""Tests for factor IC computation."""
import pytest

from tools.factor_ic_analysis import spearman_rank_ic


class TestSpearmanRankIC:
    def test_perfect_positive_correlation(self):
        a = {"i1": 10.0, "i2": 8.0, "i3": 6.0, "i4": 4.0, "i5": 2.0}
        b = {"i1": 50.0, "i2": 40.0, "i3": 30.0, "i4": 20.0, "i5": 10.0}
        rho = spearman_rank_ic(a, b)
        assert rho == pytest.approx(1.0, abs=0.01)

    def test_perfect_negative_correlation(self):
        a = {"i1": 10.0, "i2": 8.0, "i3": 6.0, "i4": 4.0, "i5": 2.0}
        b = {"i1": 10.0, "i2": 20.0, "i3": 30.0, "i4": 40.0, "i5": 50.0}
        rho = spearman_rank_ic(a, b)
        assert rho == pytest.approx(-1.0, abs=0.01)

    def test_no_correlation(self):
        a = {"i1": 1.0, "i2": 2.0, "i3": 3.0, "i4": 4.0, "i5": 5.0}
        b = {"i1": 3.0, "i2": 1.0, "i3": 5.0, "i4": 2.0, "i5": 4.0}
        rho = spearman_rank_ic(a, b)
        assert abs(rho) < 0.5

    def test_too_few_returns_zero(self):
        a = {"i1": 1.0, "i2": 2.0}
        b = {"i1": 3.0, "i2": 4.0}
        rho = spearman_rank_ic(a, b)
        assert rho == 0.0

    def test_non_overlapping_keys(self):
        a = {"i1": 1.0, "i2": 2.0, "i3": 3.0, "i4": 4.0, "i5": 5.0}
        b = {"i6": 6.0, "i7": 7.0, "i8": 8.0, "i9": 9.0, "i10": 10.0}
        rho = spearman_rank_ic(a, b)
        assert rho == 0.0

    def test_ties_handled(self):
        a = {"i1": 1.0, "i2": 1.0, "i3": 3.0, "i4": 4.0, "i5": 4.0}
        b = {"i1": 10.0, "i2": 10.0, "i3": 20.0, "i4": 30.0, "i5": 30.0}
        rho = spearman_rank_ic(a, b)
        assert rho == pytest.approx(1.0, abs=0.01)

    def test_partial_overlap(self):
        a = {"i1": 10.0, "i2": 8.0, "i3": 6.0, "i4": 4.0, "i5": 2.0}
        b = {"i1": 50.0, "i2": 40.0, "i3": 30.0, "i4": 20.0, "i5": 10.0}
        rho = spearman_rank_ic(a, b)
        assert rho == pytest.approx(1.0, abs=0.01)
