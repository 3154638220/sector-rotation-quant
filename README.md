# Quant Rotation

This project implements the first version described in `plan.md`: an
industry momentum rotation framework for A-share industry indices.

It is a research scaffold, not investment advice. The initial model uses
industry close prices plus a benchmark close series:

- monthly or 20-trading-day rebalance
- 20/60/120 day momentum
- optional 20-day versus 120-day industry amount strength
- optional industry breadth from constituents above MA20/MA60
- optional industry valuation percentile and prosperity proxy factors
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
- `data/real/market_close.csv` with default `CSI300`, `CSIAll`, and `ChiNext` columns
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

Sample data includes `industry_valuation.csv` and `industry_prosperity.csv` so
the optional fundamental-factor plumbing can be smoke-tested without external
data.

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

Run a sample-data fundamental-factor sweep:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation sweep `
  --config configs/default.toml `
  --industry-only `
  --factor-set ret60_valuation,ret60_ret5_valuation,ret60_prosperity,ret60_ret5_fundamental `
  --top-k 5 `
  --risk-off-exposure 0 `
  --risk-control false `
  --market-score-control false `
  --output-dir reports/sample_fundamental_sweep
```

Run a focused market score threshold calibration:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation sweep `
  --config configs/production.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-off-exposure 0 `
  --risk-control true `
  --market-score-control true `
  --market-score-threshold=-0.05,-0.02,0,0.02,0.05 `
  --output-dir reports/production/market_threshold_sweep
```

Run the same threshold calibration across dated SW industry universes and stitch
matching candidates into one long-history ranking:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation sweep-segments `
  --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-off-exposure 0 `
  --risk-control true `
  --market-score-control true `
  --market-score-threshold=-0.05,-0.02,0,0.02,0.05 `
  --output-dir reports/segmented_threshold_sweep
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

The sweep command defaults to the current candidate set:
`ret60`, `ret60_ret5`, `ret60_ret120`, and `ret60_ret120_ret5`,
`top_k=3,5,8`, `risk_off_exposure=0,0.2,0.3,0.5`, and both
`risk_control=true/false` plus `market_score_control=true/false` when a
benchmark or market data is available. Use `--factor-set`, `--top-k`,
`--risk-control`, `--market-score-control`, and `--market-score-threshold` to
widen or narrow that space. Threshold values only expand candidates where
`market_score_control=true`. When `industry_valuation.csv` or
`industry_prosperity.csv` is configured, additional factor sets are available:
`ret60_valuation`, `ret60_ret5_valuation`, `ret60_prosperity`, and
`ret60_ret5_fundamental`.
It writes:

- `parameter_sweep.csv`
- `parameter_sweep_equity_top.csv`
- `parameter_sweep_annual_returns.csv`

The `sweep-segments` command runs the same candidate grid for each ordered
segment config, stitches candidates with matching names, and writes the same
sweep files plus `parameter_sweep_segments.csv` for per-segment attribution.

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
industry data. Stock selection also requires a stock-to-industry map. A static
map uses one row per stock:

```csv
stock,industry
Agriculture_01,Agriculture
Agriculture_02,Agriculture
Coal_01,Coal
```

For historical research, prefer dated snapshots so the backtest uses the latest
mapping available on or before each rebalance signal date:

```csv
snapshot_date,stock,industry
2024-01-01,Agriculture_01,Agriculture
2024-01-01,Coal_01,Coal
2024-07-01,Agriculture_01,Food & Beverage
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
- `data/real/market_close.csv` when market indexes are enabled
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

For longer Shenwan history, use the predefined industry universes that match
major classification eras. The early `sw2000` segment intentionally skips
`market_close.csv` so the data can start at 2010-01-04; market-score control can
fall back to the benchmark in configs that omit `market_close`.

```powershell
python -m quant_rotation fetch-real-data `
  --output data/real_sw2000 `
  --start 2010-01-04 `
  --end 2014-02-20 `
  --benchmark sh000300 `
  --industry-universe sw2000 `
  --market-indexes=

python -m quant_rotation fetch-real-data `
  --output data/real_sw2014 `
  --start 2014-02-21 `
  --end 2021-12-10 `
  --benchmark sh000300 `
  --industry-universe sw2014

python -m quant_rotation fetch-real-data `
  --output data/real_sw2021 `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --benchmark sh000300 `
  --industry-universe sw2021
```

Historical SW constituent snapshots can be imported from a ready snapshot CSV,
expanded from an interval CSV, or fetched from supported external sources. AKShare
`index_component_sw` does not expose a historical date parameter, so use one of
these routes before treating stock-level or breadth data as production research:

```powershell
$env:PYTHONPATH="src"

# Reproducible SW 2021 classification-table source from the SWS download center.
python -m quant_rotation fetch-historical-constituents `
  --source sws `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --output data/real_sw2021/stock_industry_map_historical.csv `
  --snapshot-frequency event `
  --no-ssl-verify

# Production-grade interval sources when credentials/data are available.
python -m quant_rotation fetch-historical-constituents `
  --source joinquant `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --output data/real_sw2021/stock_industry_map_historical.csv

python -m quant_rotation fetch-historical-constituents `
  --source csv-intervals `
  --input vendor/sw_member_intervals.csv `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --output data/real_sw2021/stock_industry_map_historical.csv
```

The `fetch-breadth-data` command computes phase-3 industry breadth files from
SW industry constituents and A-share stock closes. Without
`--constituent-snapshots`, it still uses AKShare current constituents and should
be treated as a research approximation:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation fetch-breadth-data `
  --output data/real `
  --start 2021-12-13 `
  --end 2026-06-02 `
  --windows 20,60 `
  --request-interval 0.2
```

With a historical snapshot CSV, breadth is computed from point-in-time
constituents:

```powershell
python -m quant_rotation fetch-breadth-data `
  --output data/real_sw2021 `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --windows 20,60 `
  --constituent-snapshots data/real_sw2021/stock_industry_map_historical.csv `
  --request-interval 0.2
```

This writes `industry_breadth20.csv`, `industry_breadth60.csv`, and
`breadth_manifest.json`.

Fundamental factor files are plain wide CSVs aligned to `industry_close.csv`.
`industry_valuation.csv` should contain 0-1 historical valuation percentiles,
where lower values are cheaper and therefore score higher. `industry_prosperity.csv`
contains a signed or standardized prosperity proxy where higher values score
higher. These files can be precomputed from PE/PB histories, earnings revisions,
PMI-style data, or other external sources:

```toml
[data]
industry_valuation = "../data/real/industry_valuation.csv"
industry_prosperity = "../data/real/industry_prosperity.csv"

[factors]
valuation_weight = 0.15
prosperity_weight = 0.15
```

The `fetch-stock-data` command prepares phase-5 stock-selection inputs. Use
`--constituent-snapshots` for point-in-time stock-industry membership, and use
`--max-stocks-per-industry` for a small smoke test before fetching the full
constituent universe:

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation fetch-stock-data `
  --output data/real `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --adjust qfq `
  --max-stocks-per-industry 5 `
  --request-interval 0.2
```

```powershell
python -m quant_rotation fetch-stock-data `
  --output data/real_sw2021 `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --adjust qfq `
  --constituent-snapshots data/real_sw2021/stock_industry_map_historical.csv `
  --request-interval 0.2
```

This writes `stock_close.csv`, `stock_amount.csv` when AKShare returns amount
or volume fields, `stock_industry_map.csv`, and `stock_manifest.json`. The
manifest records whether the map came from current constituents or historical
snapshots.

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
industry_valuation = "../data/real/industry_valuation.csv"
industry_prosperity = "../data/real/industry_prosperity.csv"
market_close = "../data/real/market_close.csv"
stock_close = "../data/real/stock_close.csv"
stock_amount = "../data/real/stock_amount.csv"
stock_industry_map = "../data/real/stock_industry_map.csv"

[factors]
amount_strength_weight = 0.25
breadth20_weight = 0.12
breadth60_weight = 0.08
valuation_weight = 0.15
prosperity_weight = 0.15
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
stock-to-industry map snapshots are prepared without look-ahead bias.
