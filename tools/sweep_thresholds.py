"""Run state_aware threshold grid search programmatically."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_rotation.cli import _load_inputs
from src.quant_rotation.sweep import run_parameter_sweep, write_parameter_sweep_reports

config_path = "configs/exp_best_p0.toml"

(
    app_config,
    industry_data,
    amount_data,
    breadth_data,
    valuation_data,
    prosperity_data,
    market_data,
    stock_data,
    stock_amount_data,
    stock_industry_map,
    benchmark_closes,
) = _load_inputs(config_path)

strategy = app_config.strategy

runs = run_parameter_sweep(
    industry_data,
    benchmark_closes,
    strategy,
    amount_data=amount_data,
    breadth_data=breadth_data,
    valuation_data=valuation_data,
    prosperity_data=prosperity_data,
    market_data=market_data,
    market_weights=app_config.market_weights,
    stock_data=stock_data,
    stock_amount_data=stock_amount_data,
    stock_industry_map=stock_industry_map,
    factor_set_names=("ret60_ret5_consistency",),
    top_k_values=(3,),
    risk_off_exposures=(0.0,),
    risk_control_values=(True,),
    market_score_control_values=(True,),
    market_score_threshold_values=(0.0,),
    state_aware_risk_control_values=(True,),
    sideways_exposures=(0.5, 0.7, 0.9),
    bear_exposures=(0.0,),
    bull_thresholds=(0.5, 1.0, 1.5),
    bear_thresholds=(-1.0, -0.5, 0.0),
)

output_dir = Path("reports/exp_state_aware_thresholds_full")
write_parameter_sweep_reports(runs, output_dir)

best = sorted(runs, key=lambda r: -r.result.metrics["sharpe_ratio"])[0]
print(f"\nRuns: {len(runs)}")
print(f"Best: {best.spec.name}")
print(f"Best Sharpe: {best.result.metrics['sharpe_ratio']:.3f}")
print(f"Best ret: {best.result.metrics['annualized_return']*100:.2f}%")
print(f"Best DD: {best.result.metrics['max_drawdown']*100:.2f}%")
print(f"Win rate: {best.result.metrics['monthly_win_rate']*100:.1f}%")
print(f"Calmar: {best.result.metrics['calmar_ratio']:.3f}")
