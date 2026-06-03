from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quant_rotation.config import load_config

PROJECT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_load_config_parses_production_toml(self) -> None:
        config_path = PROJECT / "configs" / "production.toml"
        config = load_config(config_path)
        self.assertTrue(config.industry_close_path)
        self.assertIsNotNone(config.strategy)
        self.assertEqual(config.strategy.risk_control, True)
        self.assertEqual(config.strategy.market_score_control, True)

    def test_default_risk_control_mode_is_hard(self) -> None:
        config_path = PROJECT / "configs" / "default.toml"
        config = load_config(config_path)
        self.assertEqual(config.strategy.risk_control_mode, "hard")

    def test_soft_exposure_fields_have_defaults(self) -> None:
        config_path = PROJECT / "configs" / "default.toml"
        config = load_config(config_path)
        self.assertEqual(config.strategy.soft_exposure_min, 0.20)
        self.assertEqual(config.strategy.soft_exposure_max, 1.00)
        self.assertEqual(config.strategy.soft_exposure_center, 0.00)
        self.assertEqual(config.strategy.soft_exposure_steepness, 20.0)

    def test_state_aware_risk_control_defaults_to_false(self) -> None:
        config_path = PROJECT / "configs" / "default.toml"
        config = load_config(config_path)
        self.assertFalse(config.strategy.state_aware_risk_control)
        self.assertEqual(config.strategy.bull_exposure, 1.00)
        self.assertEqual(config.strategy.sideways_exposure, 0.50)
        self.assertEqual(config.strategy.bear_exposure, 0.10)

    def test_factor_weights_are_parsed(self) -> None:
        config_path = PROJECT / "configs" / "production.toml"
        config = load_config(config_path)
        fw = config.strategy.factor_weights
        self.assertEqual(fw.ret60, 1.0)
        self.assertTrue(fw.ret20 == 0.0)

    def test_market_weights_are_parsed(self) -> None:
        config_path = PROJECT / "configs" / "production.toml"
        config = load_config(config_path)
        self.assertIn("CSI300", config.market_weights)
        self.assertAlmostEqual(
            sum(config.market_weights.values()), 1.0, places=1
        )

    def test_missing_required_field_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text("[data]\n", encoding="utf-8")
            with self.assertRaises(KeyError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
