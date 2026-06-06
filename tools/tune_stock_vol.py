"""Fine-tune stock vol20 weight for v4c."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_rotation.cli import _load_inputs
from src.quant_rotation.backtest import run_backtest
from dataclasses import replace

config_path = "configs/exp_d_stock_v4c.toml"
(
    app_config, industry_data, amount_data, breadth_data, valuation_data,
    prosperity_data, market_data, stock_data, stock_amount_data,
    stock_industry_map, benchmark_closes,
) = _load_inputs(config_path)
strategy = app_config.strategy

for vol_w in [-0.3, -0.5, -0.7, -0.9, -1.1]:
    for top_n in [2, 3, 5]:
        s = replace(
            strategy,
            stock_selection=replace(
                strategy.stock_selection,
                vol20=vol_w,
                ret5=0.0,
                top_n_per_industry=top_n,
            ),
        )
        result = run_backtest(
            industry_data, benchmark_closes, s,
            amount_data=amount_data, breadth_data=breadth_data,
            valuation_data=valuation_data, prosperity_data=prosperity_data,
            market_data=market_data, market_weights=app_config.market_weights,
            stock_data=stock_data, stock_amount_data=stock_amount_data,
            stock_industry_map=stock_industry_map,
        )
        m = result.metrics
        print(
            f"vol={vol_w:5.1f}  top_n={top_n}  "
            f"Sharpe={m['sharpe_ratio']:.3f}  "
            f"ret={m['annualized_return']*100:.2f}%  "
            f"DD={m['max_drawdown']*100:.2f}%  "
            f"t/o={m['average_turnover']*100:.1f}%  "
            f"win={m['monthly_win_rate']*100:.1f}%"
        )
