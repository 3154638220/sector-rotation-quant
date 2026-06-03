from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quant_rotation.backtest import run_backtest
from quant_rotation.data import load_wide_close_csv
from quant_rotation.models import PriceData, StrategyConfig
from quant_rotation.sample_data import generate_sample_data
from quant_rotation.segments import (
    SegmentBacktestRun,
    SegmentParameterSweepRuns,
    stitch_parameter_sweep_segments,
    stitch_backtest_segments,
    write_segmented_backtest_reports,
    write_segmented_parameter_sweep_reports,
    merge_segment_price_data,
    merge_benchmark_closes,
)
from quant_rotation.sweep import run_parameter_sweep


def _slice_price_data(data: PriceData, start: int, end: int) -> PriceData:
    return PriceData(
        dates=data.dates[start:end],
        closes={
            asset: values[start:end]
            for asset, values in data.closes.items()
        },
    )


class SegmentedBacktestTests(unittest.TestCase):
    def test_stitches_segment_equity_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            report_dir = root / "reports"
            generate_sample_data(data_dir, days=340, seed=53)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")
            config = StrategyConfig(risk_control=False, market_score_control=False)

            first_prices = _slice_price_data(prices, 0, 170)
            second_prices = _slice_price_data(prices, 170, 340)
            first = run_backtest(first_prices, None, config)
            second = run_backtest(second_prices, None, config)

            result = stitch_backtest_segments(
                [
                    SegmentBacktestRun("first", first, len(first_prices.assets)),
                    SegmentBacktestRun("second", second, len(second_prices.assets)),
                ]
            )
            write_segmented_backtest_reports(result, report_dir)

            expected_final = first.metrics["final_equity"] * second.metrics["final_equity"]
            self.assertAlmostEqual(
                result.stitched.metrics["final_equity"],
                expected_final,
            )
            self.assertEqual(result.stitched.dates[0], first_prices.dates[0])
            self.assertEqual(result.stitched.dates[-1], second_prices.dates[-1])
            self.assertTrue((report_dir / "metrics.csv").exists())
            self.assertTrue((report_dir / "equity_curve.csv").exists())
            self.assertTrue((report_dir / "segment_summary.csv").exists())
            self.assertTrue((report_dir / "segmented_equity_curve.csv").exists())

            summary_text = (report_dir / "segment_summary.csv").read_text(
                encoding="utf-8"
            )
            equity_header = (report_dir / "segmented_equity_curve.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            self.assertIn("stitched", summary_text)
            self.assertIn("segment", equity_header)

    def test_stitches_matching_parameter_sweep_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            report_dir = root / "sweep_reports"
            generate_sample_data(data_dir, days=340, seed=71)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")
            config = StrategyConfig(risk_control=False, market_score_control=False)

            first_prices = _slice_price_data(prices, 0, 170)
            second_prices = _slice_price_data(prices, 170, 340)
            first_runs = run_parameter_sweep(
                first_prices,
                None,
                config,
                factor_set_names=("ret60",),
                top_k_values=(3, 5),
                risk_off_exposures=(0.0,),
                risk_control_values=(False,),
                market_score_control_values=(False,),
            )
            second_runs = run_parameter_sweep(
                second_prices,
                None,
                config,
                factor_set_names=("ret60",),
                top_k_values=(3, 5),
                risk_off_exposures=(0.0,),
                risk_control_values=(False,),
                market_score_control_values=(False,),
            )

            result = stitch_parameter_sweep_segments(
                [
                    SegmentParameterSweepRuns(
                        "first",
                        len(first_prices.assets),
                        first_runs,
                    ),
                    SegmentParameterSweepRuns(
                        "second",
                        len(second_prices.assets),
                        second_runs,
                    ),
                ]
            )
            write_segmented_parameter_sweep_reports(result, report_dir)

            self.assertEqual(len(result), 2)
            expected_final = (
                first_runs[0].result.metrics["final_equity"]
                * second_runs[0].result.metrics["final_equity"]
            )
            self.assertAlmostEqual(
                result[0].run.result.metrics["final_equity"],
                expected_final,
            )
            self.assertTrue((report_dir / "parameter_sweep.csv").exists())
            self.assertTrue((report_dir / "parameter_sweep_equity_top.csv").exists())
            self.assertTrue((report_dir / "parameter_sweep_segments.csv").exists())

            segment_text = (report_dir / "parameter_sweep_segments.csv").read_text(
                encoding="utf-8"
            )
            self.assertIn("stitched", segment_text)

    def test_merge_segment_price_data_combines_two_segments(self) -> None:
        from datetime import date
        seg1 = PriceData(
            dates=[date(2024, 1, 1), date(2024, 1, 2)],
            closes={"A": [100.0, 101.0], "B": [200.0, 201.0]},
        )
        seg2 = PriceData(
            dates=[date(2024, 1, 3), date(2024, 1, 4)],
            closes={"A": [102.0, 103.0], "B": [202.0, 203.0]},
        )
        merged = merge_segment_price_data(
            [(seg1, "s1"), (seg2, "s2")], fill_missing=True,
        )
        self.assertEqual(len(merged.dates), 4)
        self.assertEqual(merged.assets, ["A", "B"])
        self.assertEqual(merged.closes["A"], [100.0, 101.0, 102.0, 103.0])

    def test_merge_filters_to_common_industries(self) -> None:
        from datetime import date
        seg1 = PriceData(
            dates=[date(2024, 1, 1)],
            closes={"A": [100.0], "B": [200.0], "C": [300.0]},
        )
        seg2 = PriceData(
            dates=[date(2024, 1, 2)],
            closes={"A": [101.0], "B": [201.0]},
        )
        merged = merge_segment_price_data(
            [(seg1, "s1"), (seg2, "s2")], fill_missing=True,
        )
        self.assertEqual(merged.assets, ["A", "B"])
        self.assertNotIn("C", merged.closes)

    def test_merge_fills_missing_industries_with_nan(self) -> None:
        from datetime import date
        import math
        seg1 = PriceData(
            dates=[date(2024, 1, 1)],
            closes={"A": [100.0], "B": [200.0]},
        )
        seg2 = PriceData(
            dates=[date(2024, 1, 2)],
            closes={"A": [101.0], "B": [201.0], "C": [300.0]},
        )
        seg3 = PriceData(
            dates=[date(2024, 1, 3)],
            closes={"A": [102.0], "B": [202.0]},
        )
        merged = merge_segment_price_data(
            [(seg1, "s1"), (seg2, "s2"), (seg3, "s3")],
            fill_missing=True,
        )
        self.assertEqual(merged.assets, ["A", "B"])
        self.assertEqual(len(merged.closes["A"]), 3)

    def test_merge_benchmark_closes_combines_lists(self) -> None:
        from datetime import date
        merged = merge_benchmark_closes(
            [
                ([date(2024, 1, 1)], [100.0, 101.0], "s1"),
                ([date(2024, 1, 3)], [102.0, 103.0], "s2"),
            ]
        )
        self.assertEqual(merged, [100.0, 101.0, 102.0, 103.0])

    def test_merge_benchmark_returns_none_when_any_segment_has_none(self) -> None:
        from datetime import date
        merged = merge_benchmark_closes(
            [
                ([date(2024, 1, 1)], [100.0, 101.0], "s1"),
                ([], None, "s2"),
            ]
        )
        self.assertIsNone(merged)

    def test_merge_rejects_empty_segments_list(self) -> None:
        with self.assertRaises(ValueError):
            merge_segment_price_data([], fill_missing=True)

    def test_merge_demands_fill_missing_when_industry_disappears(self) -> None:
        from datetime import date
        seg1 = PriceData(
            dates=[date(2024, 1, 1)],
            closes={"A": [100.0], "B": [200.0], "C": [300.0]},
        )
        seg2 = PriceData(
            dates=[date(2024, 1, 2)],
            closes={"A": [101.0]},
        )
        merged = merge_segment_price_data(
            [(seg1, "s1"), (seg2, "s2")], fill_missing=False,
        )
        self.assertEqual(merged.assets, ["A"])


if __name__ == "__main__":
    unittest.main()
