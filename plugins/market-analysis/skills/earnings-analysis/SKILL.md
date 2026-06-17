---
name: earnings-analysis
description: >
  对上市公司进行财报前瞻分析和财报后复盘。
  财报前（Preview）：汇总分析师预期、历史 beat/miss 记录、关键关注指标、股价隐含预期。
  财报后（Recap）：实际 vs 预期对比、财务趋势分析、股价反应、管理层指引解读。
  当用户询问"AAPL财报前瞻"、"GOOG下周发财报"、"NVDA财报怎么样"、
  "特斯拉会beat吗"、"分析师怎么看"、"EPS预期"、"营收预期"、
  "earnings preview"、"earnings recap"、"财报分析"、"业绩怎么样"、
  "上季度表现"、"beat还是miss"、"earnings surprise"、"盈利预警"、
  "guidance"、"管理层指引"、"前瞻指引"，
  或在讨论任何公司时涉及财报/业绩话题，使用此技能。
  自动判断：如果财报尚未发布→执行前瞻模式；如果已发布→执行复盘模式。
---

# Earnings Analysis — 财报分析

综合财报前瞻 (Preview) 和财报后复盘 (Recap) 功能，提供完整的财报周期分析。

**声明：仅供研究和教育目的，不构成投资建议。**

---

## Step 1: 环境检测

```
!`python3 -c "import yfinance; print('READY')" 2>/dev/null || echo "YFINANCE_MISSING"`
```

如果 `YFINANCE_MISSING`：
```python
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "yfinance"])
```

---

## Step 2: 抓取数据并判定模式

提取用户指定的股票代码（如提及公司名需查找对应代码），一次性获取所有相关数据：

```python
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

TICKER = "AAPL"  # 替换为实际标的
t = yf.Ticker(TICKER)

# --- 核心数据 ---
info = t.info
calendar = t.calendar

# --- 预期数据 ---
earnings_est = t.earnings_estimate
revenue_est  = t.revenue_estimate

# --- 历史记录 ---
earnings_hist = t.earnings_history

# --- 分析师观点 ---
price_targets = t.analyst_price_targets
recommendations = t.recommendations

# --- 季度财务数据 ---
quarterly_income   = t.quarterly_income_stmt
quarterly_cashflow = t.quarterly_cashflow
quarterly_balance  = t.quarterly_balance_sheet

# --- 股价数据（用于反应分析） ---
hist_prices = t.history(period="3mo")

# --- 新闻 ---
news = t.news
```

### 自动模式判定

```python
# 判断财报是否已发布
now = datetime.now()
if earnings_hist is not None and len(earnings_hist) > 0:
    last_earnings_date = pd.to_datetime(earnings_hist.index[0])
    days_since = (now - last_earnings_date).days
    
    if calendar is not None:
        next_earnings = calendar.get("Earnings Date")
        # 如果下次财报日在未来 → 最近一次已发布 → 复盘模式
        # 如果距上次 <7 天 → 复盘模式
        # 否则 → 前瞻模式
    
    if days_since <= 7:
        mode = "RECAP"
    else:
        mode = "PREVIEW"
else:
    mode = "PREVIEW"  # 默认前瞻
```

如果用户明确要求"前瞻"或"复盘"，以用户指定为准。

---

## Step 3: 财报前瞻模式 (Preview)

当 `mode == "PREVIEW"` 时执行此步骤。

### Section 1: 公司信息与财报日期

```
## AAPL 财报前瞻 | Q2 FY2026

**公司**: Apple Inc.
**行业**: 科技 - 消费电子
**财报日期**: 2026-07-24 (盘后)
**当前股价**: $198.50
**市值**: $3.05T
**近1月涨跌**: +3.2%
```

从 `calendar` 获取财报日期，`info` 获取公司基本面。

### Section 2: 分析师共识预期

从 `earnings_estimate` 和 `revenue_estimate` 提取当季预期：

```
### 分析师共识预期 (当季)

| 指标 | 共识 | 最低 | 最高 | 分析师数 | 去年同期 | 同比增长 |
|------|------|------|------|---------|---------|---------|
| EPS | $1.42 | $1.35 | $1.50 | 28 | $1.26 | +12.7% |
| 营收 | $94.3B | $92.1B | $96.8B | 25 | $89.5B | +5.4% |
```

**预期分歧度分析：**
- 最高/最低估计差距 > 共识的 20% → 高度不确定，标注
- 分析师数少于 5 → 低覆盖，标注

同时展示下一季度和全年预期（如果 `earnings_estimate` 中有 `+1q`、`0y`、`+1y` 数据）。

### Section 3: 历史 Beat/Miss 记录

从 `earnings_history` 提取近 4-8 季的表现：

```
### 近4季 Beat/Miss 记录

| 季度 | EPS预期 | EPS实际 | 偏差 | Beat/Miss |
|------|---------|---------|------|-----------|
| Q1 2026 | $1.78 | $1.89 | +6.2% | ✅ Beat |
| Q4 2025 | $2.10 | $2.18 | +3.8% | ✅ Beat |
| Q3 2025 | $1.35 | $1.40 | +3.7% | ✅ Beat |
| Q2 2025 | $1.30 | $1.33 | +2.3% | ✅ Beat |

**总结**: AAPL 近 4 季全部 Beat，平均超预期 4.0%。
如果近期持续 Beat，市场可能已计入"whisper number"高于共识。
```

### Section 4: 分析师观点

```
### 分析师观点

**评级分布**:
| 强力买入 | 买入 | 持有 | 卖出 | 强力卖出 |
|---------|------|------|------|---------|
| 12 | 18 | 8 | 2 | 0 |

**目标价**:
| 最低 | 均值 | 中位数 | 最高 | 当前价 | 隐含空间 |
|------|------|--------|------|--------|---------|
| $165 | $215 | $210 | $260 | $198 | +8.6% |
```

### Section 5: 关键关注指标

**这部分需要 agent 基于公司和行业判断最重要的看点。** 思考框架：

| 公司类型 | 关注焦点 |
|---|---|
| 科技大盘 (AAPL/MSFT/GOOG) | AI 相关收入、云增长、利润率扩张 |
| SaaS | ARR/NRR、客户增长、Rule of 40 |
| 电商 (AMZN/PDD) | GMV、take rate、物流效率 |
| 半导体 (NVDA/AMD) | 数据中心收入、毛利率、指引 |
| 消费 (TSLA) | 交付量、ASP、利润率、新车型时间表 |
| 中概股 (BABA/PDD) | GMV、CMR、国际业务、回购进展 |
| 金融 (银行) | NII、拨备、贷款增长 |
| 港股科技 (腾讯/小米) | 游戏/广告收入分拆、IoT、国际化 |

基于近期季度财务数据 (`quarterly_income_stmt`)，识别 3-5 个关键趋势：
- 营收增速是加速还是减速？
- 利润率在扩张还是压缩？
- 哪些业务线变化最显著？

### Section 6: 前瞻总结

2-3 句话概括整体预期：
- 街头预期的倾向（乐观/保守/中性）
- 最大的上行/下行风险
- 用"市场预期"而非个人推荐的措辞

---

## Step 4: 财报复盘模式 (Recap)

当 `mode == "RECAP"` 时执行此步骤。

### Section 1: 标题结果

一句话概括关键数字：

```
## AAPL Q2 FY2026 财报复盘 | Beat EPS +3.7%, 营收 +5.4% YoY

**发布日期**: 2026-07-24 (盘后)
**EPS**: $1.40 实际 vs $1.35 预期 → Beat +3.7%
**营收**: $94.3B, 同比 +5.4%
**股价反应**: 盘后 +2.1%
```

### Section 2: 实际 vs 预期详情

```
### 业绩 vs 预期

| 指标 | 预期 | 实际 | 偏差 |
|------|------|------|------|
| EPS | $1.35 | $1.40 | +$0.05 (+3.7%) |
| 营收 | $94.3B | $95.1B | +$0.8B (+0.8%) |
```

### Section 3: 季度财务趋势

从 `quarterly_income_stmt` 提取近 4 季核心指标：

```
### 季度财务趋势

| 季度 | 营收 | YoY增长 | 毛利率 | 营业利润率 | EPS |
|------|------|---------|--------|-----------|-----|
| Q2 2026 | $95.1B | +5.4% | 46.2% | 30.1% | $1.40 |
| Q1 2026 | $119.6B | +4.2% | 46.5% | 33.5% | $1.89 |
| Q4 2025 | $89.5B | +2.1% | 45.9% | 29.8% | $1.33 |
| Q3 2025 | $85.8B | +4.9% | 46.0% | 29.2% | $1.26 |
```

**趋势分析：**
- 毛利率：计算 `GrossProfit / TotalRevenue`
- 营业利润率：计算 `OperatingIncome / TotalRevenue`
- 标注趋势方向（扩张/压缩/稳定）

### Section 4: 股价反应分析

```python
# 找到财报日期附近的价格
earnings_date = earnings_hist.index[0]
hist_around = t.history(
    start=pd.to_datetime(earnings_date) - timedelta(days=5),
    end=pd.to_datetime(earnings_date) + timedelta(days=5)
)

# 财报日前一天收盘 → 财报日后第一天收盘
pre_price = hist_around['Close'].iloc[0]
post_price = hist_around['Close'].iloc[-1]
reaction_pct = ((post_price - pre_price) / pre_price) * 100
```

```
### 股价反应

**财报日反应**: +2.1% (收盘 $198.50 → $202.67)
**历史平均财报日波动**: ±2.8% (基于近4季)
**当前位置**: 财报后第3天，较财报日收盘 +0.5% (涨幅维持)
```

分析：
- 反应幅度是否符合历史水平
- 涨幅/跌幅是否在后续交易日被消化或扩大
- 参考当天大盘表现（区分个股反应和市场 beta）

### Section 5: 关键变化与看点

基于财务数据变化，分析：
- 哪些业务线超预期/不及预期
- 利润率变化的驱动因素
- 现金流和资产负债表变化
- 如果有新闻 (`t.news`)，关联相关报道

### Section 6: 前瞻指引（如可获取）

yfinance 不直接提供管理层指引 (guidance)，但可以从以下来源推断：
- `earnings_estimate` 的 `+1q` 数据：下季度分析师预期（通常在财报后更新）
- 对比财报前后的预期变化：共识上调 → 指引乐观；下调 → 指引保守
- `recommendations` 变化：财报后是否有评级变动

```
### 前瞻指引信号

**下季度分析师预期** (财报后更新):
| 指标 | 预期 | vs 季度前预期 | 变化方向 |
|------|------|-------------|---------|
| EPS | $1.55 | $1.48 → $1.55 | ↑ 上调 4.7% |
| 营收 | $97.2B | $95.0B → $97.2B | ↑ 上调 2.3% |

**解读**: 分析师在财报后上调预期，暗示管理层给出了乐观指引。
```

### Section 7: 复盘总结

2-3 句话概括：
- 这是有意义的 beat 还是低基数情况？
- 财务趋势是在改善还是恶化？
- 市场反应是否合理
- 保持事实性陈述，避免投资建议

---

## Step 5: 批量模式（持仓财报季总览）

如果用户问"我的股票最近有哪些发了财报"或"财报季总结"：

1. 读取 `config/portfolio.json`
2. 对每只持仓股票检查 `earnings_history`，筛选最近 30 天内发布财报的
3. 输出汇总表：

```
### 持仓财报季总览 (近30天)

| 股票 | 日期 | EPS预期 | EPS实际 | 偏差 | 营收YoY | 股价反应 |
|------|------|---------|---------|------|---------|---------|
| GOOG | 07-22 | $1.85 | $1.93 | +4.3% | +12% | +5.2% |
| MSFT | 07-22 | $3.22 | $3.30 | +2.5% | +15% | +3.1% |
```

对于尚未发布的，标注预计日期和当前预期。

---

## Step 6: 输出格式要求

### 通用规则
1. 所有数据标注时效和来源（yfinance / Yahoo Finance）
2. 表格数字对齐，使用千分位分隔（$94.3B）
3. 百分比保留一位小数
4. Beat 用 ✅，Miss 用 ❌，符合预期用 ➖
5. 末尾附带免责声明

### 免责声明
- 预期数据可能在财报发布前变化
- 历史 beat 不保证未来表现
- Yahoo Finance 数据可能与实时共识有数小时延迟
- yfinance 不提供管理层指引原文，指引分析基于预期变化推断
- 非投资建议

---

## Reference Files

- `references/yfinance_earnings_api.md` — yfinance 财报相关 API 详细参考（方法签名、返回格式、边界情况处理）
