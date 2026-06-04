from __future__ import annotations

import unittest
from datetime import date, timedelta

from quant_rotation.factors import (
    compute_factor_snapshot,
    period_return,
    trailing_mean,
    trend_consistency,
    zscore,
)
from quant_rotation.models import BreadthData, FactorWeights, PriceData


class FactorTests(unittest.TestCase):
    def test_zscore_handles_flat_cross_section(self) -> None:
        result = zscore({"a": 1.0, "b": 1.0})
        self.assertEqual(result, {"a": 0.0, "b": 0.0})

    def test_compute_factor_snapshot_ranks_stronger_series(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        strong = [100.0 * (1.004**i) for i in range(130)]
        weak = [100.0 * (1.001**i) for i in range(130)]
        data = PriceData(dates=dates, closes={"strong": strong, "weak": weak})

        snapshot = compute_factor_snapshot(data, 129, FactorWeights())

        self.assertGreater(snapshot.scores["strong"], snapshot.scores["weak"])
        self.assertIn("ret120", snapshot.fields)

    def test_trailing_mean_uses_current_window(self) -> None:
        self.assertEqual(trailing_mean([1.0, 2.0, 3.0, 4.0], 3, 2), 3.5)

    def test_amount_strength_rewards_recent_liquidity_expansion(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        closes = [100.0 * (1.001**i) for i in range(130)]
        data = PriceData(
            dates=dates,
            closes={"active": closes, "quiet": closes},
        )
        amount_data = PriceData(
            dates=dates,
            closes={
                "active": [100.0] * 110 + [300.0] * 20,
                "quiet": [100.0] * 130,
            },
        )

        snapshot = compute_factor_snapshot(
            data,
            129,
            FactorWeights(),
            amount_data=amount_data,
        )

        self.assertGreater(snapshot.scores["active"], snapshot.scores["quiet"])
        self.assertIn("amount_strength", snapshot.fields)

    def test_breadth_rewards_broad_participation(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        closes = [100.0 * (1.001**i) for i in range(130)]
        data = PriceData(
            dates=dates,
            closes={"broad": closes, "narrow": closes},
        )
        breadth_data = BreadthData(
            breadth20=PriceData(
                dates=dates,
                closes={
                    "broad": [0.75] * 130,
                    "narrow": [0.35] * 130,
                },
            ),
            breadth60=PriceData(
                dates=dates,
                closes={
                    "broad": [0.70] * 130,
                    "narrow": [0.30] * 130,
                },
            ),
        )

        snapshot = compute_factor_snapshot(
            data,
            129,
            FactorWeights(),
            breadth_data=breadth_data,
        )

        self.assertGreater(snapshot.scores["broad"], snapshot.scores["narrow"])
        self.assertIn("breadth20", snapshot.fields)
        self.assertIn("breadth60", snapshot.fields)

    def test_breadth_rejects_values_outside_ratio_range(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        closes = [100.0 * (1.001**i) for i in range(130)]
        data = PriceData(
            dates=dates,
            closes={"a": closes, "b": closes},
        )
        breadth_data = BreadthData(
            breadth20=PriceData(
                dates=dates,
                closes={
                    "a": [1.10] * 130,
                    "b": [0.30] * 130,
                },
            ),
        )

        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            compute_factor_snapshot(
                data,
                129,
                FactorWeights(),
                breadth_data=breadth_data,
            )

    def test_valuation_and_prosperity_affect_scores(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        closes = [100.0 * (1.001**i) for i in range(130)]
        data = PriceData(
            dates=dates,
            closes={"cheap_growth": closes, "expensive_slow": closes},
        )
        valuation_data = PriceData(
            dates=dates,
            closes={
                "cheap_growth": [0.15] * 130,
                "expensive_slow": [0.85] * 130,
            },
        )
        prosperity_data = PriceData(
            dates=dates,
            closes={
                "cheap_growth": [0.80] * 130,
                "expensive_slow": [0.20] * 130,
            },
        )

        snapshot = compute_factor_snapshot(
            data,
            129,
            FactorWeights(valuation=0.50, prosperity=0.50),
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
        )

        self.assertGreater(
            snapshot.scores["cheap_growth"],
            snapshot.scores["expensive_slow"],
        )
        self.assertIn("valuation", snapshot.fields)
        self.assertIn("prosperity", snapshot.fields)

    def test_valuation_rejects_values_outside_percentile_range(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        closes = [100.0 * (1.001**i) for i in range(130)]
        data = PriceData(dates=dates, closes={"a": closes, "b": closes})
        valuation_data = PriceData(
            dates=dates,
            closes={"a": [1.10] * 130, "b": [0.20] * 130},
        )

        with self.assertRaisesRegex(ValueError, "valuation values"):
            compute_factor_snapshot(
                data,
                129,
                FactorWeights(valuation=1.0),
                valuation_data=valuation_data,
            )

    def test_trend_consistency_all_up(self) -> None:
        values = [float(i) for i in range(61)]
        result = trend_consistency(values, 60, 60)
        self.assertEqual(result, 1.0)

    def test_trend_consistency_all_down(self) -> None:
        values = [float(60 - i) for i in range(61)]
        result = trend_consistency(values, 60, 60)
        self.assertEqual(result, 0.0)

    def test_trend_consistency_mixed(self) -> None:
        values = [1.0, 2.0, 1.0, 2.0, 1.0, 2.0]
        result = trend_consistency(values, 5, 5)
        self.assertEqual(result, 0.6)

    def test_period_return_basic(self) -> None:
        values = [100.0 + i for i in range(50)]
        ret = period_return(values, 49, 40, 20)
        expected = values[49 - 20] / values[49 - 40] - 1.0
        self.assertAlmostEqual(ret, expected)

    def test_rel_ret60_reduces_beta_exposure(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        high_beta = [100.0 * (1.005**i) for i in range(130)]
        low_beta = [100.0 * (1.001**i) for i in range(130)]
        data = PriceData(
            dates=dates,
            closes={"high_beta": high_beta, "low_beta": low_beta},
        )
        market = PriceData(
            dates=dates,
            closes={"CSI300": [100.0 * (1.003**i) for i in range(130)]},
        )
        market_weights = {"CSI300": 1.0}

        snapshot_rel = compute_factor_snapshot(
            data,
            129,
            FactorWeights(rel_ret60=1.0),
            market_data=market,
            market_weights=market_weights,
        )

        self.assertIn("rel_ret60", snapshot_rel.fields)

    def test_consistency60_factor_increases_with_up_trend(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        trending_up = [100.0 * (1.004**i) for i in range(130)]
        trending_down = [100.0 * (1.004**(130 - i)) for i in range(130)]
        data = PriceData(
            dates=dates,
            closes={"up": trending_up, "down": trending_down},
        )
        snapshot = compute_factor_snapshot(
            data,
            129,
            FactorWeights(consistency60=1.0),
        )
        self.assertGreater(snapshot.scores["up"], snapshot.scores["down"])
        self.assertIn("consistency60", snapshot.fields)


if __name__ == "__main__":
    unittest.main()
