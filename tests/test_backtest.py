from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from quant_rotation.backtest import (
    _annual_budget_exposure_adjustment,
    _select_defensive_holdings,
    classify_market_state,
    filter_by_regime,
    run_backtest,
    soft_risk_exposure,
    vol_target_exposure,
)
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

    def test_classify_market_state_bull(self) -> None:
        closes = [100.0 * (1.001**i) for i in range(130)]

        state = classify_market_state(0.08, closes, 129, 120)

        self.assertEqual(state, "bull")

    def test_classify_market_state_bear(self) -> None:
        state = classify_market_state(-0.05, None, 5, 120)

        self.assertEqual(state, "bear")

    def test_classify_market_state_sideways(self) -> None:
        state = classify_market_state(0.01, None, 5, 120)

        self.assertEqual(state, "sideways")

    def test_state_aware_risk_control_uses_sideways_exposure(self) -> None:
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
                "Market": [100.0 * (1.0005**i) for i in range(150)],
            },
        )

        result = run_backtest(
            prices,
            None,
            StrategyConfig(
                rebalance_every=20,
                top_k=1,
                max_industry_weight=1.0,
                risk_control=True,
                market_score_control=True,
                market_score_window=20,
                state_aware_risk_control=True,
                sideways_exposure=0.5,
                bear_exposure=0.1,
            ),
            market_data=market_data,
        )

        self.assertGreater(len(result.rebalances), 0)
        self.assertTrue(
            any(
                0.45 < event.exposure < 0.55
                for event in result.rebalances
            )
        )

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

    def test_vol_target_exposure_reduces_when_vol_is_high(self) -> None:
        closes = [100.0]
        for _ in range(40):
            closes.append(closes[-1] * (1.0 + 0.03 * (1.0 if len(closes) % 2 == 0 else -1.0)))
        exposure = vol_target_exposure(closes, 39, vol_window=20, target_vol=0.15, max_exposure=1.0)
        self.assertLess(exposure, 1.0)
        self.assertGreaterEqual(exposure, 0.30)

    def test_vol_target_exposure_max_when_vol_is_low(self) -> None:
        closes = [100.0 * (1.001 ** i) for i in range(60)]
        exposure = vol_target_exposure(closes, 59, vol_window=20, target_vol=0.30, max_exposure=1.0)
        self.assertAlmostEqual(exposure, 1.0, places=1)

    def test_vol_target_exposure_short_history_returns_max(self) -> None:
        closes = [100.0, 101.0, 99.0]
        exposure = vol_target_exposure(closes, 2, vol_window=20, max_exposure=1.0)
        self.assertEqual(exposure, 1.0)

    def test_annual_budget_no_trigger_when_below(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]
        equity = [1.0]
        for _ in range(1, len(dates)):
            equity.append(equity[-1] * 1.0005)
        factor = _annual_budget_exposure_adjustment(
            equity, 50, dates, lock_trigger=0.10, min_exposure_after_lock=0.50,
        )
        self.assertEqual(factor, 1.0)

    def test_annual_budget_triggers_above_lock(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(200)]
        dates[50] = date(2024, 1, 1)
        equity = [1.0]
        for _ in range(1, len(dates)):
            equity.append(equity[-1] * 1.0015)
        factor = _annual_budget_exposure_adjustment(
            equity, 99, dates, lock_trigger=0.10, min_exposure_after_lock=0.50,
        )
        self.assertLess(factor, 1.0)

    def test_annual_budget_respects_min_exposure(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(200)]
        equity = [1.0] + [3.0] * 199
        factor = _annual_budget_exposure_adjustment(
            equity, 100, dates, lock_trigger=0.10, min_exposure_after_lock=0.50,
        )
        self.assertGreaterEqual(factor, 0.50)

    def test_defensive_mode_selects_low_vol(self) -> None:
        from quant_rotation.factors import compute_factor_snapshot
        from quant_rotation.models import FactorWeights

        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(150)]
        prices = PriceData(
            dates=dates,
            closes={
                "low_vol": [100.0 * (1.0005 ** i) for i in range(150)],
                "med_vol": [100.0 * (1.001 ** i) for i in range(150)],
                "high_vol": [100.0 * (1.0 + 0.03 * (1.0 if i % 3 == 0 else -0.01)) for i in range(150)],
            },
        )
        snapshot = compute_factor_snapshot(
            prices, 149, FactorWeights(vol20=0.0),
        )
        holdings = _select_defensive_holdings(snapshot, top_k=2)
        self.assertEqual(len(holdings), 2)
        self.assertIn("low_vol", holdings)

    def test_defensive_mode_integration(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(150)]
        prices = PriceData(
            dates=dates,
            closes={
                "low_vol": [100.0 * (1.0005 ** i) for i in range(150)],
                "med_vol": [100.0 * (1.001 ** i) for i in range(150)],
                "high_vol": [100.0 * (1.0 + 0.03 * (1.0 if i % 3 == 0 else -0.01)) for i in range(150)],
            },
        )
        market_data = PriceData(
            dates=dates,
            closes={
                "Market": [100.0 * (0.98 ** i) for i in range(150)],
            },
        )

        result = run_backtest(
            prices,
            None,
            StrategyConfig(
                rebalance_every=20,
                top_k=5,
                max_industry_weight=1.0,
                risk_control=False,
                market_score_control=True,
                market_score_window=20,
                risk_control_mode="soft",
                soft_exposure_min=0.2,
                soft_exposure_max=1.0,
                soft_exposure_center=0.0,
                soft_exposure_steepness=20.0,
                defensive_mode=True,
                defensive_top_k=2,
                defensive_exposure_threshold=0.50,
            ),
            market_data=market_data,
        )
        self.assertGreater(len(result.rebalances), 0)
        self.assertGreater(result.rebalances[0].exposure, 0.0)

    def test_annual_budget_control_integration(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(150)]
        prices = PriceData(
            dates=dates,
            closes={
                "strong": [100.0 * (1.002 ** i) for i in range(150)],
                "weak": [100.0 * (1.001 ** i) for i in range(150)],
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
                market_score_control=False,
                annual_budget_control=True,
                annual_budget_lock_trigger=0.05,
                annual_budget_min_exposure=0.30,
            ),
        )
        self.assertGreater(len(result.rebalances), 0)
        first_exposure = result.rebalances[0].exposure
        self.assertGreaterEqual(first_exposure, 0.0)
        self.assertLessEqual(first_exposure, 1.0)

    def test_filter_by_regime_bear_deweights_cyclical(self) -> None:
        scores = {
            "银行": 0.5,
            "公用事业": 0.3,
            "计算机": 0.8,
            "电子": 0.7,
            "国防军工": 0.6,
        }
        filtered = filter_by_regime(scores, "bear", defensive_cap=0.5)
        self.assertAlmostEqual(filtered["银行"], 0.5)
        self.assertAlmostEqual(filtered["公用事业"], 0.3)
        self.assertAlmostEqual(filtered["计算机"], 0.4)
        self.assertAlmostEqual(filtered["电子"], 0.35)
        self.assertAlmostEqual(filtered["国防军工"], 0.3)

    def test_filter_by_regime_bull_no_change(self) -> None:
        scores = {"计算机": 0.8, "银行": 0.5}
        filtered = filter_by_regime(scores, "bull")
        self.assertEqual(filtered, scores)

    def test_filter_by_regime_unknown_industry_no_crash(self) -> None:
        scores = {"计算机": 0.8, "不明行业": 0.5}
        filtered = filter_by_regime(scores, "bear")
        self.assertAlmostEqual(filtered["计算机"], 0.4)
        self.assertAlmostEqual(filtered["不明行业"], 0.5)

    def test_annual_budget_relative_mode_no_trigger(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]
        full_equity = [1.0]
        for _ in range(1, len(dates)):
            full_equity.append(full_equity[-1] * 1.001)
        full_bench = [1.0]
        for _ in range(1, len(dates)):
            full_bench.append(full_bench[-1] * 1.0008)
        idx = 50
        equity = full_equity[: idx + 1]
        bench_equity = full_bench[: idx + 1]
        factor = _annual_budget_exposure_adjustment(
            equity, idx, dates[: idx + 1],
            mode="relative",
            benchmark_equity=bench_equity,
            relative_excess_target=0.05,
        )
        self.assertEqual(factor, 1.0)

    def test_annual_budget_relative_mode_triggers(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]
        full_equity = [1.0]
        for _ in range(1, len(dates)):
            full_equity.append(full_equity[-1] * 1.004)
        full_bench = [1.0]
        for _ in range(1, len(dates)):
            full_bench.append(full_bench[-1] * 1.0001)
        idx = 50
        equity = full_equity[: idx + 1]
        bench_equity = full_bench[: idx + 1]
        factor = _annual_budget_exposure_adjustment(
            equity, idx, dates[: idx + 1],
            mode="relative",
            benchmark_equity=bench_equity,
            relative_excess_target=0.05,
        )
        self.assertLess(factor, 1.0)

    def test_defensive_sector_filter_integration(self) -> None:
        from quant_rotation.factors import compute_factor_snapshot
        from quant_rotation.models import FactorWeights

        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(150)]
        prices = PriceData(
            dates=dates,
            closes={
                "计算机": [100.0 * (1.002 ** i) for i in range(150)],
                "电子": [100.0 * (1.0015 ** i) for i in range(150)],
                "银行": [100.0 * (1.0005 ** i) for i in range(150)],
                "公用事业": [100.0 * (1.0003 ** i) for i in range(150)],
            },
        )
        market_data = PriceData(
            dates=dates,
            closes={
                "Market": [100.0 * (0.99 ** i) for i in range(150)],
            },
        )

        result = run_backtest(
            prices,
            None,
            StrategyConfig(
                rebalance_every=20,
                top_k=2,
                max_industry_weight=1.0,
                risk_control=False,
                market_score_control=True,
                market_score_window=20,
                risk_off_exposure=0.0,
                defensive_sector_filter=True,
                defensive_sector_cap=0.3,
            ),
            market_data=market_data,
        )
        self.assertGreater(len(result.rebalances), 0)
        first_exposure = result.rebalances[0].exposure
        self.assertGreaterEqual(first_exposure, 0.0)


if __name__ == "__main__":
    unittest.main()
