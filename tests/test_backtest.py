from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from quant_rotation.backtest import run_backtest, soft_risk_exposure
from quant_rotation.data import (
    align_asset_data,
    align_benchmark,
    load_benchmark_csv,
    load_stock_industry_map_csv,
    load_wide_asset_csv,
    load_wide_close_csv,
)
from quant_rotation.models import (
    BreadthData,
    PriceData,
    StockSelectionConfig,
    StrategyConfig,
)
from quant_rotation.sample_data import generate_sample_data


class BacktestTests(unittest.TestCase):
    def test_sample_backtest_runs_and_rebalances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            generate_sample_data(output, days=260, seed=11)
            prices = load_wide_close_csv(output / "industry_close.csv")
            amounts = align_asset_data(
                prices.dates,
                prices.assets,
                load_wide_asset_csv(output / "industry_amount.csv", value_name="amount"),
                value_name="amount",
            )
            breadth20 = align_asset_data(
                prices.dates,
                prices.assets,
                load_wide_asset_csv(
                    output / "industry_breadth20.csv",
                    value_name="breadth20",
                ),
                value_name="breadth20",
            )
            breadth60 = align_asset_data(
                prices.dates,
                prices.assets,
                load_wide_asset_csv(
                    output / "industry_breadth60.csv",
                    value_name="breadth60",
                ),
                value_name="breadth60",
            )
            raw_market_data = load_wide_close_csv(output / "market_close.csv")
            market_data = align_asset_data(
                prices.dates,
                raw_market_data.assets,
                raw_market_data,
                value_name="market close",
            )
            raw_stock_data = load_wide_close_csv(output / "stock_close.csv")
            stock_data = align_asset_data(
                prices.dates,
                raw_stock_data.assets,
                raw_stock_data,
                value_name="stock close",
            )
            raw_stock_amount_data = load_wide_asset_csv(
                output / "stock_amount.csv",
                value_name="stock amount",
            )
            stock_amount_data = align_asset_data(
                prices.dates,
                raw_stock_amount_data.assets,
                raw_stock_amount_data,
                value_name="stock amount",
            )
            stock_industry_map = load_stock_industry_map_csv(
                output / "stock_industry_map.csv"
            )
            benchmark_dates, benchmark = load_benchmark_csv(output / "benchmark_close.csv")
            aligned = align_benchmark(prices.dates, benchmark_dates, benchmark)

            result = run_backtest(
                prices,
                aligned,
                StrategyConfig(
                    market_score_control=True,
                    stock_selection=StockSelectionConfig(
                        enabled=True,
                        top_n_per_industry=2,
                        min_stocks_per_industry=2,
                        max_stock_weight=0.20,
                    ),
                ),
                amount_data=amounts,
                breadth_data=BreadthData(breadth20=breadth20, breadth60=breadth60),
                market_data=market_data,
                market_weights={"CSI300": 0.5, "CSIAll": 0.3, "ChiNext": 0.2},
                stock_data=stock_data,
                stock_amount_data=stock_amount_data,
                stock_industry_map=stock_industry_map,
            )

            self.assertEqual(len(result.dates), len(result.strategy_equity))
            self.assertGreater(len(result.rebalances), 0)
            self.assertIsNotNone(result.rebalances[0].market_score)
            self.assertGreater(len(result.rebalances[0].selected_industries), 0)
            self.assertTrue(all("_" in stock for stock in result.rebalances[0].holdings))
            self.assertIn("annualized_return", result.metrics)
            self.assertIn("excess_return_vs_benchmark", result.metrics)

    def test_market_score_control_reduces_exposure_when_market_momentum_is_weak(
        self,
    ) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(150)]
        prices = PriceData(
            dates=dates,
            closes={
                "strong": [100.0 * (1.002**i) for i in range(150)],
                "weak": [100.0 * (1.001**i) for i in range(150)],
            },
        )
        market_data = PriceData(
            dates=dates,
            closes={
                "Market": [100.0 * (0.998**i) for i in range(150)],
            },
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
                risk_off_exposure=0.25,
            ),
            market_data=market_data,
        )

        self.assertGreater(len(result.rebalances), 0)
        self.assertLess(result.rebalances[0].market_score or 0.0, 0.0)
        self.assertFalse(result.rebalances[0].market_score_ok)
        self.assertFalse(result.rebalances[0].risk_on)
        self.assertAlmostEqual(result.rebalances[0].exposure, 0.25)

    def test_soft_risk_exposure_extremes(self) -> None:
        self.assertAlmostEqual(soft_risk_exposure(0.0, center=0.0, steepness=20.0, min_exp=0.2, max_exp=1.0), 0.6, places=1)
        self.assertAlmostEqual(soft_risk_exposure(-10.0, center=0.0, steepness=20.0, min_exp=0.2, max_exp=1.0), 0.2, places=4)
        self.assertAlmostEqual(soft_risk_exposure(10.0, center=0.0, steepness=20.0, min_exp=0.2, max_exp=1.0), 1.0, places=4)
        self.assertAlmostEqual(soft_risk_exposure(0.0, center=0.0, steepness=20.0, min_exp=0.3, max_exp=0.8), 0.55, places=1)

    def test_soft_risk_exposure_reduces_drawdown_via_min_floor(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(150)]
        prices = PriceData(
            dates=dates,
            closes={
                "strong": [100.0 * (1.002**i) for i in range(150)],
                "weak": [100.0 * (1.001**i) for i in range(150)],
            },
        )
        market_data = PriceData(
            dates=dates,
            closes={
                "Market": [100.0 * (0.98**i) for i in range(150)],
            },
        )

        hard_result = run_backtest(
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
                risk_control_mode="hard",
            ),
            market_data=market_data,
        )
        self.assertGreater(len(hard_result.rebalances), 0)
        self.assertEqual(hard_result.rebalances[0].exposure, 0.0)

        soft_result = run_backtest(
            prices,
            None,
            StrategyConfig(
                rebalance_every=20,
                top_k=1,
                max_industry_weight=1.0,
                risk_control=False,
                market_score_control=True,
                market_score_window=20,
                risk_control_mode="soft",
                soft_exposure_min=0.2,
                soft_exposure_max=1.0,
                soft_exposure_center=0.0,
                soft_exposure_steepness=20.0,
            ),
            market_data=market_data,
        )
        self.assertGreater(len(soft_result.rebalances), 0)
        self.assertGreater(soft_result.rebalances[0].exposure, 0.0)
        self.assertLess(soft_result.rebalances[0].exposure, 0.5)


if __name__ == "__main__":
    unittest.main()
