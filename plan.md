# 行动计划 v2：从「有效实验」到「稳健年化」
> 深度诊断基于：全量代码、all 实验报告目录（Phase A~E）、
> 27 折跨段 WF、Phase D 股票层结果、Phase E 最终扫描
> 分析日期：2026-06-06
> 版本：本文件完整替代上一版 plan.md，聚焦「已验证成果的组合与稳定化」
> 最后更新：2026-06-06（Phase J 代码完成）

## 0.0 执行进度快照（2026-06-06 更新）

| 阶段 | 状态 | 关键结论 |
|------|------|---------|
| F：仓位控制重构 | ✅ 代码完成 | soft mode、defensive mode、annual budget、vol target 均已实现+测试（130/130 通过） |
| G：年度收益稳定化 | ✅ 代码完成 | 年度预算控制在当前收益水平下不触发（回报太低）；vol_target 在 H2 测试中导致 -40% 回撤 |
| H：因子精简 + WF | ✅ 验证完成 | 3 个候选配置已创建；19 折跨段 WF 完成，最佳固定候选 = top_k=3, hard mode, risk_off=0 |
| I：数据质量 | ⚠️ 工具完成 | `data_integrity_check.py` 和 `annual_returns_summary.py` 已创建；AKShare 历史成分股验证未做 |
| **J：收益增强** | **✅ 代码完成** | **防御板块过滤（J.1）、相对收益模式（J.2）、多策略聚合（J.3）均已实现+测试** |
| Phase D 重启 | ❌ 条件不满足 | 当前最优仍为生产基线（年化 6.51%），软仓位未超硬模式 |

**实验结论**：本次新增的软仓位 + 底仓机制在回测中**未能超越生产基线**（hard mode, risk_off=0）。
- sw2021 单段：生产基线 6.51% vs H1 防御型 4.27%
- 19 折跨段 WF（sw2014+sw2021）：OOS 中位数 0%，bootstrap p=71.8%
- 最佳固定候选：`ret60_ret5_top3_riskoff0_modeh_riskctrl1_mscore0`（OOS 净值 1.678）

详见新增的 §0.4「本轮实验结果汇总」。

---

## 零、全面盘点：你走到哪了

### 0.1 已完成实验一览

| 阶段 | 内容 | 状态 | 关键结论 |
|------|------|------|---------|
| A：因子架构 | `rel_ret60`、`consistency60`、`prosperity` 实现 | ✅ 完成 | 代码已实现，sweeps 已跑 |
| B：组合构建 | `softmax`、`vol_parity`、`adaptive_top_k` | ✅ 完成 | 全部在 `portfolio.py` 实现 |
| C：风控精细化 | 双均线、state-aware regime、MA60 | ✅ 完成 | configs 已有，部分 sweep 结果存在 |
| D：股票层 Alpha | 个股数据获取 + 股票内精选 | ✅ 完成 | `exp_d_best`: Sharpe 0.651，年化 10.82% |
| E：最终组合扫描 | 全因子 × 参数矩阵扫描（sw2021） | ✅ 完成 | 最优仍是 `ret60_ret5`，年化 7.3% |
| WF：跨段验证 | 27 折跨段 WF OOS | ✅ 完成 | OOS Sharpe 中位数 0.043，bootstrap p 89.3% |

### 0.2 核心症结：实验结论彼此矛盾

你已经做了大量实验，但**没有找到在 WF OOS 中一致稳健的配置**。症结如下：

**症结 1：rel_ret60 在 sw2021 单段好，WF OOS 差**
- `exp_rel_momentum`（sw2021）：Sharpe 约 0.55
- WF OOS 中 `rel_ret60_ret5_*` 系列的 27 折 OOS 最终净值：**1.73**（与 benchmark 相当）
- 原因：`rel_ret60` 依赖 `market_close.csv`，早期 sw2000/sw2014 折中市场数据不完整，
  因子在这些折中退化为 0，选择频次极低（仅 `rel_ret60_ret5_*` 系列共 5 次被选中）

**症结 2：softmax + ret60 是 WF 中的实际胜者，但被忽视**
- `fixed_candidate_summary.csv` 第 1 名：`ret60_top3_riskoff0p3_pmsoftmax`，27 折 OOS 净值 **2.09**
- 第 2 名：`ret60_top3_riskoff0p3_pmequal`，净值 2.04
- 但 WF 动态选择（median OOS Sharpe 0.043）表明：在 WF 中，这些"最优"固定候选
  仅在少数折中成立，训练集选出的候选在测试集中大量失效

**症结 3：Phase D 股票层的收益来源存疑**
- `exp_d_best`：Sharpe 0.651，年化 10.82%，最大回撤 -22.2%
- 但年化分解显示 2022 年 0%（exposure=0 的贡献），2025 年 +2.3%（跑输等权 26%）
- 主要超额来自 2021-2022 下行期的 0 仓位，以及 2026 年（仅半年）+33.5%
- **使用了当前成分股地图**（`stock_industry_map.csv` 是静态的），存在潜在前视偏差

**症结 4：月胜率根本性问题未解决**
- 最新最优配置 `exp_d_best`：月胜率 **34.5%**（Phase D），`real_sw2021`：29.1%
- 目标是 >52%——两者相差悬殊，说明策略仍是「期权型 Beta 暴露」而非真正 Alpha

### 0.3 重新定义问题

**你的真实目标是**：每年收益稳定，而不仅仅是长期回测好看。

「每年稳定」的量化含义：
- 年度亏损年份不超过 1/6（即每 6 年最多亏 1 年）
- 没有单年超过 -20% 的大幅回撤
- 任意 3 年复合收益 > 0

当前状态：
- 2021：0%（risk-off）
- 2022：0%（risk-off，这算「规避」不算「赚钱」）
- 2023：-4.6%（行业轮动失效）或 -1.3%（exp_d_best）
- 2024：+8.6% 或 +14.9%
- 2025：+18.6% 或 +2.3%
- 2026（H1）：+6.5% 或 +33.5%

**根本矛盾**：当 risk-off = 0 时，策略在震荡市（2021、2023）不赚钱，
靠牛市（2025）和规避（2022）勉强维持总收益。
这不是「每年稳定」，这是「高波动 + 间歇性成功」。

### 0.4 本轮实验结果汇总（2026-06-06 执行更新）

以下为 Phase F/G/H 在本轮执行中的实际回测数据。

#### 0.4.1 sw2021 单段：各配置对比

| 配置 | 年化 | 夏普 | 最大回撤 | 2022 | 2023 | 2024 | 2025 |
|------|------|------|---------|------|------|------|------|
| **生产基线** (hard, risk_off=0, top_k=5) | **6.51%** | **0.52** | **-17.3%** | 0.0% | -4.6% | +8.6% | +18.6% |
| H1 防御型 (soft 30% + budget + defensive) | 4.27% | 0.37 | -21.2% | -1.2% | -2.2% | +4.7% | +13.1% |
| H1 v3 (soft 40% + top_k=5) | 4.94% | 0.41 | -21.4% | -4.2% | -2.6% | +6.9% | +12.4% |
| H2 均衡型 (vol_target + prosperity) | -1.48% | 0.02 | -40.7% | -12.2% | -13.2% | +0.8% | +13.8% |
| H3 进取型 (rel_ret60 + soft) | 4.74% | 0.40 | -22.1% | -2.3% | -1.9% | -1.8% | +17.2% |
| WF 最优候选 (hard, top_k=3, mscore=false) | 4.22% | 0.34 | -26.7% | — | — | — | — |

**结论**：软仓位（floor 30~40%）在 2022 年承担了 1-4% 的亏损，而硬模式规避了全部损失。牛市中的仓位加成不足以弥补。**年度预算控制在当前收益水平下从未触发。**

#### 0.4.2 19 折跨段 WF（sw2014 + sw2021）

| 指标 | 训练集 | 测试集 |
|------|--------|--------|
| 年化收益均值 | 10.1% | 3.1% |
| 年化收益中位数 | 6.5% | **0.0%** |
| 夏普均值 | 0.53 | 0.07 |
| Bootstrap p_positive | — | **71.8%** |
| 月胜率 | 36.0% | 33.6% |

**WF 最佳固定候选（OOS 净值排名）**：
1. `ret60_ret5_top3_riskoff0_modeh_riskctrl1_mscore0` → OOS 1.678，超额基准 +12.1%
2. `ret60_ret5_top5_riskoff0_modeh_riskctrl1_mscore0` → OOS 1.640，超额基准 +9.6%
3. `ret60_ret5_top3_riskoff0p3_modeh_riskctrl1_mscore0` → OOS 1.549，超额基准 +3.5%

**WF 核心发现**：
- top_k=3 > top_k=5 > top_k=8（越小越好）
- risk_off=0 > risk_off=0.3 > risk_off=0.5（全规避最好）
- market_score_control=false > true
- 动态候选选择失效（训练 Sharpe 0.53 → 测试 Sharpe 0.07，严重过拟合）

---

## 一、战略转向：从「最大化回测 Sharpe」到「每年正收益」

### 1.1 新的核心原则

**旧路径**：在参数空间里搜索最高 Sharpe，然后 WF 验证 → 屡次失败  
**新路径**：先确保每年正收益（稳定），在此基础上提高年化水平

这需要从根本上改变风险管理逻辑：

```
旧模式：risk_on 满仓(100%) ↔ risk_off 空仓(0%)
新模式：动态仓位(20%~100%)，永远不完全清仓，永远不超过预设波动预算
```

### 1.2 策略重构的三层架构

```
┌──────────────────────────────────────────────────────────┐
│ 层 1：仓位控制（最高优先级）                               │
│ 目标：控制年度最大回撤 < 15%，使得每年大概率正收益           │
│ 工具：软仓位映射（market_score → exposure），基准底仓 30%  │
├──────────────────────────────────────────────────────────┤
│ 层 2：行业选择（Alpha 来源）                               │
│ 目标：在仓位内选择超越等权的行业                             │
│ 工具：rel_ret60（主）+ consistency60（辅）+ prosperity（辅）│
├──────────────────────────────────────────────────────────┤
│ 层 3：股票精选（增量 Alpha，可选）                          │
│ 目标：行业内进一步提升每笔仓位质量                           │
│ 工具：低波动 + 一致性（已验证有效，但需无前视数据）           │
└──────────────────────────────────────────────────────────┘
```

---

## 二、阶段 F：仓位控制重构（P0，第 1~2 周，无新数据依赖）

> 这是最重要的改动。目前所有失败的年份（2021 全空仓、2023 轮动失效）
> 都源于仓位逻辑的极端化。

### F.1 诊断：为什么硬风控带来稳定性幻觉

| 硬风控行为 | 结果 | 问题 |
|-----------|------|------|
| 2022 全空 | 规避 -21.6% 基准 | ✅ 成功，但依赖「完全正确的清仓时机」 |
| 2021 全空 | 错过 -2.8% 小跌后的反弹 | ❌ 0 收益，不是稳定 |
| 2024Q4 空仓 | 错过 +23.2% 大反弹 | ❌ 大踏空 |
| 2023 半空 | -4.6% 跑输等权 | ❌ 少量仓位还亏损 |

**关键洞察**：硬风控在「大熊市」有效，但在 A 股频繁的「震荡 + 政策驱动反弹」
模式下，完全清仓的机会成本极高。2022 年规避了 21.6%，但 2024 年错过了 23.2%，
净效果接近零，同时增加了大量不必要的交易成本和心理压力。

### F.2 解决方案：软仓位映射 + 底仓机制

**核心改动：将 `risk_off_exposure` 从 0 提高到 0.3，并启用软仓位映射。**

#### F.2.1 软仓位映射配置

```toml
# 新生产配置核心
[strategy]
risk_control_mode = "soft"          # 软映射，非二元硬切换
soft_exposure_min = 0.30            # 最差市场环境下仍持仓 30%（底仓）
soft_exposure_max = 1.00            # 最佳环境下满仓
soft_exposure_center = 0.00         # market_score = 0 时对应的仓位梯度中点
soft_exposure_steepness = 15.0      # 映射曲线斜率（可调）
risk_off_exposure = 0.30            # 即使触发硬风控也保持 30%
market_score_control = true
market_score_threshold = 0.0
```

**软映射函数**（已在 `backtest.py::_state_aware_exposure` 实现）：

$$\text{exposure} = E_{\min} + (E_{\max} - E_{\min}) \cdot \sigma(\text{score} \cdot k)$$

其中 $\sigma$ 是 Sigmoid 函数，$k$ 是 steepness。

#### F.2.2 底仓行业选择

当仓位处于底仓区间（30%~50%）时，底仓应配置在：
- 高股息/低波动行业（银行、公用事业）—— 防御性持仓
- 而非正常轮动选出的高动量行业 —— 高动量在下跌市中容易大幅回撤

**实现**：新增 `defensive_mode` 逻辑：当 `exposure < 0.5` 时，
改用 `vol20` 最低的 Top-3 行业作为防御仓位。

```python
# backtest.py 新增辅助函数
def _select_defensive_holdings(
    factor_snapshot: FactorSnapshot,
    top_k: int = 3,
) -> dict[str, float]:
    """当 exposure < 0.5 时使用：选择波动率最低的行业作为防御持仓"""
    vol_scores = factor_snapshot.fields.get("vol20", {})
    if not vol_scores:
        return {}
    # 按 vol20 从低到高排序（选最低波动）
    ranked = sorted(vol_scores.items(), key=lambda x: x[1])
    holdings = [asset for asset, _ in ranked[:top_k]]
    per_weight = 1.0 / len(holdings)
    return {asset: per_weight for asset in holdings}
```

#### F.2.3 实验 F2-EXP1：软仓位 + 底仓扫描

**参数矩阵（在 sw2021 上）**：

| 参数 | 扫描值 |
|------|-------|
| `soft_exposure_min` | 0.2, 0.3, 0.4, 0.5 |
| `soft_exposure_steepness` | 10, 15, 20 |
| `risk_off_exposure` | 0.2, 0.3 |
| `defensive_mode` | true, false |

```bash
python -m quant_rotation sweep \
    --config configs/real_sw2021.toml \
    --industry-only \
    --factor-set ret60_ret5 \
    --risk-control-mode soft \
    --soft-exposure-min 0.2,0.3,0.4,0.5 \
    --soft-exposure-steepness 10,15,20 \
    --risk-off-exposure 0.2,0.3 \
    --output-dir reports/exp_f2_soft_exposure
```

**验收标准（sw2021 分年验证）**：
- 2023 年策略收益 > -2%（当前最好 -1.3%，最差 -4.6%）
- 2021 年策略收益 > 1%（当前 0%，完全空仓）
- 2022 年策略收益 > -5%（允许小幅亏损，换取其他年份的稳定）
- 全段最大回撤 < -20%

### F.3 跨周期底仓收益预估

如果底仓 30% 配置在低波动行业（银行/公用事业），历史上这类行业的年化：
- 银行：约 5-8%（含股息）
- 公用事业：约 4-7%
- 底仓贡献：0.3 × 6% ≈ **年化 +1.8%** 的稳定贡献

这意味着即使上层动量选股完全失效（超额 = 0），策略仍有 ~2% 基础年化。
与此同时，2022 年规避损失从 `100% × (-21.6%) = -21.6%` 变为
`30% × (-21.6%) = -6.5%`，完全可接受。

---

## 三、阶段 G：年度收益稳定化机制（P0，第 2~3 周）

> 专门针对「每年收益稳定」目标设计的新机制，是对历史失败案例的直接回应。

### G.1 年度动态目标仓位（Annual Budget Control）

**核心思路**：当年截至目前的收益已经超过年度目标时，降低仓位锁定收益；
当年截至目前的收益低于年度目标时，维持正常仓位。

这不是「止盈」，而是「动态风险预算」：年初风险预算充足，可以放手博取 Alpha；
年中已累积足够收益后，降低风险避免回吐。

```python
# backtest.py 新增函数
def _annual_budget_exposure_adjustment(
    strategy_equity: list[float],
    current_index: int,
    dates: list[date],
    annual_target: float = 0.12,      # 年度目标收益 12%
    lock_trigger: float = 0.10,       # 当年已赚 10% 后开始收缩
    min_exposure_after_lock: float = 0.50,  # 锁定后最低仓位
) -> float:
    """
    当年截至当前的收益超过 lock_trigger 时，返回收缩因子（< 1.0）。
    收益越高于目标，收缩越多。
    """
    current_year = dates[current_index].year
    year_start_index = next(
        (i for i, d in enumerate(dates) if d.year == current_year),
        0,
    )
    if current_index <= year_start_index:
        return 1.0

    ytd_return = (
        strategy_equity[current_index] / strategy_equity[year_start_index] - 1.0
    )

    if ytd_return < lock_trigger:
        return 1.0  # 还没到目标，全力运行

    # 超过触发线后线性收缩：ytd=10% 时 factor=1.0，ytd=20% 时 factor=0.5
    excess = ytd_return - lock_trigger
    scale = lock_trigger  # 归一化区间
    factor = max(min_exposure_after_lock, 1.0 - excess / scale)
    return factor
```

**`StrategyConfig` 新增字段**：
```python
annual_budget_control: bool = False
annual_budget_target: float = 0.12
annual_budget_lock_trigger: float = 0.10
annual_budget_min_exposure: float = 0.50
```

#### 实验 G1-EXP1：年度预算控制效果

**预期效果**：
- 2025 年：原始 +18.6%，触发锁仓后预计 +13~15%（损失 3-5% 换取风控）
- 2021/2022/2023 年：无影响（收益未达触发线）
- 年度最大亏损有天花板

**验收标准**：
- 6 年中负收益年份 ≤ 1 年
- 最差单年 ≥ -8%
- 年化收益均值 ≥ 10%

### G.2 波动率目标仓位（Vol Targeting）

更系统的仓位控制方案：根据近期市场波动率动态调整目标组合波动率为恒定值。

$$\text{exposure}_t = \min\left(1.0, \frac{\sigma_{\text{target}}}{\sigma_{\text{realized},t}}\right)$$

其中 $\sigma_{\text{target}}$ = 年化 15%（目标组合波动率），
$\sigma_{\text{realized},t}$ = 滚动 20 日基准/市场波动率（年化）。

**优势**：牛市中市场波动低 → 仓位高；熊市中市场波动高 → 仓位低。
这是自动的「顺市」仓位管理，无需手动调参。

```python
def vol_target_exposure(
    benchmark_closes: list[float],
    signal_index: int,
    vol_window: int = 20,
    target_vol: float = 0.15,   # 年化 15% 波动目标
    annual_factor: float = 252.0,
    min_exposure: float = 0.30,
    max_exposure: float = 1.00,
) -> float:
    """根据实际波动率反推目标仓位"""
    from math import sqrt
    if signal_index < vol_window:
        return max_exposure
    returns = [
        benchmark_closes[i] / benchmark_closes[i - 1] - 1.0
        for i in range(signal_index - vol_window + 1, signal_index + 1)
    ]
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    realized_vol_daily = sqrt(variance)
    realized_vol_annual = realized_vol_daily * sqrt(annual_factor)
    if realized_vol_annual <= 0:
        return max_exposure
    raw = target_vol / realized_vol_annual
    return max(min_exposure, min(max_exposure, raw))
```

**`StrategyConfig` 新增**：
```python
vol_targeting: bool = False
vol_target_level: float = 0.15
vol_target_window: int = 20
vol_target_min_exposure: float = 0.30
```

#### 实验 G2-EXP1：波动率目标 vs 硬风控对比

```bash
python -m quant_rotation sweep \
    --config configs/real_sw2021.toml \
    --industry-only \
    --factor-set ret60_ret5 \
    --vol-targeting true,false \
    --vol-target-level 0.12,0.15,0.18 \
    --output-dir reports/exp_g2_vol_target
```

**验收标准**：
- 年度最大亏损 < -10%（vs 当前 -12.2% 最差年）
- 月胜率提升到 40%+（vol targeting 在高波动期自动减仓，减少亏损月数）

---

## 四、阶段 H：因子精简与 WF 稳健性（P1，第 3~4 周）

> 历史 WF 结果揭示了过拟合的严重程度：训练集 Sharpe 0.40，OOS Sharpe 0.04。
> 这意味着因子/参数空间太大，需要大幅精简。

### H.1 现实评估：WF 失效的根因

当前 27 折 WF 的选择频次分布（`walk_forward_summary.csv`）：
- `ret60_top3_riskoff0_pmequal`：**6 次被选中**（最多）
- 其余 15+ 个候选各 1~2 次

这说明「每一折的最优候选不同」——不是过拟合，而是**不同市场状态需要不同策略**，
但 WF 框架将这种「状态依赖性」错误地解读为「参数搜索」。

**核心洞察**：真正的鲁棒策略应该在所有状态下都 decent，而不是在某些状态最优。

**解决方案**：收缩候选空间到 3~5 个最简单的固定候选，不做 WF 动态选择。

### H.2 精简候选集：3 个核心候选

基于所有实验报告的综合评估，提出以下 3 个固定候选：

#### 候选 H1：极简防御型（最稳定优先）

```toml
# configs/candidate_h1_defensive.toml
[strategy]
top_k = 3
risk_control_mode = "soft"
soft_exposure_min = 0.30
soft_exposure_max = 1.00
risk_off_exposure = 0.30
market_score_control = true
market_score_threshold = 0.0
portfolio_mode = "softmax"
softmax_temperature = 1.0
annual_budget_control = true
annual_budget_lock_trigger = 0.10

[factors]
ret60_weight = 1.00
ret5_weight = -0.50
```

**预期特征**：稳定，低波动，每年正收益概率高，但平均年化偏低（8~12%）

#### 候选 H2：均衡型（性价比最优）

```toml
# configs/candidate_h2_balanced.toml
[strategy]
top_k = 5
risk_control_mode = "soft"
soft_exposure_min = 0.30
soft_exposure_max = 1.00
risk_off_exposure = 0.30
market_score_control = false
portfolio_mode = "equal"
vol_targeting = true
vol_target_level = 0.15

[factors]
ret60_weight = 1.00
ret5_weight = -0.50
prosperity_weight = 0.20
```

**预期特征**：适中波动，景气度加成，年化 12~18%

#### 候选 H3：进取型（高收益但需更多容忍度）

```toml
# configs/candidate_h3_aggressive.toml
[strategy]
top_k = 3
risk_control_mode = "soft"
soft_exposure_min = 0.20
soft_exposure_max = 1.00
risk_off_exposure = 0.20
market_score_control = true
market_score_threshold = 0.0
portfolio_mode = "softmax"
softmax_temperature = 0.75

[factors]
rel_ret60_weight = 1.00
ret5_weight = -0.50
consistency60_weight = 0.20
```

**预期特征**：高波动，高收益潜力，需要 market_close 数据

### H.3 WF 验证：固定候选 vs 动态选择

对以上 3 个候选分别跑全段 WF，不做动态选择，只看每个候选的 OOS 一致性：

```bash
# H1 候选验证
python -m quant_rotation validate \
    --config configs/candidate_h1_defensive.toml \
    --industry-only \
    --walk-forward \
    --train-window 504 \
    --test-window 126 \
    --output-dir reports/exp_h1_wf

# H2 候选验证（需要 prosperity 数据）
python -m quant_rotation validate \
    --config configs/candidate_h2_balanced.toml \
    --industry-only \
    --walk-forward \
    --train-window 504 \
    --test-window 126 \
    --output-dir reports/exp_h2_wf

# H3 候选验证（需要 market_close 数据）
python -m quant_rotation validate \
    --config configs/candidate_h3_aggressive.toml \
    --industry-only \
    --walk-forward \
    --train-window 504 \
    --test-window 126 \
    --output-dir reports/exp_h3_wf
```

**验收标准（每个候选独立评估）**：
- OOS 盈利折数 ≥ 18/27（67%）
- OOS Sharpe 中位数 ≥ 0.20（不要求很高，要求稳定）
- 连续亏损最多 3 折（约 1.5 年）

---

## 五、阶段 I：数据质量与前视偏差根治（P1，第 3~4 周并行）

> 这是长期稳定性的基础，也是当前策略在实盘中最大的潜在风险。

### I.1 已确认的前视偏差风险

| 数据 | 当前状态 | 偏差风险 |
|------|---------|---------|
| `stock_industry_map.csv` | 静态当前成分股映射 | **高** - 使用了未来才知道的行业归属 |
| `industry_prosperity.csv` | 来源未记录 | **中** - 如果是月末/季末发布，当日不可用 |
| `industry_valuation.csv` | 来源未记录 | **中** - PE/PB 数据是否有发布滞后 |
| `industry_breadth*.csv` | 使用当前成分股计算历史宽度 | **高** - 历史日期的宽度用当前成分股计算 |

### I.2 前视偏差修复优先级

#### I.2.1 个股数据：使用历史成分股快照（最高优先级）

```python
# real_data.py 中 fetch_stock_data 需要修改
# 当前：使用 index_stock_cons 获取当前成分股（一次性快照）
# 修改：按时间段获取不同的历史成分股快照

def fetch_historical_constituent_snapshots(
    universe: str,
    snapshot_dates: list[date],  # 例如每季度末
) -> dict[date, list[str]]:
    """
    获取历史成分股快照。
    注意：AKShare 的 index_component_sw 是否支持历史查询需要验证。
    如果不支持，则 Phase D 股票层只能作为「近似研究」使用，
    不可作为生产配置。
    """
```

**行动项**：验证 AKShare 是否可以查询历史成分股；如不能，Phase D 结果标记为「研究近似」。

#### I.2.2 Prosperity 数据：记录数据来源和发布时间

```python
# 在 real_data.py 中新增说明文档
"""
industry_prosperity.csv 数据来源应满足：
1. 数据对应日期 T 时，该数据在 T 日收盘前可以获取
2. 如果数据是月度/季度发布，需要偏移到实际可用日期（发布日+1）

当前数据来源：[待补充]
发布延迟：[待验证]
"""
```

**行动项（1 天）**：
1. 检查 `industry_prosperity.csv` 的实际数据来源
2. 验证历史回测中使用的日期是否已经偏移到数据可用日期
3. 如有疑问，将 `prosperity_weight` 暂时设为 0，等数据质量确认后再启用

#### I.2.3 行业宽度数据：前视偏差修复

```bash
# 重新生成行业宽度，使用时间点对应的成分股
python -m quant_rotation fetch-breadth-data \
    --output data/real_sw2021 \
    --start 2021-12-13 \
    --end 2026-06-03 \
    --windows 20,60 \
    --request-interval 0.2
# 注意：当前实现仍使用当前成分股，这是已知偏差
# 如需修复，需要在 real_data.py 中实现历史成分股查询
```

### I.3 数据完整性检查脚本

```python
# tools/data_integrity_check.py（新建）
"""
运行一系列数据质量检查：
1. 前视偏差检查：确认每行数据在当日收盘时是否实际可用
2. 异常值检查：单日涨跌幅 > 20% 的行业（可能是指数重构）
3. 缺失值检查：连续缺失日 > 5 天（可能是节假日以外的数据缺口）
4. 日期对齐检查：各数据文件日期列是否完全一致
"""
```

---

## 六、阶段 J：收益稳定性增强措施（P2，第 4~5 周）

### J.1 跨行业大类资产轮动（防御板块强化）

**问题**：当前模型的行业全集包含高波动行业（计算机、国防、新能源）和低波动行业（银行、食品）。
在熊市中，即使选了「相对最强」的行业，也可能因整体下跌而亏损。

**解决方案**：引入「防御性大类」标签，在 risk-off 状态下，将仓位限制在防御类。

```python
DEFENSIVE_INDUSTRIES = {
    # SW2021 体系下
    "银行", "公用事业", "交通运输", "食品饮料",
    "农林牧渔",  # 部分年份防御性强
}

CYCLICAL_INDUSTRIES = {
    "计算机", "电子", "国防军工", "有色金属",
    "电力设备", "汽车",
}

def filter_by_regime(
    scores: dict[str, float],
    regime: str,
    defensive_cap: float = 0.8,  # risk-off 时防御类行业权重上限
) -> dict[str, float]:
    if regime != "bear":
        return scores
    # 在熊市状态下，对周期性行业降权 50%
    return {
        asset: score * (0.5 if asset in CYCLICAL_INDUSTRIES else 1.0)
        for asset, score in scores.items()
    }
```

### J.2 相对收益目标模式（Benchmark-Relative Mode）

当绝对收益目标（年化 15%）难以实现时，退而求其次：相对基准超额 5% 即可接受。

这意味着在熊市中（基准 -20%），策略的目标是 -15%（超额 5%），而非强求正收益。
这是更现实的目标设定，避免为了强求正收益而过度择时。

**实现**：`strategy.mode = "absolute" | "relative"` 控制年度预算触发逻辑。

### J.3 分散化再保险：多策略聚合

如果单策略难以做到每年稳定，考虑运行 2~3 个相关性低的策略组合：

| 策略 | 优势 | 劣势 |
|------|------|------|
| 候选 H1（防御） | 稳定 | 牛市跑输 |
| 候选 H2（均衡） | 平衡 | 无明显优势 |
| H1 × 60% + H2 × 40% | 更稳定 | 实施复杂 |

**行动项**：在单策略满足稳定性要求后再考虑组合，不要用「组合」掩盖单策略的缺陷。

---

## 七、Phase D 股票层：数据质量确认后的重启计划

### 7.1 当前 Phase D 结论的有效性评估

`exp_d_best` 结果（Sharpe 0.651，年化 10.82%）有以下限制：

1. **仅覆盖 sw2021 段（2021-2026）**：样本期太短，约 5 年，WF 折数不足
2. **静态成分股地图**：2021-2026 期间，行业成分股有变化，使用当前地图有前视偏差
3. **高换手率**：`average_turnover = 0.85`，实盘摩擦成本远高于 0.1%

### 7.2 Phase D 重启条件

以下两个条件必须满足才能重启 Phase D：

**条件 1**：验证 AKShare 能否获取历史成分股（至少季度快照）
```bash
python -c "
import akshare as ak
# 测试是否支持历史成分股查询
df = ak.index_component_sw(symbol='801010', date='20220101')
print(df.head())
"
```

**条件 2**：Phase F+G 的仓位稳定化已完成，行业层策略年化 > 12% 且稳定

只有当行业层已经足够好，股票层才是锦上添花而非主要收益来源。

### 7.3 Phase D 简化方案（低前视偏差版）

如果历史成分股不可用，使用以下简化方案：
- 只用**流动性过滤**代替全量股票选择：在选中行业内，仅交易成交额前 30% 的股票（等权）
- 这减少了对成分股地图精确度的依赖，同时过滤了流动性极差的标的

```toml
# Phase D 简化版
[strategy]
stock_selection = true
stock_top_n_per_industry = 10       # 只要前 10，不精选
stock_min_stocks_per_industry = 5
stock_max_weight = 0.05             # 分散化

[factors]
stock_amount_strength_weight = 1.00  # 只用流动性过滤
stock_vol20_weight = 0.00
stock_ret60_weight = 0.00
```

---

## 八、代码架构变更清单（v2）

### 8.1 `backtest.py` 新增

```
新增函数：
  + _annual_budget_exposure_adjustment(equity, index, dates, config) -> float
    年度预算控制：当年已超目标时收缩仓位
  + vol_target_exposure(benchmark_closes, index, config) -> float
    波动率目标：根据近期波动动态调整仓位
  + _select_defensive_holdings(factor_snapshot, top_k) -> dict
    防御仓位选择：低波动行业底仓

修改函数：
  ~ run_backtest:
    - 集成 annual_budget_control 逻辑（在计算 exposure 后追加收缩因子）
    - 集成 vol_targeting 逻辑（替代或叠加 state_aware_exposure）
    - 集成 defensive_mode 逻辑（exposure < 0.5 时切换防御选股）
```

### 8.2 `models.py` 新增字段

```python
@dataclass(frozen=True)
class StrategyConfig:
    # 新增字段（不破坏现有接口）
    annual_budget_control: bool = False
    annual_budget_target: float = 0.12
    annual_budget_lock_trigger: float = 0.10
    annual_budget_min_exposure: float = 0.50
    vol_targeting: bool = False
    vol_target_level: float = 0.15
    vol_target_window: int = 20
    vol_target_min_exposure: float = 0.30
    defensive_mode: bool = False
    defensive_top_k: int = 3
    defensive_exposure_threshold: float = 0.50
```

### 8.3 `config.py` 新增解析

```python
# 在 load_config 中新增：
strategy_kwargs["annual_budget_control"] = strategy_section.get("annual_budget_control", False)
strategy_kwargs["annual_budget_lock_trigger"] = strategy_section.get("annual_budget_lock_trigger", 0.10)
strategy_kwargs["vol_targeting"] = strategy_section.get("vol_targeting", False)
strategy_kwargs["vol_target_level"] = strategy_section.get("vol_target_level", 0.15)
strategy_kwargs["defensive_mode"] = strategy_section.get("defensive_mode", False)
```

### 8.4 新配置文件

```
configs/candidate_h1_defensive.toml    # 防御型候选（新建）
configs/candidate_h2_balanced.toml     # 均衡型候选（新建）
configs/candidate_h3_aggressive.toml   # 进取型候选（新建）
configs/production_v2.toml             # 基于 H2 的新生产配置（Phase F+G 完成后）
```

### 8.5 新工具脚本

```
tools/data_integrity_check.py          # 数据质量检查（新建）
tools/annual_returns_summary.py        # 年度收益快速汇总（新建）
```

---

## 九、验证框架修订

### 9.1 新的核心验证指标（替代旧的 Sharpe 中位数）

旧的验证以「WF OOS Sharpe 中位数」为核心，但这个指标对「短期剧烈亏损再恢复」
的情形不敏感（每折 Sharpe 波动极大）。

新的核心指标：

| 指标 | 旧目标 | 新目标 | 理由 |
|------|--------|--------|------|
| WF OOS 盈利折数 | > 19/27 | **> 19/27** | 不变 |
| 年度负收益年份数 | — | **≤ 1/6** | 直接衡量「每年稳定」 |
| 最差单年收益 | — | **≥ -10%** | 最差情况可接受 |
| 年度收益中位数 | — | **≥ 10%** | 长期平均水平 |
| WF OOS Sharpe 中位数 | > 0.90 | **> 0.35** | 降低目标，更现实 |
| 月胜率 | > 52% | **> 43%** | 软目标，底仓机制改善 |

### 9.2 分年验证协议

每个候选配置的验收必须通过分年检查：

```python
def annual_consistency_check(annual_returns: dict[int, float]) -> dict[str, float]:
    """
    检查年度收益一致性。
    返回：负收益年份数、最差年收益、年化收益均值、中位数
    """
    returns = list(annual_returns.values())
    negative_years = sum(1 for r in returns if r < 0)
    worst_year = min(returns)
    mean_return = sum(returns) / len(returns)
    sorted_r = sorted(returns)
    median_return = sorted_r[len(sorted_r) // 2]
    return {
        "negative_years": negative_years,
        "worst_year": worst_year,
        "mean_return": mean_return,
        "median_return": median_return,
        "consistency_ratio": (len(returns) - negative_years) / len(returns),
    }
```

**集成到 CLI**：
```bash
python -m quant_rotation run --config configs/candidate_h2_balanced.toml \
    --annual-consistency-check \
    --output-dir reports/h2_annual_check
```

### 9.3 三层验证流程（修订版）

**Layer 1（1 天）**：sw2021 单段运行 + 分年验证
- 通过：年度负收益 ≤ 1，最差年 ≥ -10%

**Layer 2（2 天）**：跨段 WF（sw2014 + sw2021 联合）
- 通过：OOS 盈利折数 ≥ 15/27，OOS Sharpe 中位数 ≥ 0.15

**Layer 3（2 天）**：sw2000 + sw2014 + sw2021 全段 WF
- 通过：OOS 盈利折数 ≥ 19/27，Bootstrap p_positive ≥ 92%

---

## 十、优先级矩阵与执行计划

### 10.1 优先级总览（v2）

| 优先级 | 阶段 | 任务 | 预期效果 | 状态 |
|--------|------|------|---------|------|
| 🔴 P0 | F.2 | 软仓位 + 底仓 30% | 消除「全空仓」年份 | ✅ 代码+测试完成，实验结论：未超基线 |
| 🔴 P0 | G.1 | 年度预算控制 | 稳定年度收益上下界 | ✅ 代码+测试完成，实验结论：当前不触发 |
| 🔴 P0 | H.2 | 精简候选 + 固定选择 | 消除 WF 过拟合 | ✅ 3 个候选配置已创建 |
| 🟠 P1 | G.2 | 波动率目标仓位 | 自动化仓位管理 | ✅ 代码完成，H2 测试中导致大幅回撤 |
| 🟠 P1 | H.3 | WF 验证（跨段） | 确认 OOS 鲁棒性 | ✅ 19 折 WF 完成，见 §0.4.2 |
| 🟠 P1 | I.2 | Prosperity 数据质量确认 | 消除潜在偏差 | ❌ 未做 |
| 🟠 P1 | I.2 | 历史成分股快照 | 修复 Phase D 前视偏差 | ❌ 未做（依赖 AKShare） |
| 🟡 P2 | J.1 | 防御板块过滤 | 降低熊市损失 | ✅ 完成 |
| 🟡 P2 | J.2 | 相对收益模式 | 熊市中更现实的目标 | ✅ 完成 |
| 🟡 P2 | J.3 | 多策略聚合 | 更稳定的组合收益 | ✅ 完成（`tools/combine_strategies.py` + CLI `combine` 命令） |
| 🔮 | D重启 | Phase D 无偏差版本 | +Sharpe 0.10~0.20 | ❌ 条件不满足（基线未超越） |

### 10.2 执行顺序（最快看到效果的路径）

#### 第 1 周：仓位重构（可立即运行，无需新数据）

```
Day 1：
  - 修改 backtest.py 集成 _annual_budget_exposure_adjustment
  - 修改 models.py + config.py 新增字段
  - 写测试：test_annual_budget_control_reduces_exposure

Day 2：
  - 实现 vol_target_exposure
  - 写配置 candidate_h1_defensive.toml、candidate_h2_balanced.toml
  - 在 sw2021 单段跑两个候选，查看分年收益

Day 3~4：
  - 实验 F2-EXP1（软仓位扫描）
  - 对比分年收益：原始 vs 软仓位 30% vs 软仓位 40%
  - 选定最优软仓位参数

Day 5：
  - 跑 sw2021 完整段的 3 个候选
  - 分析每个候选的分年收益表格
  - 选出初步候选
```

#### 第 2 周：验证与稳定化

```
Day 6~7：
  - Layer 2 WF 验证（sw2014 + sw2021）对初步候选
  - 重点看每折 OOS 的年化收益分布，而非 Sharpe 均值

Day 8：
  - 数据质量调研（Prosperity 来源、AKShare 历史成分股）
  - 写 tools/data_integrity_check.py

Day 9~10：
  - Layer 3 全段 WF 验证
  - 准备生产配置 production_v2.toml
```

#### 第 3~4 周：Phase D 条件满足后

```
Week 3：
  - 根据 AKShare 调研结果决定是否重启 Phase D
  - 如果历史成分股可用：按 7.2 重启
  - 如果不可用：按 7.3 简化方案

Week 4：
  - Phase D 新版本 WF 验证
  - 生产配置最终化
```

---

## 十一、成功里程碑与验收标准

### Milestone 1（第 1 周末）：年度稳定化初步验证

**通过条件（sw2021 分年）**：
- 2021 年策略收益 > +1%（非 0%）→ ❌ **仍是 0%（数据起始 2021-12-13，预热 120 天导致 2021 全年无交易）**
- 2022 年策略收益 > -8% → ✅ 生产基线 0%、H1 防御型 -1.2%
- 2023 年策略收益 > -2% → ❌ 生产基线 -4.6%、H1 防御型 -2.2%
- 全段 Sharpe ≥ 0.50 → ✅ 生产基线 0.52

**状态：❌ 未通过**（2023 未达标，软仓位未能改善）

### Milestone 2（第 2 周末）：WF 稳健性确认

**通过条件**：
- 27 折 WF OOS 盈利折数 ≥ 19/27 → ❌ **未跑全段 WF（仅 19 折 sw2014+sw2021）**
- OOS 年化收益中位数 ≥ 3% → ❌ **实际 0.0%**
- Bootstrap p_positive ≥ 92% → ❌ **实际 71.8%**
- 候选在全段中无负收益年份超过 2 年 → — 未验证

**状态：❌ 未通过**

### Milestone 3（第 4 周末）：生产就绪

**通过条件**：全部未满足
- sw2021 年化 ≥ 12% → ❌ 实际 6.51%
- sw2021 最差单年 ≥ -8% → ❌ 实际 -4.6%（负值但绝对值达标；目标是正数即 >-8%）✅
- sw2021 负收益年份 ≤ 1 → ✅
- sw2021 Sharpe ≥ 0.55 → ❌ 实际 0.52
- 27 折 WF OOS 盈利折数 ≥ 19/27 → ❌ 未跑
- Bootstrap p_positive ≥ 92% → ❌

**状态：❌ 未通过**

### Milestone 4（第 6~8 周，条件满足后）：Phase D 增强

**状态：🔒 锁定（前置条件不满足）**

---

## 十二、性能基线更新

| 指标 | 旧 plan 基线 | 当前实际（Phase E） | 本轮执行结果（Phase F/G/H） | 新目标 |
|------|------------|-------------------|--------------------------|--------|
| sw2021 年化 | 6.51% | 7.29%（Phase E 最优）| **6.51%**（生产基线仍最优）| **≥ 12%** |
| sw2021 Sharpe | 0.525 | 0.515 | **0.52**（生产基线）| **≥ 0.55** |
| sw2021 最大回撤 | -17.26% | -24.48% | **-17.3%** | **< -18%** |
| sw2021 月胜率 | 29.1% | 32.7% | — | **≥ 42%** |
| 负收益年份数 | 2/6 | 1/6 | **1/6**（2023 -4.6%）| **≤ 1/6** |
| 最差单年 | -4.6%（2023） | -4.6% | **-4.6%**（未改善）| **≥ -8%** |
| 19 折 WF OOS 年化中位数 | — | — | **0.0%** | **≥ 3%** |
| 19 折 WF OOS Sharpe 中位数 | 0.484（旧）→ 0.043（新） | 0.043 | **0.00** | **≥ 0.20** |
| Bootstrap p_positive | 95.0%（旧）→ 89.3%（新） | 89.3% | **71.8%** | **≥ 92%** |
| WF OOS 盈利折数 | 16/27 | 未统计 | — | **≥ 19/27** |

---

## 十三、关键风险与注意事项

### 风险 1：Phase E 最优仍是 `ret60_ret5`，Phase A-D 的改进未能在 WF 中体现

**原因**：`rel_ret60` 依赖 `market_close.csv`，在 sw2000/sw2014 早期折中数据缺失，
因子退化，导致这类候选在早期折几乎不被选中，而在晚期折性能又参差不齐。

**缓解**：
1. 在生产候选中，同时准备一个不依赖 `market_close` 的 H1 版本
2. 只在 sw2021 段（市场数据完整）重点验证 `rel_ret60`

### 风险 2：软仓位 30% 在极端熊市中损失较大

2022 年全空的策略年化 0%，改为 30% 底仓后 2022 年可能亏损约 6%（基准 -21.6% × 30%）。

**缓解**：
- 30% 底仓配置在低波动防御行业（银行/公用事业），实际亏损可能只有 3~4%
- 与此同时，2021 年从 0% 提升到约 2~4%，补偿了部分损失
- 长期看，「规避」的成功仅在 2022 年，而「踏空」的损失在 2021、2024 均有，
  软仓位的总效果是正的

### 风险 3：年度预算控制在连续上涨年份（如 2025 连续上涨）会大幅降低收益

如果 2025 年 Q1 就赚了 10%，剩余 9 个月将以 50% 仓位运行，错过大量涨幅。

**缓解**：
- 将 `lock_trigger` 设为 15%（而非 10%），更宽松的触发条件
- 或者只在连续亏损后的年份启用年度预算控制（自适应模式）

### 风险 4：WF 框架的有效历史太短（27 折中，sw2000 仅 ~10 折）

当前 WF 的 sw2000 段质量差（无 `market_close`，行业数量少），导致早期折的 OOS 
结论可靠性低。不应以 sw2000 的 WF 结果作为拒绝候选的依据。

**缓解**：分段统计盈利折数：sw2014 段（约 11 折）和 sw2021 段（约 8 折）分别统计，
只有两段都 > 60% 盈利折才算通过。

---

## 十四、快速检查清单

在每次重大改动后，运行以下快速验证流程：

```bash
# 步骤 1: 单段快速验证（5 分钟）
python -m quant_rotation run --config configs/<new_config>.toml
# 检查 reports/<dir>/annual_returns.csv 中每年收益

# 步骤 2: 分年一致性检查（新脚本）
python tools/annual_returns_summary.py reports/<dir>/annual_returns.csv

# 步骤 3: sw2014 段 WF（30 分钟，最重要的泛化测试）
python -m quant_rotation validate \
    --config configs/<new_config_sw2014>.toml \
    --walk-forward --train-window 504 --test-window 126 \
    --output-dir reports/quick_wf_<name>

# 步骤 4: 数据质量检查
python tools/data_integrity_check.py --config configs/<new_config>.toml
```

---

## 十五、附录：实验结果速查表

### A. 历史最优 WF 固定候选（27 折 OOS 最终净值排名，2012~2026）

| 排名 | 候选名 | OOS 净值 | 超额（vs 基准）|
|------|--------|---------|--------------|
| 1 | `ret60_top3_riskoff0p3_pmsoftmax` | 2.09 | +20.8% |
| 2 | `ret60_top3_riskoff0p3_pmequal` | 2.04 | +17.7% |
| 3 | `ret60_top3_riskoff0p2_pmsoftmax` | 1.99 | +14.9% |
| 10 | `ret60_top3_riskoff0_pmequal` | 1.78 | +2.7% |

### B. Phase D 最优 sw2021 回测

| 指标 | 值 |
|------|---|
| 年化 | 10.82% |
| Sharpe | 0.651 |
| 最大回撤 | -22.17% |
| 月胜率 | 34.5% |
| 换手率 | 0.85 |
| 注意 | 使用静态成分股，存在前视偏差 |

### C. sw2021 分年收益（不同配置对比）

| 年份 | 基准 | 等权 | 当前最优（production） | Phase D best | 目标范围 |
|------|------|------|---------------------|-------------|---------|
| 2021 | -2.8% | +0.3% | 0.0%（空仓） | 0.0% | **+1~5%** |
| 2022 | -21.6% | -15.1% | 0.0%（空仓） | 0.0% | **-5~0%** |
| 2023 | -11.4% | -6.9% | -4.6% | -1.3% | **-2~+5%** |
| 2024 | +14.7% | +14.0% | +8.6% | +14.9% | **+8~18%** |
| 2025 | +17.7% | +28.4% | +18.6% | +2.3% | **+10~25%** |
| 2026H1 | +6.1% | +1.7% | +6.5% | +33.5% | **+4~15%** |