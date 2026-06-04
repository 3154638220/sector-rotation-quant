# 行动计划：从防守型轮动策略升级为强 Alpha 策略

> 基于对全量代码、6 个历史分段（sw2000/sw2014/sw2021/production）、27 折跨段 WF、
> 所有因子分解报告的深度诊断  
> 分析日期：2026-06-04  
> 版本：本文件完整替代历史 plan.md，聚焦从"有效防守"到"强 Alpha"的升级路径

---

## 零、战略级诊断

### 0.1 当前策略的本质

现有策略（`ret60_ret5 + top_k=5 + risk_control=true + risk_off=0.0`）的收益来源
**不是真正的横截面 Alpha，而是市场择时（Beta 管理）**：

| 收益来源 | 贡献比例 | 证据 |
|---------|---------|------|
| 2022 年规避熊市（持仓 0） | 主要 | 2022 超额 +21.6% vs 基准，全年 exposure=0 |
| 2025 年参与牛市（满仓动量） | 主要 | 2025 年化 +18.6%，动量共振 |
| 真正的行业轮动 Alpha | 极少 | 2023 年化 -4.6%（市场只跌 11.4%，策略跑输等权）；2024 年化 +8.6% 但跑输沪深 300 |

**核心证据**：月胜率在 sw2021（2021–2026）仅 **29.1%**。这意味着策略 71% 的月份亏损，
靠少数几次大涨月份盈利——典型的"期权式"非线性 Beta 暴露，而非持续稳定的 Alpha。

### 0.2 三段式历史的残酷现实

| 分段 | 年化 | Sharpe | 最大回撤 | Calmar | 核心问题 |
|------|------|--------|----------|--------|---------|
| sw2000（2010–2014） | **-5.2%** | **-0.34** | -27.1% | -0.19 | 绝对动量在震荡市完全失效 |
| sw2014（2014–2021） | +10.3% | 0.60 | **-54.8%** | 0.19 | Calmar 极差；2017、2019 大幅跑输基准 |
| sw2021（2021–2026） | +6.5% | 0.52 | -17.3% | 0.38 | 年化过低；月胜率 29% |

sw2014 虽然年化 10.3% 看起来不差，但 **-54.8% 最大回撤、2017 年 -8.9%（基准+21.8%）、
2019 年 +2.6%（基准+36.1%）**——这根本无法实盘运行。
跨段 27 折 WF OOS 中位数年化 8.5% 的表现，主要由 sw2021 的近期表现拉动。

### 0.3 因子质量的根本缺陷

**问题 1：绝对动量（ret60）在 A 股跨周期不稳定**  
- 2010–2014（震荡市）：绝对动量几乎无效，Sharpe -0.34
- 2014–2015（极端牛市）：动量追涨后被牛市末期暴跌重击
- 2021–2026（震荡+政策驱动）：绝对动量部分有效

根本原因：绝对收益率包含系统性 Beta，各行业涨跌同步时无法区分行业选择能力。

**问题 2：因子套利空间被"等权"抹平**  
当前 `equal_weight_target` 对排名第 1（score=2.5）和排名第 5（score=0.3）的行业给予
完全相同的 20% 权重，等于主动丢弃评分信息。

**问题 3：已有数据未被充分利用**  
- `industry_prosperity.csv` 在 sw2021 中已有数据，但 `prosperity_weight = 0.00`
- `breadth20/breadth60` 在样本数据中存在，实盘中未启用
- 成交额 z-score 景气代理从未测试

### 0.4 目标：强 Alpha 的定量定义

强 Alpha 策略必须同时满足以下指标（验证集为 27 折跨段 WF OOS）：

| 指标 | 当前 | 目标 | 说明 |
|------|------|------|------|
| OOS Sharpe 中位数 | 0.484 | **> 0.90** | 跨市场周期稳定盈利能力 |
| OOS 年化收益中位数 | 8.52% | **> 18%** | 绝对收益有吸引力 |
| 月胜率（全段） | 29.1%（sw2021）| **> 52%** | 真正的月度稳定性 |
| OOS 盈利折数 | 16/27（59%） | **> 19/27（70%）** | 跨周期一致性 |
| sw2014 段 OOS Sharpe 中位数 | 0.00 | **> 0.35** | 早期数据泛化能力 |
| sw2000 段年化收益 | -5.2% | **> +5%** | 最难验证集不亏损 |
| 最大回撤（全段） | -54.8%（sw2014）| **< -25%**（全段限制） | 可运行的风险控制 |
| Bootstrap p_positive | 95.0% | **> 97%** | 统计可信度更高 |

---

## 一、升级路径概览

将当前策略升级为强 Alpha 策略需要在**四个维度**同步突破：

```
┌─────────────────────────────────────────────────────────┐
│  维度 A: 因子架构重建           [最高优先级, 最大影响]  │
│  核心：从绝对动量 → 相对动量 + 质量确认                  │
├─────────────────────────────────────────────────────────┤
│  维度 B: 组合构建革命           [高优先级]               │
│  核心：等权 → 得分加权 + 波动率调整                       │
├─────────────────────────────────────────────────────────┤
│  维度 C: 市场状态精细化         [中高优先级]              │
│  核心：MA120 单一指标 → 多信号状态机                       │
├─────────────────────────────────────────────────────────┤
│  维度 D: 股票层 Alpha           [中优先级, 第二 alpha 层] │
│  核心：行业层选择 → 行业内优质股票精选                     │
└─────────────────────────────────────────────────────────┘
```

**防过拟合核心原则**：
- 每个新因子/改动必须在 **sw2014 OOS** 中独立验证（sw2014 是最难的样本外集，
  绝大多数策略在此期间表现差）
- 所有超参数通过 WF 走前优化确定，不允许全样本最优化
- 每个改动有独立的经济学解释，不允许纯数据挖掘

---

## 二、阶段 A：因子架构重建（P0，最高优先级，预计 2 周）

### A.1 核心诊断：绝对动量的跨周期失效

当前 `ret60 = (P_today - P_60d_ago) / P_60d_ago` 测量的是**绝对涨幅**，
在所有行业同步上涨（牛市）或同步下跌（熊市）时，区分行业的能力极差——
区分的只是"谁涨得更多"，这本质上是 Beta 而非 Alpha。

**A 股特有问题**：行业间 Beta 差异巨大（金融 Beta≈0.8，科技 Beta≈1.5），
绝对动量在市场大涨时天然偏向高 Beta 行业（科技），在横盘时随机，
在下跌时偏向低 Beta（红利/银行）。这与"行业轮动"的本意矛盾。

### A.2 解决方案：市场超额动量（最重要的单一改动）

**新增因子 `rel_ret60`**：用行业收益减去市场加权收益，消除系统性 Beta 污染。

$$\text{rel\_ret60}_i = \text{ret60}_i - \sum_j w_j \cdot \text{ret60}_j$$

其中 $w_j$ 是 `market_weights`（CSI300=0.5, CSIAll=0.3, ChiNext=0.2）中各市场的权重，
$\text{ret60}_j$ 是对应市场指数的 60 日收益。

#### 实现（`factors.py`）

```python
# 在 compute_factor_snapshot 中新增
def _market_excess_return(
    ind_ret: dict[str, float],
    market_data: PriceData | None,
    index: int,
    lookback: int,
    market_weights: dict[str, float],
) -> dict[str, float]:
    """计算各行业相对于市场加权基准的超额收益"""
    if market_data is None:
        return {}  # 无市场数据时退化为绝对动量
    
    # 计算市场加权收益（用 market_close.csv 中的多指数）
    total_w = sum(market_weights.values())
    if total_w <= 0:
        return {}
    mkt_ret = sum(
        (market_weights.get(asset, 0.0) / total_w)
        * simple_return(market_data.closes[asset], index, lookback)
        for asset in market_data.assets
        if asset in market_weights
    )
    return {asset: ret - mkt_ret for asset, ret in ind_ret.items()}

# FactorWeights 新增字段
@dataclass(frozen=True)
class FactorWeights:
    # ... 现有字段 ...
    rel_ret60: float = 0.00      # 市场超额 60 日动量（新增）
    rel_ret20: float = 0.00      # 市场超额 20 日动量（新增）
    momentum_accel: float = 0.00 # 动量加速度 = rel_ret20 - rel_ret40（新增）
```

#### 实验 A2-EXP1：rel_ret60 消融测试

```toml
# configs/exp_rel_momentum.toml
[factors]
ret60_weight = 0.00        # 关闭绝对动量
rel_ret60_weight = 1.00    # 只用相对动量
ret5_weight = -0.50
```

**测试流程**：
```bash
# Step 1: 在 sw2021 验证
python -m quant_rotation run --config configs/exp_rel_momentum.toml
python -m quant_rotation decompose --config configs/exp_rel_momentum.toml

# Step 2: 在 sw2014 WF 验证（关键：相对动量在更早期是否也有效）
python -m quant_rotation validate-segments \
    --config configs/exp_rel_momentum_sw2014.toml \
    --output-dir reports/exp_rel_momentum/wf_sw2014

# Step 3: 跨段 27 折验证
python -m quant_rotation validate-segments \
    --config configs/exp_rel_momentum_cross.toml \
    --output-dir reports/exp_rel_momentum/cross_segment_wf
```

**验收标准**：
- sw2021 Sharpe ≥ 0.55（不退化）
- sw2014 OOS Sharpe **中位数 > 0.15**（这是关键：当前为 0.00）
- sw2000 段回测 Sharpe **> -0.10**（当前为 -0.34）

**经济学解释**：相对动量测量行业相对于市场的超额吸引力，剔除市场整体方向，
真正捕捉资金从弱势行业流向强势行业的轮动信号。

### A.3 动量质量因子：一致性得分

当前 ret60 可能由单日大涨驱动（如 60 日前某天低基数），这种"噪声动量"不应受高权重。
引入**上涨一致性因子**：过去 60 日中上涨交易日的占比。

#### 实现（`factors.py`）

```python
def trend_consistency(values: list[float], index: int, lookback: int) -> float:
    """计算 lookback 期内日涨跌为正的比例，范围 [0,1]"""
    if index < lookback:
        raise ValueError("Not enough history for trend consistency")
    up_days = sum(
        1 for i in range(index - lookback + 1, index + 1)
        if values[i] > values[i - 1]
    )
    return up_days / lookback


# 在 compute_factor_snapshot 中添加：
consistency60: dict[str, float] = {}
for asset, closes in data.closes.items():
    consistency60[asset] = trend_consistency(closes, index, 60)
z_consistency60 = zscore(consistency60)

# FactorWeights 新增：
consistency60: float = 0.00   # 60 日上涨一致性
```

**测试**：同 A2-EXP1，在消融测试中独立测试 `consistency60` 因子贡献。

### A.4 景气因子激活：使用现有数据

`data/real_sw2021/industry_prosperity.csv` 已存在，但当前 `prosperity_weight = 0.00`。
这是最低成本的改进：无需新数据，直接在 sweep 中开放权重。

#### 实验 A4-EXP1：景气因子单独测试

```bash
python -m quant_rotation sweep --config configs/real_sw2021.toml \
    --factor-sets "ret60_ret5,ret60_ret5_prosperity,ret60_prosperity" \
    --output-dir reports/exp_prosperity_sweep
```

需要在 `sweep.py` 的 `DEFAULT_FACTOR_SET_NAMES` 中添加含景气因子的组合：
```python
# sweep.py
FACTOR_SETS_WITH_PROSPERITY = (
    "ret60_ret5",
    "ret60_ret5_prosperity",        # 新增
    "rel_ret60_ret5",               # 新增（待 A.2 实现后）
    "rel_ret60_ret5_prosperity",    # 新增
)
```

**验收标准**：
- 含 `prosperity` 的最优配置 Sharpe ≥ 0.58（vs 当前 0.52）
- sw2014 OOS Sharpe 不低于不含景气的版本
- 经济学解释：景气度代理（成交额 z-score 或行业 PMI 代理）反映行业基本面趋势

### A.5 动量加速度因子

区分"动量正在增强"和"动量正在衰减"。

$$\text{momentum\_accel} = \text{rel\_ret20} - \text{rel\_ret40\_to\_20}$$

其中 `rel_ret40_to_20` 是 40 日前到 20 日前的相对收益（衡量前半段动量）。

```python
# factors.py 新增
def period_return(values: list[float], index: int, 
                  start_lag: int, end_lag: int) -> float:
    """计算从 start_lag 天前到 end_lag 天前的收益"""
    # 例如 start_lag=40, end_lag=20: 返回 40->20 日前的收益
    if index < start_lag:
        raise ValueError("Not enough history")
    return values[index - end_lag] / values[index - start_lag] - 1.0
```

**经济学逻辑**：动量加速度正值表示近期比前期更强，趋势正在形成；
负值表示动量在衰减，需要降权。

### A.6 因子工程小结

完成阶段 A 后，目标因子组合为：

| 因子 | 新/现有 | 权重范围 | 经济学逻辑 |
|------|--------|---------|-----------|
| `rel_ret60` | **新增** | 0.5–1.0 | 剔除 Beta 的行业相对强度 |
| `rel_ret20` | **新增** | 0.0–0.3 | 短期相对动量 |
| `momentum_accel` | **新增** | 0.0–0.2 | 动量是否在加速 |
| `consistency60` | **新增** | 0.0–0.3 | 趋势一致性质量 |
| `ret5` | 现有（反转） | -0.3 ~ -0.5 | 短期过热惩罚 |
| `prosperity` | **激活** | 0.1–0.3 | 行业景气度 |
| `vol20` | 现有（惩罚） | -0.1 ~ -0.3 | 波动率惩罚 |

绝对动量 `ret60`（当前主因子）**降权至 0 或 0.1**，由 `rel_ret60` 取代。

---

## 三、阶段 B：组合构建革命（P0，最高优先级，预计 1 周）

### B.1 核心诊断：等权抹平评分信息

`equal_weight_target` 函数将排名第 1（score=2.5）和排名第 5（score=0.3）的行业给予
**完全相同的 20% 权重**。这相当于告诉模型："你花力气给出的排名分差异我不在乎"。

在 A 股市场中，行业轮动的信号往往集中在少数几个领涨行业。
当市场有明确主线（如 2023–2024 的 AI 行情、2025 的大盘牛市），
等权会用显著稀释领涨行业的权重来"平衡"其他弱势行业。

### B.2 Softmax 得分加权

将等权替换为**温度调控的 Softmax 加权**，评分越高的行业获得越高权重：

$$w_i = \frac{e^{s_i / \tau}}{\sum_{j \in \text{top-}k} e^{s_j / \tau}} \cdot \text{exposure}$$

其中 $\tau$（temperature）控制集中度：$\tau \to 0$ 时为集中在第 1 名，$\tau \to \infty$ 时退化为等权。

#### 实现（`portfolio.py`）

```python
import math

def softmax_weight_target(
    scores: dict[str, float],
    top_k: int,
    exposure: float,
    max_weight: float,
    temperature: float = 1.0,
) -> dict[str, float]:
    """
    Softmax 加权版本的持仓构建。
    temperature: 越小越集中，推荐范围 0.5–2.0
    """
    if not 0 <= exposure <= 1:
        raise ValueError("exposure must be between 0 and 1")
    if temperature <= 0:
        raise ValueError("temperature must be positive")

    holdings = select_top_k(scores, top_k)
    if not holdings or exposure == 0:
        return {}

    # 取 top-k 的 softmax 概率
    top_scores = {asset: scores[asset] for asset in holdings}
    max_score = max(top_scores.values())  # 数值稳定性
    exp_scores = {
        asset: math.exp((s - max_score) / temperature)
        for asset, s in top_scores.items()
    }
    total = sum(exp_scores.values())
    raw_weights = {asset: (v / total) * exposure for asset, v in exp_scores.items()}

    # 应用 max_weight 约束后归一化
    return _clamp_and_renormalize(raw_weights, max_weight, exposure)


def _clamp_and_renormalize(
    weights: dict[str, float],
    max_weight: float,
    target_exposure: float,
) -> dict[str, float]:
    """将超过 max_weight 的权重截断并重新分配到其余资产"""
    result = dict(weights)
    for _ in range(10):  # 最多迭代 10 次（防止无限循环）
        clamped = {k: min(v, max_weight) for k, v in result.items()}
        excess = sum(result[k] - max_weight for k in result if result[k] > max_weight)
        if excess < 1e-10:
            break
        below_max = [k for k, v in result.items() if v < max_weight]
        if not below_max:
            break
        per_asset = excess / len(below_max)
        result = {
            k: min(clamped[k] + per_asset, max_weight)
            for k in clamped
        }
    return result
```

#### 实验 B2-EXP1：Softmax 温度参数扫描

```python
# 在 sweep.py 中添加 softmax_temperature 到参数空间
DEFAULT_SOFTMAX_TEMPERATURES = (0.5, 0.75, 1.0, 1.5, 2.0, float("inf"))  # inf = 等权
```

**验收标准**：
- 最优温度下 sw2021 月胜率 **> 35%**（当前 29%）
- sw2021 Sharpe ≥ 0.58
- 跨段 WF OOS Sharpe 中位数 > 0.55
- 月胜率在 sw2014 也有改善

**`StrategyConfig` 新增字段**：
```python
@dataclass(frozen=True)
class StrategyConfig:
    # ... 现有字段 ...
    portfolio_mode: str = "equal"          # "equal" | "softmax" | "vol_parity"
    softmax_temperature: float = 1.0       # Softmax 温度
```

### B.3 波动率平价权重

替代方案：按行业波动率的倒数分配权重（风险平价），防止高波动行业（科技/新能源）
主导组合表现。

$$w_i = \frac{1/\sigma_i}{\sum_{j \in \text{top-}k} 1/\sigma_j} \cdot \text{exposure}$$

```python
def vol_parity_target(
    scores: dict[str, float],
    vol_data: dict[str, float],  # 各行业当前 vol20
    top_k: int,
    exposure: float,
    max_weight: float,
) -> dict[str, float]:
    """按波动率倒数分配权重，仍按得分选 top-k"""
    holdings = select_top_k(scores, top_k)
    if not holdings or exposure == 0:
        return {}
    inv_vols = {
        asset: 1.0 / max(vol_data.get(asset, 0.02), 0.001)
        for asset in holdings
    }
    total = sum(inv_vols.values())
    raw_weights = {asset: (v / total) * exposure for asset, v in inv_vols.items()}
    return _clamp_and_renormalize(raw_weights, max_weight, exposure)
```

### B.4 动态 top_k：信号强度自适应

当信号高度集中（少数行业得分明显高于其他）时使用 top_k=3；
当信号分散时使用 top_k=7，增加分散化。

```python
def adaptive_top_k(
    scores: dict[str, float],
    base_k: int = 5,
    concentration_threshold: float = 1.5,
) -> int:
    """
    根据前 base_k 名的评分集中度动态决定 top_k。
    当 top-1 分数 > top-k 均分 * threshold 时，认为信号集中，减小 k。
    """
    if not scores:
        return base_k
    ranked = sorted(scores.values(), reverse=True)
    if len(ranked) < base_k:
        return len(ranked)
    top_mean = sum(ranked[:base_k]) / base_k
    if top_mean > 0 and ranked[0] / top_mean > concentration_threshold:
        return max(3, base_k - 2)  # 信号集中：收缩到 3
    elif top_mean <= 0 or ranked[0] / max(top_mean, 0.01) < 0.8:
        return min(7, base_k + 2)  # 信号分散：扩展到 7
    return base_k
```

**注意**：adaptive_top_k 必须走前验证（在 WF 框架内选取集中度阈值），
不允许全样本最优化。

---

## 四、阶段 C：市场状态精细化（P1，预计 2 周）

### C.1 核心诊断：MA120 过于迟钝，假信号多

`risk_control_accuracy.csv` 显示（sw2021，2021–2026）：
- **假阳性（risk-off 但市场上涨）**：14 次，涉及 2024Q4 的 +23.2% 反弹被错误回避
- **假阴性**：相对较少

MA120 有 **6 个月滞后**——当市场已经确认反转时，策略还在执行 risk-off。
2022 年避险是成功的，但 2024 Q4 的 +23.2% 大涨被完全错过，代价极高。

### C.2 多信号市场状态机

用 3 个独立信号的共识替代单一 MA120：

```python
class MarketRegimeClassifier:
    """
    三信号共识法：每个信号投 1 票（+1=看多，0=中性，-1=看空）
    最终暴露 = f(consensus_score)
    """

    def classify(
        self,
        benchmark_closes: list[float],
        market_vol_closes: list[float],  # 市场日收益率（用于计算滚动波动率）
        signal_index: int,
    ) -> tuple[float, str]:
        votes = 0.0

        # 信号 1：双均线（MA20 > MA60）趋势信号（比 MA120 更灵敏）
        if signal_index >= 60:
            ma20 = mean(benchmark_closes[signal_index-19:signal_index+1])
            ma60 = mean(benchmark_closes[signal_index-59:signal_index+1])
            votes += 1.0 if ma20 > ma60 else -1.0

        # 信号 2：市场波动率状态（滚动 20 日波动率 vs 60 日均值）
        if signal_index >= 60:
            recent_vol = rolling_vol(market_vol_closes, signal_index, 20)
            hist_vol = rolling_vol(market_vol_closes, signal_index, 60)
            # 低波动 = 正常市场，高波动（>1.5倍历史）= 风险状态
            votes += 0.0 if recent_vol > 1.5 * hist_vol else 0.5

        # 信号 3：市场动量（现有 market_score）
        if market_score is not None:
            votes += 1.0 if market_score > 0.03 else (-1.0 if market_score < -0.03 else 0.0)

        # 根据得票决定状态
        if votes >= 1.5:
            return 1.0, "bull"
        elif votes >= 0.0:
            return 0.7, "sideways"
        else:
            return 0.1, "bear"  # 而非直接 0.0，保留小仓位防止踏空
```

**关键改动**：熊市 exposure 改为 **0.1** 而非 **0.0**。
全面清仓（0.0）虽然理想，但 2024 Q4 的完全踏空代价极高。
保持 10% 仓位可以捕捉突然反转的部分收益。

#### 实验 C2-EXP1：双均线 vs MA120 对比

```bash
# 测试 MA20>MA60 vs MA120 两种风控
python -m quant_rotation sweep --config configs/real_sw2021.toml \
    --market-ma-windows "120,60,20" \
    --dual-ma-test \
    --output-dir reports/exp_dual_ma
```

**验收标准**：假阳性率（risk-off 但市场实际上涨）< 30%（当前约 50%）

### C.3 状态感知因子权重

不同市场状态下使用不同的因子权重组合：

```python
REGIME_FACTOR_WEIGHTS = {
    "bull": FactorWeights(
        rel_ret60=1.0,      # 强趋势市：动量权重最高
        rel_ret20=0.3,
        ret5=-0.3,
        vol20=-0.1,
        prosperity=0.2,
    ),
    "sideways": FactorWeights(
        rel_ret60=0.5,
        rel_ret20=0.2,
        consistency60=0.3,  # 震荡市：质量因子更重要
        ret5=-0.4,
        vol20=-0.3,
        prosperity=0.3,
    ),
    "bear": FactorWeights(
        vol20=-0.6,         # 熊市：防御，最小化波动
        rel_ret60=0.2,
        ret5=-0.2,
        prosperity=0.2,
    ),
}
```

**实现方式**：在 `backtest.py` 的 `run_backtest` 中，根据分类结果选择对应的
`FactorWeights` 传入 `compute_factor_snapshot`。

**`StrategyConfig` 新增**：
```python
regime_aware_factors: bool = False         # 是否启用状态感知因子
bull_factor_weights: FactorWeights = ...   # 牛市因子权重
sideways_factor_weights: FactorWeights = ... 
bear_factor_weights: FactorWeights = ...
```

---

## 五、阶段 D：股票层 Alpha 激活（P1，预计 2 周）

### D.1 现有基础设施

`stock_selection.py`、`StockSelectionConfig`、`backtest.py::run_backtest` 中的股票模式
均已完整实现。当前未启用的原因是**缺少实盘个股数据**（`stock_close.csv`、
`stock_industry_map.csv`）。

这是第二个 Alpha 层：行业选择后，在每个选中行业中进一步选优质股票。
基于大量 A 股量化研究，在行业内部做股票精选**可额外贡献 Sharpe +0.2~0.4**。

### D.2 个股数据接入

**数据需求**：
- `stock_close.csv`：行业成分股日收盘（对应 sw2021 的成分股）
- `stock_industry_map.csv`：股票→行业映射
- `stock_amount.csv`（可选）：个股成交额

**数据来源**：AKShare `stock_zh_a_hist` + `index_stock_cons`（当前成分股）

**新增 CLI 子命令**（`real_data.py` + `cli.py`）：
```bash
python -m quant_rotation fetch-stock-data \
    --output data/real_sw2021 \
    --universe sw2021 \
    --start 2021-12-13 \
    --end 2026-06-03 \
    --request-interval 0.5
```

### D.3 股票评分因子增强

当前 `StockSelectionConfig` 只有动量+波动率因子。增加**质量因子**，
防止选中基本面差但短期动量高的股票：

```python
@dataclass(frozen=True)
class StockSelectionConfig:
    # 现有字段（保持兼容）
    ret20: float = 0.45
    ret60: float = 0.25
    amount_strength: float = 0.10
    vol20: float = -0.20
    ret5: float = -0.10
    # 新增字段
    rel_ret60: float = 0.00    # 股票相对行业超额动量（新增）
    consistency20: float = 0.00 # 近 20 日上涨一致性（新增）
```

`compute_stock_scores` 中的 `rel_ret60` 计算：
```python
# stock_selection.py 中计算行业内股票的相对动量
# ind_ret60 = 该股所在行业的 ret60（作为参考基准）
industry_ret60 = {
    ind: mean_return(stock_data, group, index, 60)
    for ind, group in grouped.items()
}
for stock in candidates:
    industry = stock_industry_map[stock]
    rel_ret60[stock] = ret60[stock] - industry_ret60.get(industry, 0.0)
```

### D.4 实验 D4-EXP1：股票层消融测试

在样本数据（`data/sample/`）上先验证，样本数据已有 `stock_close.csv` 和
`stock_industry_map.csv`：

```bash
python -m quant_rotation run \
    --config configs/default.toml \
    --stock-selection \
    --output-dir reports/exp_stock_selection_sample
```

**验收标准**：
- 样本数据上 Sharpe 提升 ≥ +0.10 vs 纯行业版
- 换手率增加不超过 50%（控制交易成本）
- 月胜率提升 ≥ +3pp

---

## 六、阶段 E：备选数据因子研究（P2，预计 3 周）

### E.1 北向资金行业流向

北向资金（沪深港通北向）是机构资金对 A 股行业的增量定价信号，
与价格动量有互补性：在机构开始加仓某行业时，往往领先于价格动量形成。

**数据来源**：AKShare `stock_connect_hist_sina`（北向持股历史）

**新因子 `northbound_flow`**：过去 20 日北向净买入/该行业总市值，
标准化后作为景气度的替代或补充。

**实现路径**：
```python
# real_data.py 新增
def fetch_northbound_flow_by_industry(
    start: date, end: date,
    industry_map: dict[str, str],
) -> PriceData:
    """
    获取北向资金分行业净买入（按行业成分股聚合），
    归一化为该行业市值的比例，输出为 PriceData 格式。
    """
```

**注意**：北向数据仅从 2014 年开始（沪股通开通），无法用于 sw2000 段验证。
需在 sw2014 + sw2021 两段独立验证。

### E.2 行业估值百分位

当某行业 PE 处于历史低位（百分位 < 20%）时，作为**价值修复信号**与动量信号结合。
这引入"动量 × 低估值"的复合信号，类似全球成熟市场中常见的 value-momentum 因子。

**数据来源**：AKShare 行业 PE 或个股 PE 聚合  
**计算**：`valuation_percentile = rank(ind_PE, last 252 days) / 252`（越低越便宜）

已在 `factors.py` 中有 `valuation` 字段支持（`valuation_score_input = -value`），
只需接入数据即可。

**经济学逻辑**：超卖行业恢复动量时，往往涨幅更大、持续更长（mean-reversion + momentum 共振）。

### E.3 行业盈利修正因子

分析师盈利预测修正（EPS revision）是行业基本面动量的领先指标。
当某行业分析师预测被频繁上调时，往往领先股价 1–3 个月。

**数据来源**：需要 Wind/Bloomberg 数据（AKShare 暂无）  
**优先级**：P3，数据获取难度较高，排在后面。

---

## 七、验证框架与防过拟合协议

### 7.1 三层验证体系

每个新因子/改动必须依次通过三层验证，**全部通过才采纳**：

**Layer 1（快速筛选，1 天内）**：sw2021 单段消融测试
- 目的：排除明显无效的因子，不是最终验收标准
- 通过标准：sw2021 Sharpe ≥ 0.50，年化 ≥ 5%

**Layer 2（核心验证，2 天内）**：sw2014 OOS WF（11 折，2014–2021）
- 目的：验证因子在更早时期的泛化能力——这是核心筛选
- 通过标准：OOS Sharpe 中位数 **> 0.15**（当前为 0）
- **如果 Layer 2 失败，无论 Layer 1 多好都不采纳**

**Layer 3（最终验证，3 天内）**：27 折跨段 WF + Bootstrap CI
- 目的：全周期稳健性确认
- 通过标准：
  - OOS Sharpe 中位数 > 0.65（最终目标路径上）
  - Bootstrap p_positive ≥ 96%
  - 盈利折数 ≥ 17/27（63%）

### 7.2 因子独立性验证

在采纳新因子之前，必须证明它与现有因子不高度相关：

```python
def factor_correlation_check(
    factor_snapshots: list[dict[str, float]],
    new_factor: str,
    existing_factors: list[str],
    correlation_threshold: float = 0.7,
) -> bool:
    """
    检查新因子与现有因子的横截面相关性。
    如果与任何现有因子的平均绝对相关 > 0.7，警告可能冗余。
    """
    for existing in existing_factors:
        corr = cross_sectional_correlation(factor_snapshots, new_factor, existing)
        if abs(corr) > correlation_threshold:
            print(f"Warning: {new_factor} 与 {existing} 相关性 = {corr:.2f}")
            return False
    return True
```

### 7.3 排列检验（Permutation Test）

对每个新因子，通过随机打乱行业标签验证因子的统计显著性：

```python
def permutation_test_factor(
    data: PriceData,
    factor_weights: FactorWeights,
    config: StrategyConfig,
    n_permutations: int = 1000,
    seed: int = 42,
) -> dict:
    """
    打乱行业标签后运行 n_permutations 次回测，
    计算真实 Sharpe 在置换分布中的百分位。
    p 值 < 0.05 才认为因子显著。
    """
```

**集成到 CLI**：
```bash
python -m quant_rotation permutation-test \
    --config configs/exp_rel_momentum.toml \
    --n-permutations 1000 \
    --output-dir reports/permutation_test
```

### 7.4 交易成本敏感性测试

每个采纳的配置必须在 **2 倍和 3 倍交易成本**下仍保持正 Sharpe：

```python
COST_MULTIPLIERS = [1.0, 2.0, 3.0]
# 在 sweep.py 中添加 cost_multiplier 参数
```

**验收标准**：3 倍交易成本下 Sharpe ≥ 0.50（当前 1 倍下 Sharpe = 0.52，
意味着当前策略几乎没有成本缓冲）

### 7.5 子期间一致性检验

将每个测试段分成 4 个子期间，计算各子期间的年化收益：
- 至少 **3/4 子期间** 为正收益才算通过
- 这防止策略只在特定年份（如 2025 牛市）有效

---

## 八、代码架构变更清单

### 8.1 `factors.py` 变更

```
新增函数：
  + trend_consistency(values, index, lookback) -> float
  + period_return(values, index, start_lag, end_lag) -> float
  
修改函数：
  ~ compute_factor_snapshot: 新增 rel_ret60, rel_ret20, 
    momentum_accel, consistency60 计算
  ~ 参数新增：market_data: PriceData | None（传入市场指数用于计算相对动量）

注意：不破坏现有接口，所有新参数有默认值 None/0.0
```

### 8.2 `models.py` 变更

```
修改：
  ~ FactorWeights: 新增 rel_ret60=0.0, rel_ret20=0.0, 
                       momentum_accel=0.0, consistency60=0.0
  ~ StrategyConfig: 新增 portfolio_mode="equal", 
                        softmax_temperature=1.0,
                        regime_aware_factors=False,
                        bull/sideways/bear_factor_weights
  ~ StockSelectionConfig: 新增 rel_ret60=0.0, consistency20=0.0
```

### 8.3 `portfolio.py` 变更

```
新增函数：
  + softmax_weight_target(scores, top_k, exposure, max_weight, temperature)
  + vol_parity_target(scores, vol_data, top_k, exposure, max_weight)
  + adaptive_top_k(scores, base_k, concentration_threshold) -> int
  + _clamp_and_renormalize(weights, max_weight, exposure)

修改函数：
  ~ equal_weight_target: 保持不变（向后兼容）
```

### 8.4 `backtest.py` 变更

```
修改函数：
  ~ run_backtest: 
    - 新增 market_data 传递给 compute_factor_snapshot
    - 根据 portfolio_mode 调用不同组合构建函数
    - 根据 regime_aware_factors 动态选择因子权重
    
新增函数：
  + _select_portfolio_weights(scores, config, vol_snapshot) -> dict[str, float]
    封装 equal/softmax/vol_parity 三种模式的调用
```

### 8.5 `config.py` 变更

```
修改：
  ~ load_config: 新增 portfolio_mode, softmax_temperature, 
                     regime_aware_factors 的 TOML 解析
```

### 8.6 `sweep.py` 变更

```
新增常量：
  + DEFAULT_SOFTMAX_TEMPERATURES = (0.5, 0.75, 1.0, 1.5, 2.0)
  + FACTOR_SETS_WITH_RELATIVE_MOMENTUM = (...)
  
修改函数：
  ~ build_parameter_sweep_specs: 新增 portfolio_mode 和 temperature 维度
```

### 8.7 `real_data.py` 变更

```
新增函数：
  + fetch_stock_data(output_dir, universe, start, end, ...)
  + compute_industry_amount_zscore(amount_data, window) -> PriceData
  + compute_northbound_flow_by_industry(...) -> PriceData [P2]
  
CLI 新增子命令：
  + fetch-stock-data
```

### 8.8 新增文件

```
src/quant_rotation/regime.py   [新文件]
  - MarketRegimeClassifier
  - classify_regime(benchmark_closes, vol_series, market_score) -> tuple[float, str]
  
tests/test_portfolio.py        [新文件或扩展]
  - test_softmax_weight_target_sums_to_exposure
  - test_softmax_temperature_extremes
  - test_vol_parity_weights_inverse_vol
  - test_adaptive_top_k_concentration
  
tests/test_factors_new.py      [新文件]
  - test_trend_consistency_all_up
  - test_trend_consistency_all_down
  - test_period_return_basic
  - test_market_excess_return_removes_beta
```

---

## 九、配置文件设计

### 9.1 强 Alpha 候选配置（待实验验证后定版）

```toml
# configs/strong_alpha_candidate.toml
[data]
industry_close = "../data/real_sw2021/industry_close.csv"
industry_amount = "../data/real_sw2021/industry_amount.csv"
industry_prosperity = "../data/real_sw2021/industry_prosperity.csv"
market_close = "../data/real_sw2021/market_close.csv"
benchmark_close = "../data/real_sw2021/benchmark_close.csv"

[strategy]
rebalance_every = 20
top_k = 5
max_industry_weight = 0.35      # 允许最高仓位提升（softmax 下头部更集中）
transaction_cost = 0.001
risk_control = true
market_ma_window = 60           # 改为 MA60（比 MA120 更灵敏）
market_score_control = true
market_score_window = 60
market_score_threshold = 0.0
risk_off_exposure = 0.10        # 改为 10%（而非 0%，防止踏空）
portfolio_mode = "softmax"      # 使用 softmax 加权
softmax_temperature = 1.0       # 待实验确定最优值
regime_aware_factors = false    # 先不启用，待 C 阶段验证

[factors]
ret60_weight = 0.00             # 绝对动量降至 0
rel_ret60_weight = 1.00         # 相对动量作为主因子
rel_ret20_weight = 0.00         # 待 A 阶段实验决定
consistency60_weight = 0.00     # 待 A 阶段实验决定
ret5_weight = -0.50             # 保留短期反转惩罚
vol20_weight = 0.00             # 暂不用（已有 vol_parity 时可关）
prosperity_weight = 0.20        # 激活景气度因子

[reports]
output_dir = "../reports/strong_alpha_candidate"

[market_weights]
CSI300 = 0.50
CSIAll = 0.30
ChiNext = 0.20
```

### 9.2 实验系列配置命名规范

```
exp_A1_rel_ret60.toml          # 相对动量实验
exp_A2_consistency.toml        # 一致性因子实验
exp_A3_prosperity.toml         # 景气度激活实验
exp_B1_softmax_t10.toml        # softmax temp=1.0
exp_B2_vol_parity.toml         # 波动率平价
exp_C1_dual_ma.toml            # 双均线风控
exp_AB_combined.toml           # A+B 联合
exp_ABC_combined.toml          # A+B+C 联合（最终候选）
```

---

## 十、优先级矩阵与执行计划

### 10.1 优先级总览

| 优先级 | 阶段 | 任务 | 预期 Sharpe 贡献 | 实现难度 | 依赖 |
|--------|------|------|-----------------|---------|------|
| 🔴 P0 | A.2 | `rel_ret60` 相对动量因子 | **+0.15~0.25** | 中 | 无 |
| 🔴 P0 | B.2 | Softmax 得分加权 | **+0.10~0.20** | 低 | 无 |
| 🔴 P0 | A.4 | 激活 `prosperity_weight` | **+0.05~0.10** | **极低** | 无（数据已有）|
| 🟠 P1 | A.3 | `consistency60` 一致性因子 | +0.05~0.10 | 低 | A.2 |
| 🟠 P1 | B.3 | 波动率平价权重 | +0.03~0.08 | 低 | B.2 |
| 🟠 P1 | B.4 | 动态 `top_k` | +0.02~0.05 | 低 | 无 |
| 🟠 P1 | C.2 | 双均线风控替代 MA120 | +0.03~0.08 | 中 | 无 |
| 🟡 P2 | A.5 | 动量加速度因子 | +0.03~0.07 | 中 | A.2 |
| 🟡 P2 | C.3 | 状态感知因子权重 | +0.05~0.10 | 高 | A.2, C.2 |
| 🟡 P2 | D.2 | 个股数据接入 + 股票层 Alpha | **+0.20~0.40** | 高（数据） | 数据获取 |
| 🟢 P3 | E.1 | 北向资金行业流向因子 | +0.05~0.10 | 高（数据）| D.2 数据基础 |
| 🟢 P3 | E.2 | 行业估值百分位 | +0.03~0.08 | 高（数据）| 无 |

### 10.2 执行顺序（最小阻塞路径）

#### 第一周：A+B 改造（无新数据依赖）

```
Day 1-2：实现 rel_ret60
  - 修改 factors.py + models.py + config.py
  - 写测试 test_factors_new.py::test_market_excess_return_removes_beta
  - 在 sw2021 快速验证（Layer 1）

Day 3：激活 prosperity（最低成本改进）
  - configs/real_sw2021.toml 中设 prosperity_weight = 0.20
  - 运行 decompose 验证因子贡献

Day 4：实现 softmax 加权
  - 修改 portfolio.py（新增 softmax_weight_target）
  - 修改 backtest.py 支持 portfolio_mode 分支
  - 写测试 test_portfolio.py

Day 5：组合 exp_AB 扫描
  - 跑 rel_ret60 × softmax_temperature 二维扫描
  - Layer 1 筛选最优组合
```

#### 第二周：验证与因子完善

```
Day 6-7：Layer 2 验证（sw2014 OOS WF）
  - 对 Day 5 最优组合跑 sw2014 WF
  - 关注 OOS Sharpe 中位数是否 > 0.15
  - 如果通过：进入 Layer 3
  - 如果失败：回到 A.2，调整 rel_ret60 实现细节

Day 8：consistency60 因子
  - 实现 trend_consistency()
  - 加入扫描比较

Day 9-10：Layer 3 验证（27 折跨段 WF + Bootstrap）
  - 对通过 Layer 2 的配置跑全量验证
  - 更新性能基线记录
```

#### 第三周：风控与扩展

```
Day 11-12：C.2 双均线风控实验
Day 13-14：vol_parity + adaptive_top_k 测试
Day 15：综合 A+B+C 联合配置验证
```

#### 第四周起：股票层 Alpha

```
Week 4：个股数据获取（AKShare）
Week 5：stock_selection 激活与调参
Week 6：股票层 + 行业层联合验证
```

---

## 十一、成功里程碑与验收标准

### Milestone 1（第 1 周末）：因子替换初步验证

**通过条件**：
- `rel_ret60` 在 sw2021 Sharpe ≥ 0.57
- `softmax(T=1.0)` + `rel_ret60` 在 sw2021 月胜率 ≥ 33%（vs 当前 29%）
- `prosperity_weight=0.20` 单独 ablation 贡献 Sharpe ≥ +0.03

### Milestone 2（第 2 周末）：sw2014 泛化性验证

**通过条件**（这是最重要的里程碑）：
- 最优 A+B 配置在 sw2014 OOS Sharpe **中位数 > 0.20**（vs 当前 0.00）
- sw2014 OOS 最大回撤绝对值 < 35%（vs 当前 -54.8%）
- sw2000 段（2010–2014）年化收益 > 0%（vs 当前 -5.2%）

如果无法通过 Milestone 2，说明因子设计有根本问题，需要回到 A.2 重新思考。

### Milestone 3（第 3 周末）：强 Alpha 初始验证

**通过条件**：
- 27 折跨段 WF OOS Sharpe 中位数 **> 0.70**（vs 当前 0.484）
- Bootstrap p_positive > 96%
- 盈利折数 ≥ 18/27（66%）

### Milestone 4（第 6 周末）：股票层 Alpha 验证

**通过条件**：
- 行业 + 股票双层策略 vs 纯行业策略 Sharpe 提升 ≥ +0.15
- 换手率增加 < 60%（控制成本）

### 最终目标（第 8–10 周）：强 Alpha 定版

**通过条件**：
- OOS Sharpe 中位数 **> 0.90**
- OOS 年化收益中位数 **> 18%**
- 月胜率（全段）**> 52%**
- Bootstrap p_positive **> 97%**

---

## 十二、风险与注意事项

### 风险 1：相对动量因子在数据质量差的早期段可能不稳定

`market_close.csv` 在 sw2000 段（2010–2014）可能有数据缺口。
`compute_factor_snapshot` 需要优雅处理 `market_data = None` 的情况：
退化到绝对动量，而非报错。

### 风险 2：Softmax 加权 + 集中持仓组合可能导致个别极端月份

当评分最高的行业权重超过 40% 时（高温参数下），单一行业崩溃可能造成重大单月损失。
**缓解措施**：`max_industry_weight = 0.35` 保持上限；禁用 temperature < 0.5。

### 风险 3：多因子组合的过拟合风险

每增加一个因子，参数空间增大，过拟合风险增加。
**缓解措施**：
- 每次只测试一个因子的独立贡献（ablation）
- 新因子必须有先验经济学解释（不允许"我试了 100 个，这个最好"）
- 因子数量上限：不超过 6 个非零权重因子

### 风险 4：prosperity 数据质量

`industry_prosperity.csv` 中的数据来源和质量未在代码注释中明确说明。
在激活前需要检查：
```python
# 验证景气度数据分布
import pandas as pd
df = pd.read_csv("data/real_sw2021/industry_prosperity.csv", index_col=0)
print(df.describe())          # 检查值域和分布
print(df.isnull().sum())      # 检查缺失值
print(df.diff().abs().max())  # 检查是否有异常跳跃
```
如果景气度数据实际上是滞后发布的（存在前视偏差），则不能使用。

### 风险 5：rel_ret60 在 market_data 缺失段的处理

部分历史段（如 sw2000）`market_close.csv` 可能不完整（manifest 中 `market_close: null`）。
需要在 `factors.py` 中确保 `market_data = None` 时 `rel_ret60` 完全退化为 0，
而不影响其他因子的计算。

---

## 十三、当前性能基线（参照记录，用于后续对比）

| 指标 | sw2021 单段 | sw2014 OOS WF | 跨段 27 折 WF |
|------|-------------|---------------|---------------|
| 年化收益 | 6.51% | 中位数 0.0% | 中位数 8.52% |
| 最大回撤 | -17.26% | 中位数 -8.4% | 中位数 -13.25% |
| Sharpe | 0.525 | 中位数 0.00 | 中位数 0.484 |
| 月胜率 | 29.1% | — | 56.5% |
| Calmar | 0.377 | — | — |
| Bootstrap p_positive | — | — | 95.02% |
| WF 盈利折数 | — | 7/11（64%）| 16/27（59%）|

**关键问题总结**：
- sw2014 OOS Sharpe 中位数 = 0（策略在 2014–2021 不具泛化性）
- sw2000（2010–2014）年化 = -5.2%（历史最早段亏损）
- 月胜率 29%（典型 Beta 暴露特征，非 Alpha）

**执行本计划的核心目标**：先让 sw2014 OOS Sharpe 中位数从 0 提升到 0.20+，
这是策略从"Beta 管理"升级为"真正 Alpha"的最重要跨越。