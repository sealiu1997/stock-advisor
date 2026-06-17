---
name: event-calendar
description: >
  经济事件日历：追踪美联储会议、CPI/非农/PMI/GDP 等关键宏观数据发布、
  以及持仓个股财报日期，提供事前预警和事后解读。当用户询问"近期有什么重要数据"、
  "美联储什么时候开会"、"FOMC"、"CPI什么时候出"、"我的股票什么时候发财报"、
  "本周经济日历"、"下周有什么大事"、"earnings calendar"、"economic calendar"、
  "利率决议"、"非农数据"、"就业数据"、"通胀数据"、"GDP什么时候出"时使用此技能。
  也用于定时场景：每日自动检测未来 48 小时内是否有关注事件，有则自动触发预警。
---

# Event Calendar — 经济事件日历与节点播报

追踪宏观经济数据发布、央行会议、个股财报等关键事件节点，提供事前预警分析和事后数据解读。

**声明：仅供研究和教育目的，不构成投资建议。**

---

## Step 1: 环境检测

```
!`python3 -c "import yfinance, pandas; print('READY')" 2>/dev/null || echo "DEPS_MISSING"`
```

如果 `DEPS_MISSING`：

```python
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "yfinance", "pandas"])
```

---

## Step 2: 确定查询范围

根据用户请求判断要查询的内容：

| 用户请求 | 查询范围 |
|---|---|
| "近期有什么重要数据" / "经济日历" / 定时检测 | 全部：宏观事件 + 财报日 |
| "美联储什么时候开会" / "FOMC" | 仅 FOMC 日程 |
| "CPI/非农/PMI 什么时候" | 仅特定宏观指标 |
| "我的股票什么时候发财报" | 仅持仓财报日 |
| 定时自动运行 | 未来 48h 内所有关注事件 |

**时间窗口默认值：**
- 手动查询：未来 14 天
- 定时检测：未来 48 小时
- 如果用户指定了"本周"、"下周"等范围，按用户指定

---

## Step 3: 查询宏观经济事件

### A. 读取事件配置

读取 `{baseDir}/../../config/events.json` 获取用户关注的宏观事件列表。

### B. 查询 FOMC 日程

读取 `references/fed_schedule.md` 获取本年度 FOMC 会议日程表。

检查时间窗口内是否有 FOMC 会议，如有则标记：
- 普通会议 (Regular)：仅利率决议和声明
- SEP 会议 (Summary of Economic Projections)：附带经济预测摘要和点阵图，重要性更高

### C. 查询宏观数据发布日

使用 yfinance 或静态日程数据来查询近期的宏观数据发布。

**方法 1（推荐）: 通过 yfinance 获取经济日历**

```python
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# yfinance 没有直接的经济日历 API
# 使用静态参考文件 + 规律性推算
```

**方法 2: 基于规律推算 + 静态维护**

多数美国宏观数据有固定发布规律：

| 指标 | 发布规律 | 发布时间 (美东) |
|---|---|---|
| CPI | 每月 10-15 日 | 08:30 |
| 非农就业 | 每月第一个周五 | 08:30 |
| ISM 制造业 PMI | 每月第一个工作日 | 10:00 |
| ISM 服务业 PMI | 每月第三个工作日 | 10:00 |
| GDP (初值/修正/终值) | 季度末月最后一周 | 08:30 |
| 初请失业金 | 每周四 | 08:30 |
| PCE 物价指数 | 每月最后一个工作日附近 | 08:30 |
| 零售销售 | 每月 13-16 日 | 08:30 |

具体日期参见 `references/economic_calendar.md`（按季度维护）。

### D. 输出日历视图

```
### 未来两周经济日历

| 日期 | 时间(北京) | 事件 | 重要性 | 前值 | 预期 |
|------|-----------|------|--------|------|------|
| 06-19 (四) | 20:30 | CPI (YoY) | ★★★ | 3.2% | 3.1% |
| 06-20 (五) | 20:30 | 初请失业金 | ★★ | 222K | 220K |
| 06-24 (二) | 02:00 | FOMC 利率决议 | ★★★★ | 5.25% | 5.25% |
...
```

---

## Step 4: 查询持仓个股财报日

读取 `{baseDir}/../../config/portfolio.json`，遍历所有持仓股票的财报日期：

```python
import yfinance as yf
from datetime import datetime, timedelta

# 读取持仓
with open("config/portfolio.json") as f:
    portfolio = json.load(f)

upcoming_earnings = []

for market in ["US", "HK"]:
    for stock in portfolio.get(market, []):
        symbol = stock["symbol"]
        # 港股需要补 .HK 后缀
        yf_symbol = f"{symbol}.HK" if market == "HK" else symbol
        try:
            t = yf.Ticker(yf_symbol)
            cal = t.calendar
            if cal is not None and not cal.empty:
                # calendar 可能返回 DataFrame 或 dict
                # 提取 Earnings Date
                earnings_date = cal.get("Earnings Date")
                if earnings_date:
                    upcoming_earnings.append({
                        "symbol": symbol,
                        "name": stock["name"],
                        "date": earnings_date,
                        "market": market
                    })
        except:
            continue
```

**同时抓取分析师预期：**

```python
t = yf.Ticker(symbol)
est = t.earnings_estimate    # 当季/下季 EPS 预期
rev = t.revenue_estimate     # 当季/下季 营收预期
hist = t.earnings_history    # 历史 EPS beat/miss 记录
```

**输出格式：**

```
### 持仓财报日历

| 股票 | 财报日期 | 距今 | EPS预期 | 营收预期 | 近4季beat率 |
|------|---------|------|---------|---------|------------|
| GOOG | 07-22 | 34天 | $1.85 | $86.3B | 4/4 ✅ |
| MSFT | 07-22 | 34天 | $3.22 | $64.5B | 4/4 ✅ |
| 小米 (1810.HK) | 08-19 | 62天 | - | - | - |
```

---

## Step 5: 事前预警分析

当检测到高重要性事件在预警时间窗口内（由 events.json 的 `alert_hours_before` 决定），生成详细的事前分析：

### A. 宏观数据预警

```
## ⚠️ 事件预警：CPI 数据将于明日发布

### 基本信息
- **事件**：美国 CPI (消费者物价指数) - 6月数据
- **发布时间**：2026-06-19 20:30 (北京时间)
- **重要性**：★★★ (高)

### 数据预期
| 指标 | 前值 | 市场预期 | 变动方向 |
|------|------|---------|---------|
| CPI YoY | 3.2% | 3.1% | ↓ 通胀降温 |
| CPI MoM | 0.2% | 0.2% | → 持平 |
| 核心 CPI YoY | 3.4% | 3.3% | ↓ 小幅下行 |

### 近6期趋势
| 月份 | CPI YoY | 核心CPI | vs预期 |
|------|---------|---------|--------|
| 1月 | 3.0% | 3.3% | 持平 |
| 2月 | 2.8% | 3.1% | 低于预期 ✅ |
...

### 情景分析
**场景 A: 低于预期 (CPI < 3.0%)**
- 降息预期升温 → 股市利好，债券利好
- 科技/成长股受益最大
- 黄金可能上涨，美元走弱

**场景 B: 符合预期 (CPI ≈ 3.1%)**
- 市场影响有限，维持当前节奏
- 关注核心 CPI 是否出现意外

**场景 C: 高于预期 (CPI > 3.2%)**
- 降息预期推迟 → 股市承压
- 利率敏感板块（科技、房地产）首当其冲
- 美元走强，黄金承压

### 对你持仓的潜在影响
```

（agent 应遍历用户持仓，分析哪些股票对 CPI 数据最敏感）

### B. FOMC 会议预警

```
## ⚠️ 事件预警：FOMC 利率决议即将公布

### 基本信息
- **会议日期**：2026-06-24 至 06-25
- **决议公布**：06-25 02:00 (北京时间)
- **鲍威尔记者会**：06-25 02:30 (北京时间)
- **类型**：SEP 会议 (附带经济预测和点阵图)

### 市场定价
```

（agent 应分析联邦基金期货隐含的利率预期，如果 yfinance 可获取）

### C. 财报预警

```
## ⚠️ 财报预警：谷歌 (GOOG) 将于后天发布财报

### 基本信息
- **公司**：Alphabet Inc. (GOOG)
- **财报日期**：2026-07-22 (盘后)
- **财报类型**：Q2 2026

### 分析师预期
| 指标 | Q2预期 | Q1实际 | QoQ变化 |
|------|--------|--------|---------|
| EPS | $1.85 | $1.89 | -2.1% |
| 营收 | $86.3B | $80.5B | +7.2% |

### 历史表现 (近4季)
| 季度 | EPS预期 | EPS实际 | Beat/Miss | 盘后反应 |
|------|---------|---------|-----------|---------|
| Q1 2026 | $1.78 | $1.89 | Beat +6.2% | +3.5% |
| Q4 2025 | $1.92 | $2.12 | Beat +10.4% | +5.1% |
...

### 关注要点
```

（agent 应分析该公司当前的关键看点：AI 业务增长、云收入、广告收入趋势等）

---

## Step 6: 事后解读（数据发布后）

当用户在数据发布后询问（如 "CPI 出来了怎么样"、"财报怎么样"），提供实际值 vs 预期值的对比分析：

### 输出结构

1. **实际值 vs 预期值** — 表格对比
2. **偏差程度** — 是否大幅超预期/不及预期
3. **市场即时反应** — 指数、相关板块、债券收益率变化
4. **对持仓影响** — 用户持仓中哪些受影响最大
5. **后续关注** — 这一数据对后续政策走向的含义

---

## Step 7: 定时自动检测模式

在定时运行场景中，执行以下自动检测流程：

```
1. 计算当前时间
2. 扫描 events.json 中所有宏观事件，检查未来 48h 内是否有匹配
3. 扫描持仓股票的财报日期，检查未来 N 天内（earnings_alert_days_before）是否有
4. 扫描 FOMC 日程，检查未来 48h 内是否有
5. 如果有任何命中 → 输出对应的事前预警
6. 如果无命中 → 输出简要日历展望（未来一周内的事件列表）
```

---

## Reference Files

- `references/fed_schedule.md` — 2026 年 FOMC 会议日程表
- `references/economic_calendar.md` — 本季度主要宏观数据发布日程
- `references/macro_data_guide.md` — 各宏观指标的含义、市场影响机制和历史数据参考
