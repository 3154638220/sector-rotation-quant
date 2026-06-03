from __future__ import annotations

import math
import unittest
from datetime import date, timedelta

from quant_rotation.metrics import annual_returns, summarize_performance


class MetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(30)]
        self.equity = [1.0]
        for i in range(1, 30):
            r = 0.001 if i % 3 != 0 else -0.002
            self.equity.append(self.equity[-1] * (1.0 + r))

    def test_summarize_performance_returns_expected_keys(self) -> None:
        metrics = summarize_performance(
            self.dates,
            self.equity,
            benchmark_equity=self.equity,
            equal_weight_equity=self.equity,
            turnovers=[0.5] * 5,
            costs=[0.001] * 5,
        )
        self.assertIn("annualized_return", metrics)
        self.assertIn("sharpe_ratio", metrics)
        self.assertIn("max_drawdown", metrics)
        self.assertIn("calmar_ratio", metrics)
        self.assertIn("excess_return_vs_benchmark", metrics)

    def test_summarize_performance_empty_sequence_handles_boundary(self) -> None:
        dates = [date(2024, 1, 1)]
        equity = [1.0]
        metrics = summarize_performance(
            dates,
            equity,
            benchmark_equity=equity,
            equal_weight_equity=equity,
            turnovers=[],
            costs=[],
        )
        self.assertEqual(metrics["final_equity"], 1.0)
        self.assertEqual(metrics["sharpe_ratio"], 0.0)
        self.assertEqual(metrics["max_drawdown"], 0.0)

    def test_annual_returns_cross_year_slicing(self) -> None:
        dates = [
            date(2023, 12, 29),
            date(2024, 1, 2),
            date(2024, 6, 30),
            date(2025, 1, 2),
        ]
        equity = [1.0, 1.02, 1.05, 1.10]
        result = annual_returns(dates, equity)
        years = set(result.keys())
        self.assertIn(2024, years)

    def test_sharpe_zero_when_returns_are_zero(self) -> None:
        equity = [1.0] * 30
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(30)]
        metrics = summarize_performance(
            dates, equity,
            benchmark_equity=equity,
            equal_weight_equity=equity,
            turnovers=[],
            costs=[],
        )
        self.assertEqual(metrics["sharpe_ratio"], 0.0)

    def test_max_drawdown_calculated_correctly(self) -> None:
        equity = [
            1.0, 1.1, 0.9, 0.85, 1.0, 1.05, 0.8, 1.0, 1.2
        ]
        dates = [
            date(2024, 1, 1) + timedelta(days=i)
            for i in range(len(equity))
        ]
        metrics = summarize_performance(
            dates, equity,
            benchmark_equity=equity,
            equal_weight_equity=equity,
            turnovers=[0.3],
            costs=[0.001],
        )
        self.assertAlmostEqual(metrics["max_drawdown"], 0.8 / 1.1 - 1.0, places=4)

    def test_excess_return_positive_when_strategy_beats_benchmark(self) -> None:
        strategy = [1.0, 1.02, 1.05, 1.10]
        benchmark = [1.0, 1.01, 1.01, 1.02]
        dates = [
            date(2024, 1, 1) + timedelta(days=i)
            for i in range(len(strategy))
        ]
        metrics = summarize_performance(
            dates, strategy,
            benchmark_equity=benchmark,
            equal_weight_equity=benchmark,
            turnovers=[],
            costs=[],
        )
        self.assertGreater(metrics["excess_return_vs_benchmark"], 0.0)


if __name__ == "__main__":
    unittest.main()
