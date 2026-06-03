from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from quant_rotation.backtest import run_backtest
from quant_rotation.data import load_wide_close_csv
from quant_rotation.models import PriceData, StrategyConfig
from quant_rotation.sample_data import generate_sample_data


class SignalTests(unittest.TestCase):
    def test_signal_weights_sum_to_exposure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            generate_sample_data(data_dir, days=260, seed=13)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            result = run_backtest(
                prices,
                None,
                StrategyConfig(
                    rebalance_every=20,
                    top_k=5,
                    risk_control=False,
                    market_score_control=False,
                ),
            )
            last = result.rebalances[-1]
            self.assertAlmostEqual(sum(last.weights.values()), last.exposure, places=6)

    def test_signal_holds_top_k_industries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            generate_sample_data(data_dir, days=260, seed=17)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            result = run_backtest(
                prices,
                None,
                StrategyConfig(
                    rebalance_every=20,
                    top_k=3,
                    risk_control=False,
                    market_score_control=False,
                ),
            )
            last = result.rebalances[-1]
            self.assertEqual(len(last.holdings), 3)
            self.assertEqual(len(last.weights), 3)

    def test_signal_handles_risk_off_scenario(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(150)]
        prices = PriceData(
            dates=dates,
            closes={
                "strong": [100.0 * (1.002 ** i) for i in range(150)],
                "weak": [100.0 * (1.001 ** i) for i in range(150)],
            },
        )
        market_data = PriceData(
            dates=dates,
            closes={"Market": [100.0 * (0.98 ** i) for i in range(150)]},
        )

        result = run_backtest(
            prices,
            None,
            StrategyConfig(
                rebalance_every=20,
                top_k=1,
                max_industry_weight=1.0,
                risk_control=False,
                market_score_control=True,
                market_score_window=20,
                risk_off_exposure=0.0,
            ),
            market_data=market_data,
        )

        last = result.rebalances[-1]
        self.assertEqual(last.exposure, 0.0)
        self.assertEqual(last.holdings, [])
        self.assertEqual(last.weights, {})

    def test_signal_json_contains_all_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            generate_sample_data(data_dir, days=260, seed=19)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            result = run_backtest(
                prices,
                None,
                StrategyConfig(
                    rebalance_every=20,
                    top_k=5,
                    risk_control=False,
                    market_score_control=False,
                ),
            )
            last = result.rebalances[-1]

            signal_data = {
                "signal_date": last.signal_date.isoformat(),
                "next_rebalance_date": last.date.isoformat(),
                "holdings": last.holdings,
                "weights": last.weights,
                "exposure": last.exposure,
                "market_trend": last.market_trend,
                "market_score": last.market_score,
                "market_score_ok": last.market_score_ok,
            }
            json_str = json.dumps(signal_data, ensure_ascii=False, default=str)
            parsed = json.loads(json_str)

            for field in [
                "signal_date", "next_rebalance_date", "holdings",
                "weights", "exposure", "market_trend",
                "market_score_ok",
            ]:
                self.assertIn(field, parsed)


if __name__ == "__main__":
    unittest.main()
