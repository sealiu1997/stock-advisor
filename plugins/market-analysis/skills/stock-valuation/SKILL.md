---
name: stock-valuation
description: >
  对上市公司进行内在价值评估，综合使用 DCF（现金流折现）、相对估值（同业比较）
  和 SOTP（分部估值，如适用）三种方法，三角交叉验证得出隐含股价和上行/下行空间。
  当用户询问"AAPL值多少钱"、"NVDA的估值"、"TSLA的公允价值"、"内在价值"、
  "DCF分析"、"现金流折现"、"WACC"、"终值"、"是否高估/低估"、"目标价"、
  "相对估值"、"同业比较"、"EV/EBITDA"、"P/E"、"这只股票贵不贵"、
  "帮我估一下值"、"fair value"、"intrinsic value"、"valuation"、
  "overvalued"、"undervalued"、"price target"、"给我做个估值"，
  或在讨论任何股票时涉及估值问题，使用此技能。
  默认运行全部适用方法（DCF + 相对 + SOTP），输出混合隐含价格和敏感性分析。
  不要凭记忆回答估值问题 — 永远执行完整工作流。
---

# Stock Valuation — 个股估值分析

通过三种方法交叉验证公司内在价值，输出混合隐含股价：

1. **DCF** — 5 年 FCFF 预测，WACC 折现，终值计算
2. **相对估值** — 同业中位数 P/E、EV/Revenue、EV/EBITDA
3. **SOTP** — 多业务分部分别估值（仅适用于多元化公司）

始终输出 WACC × 终端增长率敏感性矩阵 + Bull/Base/Bear 情景分析。

**声明：仅供研究和教育目的，不构成投资建议。**

---

## Step 1: 环境检测

```
!`python3 -c "import yfinance, numpy, pandas; print('READY')" 2>/dev/null || echo "DEPS_MISSING"`
```

```
!`python3 -c "import yfinance as yf; t=yf.Ticker('^TNX'); p=t.fast_info.last_price; print(f'RF_10Y={p/100:.4f}')" 2>/dev/null || echo "RF_FETCH_FAIL"`
```

如果 `DEPS_MISSING`：
```python
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "yfinance", "numpy", "pandas"])
```

如果 `RF_FETCH_FAIL`：使用默认无风险利率 `rf = 0.045`，并在输出中标注。
如果 `RF_10Y=` 打印出值：使用该值作为无风险利率。

---

## Step 2: 选择估值方法与设定参数

### 方法适用性判断

根据公司类型选择合适的估值方法组合：

| 公司类型 | DCF | 相对估值 | SOTP | 备注 |
|---|---|---|---|---|
| 成熟现金流型 (消费、电信、公用) | 主力 | 辅助 | 否 | 标准 DCF 最佳 |
| 高成长 SaaS / 软件 | 谨慎使用 | 主力 | 否 | 侧重 EV/Revenue + Rule of 40 |
| 多元化集团 | 是 | 是 | 主力 | 参见 `references/sotp.md` |
| 银行/保险 | 否 | 是 (P/B, P/TBV) | 否 | 用 DDM 替代，输出中说明 |
| 未盈利/亏损公司 | 否 | 仅 EV/Revenue | 否 | 标注低置信度 |
| REITs | 否 | 是 (P/FFO) | 否 | 以 NAV 为主 |
| 周期性 (能源/半导体/工业) | 中周期归一化 | 是 | 视情况 | 用穿越周期的平均值 |
| 港股 | 同上规则 | 选A+H或港股同业 | 视情况 | 注意港股折价因素 |

### 默认参数表

所有参数在进入 Step 3 前必须有确定值。用户未指定则用以下默认值：

| 参数 | 默认值 | 说明 |
|---|---|---|
| 预测期 | 5 年 | 标准显式预测窗口 |
| 终端增长率 `g` | 2.5% | 约等于美国长期名义 GDP |
| 无风险利率 `rf` | Step 1 实时值，否则 4.5% | 当前资金成本锚 |
| 股权风险溢价 `erp` | 5.5% | Damodaran 中间值 |
| Beta | yfinance `info['beta']` | 市场观测的含杠杆 beta |
| 债务成本 `kd` | 利息支出 / 总债务，否则 5.5% | 实际利率；回退到投资级利差 |
| 税率 | 3 年中位有效税率，下限 15%，上限 30% | 剔除一次性项目 |
| 利润率假设 | 3 年中位数 | 平滑周期噪音 |
| SBC 处理 | 软件/SaaS 视为现金支出；工业/消费视为非现金 | 行业惯例 |
| 同业数量 | 4-6 家 | 平衡信号与噪音 |
| 同业倍数 | 中位数 (非均值) | 抗异常值 |
| 方法权重 (无 SOTP) | DCF 50% / 相对 50% | 等权交叉 |
| 方法权重 (有 SOTP) | DCF 40% / 相对 30% / SOTP 30% | SOTP 适用时加权 |
| 敏感性网格 | WACC ±1% (0.5%步长) × g 1.5%-3.5% (0.5%步长) | 5×5 矩阵 |

详细参数参考 `references/wacc_erp_rates.md`。

---

## Step 3: 抓取财务数据

```python
import yfinance as yf
import numpy as np
import pandas as pd

TICKER = "AAPL"  # 替换为实际标的
t = yf.Ticker(TICKER)

info       = t.info
income_a   = t.income_stmt          # 年度利润表
cashflow_a = t.cashflow             # 年度现金流量表
balance_a  = t.balance_sheet        # 年度资产负债表
income_q   = t.quarterly_income_stmt
cashflow_q = t.quarterly_cashflow

earnings_est = t.earnings_estimate  # 分析师 EPS 预测
revenue_est  = t.revenue_estimate   # 分析师营收预测

price      = info.get("currentPrice") or info.get("regularMarketPrice")
market_cap = info.get("marketCap")
shares_out = info.get("sharesOutstanding")
total_debt = info.get("totalDebt") or 0
cash       = info.get("totalCash") or 0
beta       = info.get("beta") or 1.0
sector     = info.get("sector")
industry   = info.get("industry")
```

**关键财务报表行 (yfinance 标签)：**

| 需要 | 行名 |
|---|---|
| 营收 | `Total Revenue` |
| 营业利润 | `Operating Income` |
| 净利润 | `Net Income` |
| 折旧摊销 | `Depreciation And Amortization` (现金流表) |
| 资本支出 | `Capital Expenditure` (负数) |
| 营运资本变动 | `Change In Working Capital` (现金流表) |
| 股权激励 | `Stock Based Compensation` (现金流表) |

**港股特殊处理：**
- symbol 格式：`1810.HK`、`0700.HK`
- 财务数据以港币计价，需注意汇率
- 部分港股公司 yfinance 数据不完整，对于数据缺失情况在输出中标注

---

## Step 4: DCF 构建

详细方法论参见 `references/dcf.md`。核心骨架：

### 4a. 营收增长路径

```python
# 历史 CAGR
rev = income_a.loc["Total Revenue"].dropna().sort_index()
hist_cagr = (float(rev.iloc[-1]) / float(rev.iloc[0])) ** (1 / (len(rev)-1)) - 1

# 分析师共识（如果可用）
y1_growth = hist_cagr  # 默认
if revenue_est is not None and "+1y" in revenue_est.index:
    y1_growth = float(revenue_est.loc["+1y", "growth"])

g_terminal = 0.025
growth_path = np.linspace(y1_growth, g_terminal + 0.01, 5)  # 线性衰减
```

### 4b. 利润率假设 — 3 年中位数

```python
ebit_margin = float((income_a.loc["Operating Income"] / income_a.loc["Total Revenue"]).iloc[:3].median())
da_pct      = float((cashflow_a.loc["Depreciation And Amortization"] / income_a.loc["Total Revenue"]).iloc[:3].median())
capex_pct   = float((cashflow_a.loc["Capital Expenditure"].abs() / income_a.loc["Total Revenue"]).iloc[:3].median())
nwc_pct     = float((cashflow_a.loc["Change In Working Capital"].abs() / income_a.loc["Total Revenue"]).iloc[:3].median())

# 有效税率
tax_rate = max(0.15, min(0.30, float((income_a.loc["Tax Provision"] / income_a.loc["Pretax Income"]).iloc[:3].median())))
```

### 4c. 5 年 FCFF 投影

```python
rev_t = [float(income_a.loc["Total Revenue"].iloc[0])]
fcff  = []
for g in growth_path:
    rev_t.append(rev_t[-1] * (1 + g))
    ebit = rev_t[-1] * ebit_margin
    nopat = ebit * (1 - tax_rate)
    fcff.append(nopat + rev_t[-1]*da_pct - rev_t[-1]*capex_pct - rev_t[-1]*nwc_pct)
```

### 4d. WACC 计算

```python
rf = 0.045     # 或 Step 1 实时值
erp = 0.055
kd = 0.055     # 或 interest_expense / total_debt

ke = rf + beta * erp                                  # CAPM
e_v = market_cap / (market_cap + total_debt)           # 股权权重
d_v = 1 - e_v                                          # 债务权重
wacc = e_v * ke + d_v * kd * (1 - tax_rate)
```

### 4e. 终值 — 两种方法取均值

```python
tv_gordon = fcff[-1] * (1 + g_terminal) / (wacc - g_terminal)
tv_exit   = (rev_t[-1] * ebit_margin + rev_t[-1] * da_pct) * 15  # 同业中位数 EV/EBITDA
tv_base   = 0.5 * (tv_gordon + tv_exit)
```

### 4f. 企业价值桥接至股权价值

```python
pv_fcff = sum(f / (1 + wacc)**(i+1) for i, f in enumerate(fcff))
pv_tv   = tv_base / (1 + wacc)**5
ev      = pv_fcff + pv_tv
equity  = ev + cash - total_debt
implied_price_dcf = equity / shares_out
```

### 安全检查

| 条件 | 处理 |
|---|---|
| `wacc <= g_terminal` | 停止，终端增长率过高，上限设为 `wacc - 0.5%` |
| `pv_tv / ev > 0.85` 或 `< 0.45` | 标记警告，展示两种终值方法 |
| WACC 超出行业正常范围 | 标记并说明（参见 `references/wacc_erp_rates.md`） |

---

## Step 5: 相对估值

### 5a. 选择同业

根据 GICS 行业分类选择 4-6 家同业公司。同业选择规则和现成同业列表参见 `references/relative_valuation.md`。

**选择标准优先级：**
1. 同一 GICS 行业（必须）
2. 类似商业模式（必须）
3. 类似增长率（±10 个百分点）
4. 类似利润率水平
5. 类似资本结构

### 5b. 抓取同业倍数

```python
PEERS = ["MSFT", "ORCL", "CRM", "NOW", "SAP"]  # 根据行业选择
multiples = {}
for p in PEERS:
    pi = yf.Ticker(p).info
    multiples[p] = {
        "name": pi.get("shortName"),
        "market_cap": pi.get("marketCap"),
        "pe_fwd": pi.get("forwardPE"),
        "ev_rev": pi.get("enterpriseToRevenue"),
        "ev_ebitda": pi.get("enterpriseToEbitda"),
        "rev_growth": pi.get("revenueGrowth"),
        "gross_margin": pi.get("grossMargins"),
        "ebitda_margin": pi.get("ebitdaMargins"),
    }

med_pe     = np.nanmedian([v["pe_fwd"] for v in multiples.values()])
med_ev_rev = np.nanmedian([v["ev_rev"] for v in multiples.values()])
med_ev_eb  = np.nanmedian([v["ev_ebitda"] for v in multiples.values()])
```

### 5c. 计算隐含价格

```python
# TTM 数据
eps_ttm    = float(income_q.loc["Diluted EPS"].iloc[:4].sum())
rev_ttm    = float(income_q.loc["Total Revenue"].iloc[:4].sum())
ebitda_ttm = float(income_q.loc["EBIT"].iloc[:4].sum()) + \
             float(cashflow_q.loc["Depreciation And Amortization"].iloc[:4].sum())
net_debt   = total_debt - cash

implied_pe      = med_pe * eps_ttm
implied_ev_rev  = (med_ev_rev * rev_ttm - net_debt) / shares_out
implied_ev_ebit = (med_ev_eb * ebitda_ttm - net_debt) / shares_out
implied_price_rel = np.nanmedian([implied_pe, implied_ev_rev, implied_ev_ebit])
```

### 5d. 调整

如果目标公司的增长率/利润率与同业中位数偏差较大（>5 个百分点），对隐含倍数进行 ±10%-30% 调整。始终说明调整幅度和原因。

SaaS 公司补充 Rule of 40 分析（详见 `references/relative_valuation.md`）。

---

## Step 6: SOTP 分部估值（仅多元化公司）

跳过此步，除非 10-K 报告了 2 个以上具有不同经济特征的经营分部。

完整方法论参见 `references/sotp.md`：
1. 识别各分部 + 各分部的纯业务同业
2. 对每个分部应用同业中位数 EV/EBITDA（或成长分部用 EV/Revenue）
3. 扣除未分配的公司级成本（不明确时取营收的 2-5%）
4. 扣除净债务、少数股东权益、优先股；加回现金
5. 除以稀释后流通股数

集团折价 = (SOTP 价格 − 市场价格) / SOTP 价格。如 >20% 则标注为显著集团折价。

**yfinance 不提供分部数据**，如用户未提供分部信息则跳过 SOTP，在输出中说明。

---

## Step 7: 综合、敏感性与情景分析

### 7a. 混合隐含价格

```python
if sotp_price is not None:
    blended = 0.4 * implied_price_dcf + 0.3 * implied_price_rel + 0.3 * sotp_price
else:
    blended = 0.5 * implied_price_dcf + 0.5 * implied_price_rel
```

### 7b. 敏感性矩阵 (5×5)

```python
wacc_grid = [wacc + dx for dx in (-0.01, -0.005, 0, 0.005, 0.01)]
g_grid    = [0.015, 0.020, 0.025, 0.030, 0.035]
sens = {}
for w in wacc_grid:
    for g in g_grid:
        if w <= g:
            sens[(w,g)] = "N/A"
            continue
        tv = fcff[-1] * (1 + g) / (w - g)
        pv = sum(f / (1+w)**(i+1) for i, f in enumerate(fcff)) + tv / (1+w)**5
        sens[(w,g)] = (pv + cash - total_debt) / shares_out
```

输出为 Markdown 表格，高亮 base case 所在单元格。

### 7c. Bull / Base / Bear 情景

| 情景 | 营收增长 | EBIT 利润率 | WACC | 终端 g |
|------|---------|-----------|------|--------|
| Bull | Base + 3% | Base + 2% | Base - 1% | 3.0% |
| Base | 共识/历史 | 3年中位 | 计算值 | 2.5% |
| Bear | Base - 3% | Base - 2% | Base + 1% | 1.5% |

分别计算三个情景的隐含价格。

---

## Step 8: 输出报告

按以下顺序组织输出：

### 1. 标题判定

一句话结论：混合公允价值 vs 当前价格，上行/下行空间百分比，最乐观/最悲观的方法。

示例："**AAPL 公允价值 ≈ $215（混合）**，当前 $198 → 约 9% 上行空间；DCF 最乐观 ($228)。"

### 2. 公司概况

公司名、行业、市值、当前价格、3M/12M 涨跌幅、TTM 营收增长率。

### 3. 三方法汇总表

| 方法 | 隐含价格 | 权重 | 简要逻辑 |
|------|---------|------|---------|
| DCF | $228 | 50% | 5年FCFF折现，WACC 9.2% |
| 相对估值 | $202 | 50% | 同业中位数 P/E 28x |
| **混合** | **$215** | | |

### 4. DCF 详情

- 假设表（增长路径、利润率、WACC 各分项、终值方法）
- 5 年 FCFF 投影表
- 企业价值桥接（EV → + 现金 − 债务 = 股权价值）

### 5. 同业比较表

| 同业 | 市值 | 营收增长 | 毛利率 | EBITDA利润率 | P/E(fwd) | EV/Rev | EV/EBITDA |
|------|------|---------|--------|-------------|---------|--------|----------|

最后一行为中位数，标注目标公司相对同业的溢价/折价。

### 6. SOTP（如适用）

分部表 + 调整 + 股权价值。

### 7. 敏感性矩阵

WACC × g 的 5×5 表格，base case 加粗。

### 8. 情景分析

| 情景 | 隐含价格 | vs 当前价 | 关键假设差异 |
|------|---------|---------|------------|

### 9. 关键风险

3-5 条：哪个假设对结果影响最大、什么可能推翻估值逻辑。

### 错误处理

| 缺失/边界情况 | 处理 |
|---|---|
| yfinance beta 返回 None | 使用行业默认 beta (`references/wacc_erp_rates.md`) |
| TTM EBITDA 为负 | 跳过 EV/EBITDA，依赖 EV/Revenue + DCF |
| TTM EPS 为负 | 跳过 P/E，使用远期 P/E 或跳过 |
| 增长率 > WACC（Gordon 公式无效） | 上限设为 `g = wacc − 0.5%`，标记 |
| 历史数据不足 3 年 | 用可用数据，标注置信度为"低" |
| 同业数据获取失败 | 剔除该同业，标注 |
| 无分部数据 | 跳过 SOTP，仅用 DCF + 相对 |

### 必须附带的免责声明
- TTM 数据有滞后；同业倍数反映市场情绪（可能过度乐观/悲观）
- DCF 是假设驱动的，敏感性比点估计更重要
- yfinance 数据非官方，重大决策请以 SEC/港交所原始文件为准
- 非投资建议

---

## Reference Files

- `references/dcf.md` — DCF 完整方法论 + 行业特定指南（软件/零售/金融/医疗/能源/制造/消费/电信/REITs/流媒体）
- `references/relative_valuation.md` — 同业选择规则、倍数调整方法、Rule of 40、按主题分类的同业列表
- `references/sotp.md` — 分部估值方法论、集团折价检测、催化剂识别
- `references/wacc_erp_rates.md` — 无风险利率、股权风险溢价、行业 WACC 基准、行业默认 Beta
