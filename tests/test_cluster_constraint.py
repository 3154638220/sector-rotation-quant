"""Tests for industry cluster constraint."""
import pytest

from quant_rotation.portfolio import (
    INDUSTRY_CLUSTER_SW2021,
    select_top_k,
    select_with_cluster_constraint,
    equal_weight_target,
    softmax_weight_target,
    rank_weight_target,
)


class TestSelectTopK:
    def test_basic_selection(self):
        scores = {"A": 0.8, "B": 0.5, "C": 0.9, "D": 0.3}
        top3 = select_top_k(scores, 3)
        assert top3 == ["C", "A", "B"]

    def test_top_k_exceeds_items(self):
        scores = {"A": 0.8, "B": 0.5}
        top5 = select_top_k(scores, 5)
        assert set(top5) == {"A", "B"}
        assert len(top5) == 2

    def test_zero_top_k_raises(self):
        with pytest.raises(ValueError):
            select_top_k({"A": 0.5}, 0)


class TestClusterConstraint:
    def test_no_same_cluster_exceeds_limit(self):
        scores = {
            "计算机": 0.9,
            "电子": 0.85,
            "通信": 0.80,
            "医药生物": 0.75,
            "银行": 0.70,
        }
        selected = select_with_cluster_constraint(
            scores, top_k=4, max_per_cluster=2
        )
        tmt_selected = [i for i in selected if i in INDUSTRY_CLUSTER_SW2021["TMT"]]
        assert len(tmt_selected) <= 2

    def test_capped_at_top_k(self):
        scores = {
            "计算机": 0.9,
            "医药生物": 0.85,
            "银行": 0.80,
            "非银金融": 0.75,
            "公用事业": 0.70,
        }
        selected = select_with_cluster_constraint(
            scores, top_k=3, max_per_cluster=2
        )
        assert len(selected) <= 3

    def test_unmapped_industries_not_filtered(self):
        scores = {"未知行业X": 0.9, "未知行业Y": 0.8}
        selected = select_with_cluster_constraint(
            scores, top_k=2, max_per_cluster=2
        )
        assert len(selected) == 2

    def test_max_per_cluster_one(self):
        scores = {
            "计算机": 0.9,
            "电子": 0.85,
            "通信": 0.80,
        }
        selected = select_with_cluster_constraint(
            scores, top_k=3, max_per_cluster=1
        )
        tmt_selected = [i for i in selected if i in INDUSTRY_CLUSTER_SW2021["TMT"]]
        assert len(tmt_selected) <= 1


class TestWeightWithHoldingsOverride:
    def test_equal_weight_with_override(self):
        scores = {"A": 0.9, "B": 0.8, "C": 0.5, "D": 0.3}
        weights = equal_weight_target(
            scores, top_k=3, exposure=1.0, max_weight=0.5,
            holdings=["A", "D"],
        )
        assert set(weights.keys()) == {"A", "D"}
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_softmax_with_override(self):
        scores = {"A": 0.9, "B": 0.8, "C": 0.5, "D": 0.3}
        weights = softmax_weight_target(
            scores, top_k=3, exposure=1.0, max_weight=1.0,
            temperature=1.0, holdings=["A", "D"],
        )
        assert set(weights.keys()) == {"A", "D"}
        assert sum(weights.values()) == pytest.approx(1.0)
        assert weights["A"] > weights["D"]

    def test_rank_weight_with_override(self):
        scores = {"A": 0.9, "B": 0.8, "C": 0.5, "D": 0.3}
        weights = rank_weight_target(
            scores, top_k=3, exposure=1.0, max_weight=1.0,
            holdings=["A", "B", "D"],
        )
        assert set(weights.keys()) == {"A", "B", "D"}
        assert sum(weights.values()) == pytest.approx(1.0)
        assert weights["A"] > weights["B"] > weights["D"]

    def test_rank_weight_exposure_half(self):
        scores = {"A": 0.9, "B": 0.8, "C": 0.5}
        weights = rank_weight_target(
            scores, top_k=3, exposure=0.5, max_weight=1.0,
            holdings=["A", "B"],
        )
        assert sum(weights.values()) == pytest.approx(0.5)


class TestRankWeight:
    def test_rank_monotonic(self):
        scores = {"A": 0.9, "B": 0.8, "C": 0.5}
        weights = rank_weight_target(scores, 3, 1.0, 1.0)
        assert weights["A"] > weights["B"] > weights["C"]
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_rank_max_weight_clamped(self):
        scores = {"A": 0.9, "B": 0.2, "C": 0.2}
        weights = rank_weight_target(scores, 3, 1.0, 0.40)
        for w in weights.values():
            assert w <= 0.40 + 1e-9
