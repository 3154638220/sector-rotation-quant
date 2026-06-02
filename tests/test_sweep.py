from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quant_rotation.data import load_wide_close_csv
from quant_rotation.models import StrategyConfig
from quant_rotation.sample_data import generate_sample_data
from quant_rotation.sweep import (
    build_parameter_sweep_specs,
    run_parameter_sweep,
    write_parameter_sweep_reports,
)


class ParameterSweepTests(unittest.TestCase):
    def test_build_parameter_sweep_specs_crosses_factor_top_k_and_exposure(self) -> None:
        specs = build_parameter_sweep_specs(
            StrategyConfig(),
            top_k_values=(3, 5),
            risk_off_exposures=(0.0, 0.5),
        )
        names = {spec.name for spec in specs}

        self.assertIn("ret60_top3_riskoff0", names)
        self.assertIn("ret60_ret5_top5_riskoff0p5", names)
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
            self.assertIn("equal_weight", equity_header)


if __name__ == "__main__":
    unittest.main()
