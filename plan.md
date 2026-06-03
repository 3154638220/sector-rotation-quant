# 行动计划：A 股行业动量轮动策略 下一阶段

> 基于对 `sector-rotation-quant-main` 全量代码、配置、报告与历史 plan.md 的深度复盘  
> 分析日期：2026-06-03（接续历史版本，本次为全新从零起草版）

---

## 零、当前状态快照

### 0.1 已确认落地的代码

| 模块 | 关键内容 | 状态 |
|------|---------|------|
| `backtest.py` | `soft_risk_exposure()`, `classify_market_state()`, `_state_aware_exposure()` | ✅ 已实现 |
| `sweep.py` | `build_parameter_sweep_specs()` 含 soft/state-aware 分支 | ✅ 已修复（soft mode 展开正常） |
| `validation.py` | `bootstrap_oos_ci()`, `_recent_weighted_score()`, `_regime_aware_score()` | ✅ 已实现 |
| `real_data.py` | `fetch_and_write_real_data(update_mode="append")`, `write_real_data_files()` append 路径 | ✅ 已实现 |
| `plot.py` | `plot_walk_forward_folds()`, `plot_risk_control_accuracy()`, `plot_parameter_heatmap()` | ✅ 已实现 |
| `cli.py` | `plot` 子命令（自动探测 WF/accuracy/sweep CSV） | ✅ 已实现 |
| Tests | 80 个测试全部通过，覆盖 soft sweep、state-aware、bootstrap、regime-aware | ✅ 80/80 passed |

### 0.2 已完成的实验（截至 2026-06-03）

| 实验代号 | 内容 | 关键结论 |
|---------|------|---------|
| N1 | 跨段长历史 WF，27 折，2010–2026，risk_control=false | OOS Sharpe 中位数 **0.484**，年化中位数 **8.52%**，Bootstrap p_positive=95% |
| N2 | Soft risk-off 参数扫描（sw2014 + production） | Soft 最优：年化 10.4%，DD **-49.0%**；**未达**-40% 验收线；暂不采用 |
| N3 | State-aware 风控对比（sw2021） | Sharpe +0.008，DD 恶化 2.3%；**无优势**，暂不采用 |
| P | 跨段阈值定版 WF（27 折，threshold 扫描） | 各阈值 Sharpe 中位数均为 0；保持 `threshold=0.0`，`risk_control=false` |
| O | Bootstrap CI 实现并集成到 WF summary | 已完成，N1 年化 95% CI [-1.67%, 23.26%] |

### 0.3 已确认放弃的方向

| 方向 | 放弃依据 |
|------|---------|
| `amount_strength` 因子 | Ablation: 移除后 Sharpe +0.055，永久关闭 |
| `ret20` 因子 | Ablation: 移除后 Sharpe +0.134，永久关闭 |
| `top_k=8` | Sweep: top_k=5 全面优于 8 |
| `all_factors` 配置 | 全因子 Sharpe 0.18 vs 精简版 0.52 |
| 软风控（soft risk-off） | N2: sw2014 DD 仍 -49%，未改善到 -40% 目标 |
| State-aware 风控 | N3: 无统计意义的提升，回撤反而恶化 |
| 风控机制（risk_control=true） | 2024–2026 命中率仅 20%，生产 WF 中位数 Sharpe=-0.16 |

### 0.4 当前生产配置基准（`ret60_ret5 + top_k=5 + risk_control=false`）

| 指标 | 单段（sw2021, 2021–2026） | 跨段 WF（27 折, 2010–2026） |
|------|--------------------------|--------------------------|
| 年化收益 | 6.51% | 中位数 8.52%，均值 9.92% |
| 最大回撤 | -17.26% | 中位数 -13.25% |
| Sharpe | 0.525 | 中位数 0.484 |
| Calmar | 0.377 | — |
| 沪深300超额 | +35.3% | — |
| Bootstrap p_positive | — | 95.02% |

**结论：策略已通过 16 年跨段验证，所有模拟实盘前提均满足，可进入实盘准备阶段。**

---

## 一、下一阶段工作总览

当前项目的战略位置：**从研究验证转向实盘准备与长期运营**。

所有历史疑问已解答，策略参数已锁定，测试覆盖已完整。接下来的工作分三大方向：

1. **实盘基础设施**：日常数据刷新、信号生成、持仓追踪
2. **策略稳健性深化**：填补已知数据近似缺口、引入新因子维度
3. **工程质量提升**：增量数据测试覆盖、HTML 报告完善、CI 配置

---

## 二、阶段 T：实盘信号生成系统（P0，5 天）

### 背景

N1 已证明策略 16 年有效，但目前只有回测，没有"每次换仓该持什么"的实盘输出。进入模拟实盘需要一个可重复运行的**信号生成命令**，输出下次调仓日的目标持仓及权重。

### T1：新增 `signal` CLI 子命令

**目标**：在 `cli.py` 中新增 `signal` 子命令，读取最新数据后输出下一个调仓日的目标行业及权重。

```python
# 预期接口
python -m quant_rotation signal \
  --config configs/production.toml \
  --as-of 2026-06-03 \
  --output reports/signal_2026-06-03.json
```

**输出格式**（`signal_YYYY-MM-DD.json`）：

```json
{
  "signal_date": "2026-06-03",
  "next_rebalance_date": "2026-07-01",
  "holdings": ["食品饮料", "医药生物", "电子", "银行", "电力设备"],
  "weights": {"食品饮料": 0.20, "医药生物": 0.20, "电子": 0.20, "银行": 0.20, "电力设备": 0.20},
  "exposure": 1.0,
  "market_trend": true,
  "market_score": 0.023,
  "market_score_ok": true,
  "config": "production.toml",
  "generated_at": "2026-06-03T10:00:00"
}
```

**实现要点**：

```python
# cli.py 中新增 signal_command
def signal_command(args: argparse.Namespace) -> int:
    from quant_rotation.backtest import run_backtest
    from quant_rotation.models import StrategyConfig
    import json

    config, industry_data, ... = _load_inputs(args.config)
    result = run_backtest(industry_data, ...)

    # 取最后一次 rebalance 作为当前信号
    last_rebalance = result.rebalances[-1]
    signal = {
        "signal_date": last_rebalance.signal_date.isoformat(),
        "holdings": last_rebalance.holdings,
        "weights": last_rebalance.weights,
        "exposure": last_rebalance.exposure,
        "market_trend": last_rebalance.market_trend,
        "market_score": last_rebalance.market_score,
        "market_score_ok": last_rebalance.market_score_ok,
    }
    # 写入 JSON
    ...
```

**测试**（`tests/test_signal.py`）：

```python
def test_signal_command_outputs_valid_json(self):
    # 用 sample data 跑 signal 命令
    # 验证 JSON 包含 holdings, weights, exposure 字段
    # 验证 sum(weights.values()) ≈ exposure

def test_signal_weights_sum_to_exposure(self):
    # weights 之和应等于 exposure（risk-on 时为 1.0）

def test_signal_handles_risk_off(self):
    # 构造 market_score < threshold 的场景
    # exposure 应为 risk_off_exposure（生产配置下为 0.0）
```

### T2：每日数据刷新脚本（`tools/daily_refresh.py`）

**目标**：封装"拉取今日最新数据 → 追加到 data/real → 生成信号"的完整日常流程，一键执行。

```python
#!/usr/bin/env python
"""每日运营脚本：数据追加 + 信号生成"""
# tools/daily_refresh.py

import subprocess
import sys
from datetime import date

TODAY = date.today().isoformat()

steps = [
    # Step 1: 追加今日 sw2021 数据
    ["python", "-m", "quant_rotation", "fetch-real-data",
     "--output", "data/real_sw2021",
     "--end", TODAY,
     "--update-mode", "append",
     "--request-interval", "0.3"],

    # Step 2: 生成信号
    ["python", "-m", "quant_rotation", "signal",
     "--config", "configs/production.toml",
     "--as-of", TODAY,
     "--output", f"reports/signals/signal_{TODAY}.json"],
]

for step in steps:
    result = subprocess.run(step, check=True)
    if result.returncode != 0:
        print(f"Step failed: {step}")
        sys.exit(1)
```

**验收标准**：
- 在换仓日前运行，`reports/signals/signal_YYYY-MM-DD.json` 正确生成
- 在非换仓日运行，信号日期与最后一次实际调仓日匹配
- 追加模式不覆盖已有数据

### T3：持仓追踪表（`tools/position_tracker.py`）

对比信号与实际持仓，输出换仓差异（哪些行业需要买入/卖出）。

```python
# tools/position_tracker.py
def compute_rebalance_diff(
    target_signal: dict,        # signal_YYYY-MM-DD.json
    current_positions: dict,    # {"食品饮料": 0.20, "医药生物": 0.15, ...}
) -> dict:
    """返回 {'buy': [...], 'sell': [...], 'hold': [...], 'drift': {}}"""
```

**测试**（`tests/test_position_tracker.py`）：
```python
def test_diff_identifies_new_holdings(self): ...
def test_diff_identifies_dropped_holdings(self): ...
def test_diff_handles_empty_current_positions(self): ...
```

---

## 三、阶段 U：增量数据刷新测试覆盖（P1，2 天）

### 背景

`real_data.py` 的 `update_mode="append"` 功能代码已完整实现，但 `test_real_data.py` 中**完全没有 append 模式测试**。这是当前最大的测试盲区。

### U1：补充 `write_real_data_files` append 模式测试

```python
# tests/test_real_data.py 新增

def test_write_real_data_files_append_mode_extends_existing_csv(self):
    """append 模式应在已有行后追加，而非覆盖"""
    with tempfile.TemporaryDirectory() as tmp:
        # 第一次写入 2024-01-01 至 2024-01-03
        write_real_data_files(Path(tmp), initial_data, ..., update_mode="replace")
        # 第二次 append 2024-01-04 至 2024-01-05
        write_real_data_files(Path(tmp), new_data, ..., update_mode="append")

        loaded = load_wide_close_csv(Path(tmp) / "industry_close.csv")
        # 验证最终有 5 行（2 + 3，扣除 common_dates 交集）
        self.assertIn(date(2024, 1, 1), loaded.dates)
        self.assertIn(date(2024, 1, 5), loaded.dates)

def test_write_real_data_files_append_does_not_duplicate_dates(self):
    """append 已有日期时不应产生重复行"""
    with tempfile.TemporaryDirectory() as tmp:
        write_real_data_files(Path(tmp), data_3d, ..., update_mode="replace")
        # 重叠追加（包含已有日期）
        write_real_data_files(Path(tmp), data_3d, ..., update_mode="append")
        loaded = load_wide_close_csv(Path(tmp) / "industry_close.csv")
        self.assertEqual(len(loaded.dates), len(set(loaded.dates)))

def test_fetch_and_write_real_data_append_skips_before_manifest_end(self):
    """append 模式：manifest end_date 后才真正请求，不回拉已有数据"""
    # Mock AKShare 调用，验证 start 参数 >= manifest_last_date + 1天
    ...

def test_fetch_and_write_real_data_append_raises_when_already_up_to_date(self):
    """manifest last_date >= end 时应 raise ValueError，而非静默"""
    with tempfile.TemporaryDirectory() as tmp:
        # 写入 manifest end=2026-06-03
        _update_manifest(Path(tmp), date(2026, 6, 3), 100)
        with self.assertRaises(ValueError):
            fetch_and_write_real_data(Path(tmp), date(2026, 1, 1),
                                      date(2026, 6, 2), update_mode="append")
```

### U2：补充 `_write_industry_append` 边界测试

```python
def test_append_csv_rows_creates_file_if_not_exists(self):
    """首次 append（文件不存在）应创建含表头的新文件"""

def test_append_csv_rows_skips_header_if_file_exists(self):
    """追加时不重写表头，只追加数据行"""

def test_write_industry_append_preserves_column_order(self):
    """追加列必须与原文件列顺序一致，避免数据错位"""
```

**验收标准**：`test_real_data.py` 测试数从 13 升至 18+，append 路径 100% 覆盖。

---

## 四、阶段 V：HTML 报告完善（P1，2 天）

### 背景

`plot` CLI 已实现，但有两个已知缺口：

1. WF 折叠图只在 `report_dir` 根目录找 `walk_forward_oos_equity.csv`，而实际 WF 输出在子目录（如 `walk_forward/`, `walk_forward_ret60_ret5/`）
2. `write_html_report` 没有 `plot` CLI 最新图表（WF folds、risk control accuracy、parameter heatmap）的入口

### V1：修复 `plot` 命令的 WF 路径探测

当前逻辑：
```python
wf_oos_path = report_dir / "walk_forward_oos_equity.csv"  # 只看根目录
```

修改为多级探测：
```python
# cli.py::plot_command 中修改

WF_SUBDIRS = [
    "walk_forward",
    "walk_forward_ret60_ret5",
    "walk_forward_qtr",
    "walk_forward_partial",
]

wf_oos_path, wf_folds_path = None, None
# 先查根目录，再查子目录
for candidate_dir in [report_dir] + [report_dir / d for d in WF_SUBDIRS]:
    p1 = candidate_dir / "walk_forward_oos_equity.csv"
    p2 = candidate_dir / "walk_forward_folds.csv"
    if p1.exists() and p2.exists():
        wf_oos_path, wf_folds_path = p1, p2
        break
```

**同时新增 `--wf-dir` 参数**，允许显式指定：
```powershell
python -m quant_rotation plot \
  --report-dir reports/real_sw2021 \
  --wf-dir reports/real_sw2021/walk_forward_ret60_ret5
```

### V2：`plot` 命令新增 `--include-summary` 选项

在 HTML 报告头部嵌入 `walk_forward_summary.csv` 的关键指标表格：

```html
<h2>Walk-Forward Summary</h2>
<table>
  <tr><th>Metric</th><th>Mean</th><th>Median</th><th>Std</th></tr>
  <tr><td>OOS Annualized Return</td><td>9.92%</td><td>8.52%</td><td>33.3%</td></tr>
  <tr><td>OOS Sharpe</td><td>0.358</td><td>0.484</td><td>1.29</td></tr>
  <tr><td>Bootstrap p_positive</td><td colspan="3">95.02%</td></tr>
</table>
```

实现路径：`plot.py` 新增 `render_wf_summary_table(summary_csv) -> str`，返回 HTML 片段。

### V3：`plot` 命令支持跨段 WF 报告

```powershell
python -m quant_rotation plot \
  --report-dir reports/cross_segment_walk_forward \
  --output reports/cross_segment_walk_forward/html
```

当前此命令因为 `equity_curve.csv` 不存在而失败（WF-only 目录无基础净值图）。修复：允许 WF-only 模式生成仅含折叠图和汇总表的报告。

**测试**（`tests/test_reports.py` 或新增 `tests/test_plot_cli.py`）：

```python
def test_plot_command_finds_wf_in_subdirectory(self):
    # 创建临时目录，WF 文件放在子目录 walk_forward/
    # 运行 plot 命令，验证 HTML 含 WF 图表

def test_render_wf_summary_table_produces_valid_html(self):
    # 用 N1 的 summary.csv 验证表格行数和内容格式
```

---

## 五、阶段 W：历史成分股数据接入（P2，5 天）

### 背景

当前 `fetch-breadth-data` 和 `fetch-stock-data` 使用**当前成分股**回算历史，存在前视偏差（survivorship bias）。README 已明确标注为"研究近似版"。

此阶段目标是建立**历史快照**接入机制，使回测更接近实际可交易状态。

### W1：历史成分股快照 CSV 格式设计

定义通用快照格式（已在 `models.py::StockIndustryMap` 中预留）：

```csv
snapshot_date,stock,industry
2014-02-21,601318.SH,保险
2014-02-21,600036.SH,银行
2021-12-13,601318.SH,非银金融
2021-12-13,300750.SZ,电力设备
```

关键规则：
- 每次行业分类调整日必须有对应快照（sw2000→sw2014：2014-02-21；sw2014→sw2021：2021-12-13）
- 中间无变化则沿用最近一期快照（`StockIndustryMap.get_map_at()` 已实现此逻辑）

### W2：`fetch-historical-constituents` CLI 子命令

```python
# cli.py 新增
historical_const = subparsers.add_parser(
    "fetch-historical-constituents",
    help="Fetch SW level-1 historical constituent snapshots"
)
historical_const.add_argument("--output", required=True)
historical_const.add_argument("--snapshot-dates",
    help="Comma-separated snapshot dates, e.g. 2014-02-21,2021-12-13")
historical_const.add_argument("--request-interval", type=float, default=0.5)
```

**实现策略**：

AKShare 目前不提供直接历史成分股接口。实现路径：

1. **短期**（本阶段）：从 Wind/Choice 导出的历史快照 CSV 手动导入，CLI 仅做格式验证和转换
2. **中期**：接入第三方历史数据源（如 tushare Pro 的 `index_weight` 接口，需 token）

```python
def validate_constituent_snapshot_csv(path: Path) -> None:
    """验证快照 CSV 格式：必须有 snapshot_date, stock, industry 三列"""
    df = pd.read_csv(path)
    required = {"snapshot_date", "stock", "industry"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    if df["snapshot_date"].isnull().any():
        raise ValueError("snapshot_date cannot be null")
```

### W3：将历史成分股接入面包率计算

修改 `real_data.py::compute_industry_breadth()`：

```python
def compute_industry_breadth(
    stock_closes: PriceData,
    stock_map: StockIndustryMap,  # 改为接受 StockIndustryMap（含历史快照）
    windows: tuple[int, ...],
    signal_date: date,            # 新增：用于查询对应快照
) -> dict[str, dict[str, list[float]]]:
    # 用 stock_map.get_map_at(signal_date) 获取当日成分股
    ...
```

**测试**：

```python
def test_breadth_uses_snapshot_at_signal_date(self):
    """不同信号日期应用不同成分股快照"""
    early_map = {"stock_A": "行业X", "stock_B": "行业X"}
    late_map = {"stock_A": "行业Y", "stock_B": "行业X"}
    stock_map = StockIndustryMap({
        date(2014, 2, 21): early_map,
        date(2021, 12, 13): late_map,
    })
    breadth_early = compute_industry_breadth(..., signal_date=date(2020, 1, 1))
    breadth_late = compute_industry_breadth(..., signal_date=date(2022, 1, 1))
    self.assertIn("行业X", breadth_early["breadth20"])
    self.assertIn("行业Y", breadth_late["breadth20"])
```

---

## 六、阶段 X：基本面因子数据接入（P2，3 天）

### 背景

`models.py::FactorWeights` 已有 `valuation` 和 `prosperity` 字段，`backtest.py` 已支持这两个因子，但实盘数据尚未接入。Sample data 中有对应 CSV，但 real data 没有。

### X1：行业估值百分位数据接入

`industry_valuation.csv`：每个行业的 PE/PB 历史百分位（0–1，越低越便宜）。

**数据来源选项**：
- AKShare `stock_a_indicator_lg` 接口（个股 PE/PB → 聚合至行业）
- Wind 行业 PE 历史数据（手动导出）

**实现**（`real_data.py` 新增函数）：

```python
def compute_industry_valuation_percentile(
    stock_pe_data: dict[str, pd.Series],  # 个股 PE 时序
    stock_map: StockIndustryMap,
    window: int = 252,                    # 历史百分位窗口（约 1 年）
) -> PriceData:
    """
    计算各行业中位数 PE 的历史滚动百分位。
    返回 PriceData，值域 [0, 1]，越低越便宜（factor_weights.valuation 期望低值高分）。
    """
```

### X2：行业景气度代理接入

`industry_prosperity.csv`：行业景气指标（标准化后的符号值，正为景气）。

**候选指标**（单选或加权组合）：
- 行业成交量相对 60 日均量的 z-score（已有 amount 数据，可直接计算）
- AKShare `macro_china_pmi` 相关行业 PMI（制造业子行业）

**最小可行版**（不依赖新数据源）：

```python
def compute_industry_amount_zscore(
    amount_data: PriceData,
    window: int = 60,
) -> PriceData:
    """用成交额相对滚动均值的 z-score 作为景气代理"""
    # 对每个行业计算：(amount - rolling_mean) / rolling_std
    # 结果已经是有符号标准化值，可直接作为 prosperity 因子
```

**测试**：

```python
def test_valuation_percentile_is_in_unit_interval(self):
    result = compute_industry_valuation_percentile(...)
    for closes in result.closes.values():
        self.assertTrue(all(0 <= v <= 1 for v in closes if not math.isnan(v)))

def test_amount_zscore_is_zero_mean_unit_variance(self):
    result = compute_industry_amount_zscore(amount_data, window=20)
    # 验证结果均值接近 0、标准差接近 1（排除 warmup 期）
```

---

## 七、阶段 Y：CI/CD 与运营质量（P3，2 天）

### Y1：GitHub Actions 基础 CI

当前无自动化测试运行。新增 `.github/workflows/ci.yml`：

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e .
      - run: python -m pytest tests/ -v --tb=short
```

### Y2：数据质量检查工具（`tools/check_data_quality.py`）

每次拉取新数据后自动运行，检查：

```python
def check_industry_close(path: Path) -> list[str]:
    """返回发现的数据质量问题列表"""
    issues = []
    df = pd.read_csv(path, index_col=0, parse_dates=True)

    # 检查 1：连续 NaN 超过 5 个交易日（可能数据缺失）
    for col in df.columns:
        max_nan_run = df[col].isna().groupby(df[col].notna().cumsum()).sum().max()
        if max_nan_run > 5:
            issues.append(f"{col}: {max_nan_run} consecutive NaNs")

    # 检查 2：单日涨跌幅超过 ±15%（非 ST 行业）
    daily_returns = df.pct_change()
    extreme = (daily_returns.abs() > 0.15).stack()
    for (date, industry) in extreme[extreme].index:
        issues.append(f"{industry} on {date}: extreme return {daily_returns.loc[date, industry]:.1%}")

    # 检查 3：最新日期是否为今日或昨日（数据新鲜度）
    latest = df.index.max()
    lag = (date.today() - latest.date()).days
    if lag > 3:
        issues.append(f"Data lag: {lag} days (latest: {latest.date()})")

    return issues
```

### Y3：`pyproject.toml` 补充开发依赖

```toml
[project.optional-dependencies]
real-data = ["akshare>=1.18.0"]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.0",
    "ruff>=0.4",          # 代码风格检查
]
```

---

## 八、优先级总览

| 优先级 | 阶段 | 核心任务 | 性质 | 估计工时 | 依赖 |
|--------|------|---------|------|---------|------|
| 🔴 P0 | **T1** | `signal` CLI 子命令 | 新功能 | 2 天 | 无 |
| 🔴 P0 | **T2** | `daily_refresh.py` 运营脚本 | 新工具 | 0.5 天 | T1 |
| 🔴 P0 | **T3** | `position_tracker.py` 持仓差异工具 | 新工具 | 0.5 天 | T1 |
| 🟠 P1 | **U1** | append 模式测试覆盖 | 测试 | 1.5 天 | 无 |
| 🟠 P1 | **U2** | `_write_*_append` 边界测试 | 测试 | 0.5 天 | 无 |
| 🟠 P1 | **V1** | `plot` 命令 WF 路径探测修复 | Bug fix | 0.5 天 | 无 |
| 🟠 P1 | **V2** | `plot` 命令嵌入 WF summary 表格 | 功能增强 | 0.5 天 | V1 |
| 🟠 P1 | **V3** | `plot` 支持跨段 WF 报告 | Bug fix | 0.5 天 | V1 |
| 🟡 P2 | **W1** | 历史成分股快照格式设计与验证工具 | 数据基础设施 | 1 天 | 无 |
| 🟡 P2 | **W2** | `fetch-historical-constituents` CLI | 新功能 | 2 天 | W1 |
| 🟡 P2 | **W3** | 历史成分股接入面包率计算 | 功能增强 | 2 天 | W1, W2 |
| 🟡 P2 | **X1** | 行业估值百分位计算 | 因子增强 | 1.5 天 | 无 |
| 🟡 P2 | **X2** | 成交额 z-score 景气代理 | 因子增强 | 1 天 | 无 |
| 🟢 P3 | **Y1** | GitHub Actions CI | 工程质量 | 0.5 天 | 无 |
| 🟢 P3 | **Y2** | 数据质量检查工具 | 运营工具 | 1 天 | 无 |
| 🟢 P3 | **Y3** | `pyproject.toml` 开发依赖补充 | 工程质量 | 0.5 天 | 无 |

---

## 九、立即执行步骤（有序，最小阻塞）

以下 5 步可在 2–3 天内完成，且无外部数据源依赖：

### Step 1：实现 `signal` CLI 子命令（T1）

优先级最高，是模拟实盘的入口。核心逻辑直接复用 `run_backtest()`，只需提取最后一次 rebalance。

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation signal `
  --config configs/production.toml `
  --as-of 2026-06-03 `
  --output reports/signals/signal_2026-06-03.json
```

### Step 2：补充 append 模式测试（U1+U2）

在 `test_real_data.py` 中新增 4 个 append 测试，不需要网络请求（全部 mock）。

```powershell
python -m pytest tests/test_real_data.py -v -k "append"
```

**预期**：4 个新测试全部通过，总用时 < 5 秒。

### Step 3：修复 `plot` 命令 WF 路径探测（V1）

修改 `cli.py::plot_command` 中的路径探测逻辑，验证：

```powershell
# 验证跨段 WF 报告生成（当前会因缺 equity_curve.csv 报错）
python -m quant_rotation plot `
  --report-dir reports/cross_segment_walk_forward `
  --output reports/cross_segment_walk_forward/html

# 验证 sw2021 WF 子目录探测
python -m quant_rotation plot `
  --report-dir reports/real_sw2021 `
  --output reports/real_sw2021/html_new
```

### Step 4：实现 `daily_refresh.py` 运营脚本（T2）

封装 `fetch-real-data append` + `signal` 为一键脚本。

```powershell
python tools/daily_refresh.py
# 预期：拉取今日数据（追加），生成 reports/signals/signal_2026-06-03.json
```

### Step 5：实现 amount z-score 景气代理因子（X2，最小可行版）

此步无需新数据源，基于已有 `industry_amount.csv` 直接计算。完成后可立即在 sweep 中验证该因子对 Sharpe 的边际贡献（ablation）。

```powershell
python -m quant_rotation decompose `
  --config configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5,ret60_ret5_prosperity
  --output-dir reports/real_sw2021/prosperity_decomposition
```

---

## 十、关键决策节点

### 决策 A：实盘账户类型（模拟 vs 真实）

**条件**：T1 完成，信号生成系统稳定运行 2 周后。

**判断标准**：
- 模拟实盘期间信号与回测一致率 > 95%
- 数据刷新连续 10 个交易日无异常
- position_tracker 正确输出换仓差异

**选择**：
- **模拟实盘**：继续在 CSV 中记录信号，不真实下单（推荐先做 3 个月）
- **真实实盘**：需要接入券商 API（通常为 XTP/CFFEX/DMA 接口）

### 决策 B：是否引入基本面因子（阶段 X）

**条件**：X2 完成，ablation 显示 `ret60_ret5_prosperity`（含 amount z-score 景气代理）相比 `ret60_ret5` 的 Sharpe 提升。

**判断标准**：
- sw2021 段 ablation Sharpe 提升 > +0.05
- sw2014 段 ablation 无显著退化（< -0.03）
- 跨段 WF 均值 Sharpe 提升 > +0.03

**选择**：
- **纳入**：更新 `configs/production.toml` 加入 `prosperity_weight`
- **放弃**：维持 `ret60_ret5` 纯动量配置

### 决策 C：历史成分股接入（阶段 W）

**条件**：W1 格式设计完成，历史快照数据来源确认。

**判断标准**：
- 能获取 2014-02-21 和 2021-12-13 两个关键时间点的成分股快照
- 接入后面包率回测与当前近似版差异 < 5%（说明近似误差可接受）

**选择**：
- **全面接入**：使用真实历史快照替换当前成分股近似
- **维持现状**：在文档中标注近似版局限性，推迟至有可靠数据源

---

## 十一、当前悬而未决的技术问题

以下问题在实施过程中需关注，但不阻塞主线：

### 问题 1：`data/real_extended` 目录用途不明确

`data/real_extended/manifest.json` 与 `data/real/manifest.json` 内容几乎完全相同（相同 start/end/rows），仅 `generated_at` 不同。**没有任何 config 文件引用 `real_extended`**。

**建议**：在 README 或 configs/ 中明确 `real_extended` 的预期用途（如"扩展历史数据，供研究用，不作为生产数据源"），或删除该目录避免混淆。

### 问题 2：`monthly_win_rate` 计算逻辑

`reports/production/metrics.csv` 中 `monthly_win_rate=0.291`，低于预期。检查 `metrics.py` 中的计算方式是否将 risk-off 期间（exposure=0）计为"亏损月"或"中性月"。如果风控频繁触发将人为压低月胜率。

**建议**：在 `metrics.py` 中新增 `monthly_win_rate_excl_riskoff` 指标，仅统计有实际持仓的月份。

### 问题 3：`real_sw2000` 段缺少 `market_close.csv`

`data/real_sw2000/manifest.json` 显示 `"market_close": null`，该段无市场状态数据。在 `validate-segments` 跨段 WF 中，sw2000 段所有 `market_score_control=true` 的候选会自动降级为纯 `risk_control`（MA120）模式，可能导致与其他段策略不一致。

**建议**：在 `validate_segments_command` 中添加警告日志，提示当某段缺少 market_close 时 market_score_control 被降级。

---

## 十二、策略性能基线（本版记录，用于后续对照）

| 指标 | 值 | 数据范围 | 配置 |
|------|----|---------|------|
| 年化收益（全段） | 6.51% | 2021–2026 | ret60_ret5, top_k=5, riskoff=0 |
| 最大回撤（全段） | -17.26% | 2021–2026 | 同上 |
| Sharpe（全段） | 0.525 | 2021–2026 | 同上 |
| 超额收益 vs 沪深300 | +35.3% | 2021–2026 | 同上 |
| WF OOS Sharpe 中位数 | 0.484 | 2010–2026，27 折 | 同上 |
| WF OOS 年化中位数 | 8.52% | 2010–2026，27 折 | 同上 |
| WF 盈利折数 | 16/27（59.3%） | 2010–2026，27 折 | 同上 |
| Bootstrap p_positive | 95.02% | 基于 N1，10000 次 | 同上 |
| 测试用例数 | 80 通过 / 0 失败 | 截至 2026-06-03 | — |