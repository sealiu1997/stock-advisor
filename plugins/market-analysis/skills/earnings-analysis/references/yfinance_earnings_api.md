# yfinance 财报相关 API 参考

## 核心方法

### ticker.calendar

返回即将到来的公司事件（财报日、除息日等）。

```python
t = yf.Ticker("AAPL")
cal = t.calendar
# 可能返回 DataFrame 或 dict，取决于 yfinance 版本
# 关键字段: "Earnings Date", "Ex-Dividend Date", "Dividend Date"
```

**注意：** 部分公司（尤其港股）可能不返回 calendar 数据。返回 None 时跳过。

### ticker.earnings_estimate

当季和下季的 EPS 分析师预期。

```python
est = t.earnings_estimate
# DataFrame, index = ["0q", "+1q", "0y", "+1y"]
# 列: avg, low, high, yearAgoEps, numberOfAnalysts, growth
```

| 行 | 含义 |
|---|---|
| `0q` | 当季预期 |
| `+1q` | 下季预期 |
| `0y` | 当年预期 |
| `+1y` | 明年预期 |

**常见问题：**
- 某些行可能缺失（如年度预期）
- `growth` 字段可能为 NaN
- 财报后数据更新有延迟（通常 24-48 小时）

### ticker.revenue_estimate

当季和下季的营收分析师预期。

```python
rev = t.revenue_estimate
# 结构同 earnings_estimate
# 列: avg, low, high, numberOfAnalysts, yearAgoRevenue, growth
```

### ticker.earnings_history

历史 EPS 实际值 vs 预期值。

```python
hist = t.earnings_history
# DataFrame, index = 日期 (datetime)
# 列: epsEstimate, epsActual, epsDifference, surprisePercent
```

**注意：**
- 按日期降序排列（最近的在最前面）
- 通常返回近 4 季数据
- `surprisePercent` = (actual - estimate) / |estimate| × 100
- 某些公司可能返回空 DataFrame

### ticker.analyst_price_targets

分析师目标价汇总。

```python
targets = t.analyst_price_targets
# dict: {"current": float, "low": float, "high": float, "mean": float, "median": float}
```

### ticker.recommendations

分析师评级分布。

```python
recs = t.recommendations
# DataFrame，可能有多种格式
# 常见列: strongBuy, buy, hold, sell, strongSell
# 或: period, strongBuy, buy, hold, sell, strongSell
```

**注意：** 格式在 yfinance 不同版本间可能变化。用 try/except 包裹。

## 季度财务报表

### ticker.quarterly_income_stmt

```python
qi = t.quarterly_income_stmt
# DataFrame, columns = 日期 (最近的在最左边)
# 关键行:
# - Total Revenue
# - Gross Profit
# - Operating Income (EBIT)
# - Net Income
# - Basic EPS / Diluted EPS
```

### ticker.quarterly_cashflow

```python
qc = t.quarterly_cashflow
# 关键行:
# - Operating Cash Flow
# - Capital Expenditure
# - Free Cash Flow
# - Stock Based Compensation
# - Depreciation And Amortization
```

### ticker.quarterly_balance_sheet

```python
qb = t.quarterly_balance_sheet
# 关键行:
# - Total Assets
# - Total Debt
# - Cash And Cash Equivalents (或 Cash Cash Equivalents And Short Term Investments)
# - Stockholders Equity
```

## 计算常用指标

### 毛利率
```python
gm = qi.loc["Gross Profit"] / qi.loc["Total Revenue"]
```

### 营业利润率
```python
om = qi.loc["Operating Income"] / qi.loc["Total Revenue"]
```

### YoY 营收增长
```python
# quarterly_income_stmt 列按日期降序
# iloc[0] = 最近一季, iloc[4] = 去年同期 (如果有)
rev_current = float(qi.loc["Total Revenue"].iloc[0])
rev_yago    = float(qi.loc["Total Revenue"].iloc[4])  # 注意: 可能只有4列
yoy_growth  = (rev_current / rev_yago - 1) * 100
```

### 自由现金流
```python
fcf = qc.loc["Operating Cash Flow"] + qc.loc["Capital Expenditure"]  # CapEx 是负数
```

## 股价历史（反应分析用）

```python
# 获取财报日附近的价格
hist = t.history(
    start=earnings_date - timedelta(days=5),
    end=earnings_date + timedelta(days=5)
)
# DataFrame: Open, High, Low, Close, Volume
```

**计算财报日反应：**
1. 找到财报日期在 `hist.index` 中的位置
2. 盘后财报：比较当天收盘 → 次日收盘
3. 盘前财报：比较前一天收盘 → 当天收盘
4. 如果无法确定盘前/盘后，比较最近两个交易日收盘价的最大跳变

## 新闻

```python
news = t.news
# 返回 list of dict, 每个包含:
# - title, publisher, link, providerPublishTime, type
# 可用于关联财报相关报道
```

## 边界情况处理

| 情况 | 处理 |
|---|---|
| `earnings_estimate` 返回 None | 该公司分析师覆盖不足，标注 |
| `earnings_history` 为空 | 可能是新上市或数据源问题，跳过历史分析 |
| `calendar` 无 Earnings Date | 港股/部分ADR常见，标注"财报日期未知" |
| 季度财报只有 <4 列 | 新上市公司，用可用数据，标注 |
| `recommendations` 格式异常 | try/except 包裹，失败则跳过分析师评级 |
| 港股 ticker 格式 | `1810.HK`、`0700.HK`，yfinance 支持但数据完整度低于美股 |
