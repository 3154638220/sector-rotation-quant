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


if __name__ == "__main__":
    unittest.main()
