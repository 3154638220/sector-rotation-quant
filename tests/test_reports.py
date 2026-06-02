from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quant_rotation.backtest import run_backtest
from quant_rotation.data import load_wide_close_csv
from quant_rotation.models import StrategyConfig
from quant_rotation.reports import write_reports
from quant_rotation.sample_data import generate_sample_data


class ReportTests(unittest.TestCase):
    def test_write_reports_includes_holding_and_risk_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            report_dir = root / "reports"
            generate_sample_data(data_dir, days=260, seed=41)
            prices = load_wide_close_csv(data_dir / "industry_close.csv")

            result = run_backtest(
                prices,
                None,
                StrategyConfig(risk_control=False, market_score_control=False),
            )
            write_reports(result, report_dir)

            self.assertTrue((report_dir / "holding_period_returns.csv").exists())
            self.assertTrue(
                (report_dir / "holding_period_return_distribution.csv").exists()
            )
            self.assertTrue((report_dir / "industry_selection_frequency.csv").exists())
            self.assertTrue((report_dir / "risk_control_frequency.csv").exists())

            holding_header = (report_dir / "holding_period_returns.csv").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            industry_header = (
                report_dir / "industry_selection_frequency.csv"
            ).read_text(encoding="utf-8").splitlines()[0]
            risk_text = (report_dir / "risk_control_frequency.csv").read_text(
                encoding="utf-8"
            )

            self.assertIn("strategy_return", holding_header)
            self.assertIn("excess_vs_equal_weight", holding_header)
            self.assertIn("average_selected_weight", industry_header)
            self.assertIn("risk_off_rebalance_share", risk_text)


if __name__ == "__main__":
    unittest.main()
