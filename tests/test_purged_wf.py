"""Tests for purged walk-forward splits."""
from datetime import date

import pytest

from quant_rotation.validation import (
    TrainTestSplit,
    purged_walk_forward_splits,
    resolve_walk_forward_splits,
)


def _make_dates(n: int) -> list[date]:
    return [date(2020, 1, 1) + date.resolution * i for i in range(n)]


class TestPurgedWalkForwardSplits:
    def test_gap_removes_adjacent_dates(self):
        dates = _make_dates(600)
        train_window = 252
        test_window = 63
        gap = 20
        splits = purged_walk_forward_splits(
            dates, train_window, test_window, gap=gap
        )
        for split in splits:
            train_end_idx = split.train_end_index
            test_start_idx = split.test_start_index
            assert test_start_idx - train_end_idx > gap

    def test_gap_zero_equivalent_to_no_gap(self):
        dates = _make_dates(500)
        train_window = 200
        test_window = 50
        purged = purged_walk_forward_splits(
            dates, train_window, test_window, gap=0
        )
        regular = resolve_walk_forward_splits(
            dates, train_window, test_window
        )
        assert len(purged) == len(regular)
        for p, r in zip(purged, regular):
            assert p.train_start_index == r.train_start_index
            assert p.train_end_index == r.train_end_index
            assert p.test_start_index == r.test_start_index

    def test_large_gap_reduces_folds(self):
        dates = _make_dates(600)
        train_window = 252
        test_window = 63
        splits_no_gap = resolve_walk_forward_splits(
            dates, train_window, test_window
        )
        splits_big_gap = purged_walk_forward_splits(
            dates, train_window, test_window, gap=50
        )
        assert len(splits_big_gap) <= len(splits_no_gap)

    def test_insufficient_data_raises(self):
        dates = _make_dates(100)
        with pytest.raises(ValueError):
            purged_walk_forward_splits(
                dates, train_window=100, test_window=50, gap=20
            )

    def test_negative_gap_raises(self):
        dates = _make_dates(500)
        with pytest.raises(ValueError):
            purged_walk_forward_splits(
                dates, train_window=100, test_window=50, gap=-1
            )

    def test_partial_fold_included(self):
        dates = _make_dates(400)
        splits = purged_walk_forward_splits(
            dates, train_window=200, test_window=100, gap=10,
            include_partial_fold=True,
        )
        assert len(splits) > 0
        last = splits[-1]
        assert last.test_end_index == 399

    def test_train_window_before_gap_respected(self):
        dates = _make_dates(600)
        splits = purged_walk_forward_splits(
            dates, train_window=252, test_window=63, gap=20, step=63
        )
        for split in splits:
            assert split.train_end_index - split.train_start_index + 1 >= 252

    def test_test_window_respected(self):
        dates = _make_dates(600)
        splits = purged_walk_forward_splits(
            dates, train_window=252, test_window=63, gap=20
        )
        for split in splits:
            assert split.test_end_index - split.test_start_index + 1 == 63
