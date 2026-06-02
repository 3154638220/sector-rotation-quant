from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from quant_rotation.data import align_asset_data, load_wide_asset_csv, load_wide_close_csv
from quant_rotation.decomposition import (
    build_factor_decomposition_specs,
    run_factor_decomposition,
    write_factor_decomposition_reports,
)
from quant_rotation.models import BreadthData, FactorWeights, PriceData, StrategyConfig
from quant_rotation.sample_data import generate_sample_data


class FactorDecompositionTests(unittest.TestCase):
    def test_specs_skip_unavailable_optional_factors(self) -> None:
        specs = build_factor_decomposition_specs(FactorWeights())
        names = {spec.name for spec in specs}

        self.assertIn("all_factors", names)
        self.assertIn("price_momentum", names)
        self.assertIn("without_ret20", names)
        self.assertNotIn("amount_strength", names)
        self.assertNotIn("breadth", names)

    def test_specs_include_available_optional_factors(self) -> None:
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(130)]
        data = PriceData(
            dates=dates,
            closes={"a": [100.0] * 130, "b": [110.0] * 130},
        )
        breadth = BreadthData(breadth20=data)
        specs = build_factor_decomposition_specs(
            FactorWeights(),
            amount_data=data,
            breadth_data=breadth,
        )
        names = {spec.name for spec in specs}

        self.assertIn("amount_strength", names)
        self.assertIn("breadth", names)
        self.assertIn("breadth20", names)
        self.assertIn("without_amount_strength", names)
        self.assertIn("without_breadth20", names)
        self.assertNotIn("breadth60", names)

    def test_decomposition_runs_and_writes_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            report_dir = root / "reports"
            generate_sample_data(data_dir, days=260, seed=13)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")
            amounts = align_asset_data(
                prices.dates,
                prices.assets,
                load_wide_asset_csv(data_dir / "industry_amount.csv", value_name="amount"),
                value_name="amount",
            )
            breadth20 = align_asset_data(
                prices.dates,
                prices.assets,
                load_wide_asset_csv(
                    data_dir / "industry_breadth20.csv",
                    value_name="breadth20",
                ),
                value_name="breadth20",
            )
            breadth60 = align_asset_data(
                prices.dates,
                prices.assets,
                load_wide_asset_csv(
                    data_dir / "industry_breadth60.csv",
                    value_name="breadth60",
                ),
                value_name="breadth60",
            )

            runs = run_factor_decomposition(
                prices,
                None,
                StrategyConfig(risk_control=False, market_score_control=False),
                amount_data=amounts,
                breadth_data=BreadthData(breadth20=breadth20, breadth60=breadth60),
            )
            write_factor_decomposition_reports(runs, report_dir)

            names = {run.spec.name for run in runs}
            self.assertIn("all_factors", names)
            self.assertIn("amount_strength", names)
            self.assertIn("breadth60", names)
            self.assertTrue((report_dir / "factor_decomposition.csv").exists())
            self.assertTrue((report_dir / "factor_equity_curves.csv").exists())
            self.assertTrue((report_dir / "factor_annual_returns.csv").exists())
            self.assertTrue((report_dir / "factor_ablation.csv").exists())

            metrics_text = (report_dir / "factor_decomposition.csv").read_text(
                encoding="utf-8"
            )
            equity_text = (report_dir / "factor_equity_curves.csv").read_text(
                encoding="utf-8"
            )
            ablation_text = (report_dir / "factor_ablation.csv").read_text(
                encoding="utf-8"
            )
            self.assertIn("annualized_return", metrics_text.splitlines()[0])
            self.assertIn("all_factors", equity_text.splitlines()[0])
            self.assertIn("delta_annualized_return_vs_all", ablation_text.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
