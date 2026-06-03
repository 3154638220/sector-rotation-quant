# 行动计划：A 股行业动量轮动策略 下一步

> 基于对 `sector-rotation-quant-main` 全量代码、配置与报告的深度分析
> 分析日期：2026-06-02

---

## 零、执行进度更新（2026-06-02）

### 0.1 已完成

| 编号 | 事项 | 结果 |
|------|------|------|
| A1 | 新增生产配置 `configs/production.toml` | ✅ 已完成。配置为 `ret60 + ret5`、Top 5、`risk_off_exposure = 0.00`，报告输出到 `reports/production` |
| A2 | 更新 README 推荐命令流程 | ✅ 已完成。Quick Start 已改为真实数据优先，sample 数据作为 smoke test |
| A3 | 在 `configs/real.toml` 中关闭拖累因子 | ✅ 已完成。`ret20 / ret120 / amount_strength / breadth / vol20` 均显式置零，保留 `ret60_weight = 1.00` 与 `ret5_weight = -0.50` |
| B1 | 扩充历史数据至 2010 年 | ✅ 分段行业宇宙方案已落地。`fetch-real-data` 新增 `--industry-universe current/sw2021/sw2014/sw2000` 与 `--industry-indexes`；已生成 `data/real_sw2000`、`data/real_sw2014`、`data/real_sw2021` 三段官方指数宽表，覆盖 `2010-01-04` 至 `2026-06-02` |
| B2 | 增加多指数 `market_close.csv` | ✅ 已完成。`fetch-real-data` 默认写入 `CSI300`、`CSIAll`、`ChiNext` 三列宽表；`production.toml` / `real.toml` 已启用 0.5/0.3/0.2 市场权重 |
| B3 | 重校 `market_score_threshold` | ⚠️ 阶段性完成。新增 sweep/validate 阈值网格参数；当前 2021-2026 全样本中 `0.02` 年化 **8.48%**、最大回撤 **-17.26%**、Sharpe **0.68**，但月胜率仍 **29.1%**，需长历史复核后再改生产阈值 |
| B4 | 改进 walk-forward 候选选择指标 | ✅ 已完成。新增 `sharpe_plus_calmar` 选择指标，并降低 composite 中换手率惩罚 |
| C1 | 新增 `fetch-breadth-data` 子命令 | ✅ 阶段性完成。已实现当前申万成分股近似版宽度管道，输出 `industry_breadth20.csv` / `industry_breadth60.csv` 与 `breadth_manifest.json`；manifest 明确标注当前成分股幸存者偏差风险，等待历史成分快照接入后再进入生产 |
| D1 | 扩大参数扫描候选集 | ✅ 已完成。默认覆盖 `ret60`、`ret60_ret5`、`ret60_ret120`、`ret60_ret120_ret5`，`top_k=(3,5,8)`，`risk_off=(0.0,0.2,0.3,0.5)` |
| D2 | 增加基于持有期的性能分析 | ✅ 已完成。`write_reports` 现在输出 `holding_period_returns.csv`、`holding_period_return_distribution.csv`、`industry_selection_frequency.csv`、`risk_control_frequency.csv`，可直接诊断调仓周期收益、行业选择集中度与风控触发频率 |
| D3 | 添加分年度超额报告 | ✅ 已完成。`annual_returns.csv` 已包含 `benchmark_return`、`industry_equal_weight_return`、`excess_vs_benchmark`、`excess_vs_equal_weight` |
| E1/E3 | Phase 5 动态行业归属基础设施 | ✅ 阶段性完成。新增 `StockIndustryMap` 快照模型，`stock_industry_map.csv` 支持 `date` / `snapshot_date` / `as_of` 列；回测选股会按调仓信号日使用最近历史快照，静态 map 仍兼容 |
| E2 | Phase 5 股票数据管道 | ✅ 阶段性完成。新增 `fetch-stock-data` 子命令，基于当前申万成分股生成 `stock_close.csv`、可选 `stock_amount.csv`、`stock_industry_map.csv` 与 `stock_manifest.json`；manifest 标注当前成分股幸存者偏差，正式生产仍需历史快照 |

### 0.2 验证结果

| 验证项 | 命令 / 输出 | 结果 |
|------|-------------|------|
| 单元测试 | `python -m unittest discover -s tests` | ✅ 36 个测试全部通过 |
| 生产配置回测 | `python -m quant_rotation run --config configs/production.toml` | 年化收益 **6.51%**，最大回撤 **-17.26%**，Sharpe **0.52**，最终净值 **1.3079** |
| 修改后 `real.toml` 回测 | `python -m quant_rotation run --config configs/real.toml` | 年化收益 **4.90%**，最大回撤 **-22.78%**，Sharpe **0.38**；由于仍保留 `risk_off_exposure = 0.50`，弱于 production |
| 扩展候选 sweep | `python -m quant_rotation sweep --config configs/production.toml --industry-only` | ✅ 192 个候选跑通；最佳为 `ret60_ret5_top5_riskoff0_riskctrl1_mscore0` |
| walk-forward | `python -m quant_rotation validate --config configs/production.toml --industry-only --walk-forward --selection-metric sharpe_plus_calmar` | ✅ 4 折跑通；`walk_forward_summary.csv` 已输出测试 Sharpe 的 mean / median / std |
| 多指数数据管道 | `python -m quant_rotation fetch-real-data --output data/real --start 2021-12-13 --end 2026-06-02 --benchmark sh000300` | ✅ 写入 `data/real/market_close.csv`，共同日期 1074 行；列为 `CSI300`、`CSIAll`、`ChiNext` |
| 分段历史数据管道 | `fetch-real-data --industry-universe sw2000/sw2014/sw2021` | ✅ `sw2000`: 2010-01-04 至 2014-02-20，998 行、23 行业；`sw2014`: 2014-02-21 至 2021-12-10，1893 行、28 行业；`sw2021`: 2021-12-13 至 2026-06-02，1074 行、31 行业 |
| 分段固定候选 walk-forward | `validate --walk-forward --factor-set ret60_ret5 --top-k 5 --risk-off-exposure 0 --market-score-threshold 0` | ✅ `sw2000`: 3 折，测试年化均值 **4.17%**、平均回撤 **-7.73%**；`sw2014`: 11 折，测试年化均值 **4.73%**、平均回撤 **-8.98%**；`sw2021`: 4 折，测试年化均值 **21.91%**、平均回撤 **-8.01%** |
| 阈值扫描 | `python -m quant_rotation sweep --config configs/production.toml --industry-only --factor-set ret60_ret5 --top-k 5 --risk-off-exposure 0 --risk-control true --market-score-control true --market-score-threshold=-0.05,-0.02,0,0.02,0.05` | ⚠️ 全样本最佳 `threshold=0.02`，报告输出到 `reports/production/market_threshold_sweep`；walk-forward 固定候选中 `0.00` 与 `0.02` OOS 净值相同 |
| 报告增强 | `python -m unittest discover -s tests` + `python -m quant_rotation run --config configs/production.toml` | ✅ 24 个测试全部通过；生产报告新增 4 个 D2 诊断 CSV。当前生产策略 48 次调仓中 29 次空仓，`risk_off_rebalance_share = 60.4%` |
| 广度数据管道 | `python -m quant_rotation fetch-breadth-data --help` + `python -m unittest tests.test_real_data` | ✅ CLI 子命令可用；新增宽度计算、当前成分股抓取、CSV/manifest 落盘测试 |
| 动态行业归属 | `python -m unittest tests.test_stock_selection` + `python -m unittest discover -s tests` | ✅ 静态 map、带日期快照 map、按信号日切换股票行业归属均已覆盖；全量 33 个测试通过 |
| 股票数据管道 | `python -m quant_rotation fetch-stock-data --help` + `python -m unittest tests.test_real_data` | ✅ CLI 子命令可用；新增当前成分股股票 close/amount 抓取、`stock_industry_map.csv`、`stock_manifest.json` 落盘测试 |

### 0.3 当前阻塞与下一步

- **历史数据扩展的第一阶段已完成**：分段行业宇宙数据已经覆盖 2010 至今。下一步不是继续抓同一份 31 行业共同交集，而是做分段参数扫描、OOS 串接净值，以及必要时重建统一 2021 口径历史指数。
- **`market_score_threshold` 已完成阶段性扫描，但不宜仓促定版**：多指数加权市场分数下，全样本 `0.02` 优于 `0.0`，但 walk-forward 中两者 OOS 净值相同，且月胜率目标尚未达到。生产阈值暂保留 `0.0`，等待更长历史复核。
- **Phase 3 广度数据已有管道但仍未进入生产**：`fetch-breadth-data` 已能基于当前申万成分股生成宽度 CSV；`production.toml` 中 breadth 权重仍保持 `0.00`，等待历史成分快照或无偏数据源接入后再增量验证。
- **Phase 5 已具备当前成分股股票数据管道但仍非无偏生产数据**：`fetch-stock-data` 已能生成 `stock_close.csv` / `stock_amount.csv` / `stock_industry_map.csv`，回测端也支持按信号日读取历史行业归属快照；下一步需要把当前成分股近似版升级为历史成分快照版。

---

## 一、现状总结（项目已完成的工作）

### 1.1 已实现的阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| 阶段 1 | 价格动量（ret20 / ret60 / ret120） | ✅ 完整实现 |
| 阶段 2 | 成交额强度（amount_strength） | ✅ 代码完整，但**因子表现为负** |
| 阶段 3 | 行业内部广度（breadth20 / breadth60） | ⚠️ 数据管道阶段性完成，仍缺历史成分快照复核 |
| 阶段 4 | 市场环境过滤（MA120 + market_score） | ⚠️ 已实现，但 market_close 仅有基准单指数 |
| 阶段 5 | 行业内部选股 | ⚠️ 代码完整，实盘股票数据**缺失** |

### 1.2 当前最优候选策略

经参数扫描与 walk-forward 验证，全周期最优候选为 **`ret60_ret5_top5_riskoff0`**：

| 指标 | 数值 |
|------|------|
| 年化收益 | 6.51% |
| 最大回撤 | -17.26% |
| 夏普比率 | 0.525 |
| Calmar 比率 | 0.377 |
| 超额（vs 沪深300） | +35.3%（累计） |
| 超额（vs 等权） | +26.1%（累计） |
| 平均换手率 | 44.6% |
| 最大连续亏损月 | 2 个月 |

配置要点：60 日动量 + 5 日过热惩罚 + Top 5 行业等权 + **完全空仓风控**（risk_off_exposure = 0）。

对比 `all_factors` 全因子版本（年化仅 0.66%、最大回撤 -30.3%），该精简模型大幅胜出。

---

## 二、关键问题诊断

### 问题 1：因子有效性严重分化

通过 ablation 分析，因子的边际贡献如下：

| 因子 | 移除后 Δ 夏普 | 结论 |
|------|-------------|------|
| `ret60` | **-0.088**（最大负影响）| 核心因子，不可删除 |
| `ret5`（过热惩罚）| -0.048 | 重要，控制追高风险 |
| `ret20` | **+0.134**（移除反而更好） | **应当关闭** |
| `amount_strength` | +0.055（移除后提升）| **单独使用为亏损因子，应当关闭** |
| `vol20` | +0.098 | 边际有益但作用有限 |
| `ret120` | +0.002（几乎中性） | 可选保留，价值不大 |

**结论**：当前 `all_factors` 配置的 `ret20` 和 `amount_strength` 权重拖累了整体表现。已有 `real_ret60.toml` 和 `real_ret60_ret5_riskoff0.toml` 的简化配置方向是正确的。

### 问题 2：历史数据不足导致验证结论不稳定

- 实盘数据仅覆盖 **2021-12-13 至 2026-06-02**，约 **4 年**，1074 个交易日
- 这 4 年恰好覆盖了一轮完整的熊牛切换（2022-2024 熊市 + 2025-2026 牛市）
- Walk-forward 10 折（季度级）中，**6 个不同候选被选中**，比例均为 10-20%，说明无稳定优胜者
- 训练期（熊市主导）和测试期（牛市主导）存在显著 **时序不对称**，使得"训练最差的策略测试最好"的反常现象出现

### 问题 3：月胜率偏低

最优策略月胜率仅 **29%**，核心原因是激进的 `riskoff0` 设置——一旦市场条件不满足即全仓空仓，在震荡市中频繁触发，导致大量"0 收益月"被计为胜率损失。

### 问题 4：Phase 3/4/5 缺乏真实数据支撑

- 行业内部广度数据（breadth20/60）需要成分股收盘价逐日计算，`data/real/` 目录下不存在
- 多指数市场环境（沪深300 + 中证全指 + 创业板）已有 `market_close.csv`，但阈值仍未校准
- 股票选股需要全 A 股历史收盘价和行业归属图，量级大、难度高

---

## 三、行动计划

### 阶段 A：立即执行（1-2 周）

**A1：确定默认生产配置，提交干净的 `production.toml`**

当前最佳策略已明确为 `ret60_ret5_top5_riskoff0`，但配置仍散落在 `real_ret60_ret5_riskoff0.toml` 中。应：

```toml
# configs/production.toml
[data]
industry_close = "../data/real/industry_close.csv"
industry_amount = "../data/real/industry_amount.csv"
benchmark_close = "../data/real/benchmark_close.csv"

[strategy]
rebalance_every = 20
top_k = 5
max_industry_weight = 0.30
transaction_cost = 0.001
risk_control = true
market_ma_window = 120
market_score_control = true
market_score_window = 60
market_score_threshold = 0.0
risk_off_exposure = 0.00   # 完全空仓

[factors]
ret20_weight = 0.00        # 关闭 ret20（ablation 证明有害）
ret60_weight = 1.00        # 核心因子
ret120_weight = 0.00       # 关闭（贡献不稳定）
amount_strength_weight = 0.00  # 关闭（单独使用亏损）
vol20_weight = 0.00
ret5_weight = -0.50        # 保留过热惩罚

[reports]
output_dir = "../reports/production"
```

**A2：更新 README 中的推荐命令流程**

将默认演示命令从 `configs/default.toml`（sample 数据）更新为真实数据流程，明确标注各步骤的输出文件位置。

**A3：在 `configs/real.toml` 中关闭 `ret20` 和 `amount_strength`**

对现有 `real.toml` 执行一次重跑，验证修改后的 `all_factors` 配置是否向 `production.toml` 靠拢。

---

### 阶段 B：短期优化（2-4 周）

**B1：扩充历史数据至 2010 年**

这是最高优先级的数据工作。新的结论是：问题不是申万官方日线完全缺 2010 历史，而是**固定 2021 版 31 个一级行业取共同日期**会被新行业代码截断。

2026-06-03 已用本地 AKShare 1.18.64 复跑 2010 起始抓取，命令成功写入 `data/real_extended`，但申万 2021 版 31 行业共同日期仍被截断在 `2021-12-13` 至 `2026-06-02`。

```python
# 已执行
python -m quant_rotation fetch-real-data \
  --output data/real_extended \
  --start 2010-01-04 \
  --end 2026-06-03 \
  --benchmark sh000300
```

实际结果：
- `industry_close.csv` / `industry_amount.csv` / `benchmark_close.csv` / `market_close.csv` 均已写入 `data/real_extended`
- manifest 显示有效区间仍为 `2021-12-13` 至 `2026-06-02`，共 1074 行、31 个行业
- 本地 AKShare 无旧文档中的 `sw_index_daily`；`index_analysis_daily_sw` 当前对一级行业日线不能无痛替代

进一步探测申万官方 `index_publish/trend` 后确认：

| 行业宇宙 | 代码数 | 共同日期 | 说明 |
|---------|-------:|----------|------|
| 2000/旧版一级行业 | 23 | `1999-12-30` 至 `2014-02-20` | 可覆盖 2010-2014，但行业数与后续版本不同 |
| 申万 2014 版一级行业 | 28 | `2014-02-21` 至 `2021-12-10` | 可覆盖 2014-2021，含 `801020` 采掘等旧代码 |
| 申万 2021 版一级行业 | 31 | `2021-12-13` 至 `2026-06-02` | 当前生产口径，含 `801960/801970/801980` 等新行业 |

可执行路线：
- **优先路线：分段行业宇宙回测**。分别生成 2010-2014、2014-2021、2021-至今三段官方指数宽表，回测时在分类切换日清仓/重开仓并串接净值；这是最快拿到 2010 起长历史验证的方法。
- **稳健路线：分段验证，不强行串接**。先在三段各自行业宇宙上跑 `sweep` / `walk-forward`，观察 `ret60_ret5` 是否跨分类版本稳定有效，再决定是否实现串接回测。
- **统一口径路线：重建 2021 版历史指数**。用历史成分股、复权股价、市值/流通市值权重近似重建 31 个 2021 版行业到 2010；口径统一，但工程量大，并且需要严格标注“非官方重构指数”和幸存者/权重误差。
- **外部数据源路线**。Tushare Pro `sw_daily`、BigQuant `cn_stock_industry_sw_bar1d` 等能直接提供申万行业日行情字段，但仍需确认分类版本与起始日期；它们可以作为官方/AKShare数据的交叉校验或商业数据源替代。

已实现：
1. `fetch-real-data` 新增 `--industry-universe current/sw2021/sw2014/sw2000`，并新增 `--industry-indexes NAME:CODE,...` 用于显式覆盖行业列表。
2. 已输出 `data/real_sw2000`、`data/real_sw2014`、`data/real_sw2021` 三套宽表和 manifest；manifest 会记录 `industry_universe` 与行业代码映射。
3. 已新增 `configs/real_sw2000.toml`、`configs/real_sw2014.toml`、`configs/real_sw2021.toml`，可直接运行三段回测。
4. 已完成固定生产候选 `ret60_ret5_top5_riskoff0` 的分段 walk-forward 验证。

已执行命令：

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

阶段性结果：

| 段落 | 数据区间 | 行业数 | 普通回测年化 | 普通回测最大回撤 | 固定候选 WF 测试年化均值 |
|------|----------|-------:|-------------:|-----------------:|--------------------------:|
| `sw2000` | `2010-01-04` 至 `2014-02-20` | 23 | **-5.22%** | **-27.09%** | **4.17%** |
| `sw2014` | `2014-02-21` 至 `2021-12-10` | 28 | **10.28%** | **-54.83%** | **4.73%** |
| `sw2021` | `2021-12-13` 至 `2026-06-02` | 31 | **6.51%** | **-17.26%** | **21.91%** |

目标效果：
- walk-forward 的 train/test 折数从 4-10 折增加到 30+ 折
- 覆盖 2010-2015 慢牛、2015-2016 极端行情、2018-2019 大熊市、2020-2021 科技行情等多种市场环境
- 让 Calmar、Sharpe、月胜率等指标更可靠

**B2：增加多指数市场环境数据**

新增 `data/real/market_close.csv`，写入：

| 指数 | AKShare 代码 |
|------|------------|
| 沪深300 | sh000300 |
| 中证全指 | sh000985 |
| 创业板指 | sz399006 |

配置中启用 `market_score_control = true` 的多指数加权（0.5/0.3/0.2），使市场判断更全面，避免单一指数的误判。

**B3：重新校准 `market_score_threshold`**

当前阈值为 0.0（市场得分 > 0 即满仓），过于激进。建议：
- 在扩充数据集上对 threshold 做网格搜索：`[-0.05, -0.02, 0.0, 0.02, 0.05]`
- 目标：在保持超额收益的同时，将月胜率从 29% 提升到 40% 以上

**B4：改进 walk-forward 候选选择指标**

当前 composite metric 在训练期末段呈现"训练最差 → 测试最优"的异常现象。建议：

1. 在 `validation.py` 中增加 `sharpe_plus_calmar` 备选指标（不包含 turnover 惩罚项）
2. 将 `LOWER_IS_BETTER_METRICS` 中的 `average_turnover` 惩罚系数降低，避免过度惩罚高换手低回撤策略
3. 在 `walk_forward_summary.csv` 中增加一列：各折的测试 Sharpe 分布（mean + std），用于评估选择稳定性

---

### 阶段 C：Phase 3 广度数据实现（4-6 周）

当前 Phase 3（行业内部广度）的代码框架已完整，数据生成管道已完成当前成分股近似版。剩余关键问题是接入历史成分快照，消除幸存者偏差。

**C1：新增 `fetch-breadth-data` 子命令**

已在 `cli.py` 和 `real_data.py` 中增加：

```powershell
python -m quant_rotation fetch-breadth-data `
  --output data/real `
  --start 2021-12-13 `
  --end 2026-06-02 `
  --windows 20,60 `
  --request-interval 0.2
```

输出：
- `industry_breadth20.csv`
- `industry_breadth60.csv`
- `breadth_manifest.json`

注意事项：
- 当前实现使用 AKShare `index_component_sw` 当前成分股，`breadth_manifest.json` 已明确标注幸存者偏差风险。
- 正式生产前仍应优先接入历史成分快照，或使用其他稳定数据源提供的日期级行业归属。

**C2：启用广度因子并做增量测试**

在 `production.toml` 中解注释：

```toml
industry_breadth20 = "../data/real/industry_breadth20.csv"
industry_breadth60 = "../data/real/industry_breadth60.csv"

[factors]
breadth20_weight = 0.15
breadth60_weight = 0.10
```

然后重新运行 `decompose` 和 `sweep`，确认广度因子的边际贡献为正再正式纳入。

---

### 阶段 D：验证增强（与 B/C 并行）

**D1：扩大参数扫描候选集**

当前扫描仅覆盖 `ret60` 和 `ret60_ret5` 两个因子组合，可扩展：

```python
# sweep.py 建议扩展
DEFAULT_FACTOR_SET_NAMES = (
    "ret60",
    "ret60_ret5",
    "ret60_ret120",
    "ret60_ret120_ret5",
    "ret60_breadth20",        # Phase 3 后新增
    "ret60_ret5_breadth20",   # Phase 3 后新增
)
DEFAULT_TOP_K_VALUES = (3, 5, 8)       # 增加 top_k=3 的候选
DEFAULT_RISK_OFF_EXPOSURES = (0.0, 0.2, 0.3, 0.5)  # 细化 risk_off 格点
```

**D2：增加基于持有期的性能分析（已完成）**

`reports.py` 已在每次 `run` 时自动输出以下诊断文件：

- `holding_period_returns.csv`：逐调仓周期收益、相对沪深300超额、相对行业等权超额、暴露、换手、风控状态
- `holding_period_return_distribution.csv`：持有期收益分箱，可直接作为 bar chart 数据
- `industry_selection_frequency.csv`：行业入选次数、入选占比、风险开启/关闭状态下的入选次数、平均入选权重
- `risk_control_frequency.csv`：risk_off 调仓占比、risk_off 月份占比、趋势过滤失败占比、market_score 失败占比、风险开启/关闭时的平均暴露

当前 `configs/production.toml` 回测结果显示，48 次调仓中 29 次为空仓风控，`risk_off_rebalance_share = 60.4%`，这为“月胜率偏低”提供了更直接的诊断证据。

**D3：添加相对等权基准的分年度超额图**

当前 `annual_returns.csv` 只报告策略绝对收益，建议增加：
- 相对沪深300 的分年度超额
- 相对行业等权的分年度超额

以便直观判断哪些年份策略失效。

---

### 阶段 E：Phase 5 个股选择准备（6-10 周）

Phase 5 的实现较为复杂，需要以下数据基础设施：

**E1：构建历史股票行业归属图（基础设施已完成，数据管道待接入）**

申万行业成分股会随时间变更，需要按年度快照构建 `stock_industry_map_YYYYMMDD.csv`，并在回测中按日期动态加载，而非使用单一静态文件。

当前已在 `models.py` 中新增：

```python
@dataclass
class StockIndustryMap:
    snapshots: dict[date, dict[str, str]]  # date -> {stock: industry}
    
    def get_map_at(self, dt: date) -> dict[str, str]:
        # 返回 dt 当日或之前最新的成分股映射
```

`data.load_stock_industry_map_csv()` 现在支持两种格式：
- 静态格式：`stock,industry`
- 快照格式：`snapshot_date,stock,industry`（也兼容 `date` / `as_of`）

**E2：获取 A 股历史数据（当前成分股近似版已完成，历史快照版待接入）**

需要约 5000 只股票 × 10 年的日线数据，体量较大（约 500MB CSV）。建议：

- 优先获取申万行业内的成分股，而非全 A
- 使用 AKShare `stock_zh_a_hist` 接口，按行业分批下载
- 存储格式：宽表 CSV（与现有 `industry_close.csv` 格式一致）

当前已新增：

```powershell
python -m quant_rotation fetch-stock-data `
  --output data/real `
  --start 2021-12-13 `
  --end 2026-06-03 `
  --adjust qfq `
  --max-stocks-per-industry 5 `
  --request-interval 0.2
```

输出：
- `stock_close.csv`
- `stock_amount.csv`（当 AKShare 返回成交额或成交量字段）
- `stock_industry_map.csv`
- `stock_manifest.json`

注意：当前命令仍使用 AKShare `index_component_sw` 的当前成分股，属于研究近似版。正式进入 Phase 5 生产验证前，需要把 `stock_industry_map.csv` 切换为历史成分快照或日期级行业归属。

**E3：修改 `stock_selection.py` 以支持动态成分股（已完成）**

`stocks_by_industry()` 和 `stock_target_weights()` 已接受 `StockIndustryMap` 对象；`run_backtest()` 在每个调仓日传入因子 `signal_date`，选股时使用该日期之前最新的行业归属快照。静态 `dict[str, str]` 和旧版 sample CSV 仍保持兼容。

---

### 阶段 F：基本面 / 估值因子（10-16 周）

这是计划中"第四阶段加宏观/估值"的完整实现。

**F1：行业 PE/PB 历史分位数**

从 AKShare 获取申万行业 PE（TTM）和 PB（LF）历史数据，计算**行业自身 3 年历史分位数**：

```python
pe_percentile_i = 当前 PE 在过去 756 交易日（3年）中的分位数
```

分位数低 = 估值便宜。作为**乘数过滤项**（而非加法打分项），例如：
- 分位数 < 20%：score × 1.2（低估值加分）
- 分位数 > 80%：score × 0.8（高估值减分）

**F2：景气度代理因子**

在无法获取 PMI/社融数据的情况下，可用行业价量综合表现作为景气度代理：

```text
prosperity_i = 0.5 * 行业近期成交额增速 + 0.5 * 行业内盈利修正方向
```

或使用更简单的：行业指数过去 20 日创新高天数占比。

---

## 四、优先级总览

| 优先级 | 任务 | 当前进度 | 预期收益 |
|--------|------|----------|----------|
| 🔴 P0 | **提交 production.toml**（关闭 ret20/amount_strength）| ✅ 已完成 | 立即改善全因子配置性能 |
| 🔴 P0 | **扩充历史数据至 2010 年**（阶段 B1）| 🔎 已定位为行业分类版本问题；下一步实现分段行业宇宙数据与验证 | 解决验证不稳定的根本问题 |
| 🟠 P1 | 多指数 market_close.csv（阶段 B2）| ✅ 已完成 | 改善市场环境判断准确性 |
| 🟠 P1 | 重校 market_score_threshold（阶段 B3）| ⚠️ 阶段性完成，需长历史复核 | 提升月胜率 |
| 🟠 P1 | 扩大参数扫描候选集（阶段 D1）| ✅ 已完成 | 更全面的候选覆盖 |
| 🟡 P2 | 广度数据管道 fetch-breadth-data（阶段 C1）| ✅ 阶段性完成：当前成分股近似版已实现，待历史快照复核 | 验证 Phase 3 有效性 |
| 🟡 P2 | 改进 walk-forward 选择指标（阶段 B4）| ✅ 已完成 | 降低验证噪声 |
| 🟡 P2 | 持有期 / 行业频率 / 风控频率报告（阶段 D2）| ✅ 已完成 | 解释调仓收益分布、行业拥挤度与风控触发来源 |
| 🟡 P2 | 分年度超额等详细报告（阶段 D3）| ✅ 已完成 | 更清晰的策略诊断 |
| 🟢 P3 | Phase 5 个股选择基础设施（阶段 E）| ✅ 阶段性完成：动态行业归属、按信号日选股、当前成分股股票数据管道已接入；历史成分快照版待建 | 从行业到股票的完整策略 |
| 🟢 P3 | 估值/景气度因子（阶段 F）| ⏳ 未开始 | 在当前动量框架上叠加 |

---

## 五、当前核心结论

1. **策略框架已经可用**：`ret60_ret5_top5_riskoff0` 在 2021-2026 的数据上有明显的超额收益，累计跑赢沪深300 超 35%。

2. **但验证结论尚不稳定**：4 年历史太短，10 折 walk-forward 中没有稳定优胜者。需要通过扩充历史数据来解决。

3. **精简比复杂更好**：`all_factors` 全因子版本被精简的 `ret60 + ret5` 显著击败，说明在当前数据量级下因子越多越容易过拟合。应坚持"少即是多"。

4. **风控机制有效**：`riskoff0`（完全空仓）比 `riskoff0.5`（半仓）在回撤控制上更优，代价是月胜率低。这是一个权衡，后续可通过更精准的阈值来平衡。

5. **下一个里程碑应该是**：在扩充至 2010 年的数据集上，重新运行完整的参数扫描和 walk-forward，确认 `ret60_ret5` 是否在多个市场周期下持续有效。若确认，则该策略可进入"模拟实盘验证"阶段。
