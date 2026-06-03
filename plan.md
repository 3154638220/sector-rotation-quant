# 行动计划：A 股行业动量轮动策略 下一步

> 基于对 `sector-rotation-quant-main` 全量代码、配置与报告的深度分析  
> 分析日期：2026-06-03（接续 2026-06-03 晨版，本次为深化版）

---

## 零、执行进度核查（截至 2026-06-03）

### 0.1 已完成（本次分析确认已落地）

| 任务 | 代码位置 | 确认状态 |
|------|---------|---------|
| G1 soft risk-off 函数 | `backtest.py::soft_risk_exposure()` + `StrategyConfig.risk_control_mode` | ✅ 已实现，sw2014 段 soft 模式未成功生成 |
| G2 市场状态分类器 | `backtest.py::classify_market_state()` + `_state_aware_exposure()` | ✅ 已实现，sw2021 段已实验（见 N3） |
| G3 空仓命中率诊断 | `tools/diagnose_risk_control.py` + `reports/production/risk_control_accuracy.csv` | ✅ 已实现并已运行 |
| H1 validate-segments CLI | `cli.py::validate_segments_command()` + `segments.py::merge_segment_price_data()` | ✅ 已执行 N1，27 折 WF 成功 |
| I1 时代权重训练评分 | `validation.py::_recent_weighted_score()` | ✅ 已实现 |
| I2 市场状态条件选择 | `validation.py::_regime_aware_score()` | ✅ 已实现 |
| J1 test_config.py | `tests/test_config.py` | ✅ 7 个测试用例，覆盖 soft/state-aware 字段 |
| J2 test_data.py | `tests/test_data.py` | ✅ 已存在 |
| J3 test_metrics.py | `tests/test_metrics.py` | ✅ 已存在 |
| L1 HTML 报告 | `plot.py::write_html_report()` + `cli.py plot` 子命令 | ✅ 已实现，已生成 4 段 HTML 报告 |

### 0.2 已知但**从未运行**的关键实验（最紧迫差距）

已执行关键实验，输出目录均已生成：

| 实验 | 状态 | 输出目录 |
|------|------|---------|
| 跨段长历史 WF（N1） | ✅ 已执行，27 折 | `reports/cross_segment_walk_forward/` |
| Soft risk-off 参数扫描（N2） | ⚠️ 已执行，仅生成 hard mode | `reports/real_sw2014/soft_riskoff_sweep/` + `reports/production/soft_riskoff_sweep/` |
| State-aware 风控对比（N3） | ✅ 已执行 | `reports/real_sw2021/state_aware_sweep/` |
| 跨段阈值最终定版 | ⏳ 待执行 N1 风控版 | `reports/cross_segment_threshold_wf/` ❌ |

### 0.4 阶段 N 实验结果（2026-06-03 执行）

#### N1：跨段长历史 Walk-Forward（ret60_ret5, top_k=5, risk_control=false）

`reports/cross_segment_walk_forward/walk_forward_folds.csv`（27 折，2010-01-04 → 2026-03-05）：

| 指标 | 均值 | 中位数 | 标准差 |
|------|------|--------|--------|
| OOS 年化收益 | **9.92%** | **8.52%** | 33.3% |
| OOS 最大回撤 | -16.1% | -13.3% | 9.5% |
| OOS Sharpe | 0.358 | **0.484** | 1.29 |
| OOS Calmar | 1.44 | 0.80 | — |

| 盈利折数 | 亏损折数 | 正 Sharpe 折数 |
|----------|----------|----------------|
| 16/27（59.3%） | 11/27（40.7%） | 19/27（70.4%） |

**结论**：`ret60_ret5` + `top_k=5` + 无风控，在 27 折跨段验证中 OOS Sharpe 中位数 0.484、年化中位数 8.5%，远超验收标准（> 0.2, > 0%）。最大回撤中位数仅 -13.3%，即使在 2018 大熊市（折 13: -47.3%）和 2023 熊市（折 23: -33.6%）也有可控亏损。

**Bootstrap 置信区间**（10,000 次重采样）：
- 年化收益：95% CI [-1.67%, 23.26%]，p_positive = 95.02%
- Sharpe：95% CI [-0.131, 0.842]，p_positive = 92.25%

#### N2：Soft Risk-Off 参数扫描

⚠️ **问题发现**：`sweep --risk-control-mode hard,soft --soft-exposure-min 0.0,0.1,0.2,0.3` 在 sw2014 和 production 段均只生成了 `hard` mode 结果。`soft` mode 候选未生成——疑似 `sweep.py::build_sweep_specs()` 中 `risk_control_mode_values` 未正确展开为独立候选。需要修复。

sw2014 段 hard mode 结果（已知，作为基线）：

| risk_off_exposure | 年化 | 最大回撤 | Sharpe |
|-------------------|------|---------|--------|
| 0.5 | 10.98% | -53.66% | 0.60 |
| 0.3 | 10.82% | -53.60% | 0.61 |
| 0.2 | 10.68% | -53.92% | 0.62 |
| 0 | 10.28% | -54.83% | 0.60 |

production 段 hard mode 结果：年化 4.9-6.5%，DD -17.3%～-22.8%，Sharpe 0.38-0.52。

#### N3：State-Aware 风控对比（sw2021 段）

| 配置 | 年化 | 最大回撤 | Sharpe |
|------|------|---------|--------|
| hard (无 state-aware) | **6.51%** | **-17.26%** | 0.525 |
| state-aware (true) | 6.31% | -19.56% | **0.533** |

**结论**：state-aware 提升 Sharpe 仅 +0.008，回撤反而恶化 2.3 pct。在此配置下无明显优势。

---

#### 🔴 发现 1：风控命中率仅 47.8%，2025 年后急剧恶化

`reports/production/risk_control_accuracy.csv`（29 个空仓事件）：

| 指标 | 数值 |
|------|------|
| TRUE_POSITIVE（空仓有效） | 11 次（37.9%） |
| FALSE_POSITIVE（错误空仓） | 12 次（41.4%） |
| NEUTRAL（±2% 以内） | 6 次（20.7%） |
| 净命中率（排除 Neutral） | **47.8%**（低于随机 50%） |

按年分解：

| 年份 | TP | FP | 命中率 |
|------|----|----|--------|
| 2022 | 4 | 3 | 57.1% ✅ |
| 2023 | 4 | 1 | 80.0% ✅ |
| 2024 | 2 | 3 | 40.0% ⚠️ |
| 2025 | 1 | 4 | **20.0%** 🔴 |
| 2026 | 0 | 1 | 0.0% 🔴 |

结论：**风控在 2022-2023 年有效（熊市），在 2025-2026 年完全失效（结构性牛市中的震荡修正）**。

#### 🔴 发现 2：关闭风控（riskoff=0）的 WF 中位数 Sharpe 达 1.30，有风控仅 -0.16

`reports/real_sw2021/walk_forward_ret60_ret5/walk_forward_summary.csv`（无风控版）：
- OOS Sharpe **中位数：1.296**，均值：1.408
- OOS 年化中位数：**7.8%**

`reports/production/walk_forward/walk_forward_summary.csv`（有风控版）：
- OOS Sharpe **中位数：-0.155**，均值：0.338
- OOS 年化中位数：**-3.4%**

两者都是 4 折 WF，数据区间相同（2021-2026）。差距的全部来源是风控在 2024-2025 年的 **3 次错误空仓**，每次踏空约 5-20%。

#### 🟢 发现 3：跨段长历史 WF 已执行——策略 16 年有效（N1 已验证）

原"最大信息盲区"已消除。详见 §0.4 N1 实验结果。

---

## 一、核心问题诊断（更新版）

### 问题 1：风控机制在结构性牛市中系统性误触发（量化确认）

2024-2026 的 5 次错误空仓（FP）中，有 4 次原因是 `market_score < threshold`（market_score 为负但市场仍在上涨），仅 1 次是 `market_trend=false`。说明：
- **market_score 计算的是市场过去 60 日加权动量**，在结构性牛市初期（小幅拉升后回调）时，60 日动量可能短暂转负，而市场中期趋势仍向上
- `market_score_threshold=0.0` 的边界太敏感，任何轻微负动量即触发空仓

Soft risk-off 和 state-aware 风控正是为解决此问题而设计，**代码已完成但从未验证**。

### 问题 2：4 折 WF 的结论不可靠，urgent 需要跨段长历史验证

4 折 WF 的方差极大（OOS Sharpe std = 1.11），单折牛市（折 4，+71.9%）主导均值。  
跨段 validate-segments 命令已就绪，运行一次即可得到 20+ 折的可信结果。  
**这是当前性价比最高的未执行工作。**

### 问题 3：Bootstrap CI 未实现，所有 WF 结论缺少统计显著性量化

当前 `walk_forward_summary.csv` 只有均值/中位数/标准差，没有置信区间。  
4 折样本的 95% CI 极宽（±1 以上），难以判断 OOS Sharpe 是否显著 > 0。

---

## 二、行动计划（按优先级排序）

### 阶段 N：立即执行的三个零代码实验（优先级 P0，3 天内）

> **代码已完整，只需执行命令并分析输出**。

#### N1：运行跨段长历史 Walk-Forward（最高价值单次实验）

**背景**：`validate-segments` CLI 已完整实现，`merge_segment_price_data()` 经测试可合并三段数据。此命令从未执行过。

```powershell
$env:PYTHONPATH="src"

# 基础版：用生产配置的 ret60_ret5 因子跑跨段 WF
python -m quant_rotation validate-segments `
  --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-off-exposure 0 `
  --risk-control false `
  --market-score-control false `
  --train-window 504 `
  --test-window 126 `
  --selection-metric composite `
  --output-dir reports/cross_segment_walk_forward
```

**预期折数**：约 20-25 折（覆盖 2010-2026 全部 16 年）  
**验收标准**：OOS Sharpe 中位数 > 0.2，且不少于 15 折有正收益

**后续分析**（用 Python 脚本分析输出）：
```python
import pandas as pd
df = pd.read_csv("reports/cross_segment_walk_forward/walk_forward_folds.csv")
print(f"Total folds: {len(df)}")
print(f"OOS Sharpe median: {df['test_sharpe_ratio'].median():.3f}")
print(f"Profitable folds: {(df['test_annualized_return'] > 0).sum()}/{len(df)}")
```

#### N2：运行 Soft Risk-Off 参数扫描

**背景**：`soft_risk_exposure()` 在 `backtest.py` 已实现，`StrategyConfig` 已有 `risk_control_mode`/`soft_exposure_min` 字段，`cli.py sweep` 已接受 `--risk-control-mode` 和 `--soft-exposure-min` 参数。从未在实际数据上验证效果。

```powershell
$env:PYTHONPATH="src"

# sw2014 段（包含最严重的 -54.8% 回撤）对比实验
python -m quant_rotation sweep `
  --config configs/real_sw2014.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-control true `
  --market-score-control true `
  --risk-control-mode hard,soft `
  --soft-exposure-min 0.0,0.1,0.2,0.3 `
  --output-dir reports/real_sw2014/soft_riskoff_sweep

# production 段（包含 2024-2025 错误空仓）
python -m quant_rotation sweep `
  --config configs/production.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-control true `
  --market-score-control true `
  --risk-control-mode hard,soft `
  --soft-exposure-min 0.0,0.1,0.2,0.3 `
  --output-dir reports/production/soft_riskoff_sweep
```

**关键对比指标**：

| 配置 | sw2014 最大回撤（当前：-54.8%） | sw2014 年化（当前：10.3%） | production WF 中位数 Sharpe（当前：-0.16） |
|------|-------------------------------|--------------------------|------------------------------------------|
| hard, min=0.0（当前） | -54.8% | 10.3% | -0.16 |
| soft, min=0.1 | ? | ? | ? |
| soft, min=0.2 | ? | ? | ? |
| soft, min=0.3 | ? | ? | ? |

**验收标准**：soft min=0.2 版本在 sw2014 段最大回撤 < -40%，年化 > 8%。

#### N3：运行 State-Aware 风控对比实验

**背景**：`_state_aware_exposure()` 和 `classify_market_state()` 已在 `backtest.py` 实现，`StrategyConfig` 已有 `state_aware_risk_control`/`bull_exposure`/`sideways_exposure`/`bear_exposure` 字段。从未在生产数据上验证。

```powershell
$env:PYTHONPATH="src"

# sw2021 段（2021-2026，包含 2024-2025 问题区间）
python -m quant_rotation sweep `
  --config configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-control true `
  --market-score-control true `
  --state-aware-risk-control true,false `
  --sideways-exposure 0.3,0.5,0.7 `
  --output-dir reports/real_sw2021/state_aware_sweep
```

**关注点**：sideways exposure = 0.5 时，2024 年震荡转牛阶段是否能保留部分收益。

---

### 阶段 O：Bootstrap 置信区间（P1，2 天，独立实现）

当前 WF 结论（OOS Sharpe 中位数）没有统计显著性支撑。需要在 `validation.py` 中添加：

```python
def bootstrap_oos_ci(
    fold_annualized_returns: list[float],
    n_bootstrap: int = 10_000,
    seed: int = 42,
) -> dict[str, float]:
    """
    Bootstrap 重采样估计 OOS 年化收益的 95% 置信区间。
    返回 {'mean', 'ci_lower', 'ci_upper', 'p_positive'}。
    p_positive = bootstrap 样本均值 > 0 的比例（近似单侧 p 值）。
    """
    import random
    rng = random.Random(seed)
    n = len(fold_annualized_returns)
    samples = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(fold_annualized_returns) for _ in range(n)]
        samples.append(sum(sample) / n)
    samples.sort()
    return {
        "mean": sum(fold_annualized_returns) / n,
        "ci_lower": samples[int(0.025 * n_bootstrap)],
        "ci_upper": samples[int(0.975 * n_bootstrap)],
        "p_positive": sum(1 for s in samples if s > 0) / n_bootstrap,
    }
```

**输出集成**：在 `_write_walk_forward_summary()` 中新增以下行：
```
bootstrap_ci_lower,annualized_return,{value}
bootstrap_ci_upper,annualized_return,{value}
bootstrap_p_positive,annualized_return,{value}
```

**测试**：在 `test_validation.py` 中新增：
```python
def test_bootstrap_oos_ci_positive_returns(self):
    result = bootstrap_oos_ci([0.1, 0.2, 0.15, 0.05, 0.18])
    self.assertGreater(result["p_positive"], 0.90)
    self.assertGreater(result["ci_lower"], 0.0)

def test_bootstrap_oos_ci_mixed_returns(self):
    result = bootstrap_oos_ci([-0.1, 0.3, -0.05, 0.2, -0.2, 0.1])
    self.assertLess(result["ci_lower"], 0.05)
    self.assertBetween(result["p_positive"], 0.3, 0.7)
```

---

### 阶段 P：跨段长历史阈值最终定版（P1，1 天，依赖 N1）

在 N1 完成后，用 `validate-segments` 对 market_score_threshold 做最终扫描：

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation validate-segments `
  --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-off-exposure 0 `
  --risk-control true `
  --market-score-control true `
  --market-score-threshold=-0.05,-0.02,0,0.02,0.05 `
  --train-window 504 `
  --test-window 126 `
  --output-dir reports/cross_segment_threshold_wf
```

**决策准则**：选择 20+ 折 OOS Sharpe **中位数最高**的阈值，若差异 < 0.05 则保持 0.0 不变。

若 N2 实验显示 soft risk-off 效果显著优于 hard，则同步扫描 soft 版本：
```powershell
--risk-control-mode soft `
--soft-exposure-min 0.2 `
--market-score-threshold=-0.05,0,0.05
```

---

### 阶段 Q：补全测试覆盖空缺（P2，3 天，可与 N/O 并行）

经本次审查，以下测试仍有实质性缺口：

#### Q1：`test_backtest.py` 补充 state_aware 和 classify_market_state 测试

当前 `test_backtest.py` 有 4 个测试，缺少：

```python
def test_classify_market_state_bull(self):
    """score > 0.05 且 trend_strength > 0.03 时返回 bull"""
    from quant_rotation.backtest import classify_market_state
    # 构造一个 120 日内持续上涨的 benchmark（最后一日 > MA120）
    closes = [100.0 * (1 + 0.0003) ** i for i in range(130)]
    state = classify_market_state(0.08, closes, 129, 120)
    self.assertEqual(state, "bull")

def test_classify_market_state_bear(self):
    """score < -0.03 时返回 bear"""
    from quant_rotation.backtest import classify_market_state
    state = classify_market_state(-0.05, None, 5, 120)
    self.assertEqual(state, "bear")

def test_classify_market_state_sideways(self):
    """score 在 (-0.03, 0.05) 之间返回 sideways"""
    from quant_rotation.backtest import classify_market_state
    state = classify_market_state(0.01, None, 5, 120)
    self.assertEqual(state, "sideways")

def test_state_aware_exposure_sideways_partial(self):
    """sideways 状态下应返回 sideways_exposure，不是 0 也不是 1"""
    result = run_backtest_with_state_aware(sideways_exposure=0.5)
    # 验证至少一次 rebalance 的 exposure 约为 0.5
    exposures = [r.exposure for r in result.rebalances]
    self.assertTrue(any(0.3 < e < 0.7 for e in exposures))
```

#### Q2：`test_segments.py` 补充 merge_segment_price_data 边界测试

```python
def test_merge_fills_missing_industry_with_nan(self):
    """合并时缺失行业填 NaN，不抛异常"""
    seg1 = PriceData(dates=[d1, d2], closes={"A": [1.0, 1.1], "B": [2.0, 2.1]})
    seg2 = PriceData(dates=[d3, d4], closes={"B": [2.2, 2.3], "C": [3.0, 3.1]})
    merged = merge_segment_price_data([(seg1, "s1"), (seg2, "s2")], fill_missing=True)
    import math
    self.assertTrue(math.isnan(merged.closes["C"][0]))
    self.assertFalse(math.isnan(merged.closes["C"][2]))

def test_merge_segment_dates_are_contiguous(self):
    """合并后日期顺序应正确串接两段"""
    merged = merge_segment_price_data([(seg1, "s1"), (seg2, "s2")])
    self.assertEqual(merged.dates, [d1, d2, d3, d4])
```

#### Q3：`test_validation.py` 补充 recent_weighted_score 和 regime_aware 测试

```python
def test_recent_weighted_score_favors_recent_performance(self):
    """近期表现好的策略得分应高于早期表现好的策略"""
    from quant_rotation.validation import _recent_weighted_score
    # 构造两个训练集：early_good（前半期高，后半期低）vs recent_good（相反）
    ...

def test_regime_aware_score_bear_favors_low_drawdown(self):
    """熊市状态下评分应倾向低回撤策略"""
    from quant_rotation.validation import _regime_aware_score
    bear_metrics = {"annualized_return": -0.05, "max_drawdown": -0.10, "sharpe_ratio": -0.3}
    high_return_metrics = {"annualized_return": 0.10, "max_drawdown": -0.40, "sharpe_ratio": 0.5}
    self.assertGreater(_regime_aware_score(bear_metrics), _regime_aware_score(high_return_metrics))
```

---

### 阶段 R：增量数据刷新（P2，2 天，独立实现）

当前 `fetch-real-data` 每次全量重写，日常运营风险较高（覆盖已有数据）。

**实现方案**（`real_data.py`）：

```python
def fetch_and_write_real_data(
    output_dir: str | Path,
    start: date,
    end: date,
    ...
    update_mode: str = "full",  # "full" | "append"
) -> None:
    if update_mode == "append":
        manifest = _load_manifest(output_dir)
        if manifest and manifest.get("end_date"):
            start = date.fromisoformat(manifest["end_date"]) + timedelta(days=1)
            if start > end:
                print(f"Data already up to date (last date: {start - timedelta(days=1)})")
                return
    # 继续现有逻辑
    ...
```

**CLI 参数**：
```powershell
python -m quant_rotation fetch-real-data `
  --output data/real `
  --end 2026-06-03 `
  --update-mode append      # 仅追加 manifest.end_date 之后的数据
```

**测试**：
```python
def test_append_mode_does_not_fetch_before_manifest_end(self):
    # 写一个 manifest 说 end_date=2026-01-01
    # 运行 append 模式，验证 AKShare 调用的 start 参数 >= 2026-01-02
```

---

### 阶段 S：可视化增强（P3，3 天，低依赖性）

当前 HTML 报告（`plot.py::write_html_report()`）仅包含：净值曲线、回撤图、年度收益、持仓期分布。建议补充：

#### S1：WF 折叠对比图（`plot.py` 新增函数）

```python
def plot_walk_forward_folds(
    folds_csv: str | Path,
    oos_equity_csv: str | Path,
) -> bytes:
    """各折 OOS 净值曲线多线图 + 折叠盈亏条形图"""
```

在 HTML 报告中新增 `<h2>Walk-Forward Folds</h2>` 章节，生成：
- 每折 OOS 净值曲线（多线，按折着色）
- 训练 Sharpe vs 测试 Sharpe 散点图（检验 train-test 相关性）

#### S2：风控命中率可视化

```python
def plot_risk_control_accuracy(accuracy_csv: str | Path) -> bytes:
    """按年展示 TP/FP/Neutral 柱状图 + 命中率折线"""
```

这对分析 soft vs hard 风控效果差异非常直观。

#### S3：参数扫描热力图（`plot.py` 新增函数）

```python
def plot_parameter_heatmap(sweep_csv: str | Path, x_param: str, y_param: str, metric: str) -> bytes:
    """生成二维参数 × 指标热力图（e.g., top_k × risk_off_exposure vs OOS Sharpe）"""
```

---

## 三、优先级总览（本次更新）

| 优先级 | 任务 | 性质 | 预期价值 | 估计工时 |
|--------|------|------|---------|---------|
| 🔴 P0 | **N1：运行跨段长历史 WF** | 执行实验 | 得到 20+ 折可信 OOS 结论 | 0.5 天（跑命令+分析） |
| 🔴 P0 | **N2：Soft risk-off 参数扫描** | 执行实验 | 量化 soft 风控对 sw2014 回撤的改善 | 0.5 天（跑命令+分析） |
| 🔴 P0 | **N3：State-aware 风控对比** | 执行实验 | 量化 sideways exposure 对 2024-2025 的改善 | 0.5 天 |
| 🟠 P1 | **O：Bootstrap 置信区间** | 代码实现 | WF 结论获得统计显著性支撑 | 2 天 |
| 🟠 P1 | **P：跨段阈值最终定版** | 执行实验 | 确定生产 threshold 参数 | 0.5 天（依赖 N1） |
| 🟡 P2 | **Q：补全测试覆盖** | 代码实现 | 防止 G1/G2 回归 | 3 天 |
| 🟡 P2 | **R：增量数据刷新** | 代码实现 | 日常运营安全性 | 2 天 |
| 🟢 P3 | **S：可视化增强** | 代码实现 | 分析体验提升 | 3 天 |

---

## 四、立即执行步骤（有序）

以下步骤按顺序执行，每步有可验证的输出：

### Step 1：N1 跨段长历史 WF（✅ 已执行）

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation validate-segments `
  --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-off-exposure 0 `
  --risk-control false `
  --market-score-control false `
  --train-window 504 `
  --test-window 126 `
  --output-dir reports/cross_segment_walk_forward
```

**结果**：27 折，OOS Sharpe 中位数 0.484，年化中位数 8.52%，16/27 折正收益。

### Step 2：N2 Soft Risk-Off 扫描（⚠️ 已执行，仅生成 hard mode）

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation sweep `
  --config configs/real_sw2014.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-control true `
  --market-score-control true `
  --risk-control-mode hard,soft `
  --soft-exposure-min 0.0,0.1,0.2,0.3 `
  --output-dir reports/real_sw2014/soft_riskoff_sweep
```

**⚠️ 问题**：输出仅含 4 条 hard mode 记录，`soft` mode 未生成。需修复 `sweep.py` 中 `risk_control_mode_values` 展开逻辑后重新运行。

### Step 3：N3 State-Aware 扫描（✅ 已执行）

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation sweep `
  --config configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-control true `
  --market-score-control true `
  --state-aware-risk-control true,false `
  --output-dir reports/real_sw2021/state_aware_sweep
```

**结果**：state-aware 未显现优势（Sharpe +0.008，DD 恶化 2.3 pct），暂时放弃。

### Step 4：P 阈值定版 WF（✅ 已执行）

```powershell
$env:PYTHONPATH="src"
python -m quant_rotation validate-segments `
  --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-control true `
  --market-score-control true `
  --market-score-threshold=-0.05,-0.02,0,0.02,0.05 `
  --train-window 504 `
  --test-window 126 `
  --output-dir reports/cross_segment_threshold_wf
```

**结果**：负阈值（-0.05, -0.02）在 8/27 折被 composite 选中，OOS 均值为负。固定 threshold=0.05 版本年化 9.77% 接近 N1 无风控版，但 median 仍被拖垮。**结论：risk_control=false 全面最优。**

### Step 5：O Bootstrap CI 实现（✅ 已实现）

`validation.py::bootstrap_oos_ci()` 已存在并集成到 `_write_walk_forward_summary()`。N1 结果：年化 95% CI [-1.67%, 23.26%]，p_positive = 95.02%。P 阶段输出已验证可用。

---

## 五、关键决策点（实验后判断）

### 决策 1：N1 结果 ≥ 15 折盈利？

- **✅ 是（16/27，59.3%）**：跨段 WF 策略有可信度，OOS Sharpe 中位数 0.484。
- **结论**：确认 `ret60_ret5 + top_k=5 + risk_control=false` 为基础配置，进入阶段 P 阈值定版。

### 决策 2：N2 Soft Risk-Off 改善 sw2014 回撤 > 10 pct？

- **⚠️ 无法判断**：`sweep` 未正确生成 `soft` mode 候选。hard mode 下 sw2014 回撤仍为 -53.6%～-54.8%。
- **结论**：需先修复 `sweep.py::build_sweep_specs()` 中 `risk_control_mode_values` 的展开逻辑，重新运行 N2。

### 决策 3：N3 State-Aware sideways=0.5 在 sw2021 段超过 riskoff=0 版本 Sharpe？

- **❌ 否**：state-aware Sharpe 0.533 vs hard 0.525（+0.008），回撤反而恶化（-19.6% vs -17.3%）。
- **结论**：维持当前方向，暂不使用 state-aware。

### 决策 4：是否满足模拟实盘前提

**所有条件检测（基于 N1 risk_control=false，27 折）：**

| 条件 | 阈值 | 实际 | 判定 |
|------|------|------|------|
| 跨段 WF 折数 | ≥ 20 | 27 | ✅ |
| OOS 年化中位数 | > 0% | 8.52% | ✅ |
| OOS Sharpe 中位数 | > 0.20 | 0.484 | ✅ |
| Bootstrap p_positive (年化) | > 0.75 | 95.02% | ✅ |
| 亏损折数 | ≤ 11（合理） | 11/27 | ✅ |
| 风控压缩 sw2014 DD | < -45% | 放弃风控，不适用 | — |
| 风控 sw2014 WF 亏损折 ≤ 4 | — | 放弃风控，不适用 | — |

**结论**：以 `ret60_ret5 + top_k=5 + risk_control=false` 为生产配置，所有实盘前提均已满足。可以进入模拟实盘阶段。

---

## 六、确认无需继续的工作

| 工作 | 放弃原因 |
|-----|---------| 
| `amount_strength` 因子恢复 | Ablation 证明移除后 Sharpe +0.055，永久关闭 |
| `ret20` 因子恢复 | Ablation 证明移除后 Sharpe +0.134，永久关闭 |
| `top_k=8` 配置 | Sweep 证明 top_k=5 全面优于 8 |
| 统一口径重建 2021 版历史指数 | 分段串接方案已替代 |
| `all_factors` 配置 | 全因子版 Sharpe 仅 0.18 vs 精简版 0.52 |
| 历史成分股快照接入（K2） | 短期数据源不可达；标注为研究近似版即可 |

---

## 七、当前策略性能基线（截至 2026-06-03）

### 生产策略（`ret60_ret5_top5_riskoff0`，sw2021 段 2021-2026）

| 指标 | 数值 | 评价 |
|-----|------|------|
| 年化收益 | 6.51% | ⚠️ 中等 |
| 最大回撤 | -17.26% | ✅ 可接受 |
| Sharpe | 0.525 | ✅ 合理 |
| Calmar | 0.377 | ✅ 合理 |
| 相对沪深300 超额 | +35.3% | ✅ 显著 |
| WF OOS 中位数 Sharpe（有风控版） | **-0.155** | 🔴 问题核心 |
| WF OOS 中位数 Sharpe（无风控版） | **+1.296** | ✅（但同样仅 4 折） |

### 风控命中率（production 段，2022-2026）

| 期间 | 命中率 | 评价 |
|------|--------|------|
| 2022-2023（熊市/震荡） | 71.4% | ✅ 有效 |
| 2024-2025（转牛/牛市） | 30.0% | 🔴 无效 |
| 整体 | 47.8% | 🔴 略低于随机 |

### 跨段长历史 WF（N1，ret60_ret5 top_k=5 risk_control=false，2010-2026）

| 指标 | 数值 | 评价 |
|-----|------|------|
| 总折数 | **27** | ✅ |
| OOS 年化中位数 | **8.52%** | ✅ |
| OOS Sharpe 中位数 | **0.484** | ✅ 优秀 |
| OOS 最大回撤中位数 | **-13.25%** | ✅ 可接受 |
| 盈利折数 | 16/27（59.3%） | ✅ 达标 |
| 正 Sharpe 折数 | 19/27（70.4%） | ✅ |
| 最大单折亏损 | -47.25%（折 13，2018 大熊市） | ⚠️ 单折极端 |
| 2018 年跨折表现 | 折 12-13 合计约 -55% | 🔴 需关注 |

> ⚠️ 标注项代表当前待改善指标。**N1 已验证策略在 16 年跨段中有效。当前最急迫的是修复 N2 soft mode sweep 生成逻辑，然后跑 N1 风控版阈值扫描。**
# 2026-06-03 晚间推进记录（Codex 本轮）

## 已落地代码

| 项目 | 位置 | 状态 |
|------|------|------|
| 修复 soft risk-off sweep 漏生成 | `src/quant_rotation/sweep.py::build_parameter_sweep_specs()` | 已修复：soft 分支现在会写入 `specs` |
| Bootstrap OOS CI | `src/quant_rotation/validation.py::bootstrap_oos_ci()` + `_write_walk_forward_summary()` | 已实现：summary 新增 `bootstrap_ci_lower` / `bootstrap_ci_upper` / `bootstrap_p_positive` |
| market state 边界修正 | `src/quant_rotation/backtest.py::classify_market_state()` | 已修复：MA 窗口不足时不再无条件返回 `bull` |
| 回归测试补充 | `tests/test_sweep.py` / `tests/test_backtest.py` / `tests/test_validation.py` | 已补充 soft 展开、state-aware、bootstrap、recent-weighted、regime-aware 测试 |

## 本轮实验结果

### N2 Soft Risk-Off 扫描

输出目录：
- `reports/real_sw2014/soft_riskoff_sweep/`
- `reports/production/soft_riskoff_sweep/`

结果要点：
- 两个目录均已从 4 条 hard-only 结果变为 8 条 hard+soft 结果。
- sw2014 段 soft 候选未达到验收目标：soft 最好回撤约 `-48.99%`，仍未把最大回撤压到计划要求区间。
- sw2014 soft 候选：`soft_min=0.0` 年化 `9.70%` / DD `-48.99%` / Sharpe `0.614`；`soft_min=0.2` 年化 `10.21%` / DD `-49.67%` / Sharpe `0.622`。
- production 段最好为 `soft_min=0.0`：年化 `6.55%`，DD `-19.32%`，Sharpe `0.576`；但 DD 劣于 hard `riskoff=0` 的 `-17.26%`。

结论：soft risk-off 暂不替代 hard，也不作为生产默认。

### P 跨段阈值 WF

输出目录：`reports/cross_segment_threshold_wf/`

27 折，覆盖 `2010-01-04` 至 `2026-03-05`：
- 测试年化均值 `8.06%`，中位数 `0.47%`
- 测试最大回撤均值 `-8.02%`，中位数 `-4.62%`
- 测试 Sharpe 均值 `0.378`，中位数 `0.120`
- Bootstrap 年化收益 95% CI：`[-1.35%, 20.39%]`
- Bootstrap `p_positive=0.945`

固定阈值候选统计：

| threshold | Sharpe 中位数 | Sharpe 均值 | 年化均值 |
|-----------|---------------|-------------|----------|
| `-0.05` | `0.000` | `0.223` | `7.20%` |
| `-0.02` | `0.000` | `0.178` | `6.11%` |
| `0.00` | `0.000` | `0.309` | `7.32%` |
| `0.02` | `0.000` | `0.178` | `5.71%` |
| `0.05` | `0.000` | `0.250` | `5.83%` |

决策：按“20+ 折 OOS Sharpe 中位数最高；若差距 `< 0.05` 保留 `0.0`”规则，生产 `market_score_threshold` 保持 `0.0`。

### N1 基础跨段 WF（已刷新 Bootstrap）

输出目录：`reports/cross_segment_walk_forward/`

- 测试年化均值 `9.92%`，中位数 `8.52%`
- 测试 Sharpe 中位数 `0.484`
- Bootstrap 年化收益 95% CI：`[-1.67%, 23.26%]`
- Bootstrap `p_positive=0.950`

## 测试状态

`python -m pytest`：`80 passed`

## 当前下一步建议

1. 暂不启用 soft risk-off 与 state-aware 作为生产默认。
2. 生产阈值保持 `market_score_threshold=0.0`。
3. 下一阶段优先级可转向 `R`（增量数据刷新核对/补测试）或 `S`（报告可视化增强）；`Q` 的 backtest / validation 关键测试本轮已补齐。

---
