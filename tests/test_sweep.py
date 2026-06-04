from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from quant_rotation.data import load_wide_close_csv
from quant_rotation.models import PriceData, StrategyConfig
from quant_rotation.sample_data import generate_sample_data
from quant_rotation.sweep import (
    build_parameter_sweep_specs,
    run_parameter_sweep,
    write_parameter_sweep_reports,
)


class ParameterSweepTests(unittest.TestCase):
    def test_build_parameter_sweep_specs_uses_expanded_default_candidates(self) -> None:
        specs = build_parameter_sweep_specs(
            StrategyConfig(),
            risk_off_exposures=(0.0, 0.5),
        )
        names = {spec.name for spec in specs}

        self.assertIn("ret60_top5_riskoff0_riskctrl0_mscore0", names)
        self.assertIn("ret60_ret5_top5_riskoff0p5_riskctrl1_mscore1", names)
        self.assertEqual(
            {spec.factor_set for spec in specs},
            {"ret60", "ret60_ret5", "ret60_ret120", "ret60_ret120_ret5", "rel_ret60_ret5"},
        )
        self.assertEqual({spec.top_k for spec in specs}, {3, 5, 8})
        self.assertEqual({spec.risk_control for spec in specs}, {False, True})
        self.assertEqual(
            {spec.market_score_control for spec in specs},
            {False, True},
        )
        self.assertTrue(any("top3" in name for name in names))
        self.assertFalse(any(name.startswith("all_factors") for name in names))
        self.assertFalse(any("breadth20" in name for name in names))
        self.assertEqual(
            len(specs),
            len({spec.name for spec in specs}),
        )

    def test_parameter_sweep_runs_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            report_dir = root / "reports"
            generate_sample_data(data_dir, days=260, seed=17)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            runs = run_parameter_sweep(
                prices,
                None,
                StrategyConfig(risk_control=False, market_score_control=False),
                top_k_values=(3, 5),
                risk_off_exposures=(0.0,),
            )
            write_parameter_sweep_reports(runs, report_dir, top_n_equity=3)

            self.assertGreater(len(runs), 0)
            self.assertTrue((report_dir / "parameter_sweep.csv").exists())
            self.assertTrue((report_dir / "parameter_sweep_equity_top.csv").exists())
            self.assertTrue((report_dir / "parameter_sweep_annual_returns.csv").exists())

            metrics_text = (report_dir / "parameter_sweep.csv").read_text(
                encoding="utf-8"
            )
            equity_header = (report_dir / "parameter_sweep_equity_top.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            self.assertIn("risk_off_exposure", metrics_text.splitlines()[0])
            self.assertIn("market_score_threshold", metrics_text.splitlines()[0])
            self.assertIn("equal_weight", equity_header)

    def test_market_score_threshold_grid_only_expands_market_score_candidates(
        self,
    ) -> None:
        specs = build_parameter_sweep_specs(
            StrategyConfig(),
            factor_set_names=("ret60",),
            top_k_values=(5,),
            risk_off_exposures=(0.0,),
            risk_control_values=(True,),
            market_score_control_values=(False, True),
            market_score_threshold_values=(-0.05, 0.0, 0.02),
        )

        self.assertEqual(len(specs), 4)
        self.assertEqual(
            sum(1 for spec in specs if not spec.market_score_control),
            1,
        )
        threshold_specs = [
            spec for spec in specs if spec.market_score_control
        ]
        self.assertEqual(
            {spec.market_score_threshold for spec in threshold_specs},
            {-0.05, 0.0, 0.02},
        )
        self.assertTrue(any("_mthrneg0p05" in spec.name for spec in specs))
        self.assertTrue(any("_mthr0p02" in spec.name for spec in specs))

    def test_risk_control_mode_grid_includes_soft_candidates(self) -> None:
        specs = build_parameter_sweep_specs(
            StrategyConfig(),
            factor_set_names=("ret60",),
            top_k_values=(5,),
            risk_off_exposures=(0.0, 0.5),
            risk_control_values=(True,),
            market_score_control_values=(True,),
            risk_control_mode_values=("hard", "soft"),
            soft_exposure_min_values=(0.0, 0.1, 0.2),
        )

        self.assertEqual(len(specs), 5)
        self.assertEqual(
            sum(1 for spec in specs if spec.risk_control_mode == "hard"),
            2,
        )
        self.assertEqual(
            sum(1 for spec in specs if spec.risk_control_mode == "soft"),
            3,
        )
        self.assertEqual(
            {spec.soft_exposure_min for spec in specs if spec.risk_control_mode == "soft"},
            {0.0, 0.1, 0.2},
        )
        self.assertIn(
            "ret60_top5_softoff0p2_modes",
            {spec.name for spec in specs},
        )

    def test_fundamental_factor_sets_are_available_with_data(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        closes = {
            "a": [100.0 * (1.001**i) for i in range(130)],
            "b": [100.0 * (1.002**i) for i in range(130)],
        }
        valuation_data = PriceData(
            dates=dates,
            closes={"a": [0.20] * 130, "b": [0.80] * 130},
        )
        prosperity_data = PriceData(
            dates=dates,
            closes={"a": [0.70] * 130, "b": [0.30] * 130},
        )

        specs = build_parameter_sweep_specs(
            StrategyConfig(),
            valuation_data=valuation_data,
            prosperity_data=prosperity_data,
            factor_set_names=(
                "ret60_valuation",
                "ret60_ret5_valuation",
                "ret60_prosperity",
                "ret60_ret5_fundamental",
            ),
            top_k_values=(1,),
            risk_off_exposures=(0.0,),
            risk_control_values=(False,),
            market_score_control_values=(False,),
        )

        self.assertEqual(
            {spec.factor_set for spec in specs},
            {
                "ret60_valuation",
                "ret60_ret5_valuation",
                "ret60_prosperity",
                "ret60_ret5_fundamental",
            },
        )
        self.assertTrue(any("valuation" in spec.factors for spec in specs))
        self.assertTrue(any("prosperity" in spec.factors for spec in specs))


if __name__ == "__main__":
    unittest.main()
