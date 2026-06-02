# Quant Rotation

This project implements the first version described in `plan.md`: an
industry momentum rotation framework for A-share industry indices.

It is a research scaffold, not investment advice. The initial model uses
industry close prices plus a benchmark close series:

- monthly or 20-trading-day rebalance
- 20/60/120 day momentum
- optional 20-day versus 120-day industry amount strength
- optional industry breadth from constituents above MA20/MA60
- optional market/style momentum score for risk-on/risk-off filtering
- 20 day volatility penalty
- 5 day overheating penalty
- Top K equal-weight industry allocation
- optional Top N stock selection inside selected industries
- market trend risk control with benchmark close versus MA120
- transaction cost, turnover, drawdown, Sharpe, Calmar, monthly win rate,
  excess return, and annual return reporting

## Quick Start

Install real-data support and fetch the current real-data set:

```powershell
python -m pip install -e .[real-data]
$env:PYTHONPATH="src"
python -m quant_rotation fetch-real-data `
  --output data/real `
  --start 2021-01-01 `
  --end 2026-06-02 `
  --benchmark sh000300 `
  --request-interval 0.2
```

This writes:

- `data/real/industry_close.csv`
- `data/real/industry_amount.csv` when AKShare returns amount or volume fields
- `data/real/benchmark_close.csv`
- `data/real/manifest.json`

Run the production candidate:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation run --config configs/production.toml
```

Production reports are written to `reports/production/`:

- `metrics.csv`
- `equity_curve.csv`
- `rebalances.csv`
- `annual_returns.csv`

The production config currently uses the simplified `ret60 + ret5` industry
model: 60-day industry momentum, 5-day overheating penalty, Top 5 industries,
and zero exposure when market risk controls are off.

For a deterministic sample-data smoke test:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation sample-data --output data/sample --days 520
python -m quant_rotation run --config configs/default.toml
```

Run factor decomposition backtests:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation decompose --config configs/production.toml --industry-only
```

Run a parameter sweep around candidate factor models:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation sweep --config configs/production.toml --industry-only
```

Run train/test validation:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation validate `
  --config configs/production.toml `
  --industry-only `
  --train-end 2024-12-31 `
  --test-start 2025-01-01
```

Run rolling walk-forward multi-fold validation:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation validate `
  --config configs/production.toml `
  --industry-only `
  --walk-forward `
  --train-window 504 `
  --test-window 126 `
  --selection-metric composite
```

The decomposition command keeps rebalance rules, transaction cost, and risk
controls fixed, then reruns the strategy with the full model, factor groups, and
single industry factors. It also runs leave-one-factor-out ablations to estimate
each factor's marginal contribution inside the configured full model. It writes:

- `factor_decomposition.csv`
- `factor_ablation.csv`
- `factor_equity_curves.csv`
- `factor_annual_returns.csv`

The sweep command defaults to the current narrow candidate set:
`ret60` and `ret60_ret5`, `top_k=5`, `risk_off_exposure=0,0.3,0.5`,
and both `risk_control=true/false` plus `market_score_control=true/false`
when a benchmark or market data is available. Use `--factor-set`, `--top-k`,
`--risk-control`, and `--market-score-control` to widen or narrow that space.
It writes:

- `parameter_sweep.csv`
- `parameter_sweep_equity_top.csv`
- `parameter_sweep_annual_returns.csv`

The validation command runs the same candidate set, ranks candidates on the
train segment, and reports the selected candidate's test-segment performance.
By default it selects with `--selection-metric composite`, computed as
train excess return versus equal weight plus Calmar plus Sharpe, less turnover
and absolute drawdown penalties. Pass `--selection-metric annualized_return` to
reproduce the older train-return ranking.
It writes:

- `train_test_validation.csv`
- `train_test_selected_equity.csv`
- `train_test_annual_returns.csv`

With `--walk-forward`, validation rolls a fixed train window forward, selects
the best candidate inside each train fold, and reports the selected candidate's
out-of-sample test fold. It writes:

- `walk_forward_candidates.csv`
- `walk_forward_folds.csv`
- `walk_forward_selected_equity.csv`
- `walk_forward_oos_equity.csv`
- `fixed_candidate_summary.csv`
- `walk_forward_summary.csv`

`fixed_candidate_summary.csv` ignores dynamic train-fold selection and instead
chains each fixed candidate's OOS fold equity across the whole walk-forward
period, then ranks candidates by the chained final equity. Treat all real-data
walk-forward conclusions as provisional while the effective history only
contains a small number of folds; prefer fetching and validating the longest
reliable historical range before considering any candidate a finalized strategy.

To extend the real-data history for more reliable validation, fetch a longer
dataset:

```powershell
python -m pip install -e .[real-data]
$env:PYTHONPATH="src"
python -m quant_rotation fetch-real-data `
  --output data/real_extended `
  --start 2010-01-04 `
  --end 2026-06-02 `
  --benchmark sh000300 `
  --request-interval 0.2
```

Run tests:

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
```

## Data Format

Industry close data uses a wide CSV:

```csv
date,Agriculture,Coal,Bank
2024-01-02,1000.0,1000.0,1000.0
2024-01-03,1002.1,998.4,1001.7
```

Industry amount data is optional and uses the same wide format:

```csv
date,Agriculture,Coal,Bank
2024-01-02,820000000.0,760000000.0,1200000000.0
2024-01-03,910000000.0,810000000.0,1300000000.0
```

Industry breadth data is optional and uses one wide CSV per breadth window.
Values are ratios from 0 to 1, such as the share of constituents with close
above MA20 or MA60:

```csv
date,Agriculture,Coal,Bank
2024-01-02,0.61,0.48,0.72
2024-01-03,0.64,0.51,0.70
```

Benchmark close data uses:

```csv
date,close
2024-01-02,4000.0
2024-01-03,4004.2
```

Market/style close data is optional and uses a wide CSV. It can hold broad
market indices, growth/value indices, large/small-cap indices, or other regime
proxies:

```csv
date,CSI300,CSIAll,ChiNext
2024-01-02,4000.0,3600.0,2500.0
2024-01-03,4004.2,3608.1,2512.4
```

Stock close and amount data are optional and use the same wide format as
industry data. Stock selection also requires a stock-to-industry map:

```csv
stock,industry
Agriculture_01,Agriculture
Agriculture_02,Agriculture
Coal_01,Coal
```

When stock selection is enabled, the model first selects industries, then ranks
stocks within those industries using 20/60-day momentum, optional amount
strength, 20-day volatility, and 5-day overheating penalty.

## Real Data

The `fetch-real-data` command downloads Shenwan level-1 industry index close
prices through AKShare and writes them in the same CSV format as the sample
data. By default it also downloads CSI 300 as the market benchmark using
symbol `sh000300`.

The generated files are:

- `data/real/industry_close.csv`
- `data/real/industry_amount.csv` when AKShare returns amount or volume fields
- `data/real/benchmark_close.csv`
- `data/real/manifest.json`

Useful options:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation fetch-real-data `
  --output data/real `
  --start 2021-01-01 `
  --end 2026-06-02 `
  --benchmark sh000300 `
  --request-interval 0.2
```

The CLI writes reports to `reports/` by default:

- `metrics.csv`
- `equity_curve.csv`
- `rebalances.csv`
- `annual_returns.csv`

`configs/real_ret60.toml` is a simple post-decomposition candidate that keeps
only the 60-day industry momentum factor while preserving the same rebalance,
cost, and market risk controls as `configs/real.toml`.

`configs/real_ret60_ret5_riskoff0.toml` is the current parameter-sweep candidate.
It combines 60-day industry momentum with a 5-day overheating penalty and moves
to zero exposure when the market risk controls are off.

For the phase-2 price-volume model, add this optional data entry when the file is
available. For the phase-3 breadth model, also add the breadth files:

```toml
[data]
industry_amount = "../data/real/industry_amount.csv"
industry_breadth20 = "../data/real/industry_breadth20.csv"
industry_breadth60 = "../data/real/industry_breadth60.csv"
market_close = "../data/real/market_close.csv"
stock_close = "../data/real/stock_close.csv"
stock_amount = "../data/real/stock_amount.csv"
stock_industry_map = "../data/real/stock_industry_map.csv"

[factors]
amount_strength_weight = 0.25
breadth20_weight = 0.12
breadth60_weight = 0.08
stock_ret20_weight = 0.45
stock_ret60_weight = 0.25
stock_amount_strength_weight = 0.10
stock_vol20_weight = -0.20
stock_ret5_weight = -0.10

[strategy]
market_score_control = true
market_score_window = 60
market_score_threshold = 0.0
stock_selection = true
stock_top_n_per_industry = 5
stock_min_stocks_per_industry = 3
stock_max_weight = 0.05

[market_weights]
CSI300 = 0.50
CSIAll = 0.30
ChiNext = 0.20
```

When `market_score_control` is enabled, the strategy computes weighted market
momentum over `market_score_window`. If the score is below
`market_score_threshold`, or the benchmark is below MA120, exposure is reduced
to `risk_off_exposure`.

The default sample config enables phase-5 stock selection. For real data, keep
`stock_selection` disabled until the stock close data and historical
stock-to-industry map are prepared without look-ahead bias.
