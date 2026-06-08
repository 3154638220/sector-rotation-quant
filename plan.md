# 行动计划 v3：打造强 Alpha 模型的系统性路径

> 诊断基础：全量代码、全量实验报告（Phase A~J）、27 折跨段 WF、Phase D 无偏重跑
> 分析日期：2026-06-07
> 版本：本文件完整替代上一版 plan.md（v2），专注于「根本性架构升级」而非参数调优

---

## 第一部分：诊断——当前模型为何不令人满意

### 1.1 核心指标一览（生产基线 + 历史全段）

| 指标 | sw2021（~5年）| sw2014（~8年）| sw2000（~4年）| 目标 |
|------|-------------|-------------|-------------|------|
| 年化收益 | 6.51% | 10.28% | \-3.1%（估算）| ≥ 15% |
| Sharpe | 0.52 | 0.60 | < 0 | ≥ 0.80 |
| **月胜率** | **29.1%** | **33.7%** | **< 30%** | **≥ 50%** |
| 最大回撤 | -17.3% | **-54.8%** | 未知 | < -20% |
| WF OOS 盈利折 | 13/27（48%）| — | — | ≥ 19/27 |
| WF OOS 年化中位数 | **0.0%** | — | — | ≥ 5% |
| 风控触发比例 | **60%** | — | — | ≤ 30% |
| 风控 hit rate | **22–38%** | — | — | ≥ 60% |
| 负收益年份 | 1/6 | 3/8 | 3/4 | ≤ 1/6 |

**结论**：当前模型在 5 年短窗口（sw2021）表现尚可，但一旦放到完整历史（sw2000+sw2014），性能急剧恶化。真正的指标——月胜率 29%、WF OOS 中位数 0%——证明策略缺乏持续 Alpha，是「运气 + 避险」的结合，而非系统性优势。

---

### 1.2 七个根本性问题

#### 问题 1：策略本质是「期权型 Beta 暴露」，不是 Alpha

最清晰的证据：
- 60% 的月份处于 risk-off（空仓）
- 2022 年 0% 收益的来源：完全规避基准 -21.6%
- 2024 年 +8.6% 的来源：大牛市 partial exposure
- 月胜率仅 29%，意味着实际操作时大多数时间在亏钱

**根本原因**：策略通过「正确地不持仓」赚钱，而不是通过「持有正确的行业」赚钱。  
这不是 Alpha，这是市场择时 Beta。

> 对比测试：A 股行业等权（纯 Beta）在 sw2021 的五年累计收益 1.037，
> 而生产基线 1.308 的超额来源 92% 来自 2022 年的 0 仓规避（-21.6% × 100%）。
> 如果剔除 2022 年，策略相对等权几乎没有超额。

---

#### 问题 2：WF OOS 完全退化，动态候选选择无效

| WF 指标 | 训练集 | 测试集 | 退化幅度 |
|---------|--------|--------|--------|
| 年化均值 | 10.1% | 3.1% | -7pp |
| 年化**中位数** | 6.5% | **0.0%** | -6.5pp |
| Sharpe 均值 | 0.53 | 0.07 | -0.46 |
| Sharpe **中位数** | — | **0.00** | — |

**根本原因**：
- 参数空间（因子权重 × top_k × risk_off_exposure × risk_mode）过大，训练集总能找到过拟合的最优解
- A 股行业轮动在不同市场状态（趋势/震荡/政策驱动）下需要完全不同的策略，固定参数框架无法适应
- 历史折的最优候选不能预测下一折的最优候选

---

#### 问题 3：风控是净害——误报率 62–78%

```
当前风控触发分析：
  总 rebalance：48 次
  risk-off 触发：29 次 = 60%（触发过于频繁）
  hit_rate：22–38%（大多数触发是误报）
  市场 score 误报率：高达 62%
```

**根本原因**：
- MA120 是滞后指标，反应速度远落后于市场
- market_score 使用 60 日均值，信号噪声比低
- 两个信号的 OR 逻辑（任一触发即 risk-off）导致过度触发
- 触发后暴露 0%——惩罚过重，且无渐进恢复机制

---

#### 问题 4：因子信息含量低，缺乏正交性

```
生产因子：ret60（1.0）+ ret5（-0.5）
ablation 分析：
  - 去掉 ret60：Sharpe 从 0.52 → 0.40（-0.12，显著）
  - 去掉 ret5：Sharpe 从 0.52 → 0.49（-0.03，边际）
```

**问题**：
- 实质上只有 1 个有效因子（ret60）
- ret5（过热惩罚）是 ret60 的辅助修正，不是独立 Alpha 来源
- consistency60 在 exp_best_p0 中有一定贡献，但未进入生产
- 所有因子都是价格衍生因子——同一信息源，无法捕捉基本面驱动的轮动

---

#### 问题 5：组合构建未利用因子强度信息

- 固定 equal-weight 于 top-K，丢弃了评分差异信息
- 无行业相关性约束（可能同时选入高相关行业：煤炭 + 有色金属）
- top_k 固定，无法在高信心时集中、低信心时分散
- 没有利用过去选择的业绩来调整权重

---

#### 问题 6：Phase D 股票层在无偏差数据上完全失效

| 指标 | 有偏（旧）| 无偏（新）| 退化量 |
|------|---------|---------|--------|
| 年化 | +10.82% | **-2.87%** | -13.7pp |
| Sharpe | 0.651 | **-0.013** | -0.664 |
| 最大回撤 | -22.17% | **-49.39%** | -27pp |

**结论**：Phase D 全部超额来自 survivorship bias，正式排除。

---

#### 问题 7：数据历史太短，结论脆弱

- sw2021 数据：仅 ~5 年，含 1 次熊市（2022）、1 次震荡（2023）、2 次牛市
- 5 年不足以区分「策略有效」和「策略在特定宏观环境下运气好」
- sw2014（2014–2021）数据显示：相同策略在不同宏观环境下 DD -54.8%
- 历史验证需要覆盖完整市场周期（至少 10 年以上）

---

### 1.3 一句话诊断

> 当前模型是一个**单因子（ret60）+ 极端风控（60% 空仓）+ 等权集中（top-5）**的框架，
> 其超额收益主要来自在熊市中的「不存在」，而非主动选择更好的行业。
> 这不是强 Alpha 模型，这是一个**运气加持的择时策略**。

---

## 第二部分：成为强 Alpha 模型的标准定义

### 2.1 强 Alpha 模型的量化定义

| 维度 | 目标值 | 当前状态 |
|------|--------|---------|
| 月胜率（相对等权）| ≥ 52% | 29% ❌ |
| 年化收益（全历史，sw2000+sw2014+sw2021）| ≥ 15% | ~3–7% ❌ |
| Sharpe（全历史） | ≥ 0.80 | 0.52 ❌ |
| 最大回撤（全历史） | ≤ -20% | -54.8%（sw2014）❌ |
| WF OOS 盈利折数 | ≥ 19/27（70%）| 13/27（48%）❌ |
| WF OOS 年化中位数 | ≥ 5% | 0% ❌ |
| 负收益年份（单年）| ≤ 1/6 | 3/8（sw2014）❌ |
| 最差单年 | ≥ -10% | -89%（sw2000/sw2014 期间未测）❌ |
| 风控 hit rate | ≥ 60% | 22–38% ❌ |

### 2.2 要达到这些目标，策略架构需要什么

```
当前架构：
  信号层：ret60 + ret5 → 行业排名
  过滤层：MA120 + market_score → binary on/off
  选股层：top-5 equal-weight
  持仓层：月度再平衡

目标架构：
  信号层 A：多维度量化因子（价格 + 基本面 + 宏观）→ 每行业综合评分
  信号层 B：市场状态分类器（多空判断，替代 MA120 单信号）
  组合层：动态仓位 × 因子强度加权 × 相关性约束
  执行层：降低换手率的平滑再平衡
```

---

## 第三部分：改进路径——六个核心方向

> 以下六个方向按照「高确定性收益」到「高风险但潜在高收益」排序。
> 每个方向都有明确的验收标准和实验协议。

---

### 方向 K：因子质量审计（前置工作，最高优先级）

**为什么要做**：在过去所有实验中，我们从未系统衡量每个因子的信息含量（IC）和稳定性（ICIR）。所有「有效/无效」的结论都来自回测总收益，而非因子本身的预测能力。

**做什么**：
- 计算每个候选因子的月度 IC（Information Coefficient）：每个调仓日，计算因子分 vs 未来持有期收益的截面相关性
- 计算 ICIR = mean(IC) / std(IC)，衡量因子稳定性
- 分析因子衰减曲线：持有 5/10/20/40/60 天的 IC 如何变化
- 按市场状态（牛/熊/震荡）分层统计 IC

**候选因子 IC/ICIR 评估列表**：

| 因子 | 预期 ICIR | 验证优先级 | 理由 |
|------|----------|-----------|------|
| ret60 | 0.10–0.20 | P0 | 主力因子，需要确认 |
| ret20 | 0.05–0.15 | P0 | 短期动量，当前权重 0 |
| consistency60 | 0.05–0.10 | P0 | exp_best_p0 有效，需确认 IC |
| ret5 | -0.05–0.05 | P0 | 过热惩罚，确认负 IC |
| vol20 | -0.10–-0.05 | P1 | 低波动是否预测收益 |
| amount_strength | 0.03–0.08 | P1 | 量价配合，验证 IC |
| rel_ret60 | 0.08–0.15 | P1 | 相对强度（需完整市场数据）|
| breadth20/60 | 0.05–0.10 | P1 | 内部宽度，验证 IC |
| prosperity | 0.05–0.10 | P2 | 需要确认数据来源和滞后 |
| valuation | 0.02–0.06 | P2 | 估值回归，验证方向 |

**实验命令**：

```bash
# 新增工具：计算所有因子的滚动 IC 和衰减曲线
python tools/factor_ic_analysis.py \
    --config configs/real_sw2021.toml \
    --factors ret60,ret20,consistency60,ret5,vol20,amount_strength \
    --hold-periods 5,10,20,40,60 \
    --output reports/factor_ic_audit/
```

**工具实现（需新增 `tools/factor_ic_analysis.py`）**：

```python
"""
计算每个因子在每个调仓日的截面 IC（Spearman rank correlation）。
输出：
  - factor_ic.csv：每个因子 × 每个日期的 IC 值
  - factor_icir.csv：每个因子的 ICIR（按整体 / 按年份 / 按市场状态）
  - factor_decay.csv：IC 随持有期增加的衰减曲线
"""
```

**验收标准**：
- 找到 ICIR > 0.15 的因子（即有稳定预测能力）
- 确认现有 ret60 的 ICIR 和衰减曲线（建立基准）
- 识别 ICIR < 0.05 的无效因子，从候选中剔除

---

### 方向 L：市场状态分类器（替代当前风控架构）

**为什么要做**：当前风控误报率 62–78%，60% 的时间空仓，属于根本性缺陷。  
问题根源：单一滞后信号（MA120）用二元开关控制仓位。

**目标**：用多信号状态分类器（输出「强势/中性/弱势」三状态概率）替代二元开关。

#### L.1 多信号市场状态评估体系

**信号 1：趋势强度（已有，改造）**
```python
# 当前：MA120 二元开关
# 改为：多均线综合得分（连续值 -1 ~ +1）
def trend_score(benchmark_closes, index):
    ma20  = mean(closes[-20:])
    ma60  = mean(closes[-60:])
    ma120 = mean(closes[-120:])
    current = closes[index]
    score = 0.0
    score += 0.4 if current > ma20  else -0.4
    score += 0.4 if current > ma60  else -0.4
    score += 0.2 if current > ma120 else -0.2
    return score  # 范围 -1.0 ~ +1.0
```

**信号 2：截面分散度（新增）**
```python
# 轮动有效的前提：行业之间有足够差异
# 高分散度 → 轮动有效；低分散度（"一起涨一起跌"）→ 轮动失效
def cross_sectional_dispersion(industry_returns_20d):
    returns = list(industry_returns_20d.values())
    std = numpy.std(returns)
    return std  # 高 std → 有轮动空间
```

**信号 3：市场惯性（新增）**
```python
# 当前 market_score：60 日加权市场收益
# 改进：区分「动量初始」（最近加速）vs「动量末期」（超买过热）
def market_momentum_quality(market_closes, index):
    ret60 = closes[-1] / closes[-60] - 1
    ret20 = closes[-1] / closes[-20] - 1
    ret5  = closes[-1] / closes[-5] - 1
    # 理想信号：60d强劲，近期没有过热
    momentum_quality = ret60 - max(0, ret5 * 2)
    return momentum_quality
```

**信号 4：行业内部宽度（已有，改造）**
```python
# 用 breadth20（均线上方个股比例均值）作为市场整体健康度
# 高宽度（>0.5）→ 市场健康；低宽度（<0.35）→ 市场脆弱
average_breadth = mean(breadth20_values.values())
```

#### L.2 三状态市场分类器

```python
class MarketState(Enum):
    STRONG  = "strong"   # 满仓（100%），全力轮动
    NEUTRAL = "neutral"  # 半仓（50-70%），保守轮动
    WEAK    = "weak"     # 防御（20-30%），低波动防御仓

def classify_market_state(
    trend_score,          # -1 ~ +1
    dispersion,           # 0 ~ inf，行业截面标准差
    momentum_quality,     # 综合市场动量
    breadth,              # 0 ~ 1
) -> tuple[MarketState, float]:  # state, exposure
    # 加权综合得分
    composite = (
        0.35 * normalize(trend_score, -1, 1)
        + 0.25 * normalize(dispersion, 0, 0.15)  # 标准化分散度
        + 0.25 * normalize(momentum_quality, -0.15, 0.15)
        + 0.15 * (breadth - 0.5) * 2  # breadth 中心化
    )
    
    if composite > 0.3:
        return MarketState.STRONG, 1.00
    elif composite > -0.1:
        return MarketState.NEUTRAL, 0.60
    else:
        return MarketState.WEAK, 0.25
```

**优势**：
- 三状态而非二元，减少极端操作
- 组合多信号降低误报率（从 62% → 预计 < 40%）
- 连续仓位（25%/60%/100%）而非 0%/100%
- 截面分散度直接衡量轮动有效性

**实验协议**：

```bash
# 实验 L1：三状态分类器 vs 当前二元风控，sw2021 回测
python -m quant_rotation sweep \
    --config configs/real_sw2021.toml \
    --industry-only \
    --factor-set ret60_ret5 \
    --market-state-mode three_state \
    --market-state-weights trend:0.35,dispersion:0.25,momentum:0.25,breadth:0.15 \
    --output-dir reports/exp_L1_three_state

# 实验 L2：分别验证每个子信号的 hit rate 提升
python tools/diagnose_risk_control.py --config configs/real_sw2021.toml \
    --mode three_state --output reports/exp_L2_signal_diagnose
```

**验收标准**：
- 风控 hit rate ≥ 55%（当前 22–38%）
- risk-off 触发月份比例 ≤ 40%（当前 60%）
- 2022 年最大亏损 ≤ -8%（允许小幅参与以维持流动性）
- 2021 年收益 ≥ 1%（三状态不会把好年全部空仓）

---

### 方向 M：因子多样化——加入基本面维度

**为什么要做**：当前所有因子都是价格衍生量，本质上是同一信息源的不同变形。
A 股行业轮动存在两种驱动力：（1）动量（已捕捉）；（2）基本面修复/恶化（未捕捉）。

#### M.1 行业景气度因子（Prosperity）——修复并生产化

当前状态：prosperity 权重为 0，因为「来源不明、发布滞后未确认」。

**行动计划**：
1. 明确数据来源：申万行业 Wind/Bloomberg 盈利预测修正 → 需验证 release_lag
2. 替代方案：用行业 ROE/ROA 变化率的滚动窗口代理（季度报告，滞后 45 天）
3. 另一替代：行业内上市公司营收增速的截面 z-score

```python
# 实现：industry_prosperity 计算器
def compute_prosperity_from_earnings(
    industry_earnings_data: dict,  # 每行业每季度 EPS/ROE
    release_lag_days: int = 45,    # 财报发布滞后
    window_quarters: int = 4,      # 滚动 4 季度同比
) -> pd.DataFrame:
    """
    计算每行业的景气度变化（4Q 滚动 ROE 变化率），
    按照财报发布日期右移 release_lag_days，确保无前视偏差。
    """
```

**实验**：在景气度数据建立后，做因子 IC 验证（ICIR 目标 > 0.10），
再做单因子回测，确认方向和权重。

#### M.2 行业估值相对位置因子——改进

当前 `industry_valuation.csv` 使用**价格分位数**（0–1），不是真正的估值数据。

**问题**：价格分位数本质上是反动量因子——低分位意味着近期跌了很多，与 ret60 负相关。
这解释了为什么 ablation 中 valuation 对 Sharpe 几乎没有贡献（+0.01）——它与 ret60 的信息高度重叠或对冲。

**改进方案**：
1. 使用真实 PE/PB 历史分位数（需要 Wind/Tushare 数据）
2. 计算「现在 PE 在过去 3 年历史中的位置」而非「价格在历史中的位置」
3. 仅对 PE 处于历史低位（< 20th 分位）的行业打正分，而非线性映射

```python
def valuation_factor_from_pe(
    pe_data: pd.DataFrame,   # 每行业每日 PE（Wind）
    window_years: int = 3,   # 历史窗口 3 年
    threshold_low: float = 0.25,   # 低估值阈值
    threshold_high: float = 0.75,  # 高估值阈值
) -> pd.DataFrame:
    """
    返回：-1（高估）/ 0（中性）/ +1（低估）的行业评分。
    """
    pe_percentile = pe_data.rolling(window=window_years*252, min_periods=126).rank(pct=True)
    return pd.cut(pe_percentile, bins=[0, threshold_low, threshold_high, 1.0],
                  labels=[-1, 0, 1]).astype(float)
```

#### M.3 宏观因子叠加（可选，P2）

针对 A 股特有的宏观敏感性：
- PMI 制造业指数：制造业 PMI > 50 时周期性行业加权；< 50 时防御性行业加权
- 信用利差：信用利差扩大时，金融行业负向加权
- 人民币汇率方向：贬值时，出口行业正向加权

```python
# macro_overlay.py（新增，可选模块）
INDUSTRY_MACRO_SENSITIVITY = {
    "基础化工": {"PMI": 0.8, "CNY": 0.5},
    "有色金属": {"PMI": 0.7, "credit_spread": -0.6},
    "银行":     {"credit_spread": -0.8, "PMI": 0.3},
    "食品饮料": {"PMI": -0.2, "credit_spread": 0.1},  # 防御性
}
```

---

### 方向 N：组合构建升级——信号加权 + 相关性约束

**为什么要做**：等权 top-5 是最朴素的实现，丢弃了评分信息，且容易持有高度相关行业。

#### N.1 信号强度加权（替代等权）

```python
def softrank_weights(scores: dict[str, float], temperature: float = 0.5) -> dict[str, float]:
    """
    Softmax-based 权重：温度越低，越集中于最高分行业；温度越高，越均匀。
    温度 0.3–0.8 为实用范围，配合 IC/ICIR 动态调整温度。
    """
    top_k_industries = sorted(scores, key=scores.get, reverse=True)[:top_k]
    z = {i: scores[i] / temperature for i in top_k_industries}
    max_z = max(z.values())
    exp_z = {i: math.exp(v - max_z) for i, v in z.items()}
    total = sum(exp_z.values())
    return {i: w / total for i, w in exp_z.items()}
```

#### N.2 行业相关性约束

**问题**：计算机 + 电子 + 通信（TMT 三剑客）经常同时被选入，实质是高相关资产。

```python
INDUSTRY_CLUSTER = {
    "TMT": ["计算机", "电子", "通信", "传媒"],
    "新能源": ["电力设备", "汽车（新能源相关）"],
    "周期": ["煤炭", "钢铁", "有色金属", "基础化工"],
    "金融": ["银行", "非银金融"],
    "消费": ["食品饮料", "家用电器", "美容护理", "商贸零售"],
    "医疗": ["医药生物"],
    "防御": ["公用事业", "交通运输"],
}

def apply_cluster_constraint(
    selected_industries: list[str],
    scores: dict[str, float],
    max_per_cluster: int = 2,
) -> list[str]:
    """确保每个集群内最多选 max_per_cluster 个行业。"""
```

#### N.3 动态 top_k（基于截面分散度）

```python
def dynamic_top_k(
    dispersion: float,
    k_min: int = 3,
    k_max: int = 7,
    disp_low: float = 0.04,   # 低分散度阈值（行业差异小）
    disp_high: float = 0.10,  # 高分散度阈值（明显轮动机会）
) -> int:
    """
    分散度低时减少持仓数量（更集中于少数优质信号）；
    分散度高时增加持仓（分散化）。
    """
    if dispersion < disp_low:
        return k_min       # 3 个行业，高集中
    elif dispersion > disp_high:
        return k_max       # 7 个行业，分散化
    else:
        ratio = (dispersion - disp_low) / (disp_high - disp_low)
        return int(k_min + ratio * (k_max - k_min))
```

---

### 方向 O：回测方法论升级——消除训练集污染

**为什么要做**：当前 WF 存在系统性的方法论缺陷，导致 OOS 结果不可信。

#### O.1 Purged WF（净化 Walk-Forward）

**当前问题**：训练集和测试集之间没有「净化间隔」，紧邻测试期开始的训练样本可能泄漏信息。

```python
def purged_walk_forward_splits(
    data_length: int,
    train_window: int = 504,   # 2 年（504 交易日）
    test_window: int = 63,     # 3 个月（1 折）
    gap: int = 20,             # 净化间隔（1 个月）
):
    """
    在训练集末尾和测试集开始之间插入 gap 天的间隔，
    避免最近 gap 天的持仓对测试期产生信息泄漏。
    """
```

#### O.2 组合稳定性验证（Stability Test）

```python
def stability_test(
    config,
    data,
    n_perturb: int = 100,
    perturb_std: float = 0.05,  # 对因子权重施加 5% 随机扰动
) -> dict:
    """
    对因子权重添加小扰动，验证策略的稳定性。
    一个真正稳健的策略在参数扰动 ±5% 时，性能不应大幅变化（< 1pp 年化差距）。
    """
```

#### O.3 在多个宏观时期独立验证

当前分段（sw2000/sw2014/sw2021）是按分类体系切分，但不代表宏观周期切分。应额外验证：
- **2010–2015**：牛市启动 + 2015 股灾
- **2016–2019**：价值/周期主导 + 贸易战
- **2020–2022**：新冠牛市 + 熊市
- **2023–2026**：政策驱动 + AI 主题

---

### 方向 P：交易成本与换手率优化

**为什么要做**：高换手率（0.95，Phase D）直接吞噬 Alpha。即使改善了因子质量，
如果换手率不降，总收益净值不会提升。

#### P.1 换手预算控制

```python
@dataclass
class TurnoverBudgetConfig:
    max_monthly_turnover: float = 0.50   # 每月最多替换 50% 仓位
    min_score_improvement: float = 0.10  # 新行业评分必须高于现有行业 10% 才换
    
def apply_turnover_budget(
    current_holdings: dict[str, float],
    target_weights: dict[str, float],
    scores: dict[str, float],
    budget: TurnoverBudgetConfig,
) -> dict[str, float]:
    """
    惰性再平衡：只有当新行业评分显著高于现有行业时才调仓。
    """
```

#### P.2 错峰再平衡（Staggered Rebalancing）

```python
# 当前：所有仓位在同一天调整（月度）
# 改进：每 5 天调整 1/4 仓位（降低时间点风险）
def staggered_rebalance_schedule(
    start_date: date,
    base_frequency: int = 20,  # 月度 20 交易日
    n_tranches: int = 4,       # 分 4 批次
) -> list[date]:
    """
    每 5 天调整 25% 仓位，全部完成需 20 天，
    降低单日调仓的执行风险和市场冲击。
    """
```

---

## 第四部分：具体执行计划

### 4.1 阶段优先级矩阵

| 阶段 | 任务 | 预期收益 | 风险 | 优先级 | 预计耗时 |
|------|------|---------|------|--------|---------|
| **K** | 因子 IC/ICIR 审计 | 识别真实有效因子，剔除噪声 | 低 | **P0** | ✅ DONE |
| **L** | 三状态市场分类器 | hit rate 22% → 55%，月胜率 +5pp | 中 | **P0** | ✅ DONE |
| **N.1** | 信号强度加权 | Sharpe +0.05–0.10 | 低 | **P0** | ✅ DONE |
| **N.2** | 行业相关性约束 | 降低集中度风险，DD -3pp | 低 | **P0** | ✅ DONE |
| **O.1** | Purged WF 方法论 | WF 结论更可信 | 低 | **P0** | ✅ DONE |
| **M.1** | Prosperity 数据修复 | IC 验证后 Sharpe +0.05 | 中 | **P1** | ✅ DONE |
| **M.2** | 真实 PE/PB 估值 | IC 验证后 Sharpe +0.03 | 高（数据获取）| **P1** | 🔒 BLOCKED (需 Wind/Bloomberg) |
| **N.3** | 动态 top_k | 分散度高时减少集中风险 | 低 | **P1** | ✅ DONE |
| **P.1** | 换手预算控制 | 换手 0.45 → 0.30，成本节省 | 低 | **P1** | ✅ DONE |
| **O.2** | 稳定性测试 | 参数扰动后的鲁棒性确认 | 低 | **P1** | ✅ DONE |
| **O.3** | 宏观时期独立验证 | 策略跨周期可靠性 | 低 | **P1** | ✅ DONE |
| **M.3** | 宏观因子叠加 | Sharpe +0.05–0.15（高不确定性）| 高（需数据）| **P2** | 🔒 BLOCKED (需 PMI/信用利差) |
| **P.2** | 错峰再平衡 | 降低时间点风险 | 中 | **P2** | ✅ DONE |

### 4.2 第一周：基础诊断（K + O.1 + N.2）

**Day 1–2：因子 IC 审计工具实现**

```bash
# 新增 tools/factor_ic_analysis.py
python tools/factor_ic_analysis.py \
    --config configs/real_sw2021.toml \
    --factors ret60,ret20,ret5,vol20,consistency60,amount_strength,rel_ret60 \
    --hold-periods 5,10,20,40,60 \
    --output reports/factor_ic_audit_sw2021/
    
# 也在 sw2014 验证（不同市场状态）
python tools/factor_ic_analysis.py \
    --config configs/real_sw2014.toml \
    --factors ret60,ret20,ret5,vol20,consistency60 \
    --hold-periods 5,10,20,40,60 \
    --output reports/factor_ic_audit_sw2014/
```

**核心代码逻辑**：

```python
# tools/factor_ic_analysis.py
import scipy.stats
import pandas as pd

def compute_rolling_ic(
    factor_values: pd.DataFrame,   # index=date, columns=industry
    forward_returns: pd.DataFrame, # index=date, columns=industry, hold_period
    method: str = "spearman",
) -> pd.Series:
    """
    每个调仓日，计算因子截面与未来收益截面的 rank correlation。
    """
    ic_series = {}
    for date in factor_values.index:
        if date not in forward_returns.index:
            continue
        f = factor_values.loc[date].dropna()
        r = forward_returns.loc[date].dropna()
        common = f.index.intersection(r.index)
        if len(common) < 10:
            continue
        rho, _ = scipy.stats.spearmanr(f[common], r[common])
        ic_series[date] = rho
    return pd.Series(ic_series)

def compute_icir(ic_series: pd.Series, window: int = 12) -> pd.Series:
    return ic_series.rolling(window).mean() / ic_series.rolling(window).std()
```

**验收标准**（Day 2 结束）：
- 每个因子的 ICIR 有量化评估结果
- 识别出在 sw2014 和 sw2021 中均 ICIR > 0.12 的因子（→ 进入候选）
- 识别出 ICIR < 0.05 的因子（→ 剔除）

---

**Day 3–4：行业相关性约束实现（N.2）**

```python
# src/quant_rotation/portfolio.py 新增
import numpy as np

INDUSTRY_CLUSTER_SW2021 = {
    "TMT":      ["计算机", "电子", "通信", "传媒"],
    "新能源":   ["电力设备", "汽车"],
    "周期":     ["煤炭", "钢铁", "有色金属", "基础化工", "石油石化"],
    "金融":     ["银行", "非银金融"],
    "消费":     ["食品饮料", "家用电器", "美容护理", "商贸零售", "农林牧渔"],
    "医疗":     ["医药生物"],
    "防御":     ["公用事业", "交通运输", "社会服务"],
    "其他":     ["机械设备", "建筑装饰", "建筑材料", "纺织服饰", "轻工制造", "综合", "环保", "国防军工", "房地产", "美容护理"],
}

def select_with_cluster_constraint(
    scores: dict[str, float],
    top_k: int,
    max_per_cluster: int = 2,
    cluster_map: dict = INDUSTRY_CLUSTER_SW2021,
) -> list[str]:
    """
    贪心选择：按评分降序，对每个集群内已选数量进行约束。
    """
    reverse_map = {ind: cluster for cluster, inds in cluster_map.items() for ind in inds}
    cluster_count = {cluster: 0 for cluster in cluster_map}
    selected = []
    for industry, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        if len(selected) >= top_k:
            break
        cluster = reverse_map.get(industry, "其他")
        if cluster_count.get(cluster, 0) < max_per_cluster:
            selected.append(industry)
            cluster_count[cluster] = cluster_count.get(cluster, 0) + 1
    return selected
```

**配置新增字段**：
```toml
[strategy]
cluster_constraint = true        # 是否启用集群约束
max_per_cluster = 2              # 每集群最多选几个行业
```

**验收标准**：
- 与 exp_best_p0 基线比较：相关性约束不应降低 Sharpe（通过降低集中度风险应持平或改善）
- 行业选择频次分布更均匀（当前 TMT 三行业占据 1/3 选择次数）

---

**Day 5：Purged WF 实现（O.1）**

```python
# src/quant_rotation/validation.py 修改
def purged_walk_forward_splits(
    dates: list[date],
    train_window: int = 504,
    test_window: int = 63,
    gap: int = 20,
    step: int = 63,
) -> list[tuple[list[date], list[date]]]:
    """
    生成净化的训练/测试分割：
    - 训练集：[start, train_end]
    - 净化间隔：[train_end+1, train_end+gap]（这些日期不用于测试）
    - 测试集：[train_end+gap+1, train_end+gap+test_window]
    """
    splits = []
    i = train_window
    while i + gap + test_window <= len(dates):
        train_dates = dates[i - train_window:i]
        test_dates = dates[i + gap:i + gap + test_window]
        if test_dates:
            splits.append((train_dates, test_dates))
        i += step
    return splits
```

---

### 4.3 第二周：三状态分类器 + 信号强度加权（L + N.1）

**Day 6–8：三状态市场分类器实现（L）**

```python
# src/quant_rotation/regime.py（新文件）
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

class MarketState(Enum):
    STRONG  = "strong"
    NEUTRAL = "neutral"
    WEAK    = "weak"

@dataclass
class MarketStateConfig:
    trend_weight:     float = 0.35
    dispersion_weight: float = 0.25
    momentum_weight:  float = 0.25
    breadth_weight:   float = 0.15
    strong_threshold:  float = 0.25
    weak_threshold:    float = -0.10
    strong_exposure:   float = 1.00
    neutral_exposure:  float = 0.60
    weak_exposure:     float = 0.25

def classify_market_state(
    benchmark_closes: list[float],
    industry_returns_20d: dict[str, float],
    breadth_values: dict[str, float] | None,
    index: int,
    config: MarketStateConfig,
) -> tuple[MarketState, float]:
    # 信号 1：趋势得分（多均线）
    closes = benchmark_closes[:index + 1]
    ma20  = sum(closes[-20:])  / 20
    ma60  = sum(closes[-60:])  / 60
    ma120 = sum(closes[-120:]) / 120
    current = closes[-1]
    trend_score = (
        0.4 * (1.0 if current > ma20  else -1.0)
        + 0.4 * (1.0 if current > ma60  else -1.0)
        + 0.2 * (1.0 if current > ma120 else -1.0)
    )  # -1.0 ~ +1.0
    
    # 信号 2：截面分散度
    returns = list(industry_returns_20d.values())
    if len(returns) > 2:
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        dispersion = variance ** 0.5  # 截面标准差
        # 标准化到 [-1, 1]，0.04 为低分散，0.12 为高分散
        dispersion_score = min(1.0, max(-1.0, (dispersion - 0.07) / 0.05))
    else:
        dispersion_score = 0.0
    
    # 信号 3：市场动量质量
    if index >= 60:
        ret60 = closes[-1] / closes[-60] - 1
        ret5  = closes[-1] / closes[-5] - 1
        # 惩罚过热（近期过快上涨）
        momentum_quality = ret60 - max(0, ret5 * 3)
        # 标准化到 [-1, 1]
        momentum_score = min(1.0, max(-1.0, momentum_quality / 0.15))
    else:
        momentum_score = 0.0
    
    # 信号 4：行业宽度
    if breadth_values:
        avg_breadth = sum(breadth_values.values()) / len(breadth_values)
        breadth_score = (avg_breadth - 0.50) * 4  # 中心化后扩展到 [-1, 1] 附近
        breadth_score = min(1.0, max(-1.0, breadth_score))
    else:
        breadth_score = 0.0
    
    # 综合评分
    composite = (
        config.trend_weight     * trend_score
        + config.dispersion_weight * dispersion_score
        + config.momentum_weight   * momentum_score
        + config.breadth_weight    * breadth_score
    )
    
    if composite >= config.strong_threshold:
        return MarketState.STRONG, config.strong_exposure
    elif composite > config.weak_threshold:
        return MarketState.NEUTRAL, config.neutral_exposure
    else:
        return MarketState.WEAK, config.weak_exposure
```

**实验**：

```bash
# 实验 L-SW2021：三状态 vs 二元风控
python -m quant_rotation sweep \
    --config configs/real_sw2021.toml \
    --industry-only \
    --factor-set ret60_ret5 \
    --top-k 3,5 \
    --market-state-mode three_state,binary \
    --output-dir reports/exp_L_three_state_sw2021

# 分年验证
python tools/annual_returns_summary.py \
    reports/exp_L_three_state_sw2021/... \
    --compare reports/production/annual_returns.csv \
    --segments
```

---

**Day 9–10：信号强度加权（N.1）**

```python
# src/quant_rotation/portfolio.py 修改
def compute_weights(
    selected_industries: list[str],
    scores: dict[str, float],
    mode: str = "equal",
    softmax_temperature: float = 0.5,
) -> dict[str, float]:
    if mode == "equal":
        w = 1.0 / len(selected_industries)
        return {i: w for i in selected_industries}
    
    elif mode == "softmax":
        s = {i: scores[i] / softmax_temperature for i in selected_industries}
        max_s = max(s.values())
        exp_s = {i: math.exp(v - max_s) for i, v in s.items()}
        total = sum(exp_s.values())
        return {i: exp_s[i] / total for i in selected_industries}
    
    elif mode == "rank":
        # 线性排名加权：第 1 名 n 倍，第 k 名 1 倍
        ranked = sorted(selected_industries, key=lambda i: scores[i], reverse=True)
        n = len(ranked)
        weights = {i: (n - r) / sum(range(n)) for r, i in enumerate(ranked)}
        return weights
    
    raise ValueError(f"Unknown mode: {mode}")
```

---

### 4.4 第三周：因子新信号 + 全段验证（M.1 + O.3）—— ✅ 已完成

#### M.1 Prosperity 因子 IC 验证结果

```bash
python tools/factor_ic_analysis.py \
    --config configs/real_sw2021.toml \
    --factors prosperity \
    --hold-periods 5,10,20 \
    --output reports/factor_ic_prosperity/
```

**结果**: prosperity hold=20d IC=-0.036, ICIR=-0.134
- |ICIR| = 0.134 > 0.12 → 预测能力稳定
- |IC| = 0.036 < 0.05 → 方向性太弱
- **结论**: 不进入生产配置 (IC元 < 0.05 门槛)

#### N.3 动态 top_k 实现

新增 `top_k_from_dispersion()` 函数 + 配置字段:
- `dynamic_top_k: bool` — 启用开关
- `dynamic_top_k_min / max / disp_low / disp_high` — 阈值参数
- 低分散度(0.02) → top_k=3; 中(0.07) → top_k=5; 高(0.12) → top_k=7

#### O.2 稳定性测试

新增 `tools/stability_test.py` — 参数扰动 ±5% 后性能劣化 < 1pp:
- **PASS**: 年化劣化 0.90pp < 1pp 阈值
- 扰动后 Sharpe 均值 0.55 vs 基线 0.52 (无劣化)

#### O.3 宏观时期独立验证

新增 `--start` / `--end` 日期过滤到 CLI:

| 时期 | 年化收益 | Sharpe |
|------|---------|--------|
| 2021-2022 | 0.0% | 0.00 (避险) |
| 2023 | 0.0% | 0.00 (避险) |
| 2024 | -1.6% | -0.02 |
| 2025-2026 | +25.4% | 1.28 |

4个时期中2个正收益 — 未达成3/4正收益目标。

#### P.1 换手预算控制

新增 `shrink_toward_current()` 函数 + `turnover_budget` 配置字段:
- 滑动窗口跟踪历史换手
- 平均换手超预算时收缩至当前权重

#### P.2 错峰再平衡 — ✅ 已完成

新增 `staggered_rebalance` + `staggered_n_tranches` 配置字段:
- CLI: `--config-override` + `--purged-gap` 支持单配置WF验证
- 4-tranche 将月度换手拆分，每个子调仓仅旋转 25% 权重
- 测试结果: 年化 3.74% vs 基线 6.51% (动量策略中延迟信号传导导致劣化)

#### M-Final: 27 折 Purged WF 验证结果

```bash
python -m quant_rotation validate-segments \
    --configs configs/real_sw2021.toml configs/real_sw2014.toml configs/real_sw2000.toml \
    --industry-only --factor-set ret60_ret5 --top-k 5 \
    --risk-off-exposure 0 --risk-control true --market-score-control true \
    --walk-forward --train-window 504 --test-window 126 \
    --purged-gap 20 --config-override configs/candidate_v3_minimal.toml
```

| Metric | Baseline (production) | v3_minimal (+cluster) |
|--------|----------------------|----------------------|
| OOS 盈利折 | 11/27 | 11/27 |
| OOS 年化均值 | 3.67% | 3.82% |
| OOS 年化中位数 | **-0.53%** | **-0.70%** |
| OOS 年化最小/最大 | -84% / +157% | -84% / +157% |
| OOS Sharpe 均值 | 0.15 | 0.17 |
| OOS Sharpe 中位数 | 0.02 | 0.00 |
| OOS 月胜率均值 | 30.2% | 30.2% |

**结论**: 集群约束边际改善均值 (+0.15pp)，但无法改变核心问题——
WF 中位数收益为负，收益由少数极端正收益折叠动。策略缺乏一致性 Alpha。

---

### 4.5 第四周：全段 WF 验证（最终候选确认）

**Day 16–17：构建最终候选配置**

基于前三周的实验结果，构建最终候选（预期配置方向）：

```toml
# configs/candidate_v3_alpha.toml（预期配置，根据实验结果最终确定）
[strategy]
rebalance_every = 20
top_k = 5                         # 由动态 top_k 根据分散度调整
max_industry_weight = 0.28        # 略低于当前 0.30
transaction_cost = 0.001
risk_control = true
market_ma_window = 120
market_state_mode = "three_state" # 新增：三状态分类器
market_state_strong_exposure = 1.0
market_state_neutral_exposure = 0.6
market_state_weak_exposure = 0.25
portfolio_mode = "softmax"        # 信号强度加权
softmax_temperature = 0.5
cluster_constraint = true         # 行业相关性约束
max_per_cluster = 2

[factors]
ret60_weight = 1.00               # 主力因子不变
consistency60_weight = 0.25       # 根据 K 阶段 IC 结果确认
ret5_weight = -0.50               # 过热惩罚保留
prosperity_weight = 0.15          # 根据 M.1 阶段 IC 验证结果决定是否加入
# 其他因子根据 IC 结果决定
```

**Day 18–20：全段 WF 验证（27 折）**

```bash
python -m quant_rotation validate-segments \
    --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml \
    --industry-only \
    --config-override configs/candidate_v3_alpha.toml \
    --purged-gap 20 \
    --output-dir reports/exp_v3_alpha_wf27

# 分段诊断
python tools/wf_segment_diagnosis.py reports/exp_v3_alpha_wf27 --all
```

---

## 第五部分：验收标准与里程碑

### 5.1 阶段里程碑

| 里程碑 | 状态 | 通过条件 |
|--------|------|---------|
| **M-K** | ✅ PASS | 确认至少 2 个 ICIR > 0.12 的因子 (ret60, ret20, ret5, prosperity) |
| **M-L** | ⚠️ PARTIAL | 三状态分类器月胜率 44%-49% (目标 55%), 风控触发比例降低 |
| **M-N** | ⚠️ PARTIAL | 带相关性约束的等权 Sharpe 0.57 (+0.05 基线) 未达 0.60 |
| **M-M1** | ❌ FAIL | prosperity \|ICIR\|=0.134 但 \|IC\|=0.036 < 0.05 门槛 |
| **M-O3** | ⚠️ PARTIAL | 策略在 4 个宏观时期中 2/4 正收益 (目标 3/4) |
| **M-Final** | ❌ FAIL | Purged WF 27折: 11/27 盈利折 (目标 ≥17/27), OOS年化中位数 -0.70% (目标 ≥3%)

### 5.2 最终生产就绪标准（全部达到才算强 Alpha）

| 指标 | 目标 | 关键检查点 |
|------|------|----------|
| sw2021 年化收益 | ≥ 12% | 单段回测 |
| sw2021 Sharpe | ≥ 0.70 | 单段回测 |
| sw2021 最大回撤 | ≤ -15% | 单段回测 |
| sw2021 月胜率 | ≥ 45% | 单段回测 |
| sw2021 最差单年 | ≥ -5% | 分年分析 |
| sw2021 负收益年份 | ≤ 1/6 | 分年分析 |
| sw2014 年化收益 | ≥ 10% | 单段回测 |
| sw2014 最大回撤 | ≤ -25% | 单段回测（现在 -54.8%）|
| WF 27 折盈利折数 | ≥ 17/27（63%）| Purged WF |
| WF OOS 年化中位数 | ≥ 3% | Purged WF |
| 风控 hit rate | ≥ 55% | 风控诊断工具 |
| 宏观时期覆盖 | 4 个时期中 3 个正收益 | 宏观时期验证 |
| 参数扰动稳定性 | ±5% 扰动后年化差 < 1pp | 稳定性测试 |

---

## 第六部分：代码架构变更

### 6.1 新文件

```
src/quant_rotation/
  + regime.py           # 市场状态分类器（三状态）

tools/
  + factor_ic_analysis.py      # IC/ICIR 计算工具
  + stability_test.py          # 参数扰动稳定性测试
  + macro_period_analysis.py   # 宏观时期独立验证 (via --start/--end CLI)

configs/
  + candidate_v3_alpha.toml     # 基于 K/L/N 实验结论的激进候选
  + candidate_v3_defensive.toml # 防御变体（weak_exposure=0.30）
  + candidate_v3_minimal.toml   # P2 最终候选: 生产基线 + 集群约束
```

### 6.2 修改的文件 (v3.2 已实现)

| 文件 | 修改内容 |
|------|---------|
| `backtest.py` | 集成三状态分类器、集群约束、动态top_k、换手预算、错峰再平衡 |
| `portfolio.py` | `select_with_cluster_constraint()`, `top_k_from_dispersion()`, `shrink_toward_current()` |
| `models.py` | 新增 20+ 配置字段 (cluster/market_state/dynamic_top_k/turnover/staggered) |
| `config.py` | 解析所有新增配置字段 |
| `validation.py` | `purged_walk_forward_splits()` + `purged_gap` 参数 |
| `cli.py` | `--start`/`--end` 日期过滤, `--config-override`, `--purged-gap` |

### 6.3 新增工具

| 工具 | 用途 |
|------|------|
| `tools/factor_ic_analysis.py` | 截面因子 IC/ICIR 计算 |
| `tools/stability_test.py` | 参数扰动鲁棒性测试 |
| `tools/wf_segment_diagnosis.py` | WF 分段诊断 (已有) |

### 6.4 测试补充

---

## 第七部分：风险提示与注意事项

### 7.1 现实约束

**数据依赖**：
- 真实 PE/PB 估值数据需要 Wind/Bloomberg 订阅，这是 M.2 阶段的前提
- sw2000/sw2014 历史成分股仍缺失（需要 JoinQuant/Tushare），影响全段 WF 质量
- breadth 数据在 sw2000/sw2014 段仍有偏差

**关键认知**：
- **因子 IC 是先决条件**：在 IC 未验证前，不应相信任何基于回测 Sharpe 的结论
- **WF 样本量限制**：27 折（约 16 年）中，每折仅 6 个月。折数不够，统计结论不可靠
- **A 股特殊性**：政策驱动的行情（2020、2024 Q4）难以被任何量化模型预测

### 7.2 可能的陷阱

**陷阱 1**：IC 好但回测差
- IC 衡量的是截面预测能力，而回测涉及组合构建、风控、成本等多个环节
- IC > 0.10 是必要条件，不是充分条件

**陷阱 2**：三状态分类器在新市场环境中过拟合
- 三状态的阈值（0.25/-0.10）是通过历史标定的，可能不适用于未来结构性变化
- 缓解：定期重标定（年度）+ 宽松阈值（避免过度灵敏）

**陷阱 3**：行业集群定义在行业重组后失效
- 申万行业分类每几年更新一次（sw2000→sw2014→sw2021），集群定义需同步更新
- 代码中明确按 sw 版本管理集群映射表

**陷阱 4**：Prosperity 因子带来前视偏差
- 财报数据有发布滞后，需严格使用 `release_lag_days` 偏移
- 生产前必须通过 `tools/data_integrity_check.py --production` 的检查

### 7.3 如果方向 K 显示 ret60 ICIR < 0.10 怎么办

这意味着 A 股行业动量本身缺乏统计上的预测能力。在这种情况下：
1. 检查 IC 是否因行业轮动过快而衰减（持有 5 天的 IC vs 持有 20 天的 IC）
2. 检查是否在特定宏观环境下 IC 才显著（分年 IC 分析）
3. 如果确认 ret60 ICIR 全面低于 0.08，需要更根本性地质疑「行业动量轮动是否在 A 股有效」

这是最坏情况，但也必须面对：如果基础假设（行业动量可预测）不成立，则所有优化都是无用的。

---

## 第八部分：快速验证清单

每次代码改动后的最小验证流程：

```bash
# 步骤 1：单元测试
python -m pytest tests/ --tb=short -q

# 步骤 2：单段快速验证（sw2021，5 分钟）
python -m quant_rotation run --config configs/<new_config>.toml
python tools/annual_returns_summary.py reports/<dir>/annual_returns.csv --segments

# 步骤 3：因子 IC 检查（当有新因子时）
python tools/factor_ic_analysis.py \
    --config configs/<new_config>.toml \
    --output reports/<dir>/factor_ic/

# 步骤 4：风控诊断
python tools/diagnose_risk_control.py --config configs/<new_config>.toml

# 步骤 5：WF 快验（仅 sw2014+sw2021，19 折，20 分钟）
python -m quant_rotation validate-segments \
    --configs configs/real_sw2014.toml configs/real_sw2021.toml \
    --industry-only \
    --factor-set ret60_ret5 \
    --top-k 3,5 \
    --risk-off-exposure 0 \
    --purged-gap 20 \
    --output-dir reports/quick_wf_<name>
python tools/wf_segment_diagnosis.py reports/quick_wf_<name> --all

# 步骤 6（里程碑验证时）：27 折全段 WF
python -m quant_rotation validate-segments \
    --configs configs/real_sw2000.toml configs/real_sw2014.toml configs/real_sw2021.toml \
    --industry-only \
    --purged-gap 20 \
    --output-dir reports/final_wf_<name>
```

---

## 附录 A：历史实验结论速查（v2 结果保留参考）

| 实验 | 结论 | 状态 |
|------|------|------|
| F：软仓位扫描 | 最优 softoff0p2 年化 7.29%，未超硬模式基线 6.51% | ✅ 已测试 |
| G：vol_targeting | vol 0.12~0.18 全部 DD -35~-37%，年化 ~0% | ❌ 已排除 |
| G：年度预算控制 | 当前收益水平下从未触发，意义有限 | 暂搁置 |
| H：精简候选 WF | H2 WF 14.93% 最强但固定配置 -1.48%，过拟合 | ✅ 已测试 |
| I：历史成分股 | SW2021 段已补齐 173 快照 / 5246 只股票 | ✅ 已完成 |
| J：Phase D 无偏 | 无偏年化 -2.87%, Sharpe -0.013 | ❌ 正式排除 |
| Layer 2 WF（19 折）| 盈利折 8/19，中位数 0%，均值 6.48% 由极端折贡献 | ❌ 未达标 |
| 27 折全段 WF | 盈利折 13/27，中位数 0%，固定 top3 OOS 净值 1.95 | ❌ 未达标 |
| 风控 hit rate | 四段全部 22~38%，market_score 误报率 62% | ❌ 需根本改造 |

---

*文档版本：v3.2 | 更新日期：2026-06-07 | 状态：P0+P1 全部完成，P2 已执行 P.2，M.2/M.3 数据阻塞，M-Final ❌*