# 行动计划：A 股行业动量轮动策略 下一步

> 基于对 `sector-rotation-quant-main` 全量代码、配置与报告的深度分析
> 分析日期：2026-06-03（接续 2026-06-02 版本）

---

## 零、执行进度更新（2026-06-03）

### 0.1 本次分析新增发现（相较 06-02 版本）

本次对所有报告数据做了定量深挖，发现三个此前未量化的严重问题：

#### 🔴 发现 1：生产 WF 的 OOS 表现 3/4 折亏损，均值被单折拉高

`reports/production/walk_forward/walk_forward_folds.csv` 显示：

| 折 | 测试区间 | 选中候选 | OOS 年化 | OOS Sharpe | OOS vs 沪深300 |
|---|---------|---------|---------|-----------|---------------|
| 1 | 2024-01-18～2024-07-29 | `ret60_ret120_ret5_top3_riskctrl1` | **-3.5%** | -0.255 | **-5.1%** |
| 2 | 2024-07-30～2025-02-10 | `ret60_ret120_ret5_top3_riskctrl1` | **-3.3%** | -0.055 | **-15.1%** |
| 3 | 2025-02-11～2025-08-12 | `ret60_ret5_top5_riskctrl1_mscore0` | **-13.6%** | -0.577 | **-12.9%** |
| 4 | 2025-08-13～2026-02-24 | `ret60_ret5_top5_riskctrl1_mscore1` | **+71.9%** | +2.237 | **+16.1%** |

OOS 年化均值 **+12.9%** 完全由折 4（2025 牛市）驱动；OOS **中位数为 -3.4%**，Sharpe 中位数 **-0.16**。  
→ **风控机制在 2024-2025 震荡转牛阶段反复踏空，OOS 超额为负。**

#### 🔴 发现 2：固定候选 WF 中无风控版本全面跑赢有风控版本

`reports/production/walk_forward/fixed_candidate_summary.csv`：
OOS 净值前 10 名全部为 `riskctrl0_mscore0`（无风控无市场评分），OOS 净值 **1.526**，相对沪深300 超额 **+5.8%**。
对比生产策略（有风控）WF OOS 净值仅 **1.051**，超额 **-4.2%**。

→ **在 4 折 WF 测试窗口中，关闭风控反而更好，与全样本结论相反。**

#### 🔴 发现 3：sw2014 段 -54.83% 回撤来源确认为"踏空型长期亏损"

`reports/real_sw2014/equity_curve.csv` 定量分析：
- **峰值：2015-06-12**，净值 **2.841**（捕捉到 2015 年初牛市）
- **谷底：2019-07-xx**，净值 **1.346**（4 年持续回撤）
- **机制**：2015 年底进入风控空仓后，2016–2019 市场多次小幅反弹，策略反复因市场评分不足而踏空，净值持续被侵蚀

sw2014 段 WF 11 折中，**6 折亏损（2016-2019 区间）**，仅 4 折盈利（2019 后）。
2017 年策略净值仅 1.51，而沪深300 净值已达 1.78——核心蓝筹牛市完全踏空。

---

### 0.2 现有功能完成度总结

| 功能模块 | 状态 | 说明 |
|---------|------|------|
| 价格动量因子（ret5/20/60/120） | ✅ 完整 | 已通过 ablation 确认 ret60+ret5 最优 |
| 成交额强度因子 | ✅ 完整 | 生产权重已置零（ablation 证明有害） |
| 广度因子管道 | ⚠️ 阶段性 | 当前成分股近似版；幸存者偏差未消除 |
| 多指数市场环境过滤 | ✅ 完整 | CSI300/CSIAll/ChiNext 三指数加权 |
| 分段行业宇宙（sw2000/2014/2021） | ✅ 完整 | 三段数据 + run-segments + sweep-segments |
| 参数扫描（sweep） | ✅ 完整 | 192 候选；最优 ret60_ret5_top5_riskoff0 |
| Walk-forward 验证 | ✅ 完整 | 支持 sharpe_plus_calmar 等指标 |
| 分段 walk-forward | ✅ 完整 | sw2000/2014/2021 各自 WF |
| 跨段长历史 walk-forward | ❌ 缺失 | 当前不支持跨段接续 WF |
| 动态风控（连续暴露） | ❌ 缺失 | 现仅支持固定 risk_off_exposure |
| 市场状态分类（牛/熊/震荡） | ❌ 缺失 | 现有单阈值二元开关 |
| 股票数据管道 | ⚠️ 阶段性 | 当前成分股近似版；历史快照版待建 |
| 估值/景气因子框架 | ⚠️ 工程完整 | 无真实数据；生产权重为 0 |
| HTML/图表报告 | ❌ 缺失 | 所有输出仅 CSV |
| 测试覆盖 | ⚠️ 有空缺 | cli/config/data/metrics/models/portfolio 无测试 |
| 增量数据刷新 | ❌ 缺失 | 每次 fetch 全量重写 |

---

## 一、核心问题诊断

### 问题 1：风控机制的二元开关在震荡/复苏市中系统性失效

当前 `risk_off_exposure = 0.0`（完全空仓）在以下市场环境中表现如下：

| 市场环境 | 策略行为 | 结果 |
|---------|---------|------|
| 纯熊市（2018、2022） | 空仓 | ✅ 大幅跑赢 |
| 纯牛市（2020-2021） | 满仓 | ✅ 跟上涨幅 |
| 震荡/缓慢复苏（2016-2019） | 反复进出 | ❌ 系统性踏空，4 年亏损 |
| 震荡转牛（2024-2025） | 反复触发空仓 | ❌ OOS 3/4 折亏损 |

根本原因：MA120 + market_score 是**滞后型**信号，在震荡市中产生大量伪阴性（错误触发空仓），每次错误空仓约损失 2-5% 回弹。

### 问题 2：OOS WF 样本太少，结论统计上不可靠

- 生产 WF：仅 **4 折**，每折约 6 个月
- sw2021 WF：仅 **4 折**（数据量不足）
- sw2014 WF：**11 折**，但 6 折亏损
- 无跨段接续 WF，无法使用全部 2010-2026 数据

4 折 WF 的 95% 置信区间极宽，单折结果（折 4 年化 +71.9%）主导均值，不可信。

### 问题 3：训练选取指标与测试结果相关性差

`sharpe_plus_calmar` 在训练期选出的候选，测试期超额均值为 **-4.2%**，说明当前指标存在系统性的 train-test 失配。原因可能是：
1. 训练期太短（约 2 年），不包含完整市场周期
2. 参数空间中高训练 Sharpe 的策略恰好是熊市下"空仓成功"的，不代表多种市场状态

### 问题 4：无跨市场周期稳健性验证

当前最好的全样本配置 `ret60_ret5_top5_riskoff0` 在：
- 2010-2014 段：年化 **-5.2%**（弱牛/震荡市）
- 2014-2021 段：年化 **10.3%** 但最大回撤 **-54.8%**
- 2021-2026 段：年化 **6.5%**，最大回撤 **-17.3%**

三段差异巨大，尚未找到在所有市场周期稳健有效的参数组合。

---

## 二、行动计划

### 阶段 G：风控机制重构（最高优先级，1-3 周）

> **这是当前策略框架最根本的缺陷，比任何数据扩展和参数调整都重要。**

#### G1：实现连续暴露曲线（Soft Risk-Off）

**目标**：将当前二元开关（满仓/全仓）改为基于市场评分的连续暴露函数。

**当前逻辑**：
```
if market_score > threshold:
    exposure = 1.0
else:
    exposure = risk_off_exposure  # 固定值，通常 0.0
```

**建议改为**：
```
soft_exposure = clamp(sigmoid_scale(market_score, center, steepness), min_exp, max_exp)
# 或更简单的线性插值版本：
soft_exposure = clamp(base_exp + slope * market_score, min_exp, max_exp)
```

**实现位置**：`backtest.py` 中的 `_market_exposure()` 函数（若不存在则新建）

**新配置参数**（`configs/*.toml` `[strategy]` 节）：
```toml
risk_control_mode = "soft"         # "hard"（当前）或 "soft"（新）
soft_exposure_min = 0.20           # 极度悲观时保留底仓
soft_exposure_max = 1.00           # 极度乐观时满仓
soft_exposure_center = 0.00        # market_score = 0 时对应 0.60 暴露
soft_exposure_steepness = 20.0     # sigmoid 陡度
```

**Sweep 新增候选**：
- `ret60_ret5_top5_softoff_riskctrl1`（soft risk-off）
- `ret60_ret5_top5_softoff0p2_riskctrl1`（最低仓位 20%）

**测试**：在 `test_backtest.py` 中增加 soft exposure 分支的单元测试

#### G2：实现市场状态分类器（Bull/Bear/Sideways）

**目标**：区分三种市场状态，在每种状态下使用不同的风控参数。

**分类方法**（从简到繁，按需选择）：
```python
def classify_market_state(market_score: float, trend_strength: float) -> str:
    if market_score > 0.05 and trend_strength > 0.03:
        return "bull"        # 强上升趋势
    elif market_score < -0.03:
        return "bear"        # 下降趋势
    else:
        return "sideways"    # 震荡
```

**每种状态的风控策略**：
```toml
[risk_control_by_state]
bull_exposure = 1.00
sideways_exposure = 0.50      # 震荡时保留半仓，不完全空仓
bear_exposure = 0.10          # 熊市保留底仓
```

**核心洞察**：sw2014 段踏空的根本原因是 2016-2019 的震荡市中策略把"不是熊市"误判为"必须满仓"，应当为震荡态设置专属暴露。

#### G3：市场分段回测诊断报告

新增 CLI 子命令 `diagnose-risk-control`，对已有回测结果进行：
1. 计算每次"空仓事件"后市场的实际走势（空仓是否有效规避了下跌）
2. 统计空仓事件的**命中率**（空仓后市场确实下跌）与**漏报率**（空仓后市场上涨）
3. 按市场状态分段输出空仓效果统计

输出文件：`reports/*/risk_control_accuracy.csv`

---

### 阶段 H：跨段长历史 Walk-Forward（高优先级，2-4 周）

> 当前 4 折 WF 统计上不可靠；需要覆盖 2010-2026 全部 16 年数据的跨段 WF。

#### H1：实现跨段 walk-forward 子命令

新增 `validate-segments` 子命令，接受多段配置 + WF 参数：

```powershell
python -m quant_rotation validate-segments `
  --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml `
  --industry-only `
  --walk-forward `
  --train-window 504 `
  --test-window 126 `
  --output-dir reports/cross_segment_walk_forward
```

**实现方案**：
1. 把三段数据按时间顺序接续成一个合并后的 `PriceData` 对象（行业列取最小公共集，或为缺失行业填 NaN）
2. 在合并后的时间序列上运行标准的 `resolve_walk_forward_splits`
3. 对每折的 train/test 边界跨越段边界的情况：在清仓日（行业宇宙切换日）前后设置换手率=100%

**预期效果**：
- WF 折数从 4 折增加到 **20-30 折**（覆盖 2010-2026 全部）
- OOS Sharpe 的 95% 置信区间从 ±1.1 缩窄到 ±0.4
- 能看到策略是否在 2015 崩盘前后、2018 大熊市等多个历史事件中稳健

#### H2：跨段长历史的市场阈值最终定版

在 `validate-segments` 的基础上，对 `market_score_threshold ∈ {-0.05, 0, 0.02, 0.05}` 各跑一次跨段 WF：

```powershell
python -m quant_rotation validate-segments `
  --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --market-score-threshold=-0.05,-0.02,0,0.02,0.05 `
  --walk-forward `
  --output-dir reports/cross_segment_threshold_wf
```

**决策准则**：
- 在 20+ 折的 OOS 中，OOS Sharpe 中位数更高的阈值为最优
- 若无明显差异（中位数 Sharpe 差 < 0.1），保留 `0.0` 不变
- 若 `soft exposure` 方案通过 G1 实现，则阈值对结果的影响应显著减小

---

### 阶段 I：OOS 选择机制改进（中优先级，2-3 周）

> 当前 WF 训练选出的候选，OOS 中位数均为负——选择标准存在根本性问题。

#### I1：增加时代权重（Recent-Biased Training Score）

当前训练期所有时点等权，导致 2 年前的熊市数据权重等于最近牛市数据。建议新增：

```python
def time_weighted_selection_score(metrics: dict, run_dates: list[date]) -> float:
    """最近 1 年的 Sharpe 权重 = 2x，其余 1x"""
    recent_sharpe = compute_recent_sharpe(run_dates, lookback_days=252)
    overall_sharpe = metrics["sharpe_ratio"]
    return 0.6 * recent_sharpe + 0.4 * overall_sharpe
```

**候选指标名**：`recent_weighted_composite`

#### I2：引入市场状态条件选择

在训练阶段，分别统计候选在"牛市折"和"熊市折"的表现，选择**当前市场状态**下历史表现最优的候选：

```python
def regime_aware_selection(runs, current_regime: str) -> ParameterSweepRun:
    if current_regime == "bear":
        return max(runs, key=lambda r: r.metrics["calmar_ratio"])
    elif current_regime == "bull":
        return max(runs, key=lambda r: r.metrics["excess_return_vs_equal_weight"])
    else:  # sideways
        return max(runs, key=lambda r: r.metrics["sharpe_ratio"] - abs(r.metrics["max_drawdown"]))
```

#### I3：增加 Bootstrap 置信区间报告

对 WF OOS 结果做 Bootstrap 重采样（10,000 次）估计 Sharpe、年化收益的 95% CI：

```python
def bootstrap_oos_ci(fold_returns: list[float], n_bootstrap: int = 10000) -> dict:
    samples = [np.mean(np.random.choice(fold_returns, len(fold_returns))) for _ in range(n_bootstrap)]
    return {"mean": np.mean(samples), "ci_lower": np.percentile(samples, 2.5), "ci_upper": np.percentile(samples, 97.5)}
```

输出到 `walk_forward_summary.csv` 中新增 `test_annualized_return_ci_lower` / `ci_upper` 列。

---

### 阶段 J：补全测试覆盖（中优先级，与 G/H 并行）

当前 `cli.py`（1329 行）、`config.py`（85 行）、`data.py`（162 行）、`metrics.py`（132 行）、`models.py`（179 行）、`portfolio.py`（32 行）均无测试文件。

#### J1：新增 `test_config.py`

覆盖：
- `load_config()` 对合法 TOML 文件的正常加载
- 缺少必填字段时抛出 `ValueError`
- `risk_control_mode = "soft"` 等新字段的正确解析
- `[market_weights]` 权重之和不为 1 时的警告/归一化

#### J2：新增 `test_data.py`

覆盖：
- `load_wide_close_csv()` 处理 NaN 行
- `align_asset_data()` 在日期不对齐时的行为
- `load_stock_industry_map_csv()` 同时兼容静态格式和快照格式

#### J3：新增 `test_metrics.py`

覆盖：
- `summarize_performance()` 空序列的边界处理
- `annual_returns()` 跨年度的切分逻辑
- Sharpe 分子为 0 时的处理

#### J4：补充 `test_segments.py` 场景

当前仅 2 个测试，缺少：
- 段边界跨越时等权/基准净值的正确串接
- `sweep-segments` 候选名不匹配时的 graceful 降级
- 行业列不完全重叠时的处理

---

### 阶段 K：数据层增强（中低优先级，按资源决定）

#### K1：增量数据刷新（delta update）

当前 `fetch-real-data` 每次全量重写所有 CSV，在日常运营中既慢又不安全。

新增 `--update-mode append` 参数：
```python
# 读取 manifest.json 中的 last_date
# 只从 last_date+1 抓取新数据
# 追加写入现有 CSV，更新 manifest
```

实现位置：`real_data.py` 中 `fetch_and_write_real_data()` 增加 `update_mode` 参数

#### K2：历史成分股快照接入（Phase 3/5 的前提）

当前广度数据和股票数据管道均使用当前成分股（幸存者偏差），导致：
- `breadth20/60` 仅能作为研究近似，不进生产
- `stock_close.csv` 的历史回测结论不可信

**可行路线**（按优先级排序）：
1. **Tushare Pro**：`sw_daily` 接口提供申万行业历史日线 + `index_member_all` 提供历史成分快照。需 Tushare Pro 账号。
2. **Wind/同花顺 API**：`INDEXMEMBERS()` 历史成分。需机构账号。
3. **AKShare 历史成分**：检查 `index_component_sw` 是否支持 `date` 参数。若支持，可按季度快照逐日拉取。

如果以上均不可行，则：
- 在 `breadth_manifest.json` 和 `stock_manifest.json` 中明确标注为"研究近似版"
- 在 README 中增加独立章节说明数据局限性和潜在 bias 来源

#### K3：行业估值/景气数据接入（Phase F 前提）

当前 `industry_valuation.csv` 和 `industry_prosperity.csv` 仅有 sample 数据。

**建议接入方式**：
1. 行业 PE/PB 分位数：AKShare `stock_zh_a_hist_index_analysis_sw` → 计算滚动 252 日历史分位数
2. 景气代理：近 20 日成交额增速（已有 `industry_amount.csv`）+ AKShare 分析师评级修正方向（研究阶段）

---

### 阶段 L：可视化与报告增强（低优先级，增量推进）

#### L1：HTML 净值曲线报告

当前所有输出仅 CSV，缺少直观图表。建议新增：

```powershell
python -m quant_rotation plot --config configs/production.toml --output reports/production/
```

使用纯 Python（`matplotlib`）生成：
- 策略净值 vs 沪深300 vs 等权基准（三线图）
- 分年度超额柱状图
- 回撤水下图（drawdown underwater chart）
- 持仓期收益分布直方图

输出格式：HTML（内嵌 base64 图片）+ PNG

#### L2：WF 折叠对比图

对每次 walk-forward 输出：
- 各折 OOS 净值曲线（多线图）
- 训练指标 vs 测试指标散点图（检验相关性）
- 选中候选的历史变化时间轴

#### L3：参数扫描热力图

对 `parameter_sweep.csv` 生成：
- `top_k × risk_off_exposure` 的 OOS Sharpe 热力图
- 不同因子组合的 Calmar vs Sharpe 散点图

---

## 三、优先级总览（更新版）

| 优先级 | 任务 | 当前状态 | 预期收益 | 估计工时 |
|--------|------|---------|---------|---------|
| 🔴 P0 | **G1：连续暴露风控（soft risk-off）** | ❌ 未实现 | 修复 2016-2019/2024-2025 系统性踏空 | 2-3 天 |
| 🔴 P0 | **H1：跨段长历史 WF（20+ 折）** | ❌ 未实现 | 使验证结论统计上可靠 | 3-5 天 |
| 🟠 P1 | **G2：市场状态分类器（Bull/Bear/Sideways）** | ❌ 未实现 | 按市场状态差异化风控 | 2-3 天 |
| 🟠 P1 | **G3：空仓事件命中率诊断报告** | ❌ 未实现 | 量化风控机制的真实价值 | 1 天 |
| 🟠 P1 | **H2：跨段长历史阈值最终定版** | ⚠️ 依赖 H1 | 解决 threshold 悬而未决问题 | 1 天 |
| 🟠 P1 | **I1：时代权重训练选择分数** | ❌ 未实现 | 改善 WF 训练→测试转化率 | 1-2 天 |
| 🟡 P2 | **I3：Bootstrap OOS 置信区间** | ❌ 未实现 | 量化结论的统计置信度 | 1 天 |
| 🟡 P2 | **J1-J4：补全测试覆盖** | ⚠️ 有空缺 | 防止回归，提升代码可信度 | 3-4 天 |
| 🟡 P2 | **I2：市场状态条件候选选择** | ❌ 未实现 | 依赖 G2，进一步改善 OOS | 2 天 |
| 🟡 P2 | **K1：增量数据刷新** | ❌ 未实现 | 日常运营效率 | 1-2 天 |
| 🟢 P3 | **K2：历史成分股快照接入** | ⚠️ 阶段性 | 解锁 Phase 3/5 | 取决于数据源 |
| 🟢 P3 | **K3：行业估值/景气数据接入** | ⚠️ 阶段性 | 解锁 Phase F | 取决于数据源 |
| 🟢 P3 | **L1-L3：可视化报告** | ❌ 未实现 | 可读性提升 | 3-5 天 |

---

## 四、立即执行的具体步骤

以下按顺序执行，每步均有可验证的输出：

### Step 1：空仓命中率诊断（G3，1 天，零代码改动）

用现有数据做离线分析，不需要改代码：

```python
# 读取 reports/production/rebalances.csv
# 读取 data/real/benchmark_close.csv
# 对每个"空仓期"（exposure=0 的调仓区间）：
#   计算该期间沪深300 的实际涨跌幅
#   若跌幅 > 2%：命中（空仓有效）
#   若涨幅 > 2%：漏报（空仓无效，错过上涨）
```

**输出**：`reports/production/risk_control_accuracy.csv`
```
event_type, date_start, date_end, benchmark_return, result
risk_off,   2024-02-01, 2024-03-15, +3.2%,         FALSE_POSITIVE (错误空仓)
risk_off,   2024-10-01, 2024-11-14, -5.1%,         TRUE_POSITIVE  (正确空仓)
...
summary: hit_rate=41.4%, false_alarm_rate=58.6%
```

若命中率 < 50%，则 G1/G2 的优先级进一步提升。

### Step 2：Soft Risk-Off 原型实现（G1，2-3 天）

在 `backtest.py` 的 `_compute_risk_exposure()` 中（或新建此函数）增加：

```python
def soft_risk_exposure(
    market_score: float,
    center: float = 0.0,
    steepness: float = 20.0,
    min_exp: float = 0.2,
    max_exp: float = 1.0,
) -> float:
    """Sigmoid-shaped continuous exposure based on market score."""
    import math
    raw = 1.0 / (1.0 + math.exp(-steepness * (market_score - center)))
    return min_exp + (max_exp - min_exp) * raw
```

对应的 `StrategyConfig` 新增：
```python
risk_control_mode: str = "hard"   # "hard" | "soft"
soft_exposure_min: float = 0.20
soft_exposure_max: float = 1.00
soft_exposure_center: float = 0.00
soft_exposure_steepness: float = 20.0
```

**验证命令**：
```powershell
python -m quant_rotation sweep `
  --config configs/production.toml `
  --industry-only `
  --factor-set ret60_ret5 `
  --top-k 5 `
  --risk-control-mode soft `
  --soft-exposure-min=0.1,0.2,0.3 `
  --output-dir reports/production/soft_riskoff_sweep
```

**验收标准**：sw2014 段最大回撤从 **-54.8%** 降低至 **< -40%**，且年化收益维持 > 8%。

### Step 3：跨段 WF 基础设施（H1，3-5 天）

在 `segments.py` 中新增 `merge_segment_price_data()`：

```python
def merge_segment_price_data(
    segments: list[tuple[PriceData, str]],
    fill_missing: bool = True,
) -> PriceData:
    """
    Merge multiple PriceData segments into one contiguous timeline.
    Industries not present in a segment are filled with the industry 
    equal-weight for that day (to avoid look-ahead bias).
    """
```

在 `cli.py` 中新增 `validate-segments` 子命令，复用现有 `run_walk_forward_validation`。

**验收标准**：在 sw2000/sw2014/sw2021 三段数据上跑出 **20+** WF 折，OOS Sharpe 的中位数和 95% CI 均稳健估计。

---

## 五、关键决策点

### 决策 1：Soft Risk-Off 方案在 sw2014 段效果如何？

**实验**：用 soft_exposure_min = 0.2、0.3 分别跑 sw2014 段全样本回测，与 hard_exposure=0 对比：

| 指标 | hard_riskoff=0（当前）| soft_min=0.2 | soft_min=0.3 |
|-----|---------------------|-------------|-------------|
| 年化 | 10.28% | ? | ? |
| 最大回撤 | -54.83% | ? | ? |
| 月胜率 | 33.7% | ? | ? |

**决策准则**：若 soft_min=0.2 或 0.3 能把最大回撤压缩至 < -40%，同时年化 > 8%，则替换 production.toml 的 `risk_off_exposure`。

### 决策 2：跨段 WF 的行业列对齐策略

三段行业宇宙不同（23/28/31 个行业），跨段 WF 有以下对齐方案：

| 方案 | 行业数 | 优点 | 缺点 |
|-----|-------|------|------|
| 最小公共集 | ~15 | 严格无偏 | 损失 50% 行业信息 |
| 各段使用自己的行业列 | 变化 | 保留最大信息 | 段边界换手率突增 |
| 填充缺失为等权 | ~31 | 行业数稳定 | 引入轻微 look-ahead |

**推荐**：各段使用自己的行业列，段边界强制 100% 换手一次（代表宇宙重构）。

### 决策 3：何时进入"模拟实盘验证"阶段

**前提条件**（需要同时满足）：
1. Soft risk-off 实施后，sw2014 段最大回撤 < -45%
2. 跨段长历史 WF（20+ 折）的 OOS 年化中位数 > 0%
3. 跨段 WF 的 OOS Sharpe 中位数 > 0.15
4. sw2014 段 WF（11 折）中，亏损折 ≤ 4 折（目前 6 折）

若以上条件在 G1+H1 完成后达到，则可将策略导出为可定期运行的生产信号，每 20 个交易日自动输出下一期行业权重。

---

## 六、已确认无需继续的工作

| 工作 | 放弃原因 |
|-----|---------|
| `amount_strength` 因子恢复 | Ablation 证明移除后 Sharpe +0.055，永久关闭 |
| `ret20` 因子恢复 | Ablation 证明移除后 Sharpe +0.134，永久关闭 |
| 统一口径重建 2021 版历史指数 | 工程量大且幸存者/权重误差难以量化；已有分段串接方案替代 |
| `all_factors` 配置 | 全因子版 Sharpe 仅 0.18，精简版 0.52，差距过大 |
| `top_k=8` 的高分散版本 | Sweep 显示 top_k=5 在所有维度优于 top_k=8 |

---

## 七、当前策略性能基线（截至 2026-06-03）

### 生产策略（`ret60_ret5_top5_riskoff0`，2021-2026）

| 指标 | 数值 |
|-----|------|
| 年化收益 | 6.51% |
| 最大回撤 | -17.26% |
| Sharpe | 0.525 |
| Calmar | 0.377 |
| 相对沪深300 累计超额 | +35.3% |
| WF OOS 年化中位数 | **-3.4%**（⚠️） |
| WF OOS Sharpe 中位数 | **-0.155**（⚠️） |

### 长历史串接（2010-2026）

| 指标 | 数值 |
|-----|------|
| 年化收益 | 5.16% |
| 最大回撤 | **-54.83%**（⚠️） |
| Sharpe | 0.387 |
| 相对沪深300 累计超额 | +58.0% |
| 跨段 WF OOS 中位数 | **未知**（需 H1 完成） |

> ⚠️ 标注项代表当前最需要改善的指标，对应行动计划阶段 G/H。