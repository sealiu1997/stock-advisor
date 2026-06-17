---
name: market-news
description: >
  抓取与持仓和关注标的相关的财经新闻，做摘要和影响分析。
  当用户询问"最近有什么新闻"、"AAPL有什么消息"、"市场新闻"、
  "我的股票有什么新闻"、"financial news"、"有什么利好利空"、
  "新闻汇总"、"news digest"、"发生了什么"、"为什么涨/跌"、
  或在讨论某只股票时想了解近期消息面时使用此技能。
  数据来源：yfinance 新闻 API（主路径） + OpenCLI 财经新闻站点（增强路径）。
---

# Market News — 财经新闻抓取与分析

抓取与用户持仓和关注标的相关的财经新闻，提供结构化摘要和潜在影响分析。

**声明：仅供研究和教育目的，不构成投资建议。**

---

## Step 1: 环境检测

```
!`python3 -c "import yfinance; print('YFINANCE_OK')" 2>/dev/null || echo "YFINANCE_MISSING"`
```

```
!`(command -v opencli && echo "OPENCLI_OK") 2>/dev/null || echo "OPENCLI_MISSING"`
```

- yfinance: 主要新闻数据源（每只股票的相关新闻）
- OpenCLI: 增强路径（财经媒体头条、深度文章）

---

## Step 2: 确定抓取范围

| 用户请求 | 抓取范围 |
|---|---|
| "最近有什么新闻" / 定时播报 | 全部持仓 + 关注列表的新闻 |
| "AAPL有什么消息" | 仅指定标的 |
| "为什么涨/跌" | 指定标的的新闻 + 板块新闻 |
| "市场新闻" | 主要指数 + 宏观新闻 |

**配置文件读取：**
- 全量模式：读取 `config/portfolio.json` + `config/watchlist.json`
- 指定标的：直接使用用户给的 ticker

---

## Step 3: 抓取新闻

### 路径 A: yfinance（主路径）

```python
import yfinance as yf
from datetime import datetime, timedelta

def get_news(symbol):
    """获取单只股票的相关新闻"""
    t = yf.Ticker(symbol)
    news = t.news  # 返回 list of dict
    return news

# 批量获取
all_news = {}
for symbol in target_symbols:
    news = get_news(symbol)
    if news:
        all_news[symbol] = news
```

yfinance `.news` 返回字段：

| 字段 | 说明 |
|---|---|
| `title` | 新闻标题 |
| `publisher` | 来源（Reuters, Bloomberg, CNBC 等） |
| `link` | 原文链接 |
| `providerPublishTime` | 发布时间 (Unix timestamp) |
| `type` | 类型 (STORY, VIDEO 等) |
| `relatedTickers` | 相关股票代码列表 |

### 路径 B: OpenCLI（增强路径，可选）

如果 OpenCLI 可用，可以补充抓取财经媒体的头条：

```bash
# Bloomberg 市场头条
opencli bloomberg markets --limit 10 -f json

# Reuters 商业新闻
opencli reuters business --limit 10 -f json

# 东方财富热点（中文财经）
opencli eastmoney hot --limit 10 -f json

# 雪球热门讨论
opencli xueqiu hot --limit 10 -f json

# BBC 商业新闻
opencli bbc business --limit 10 -f json
```

### 路径 C: 宏观新闻（市场级别）

对于"市场新闻"请求，抓取指数和宏观标的的新闻：

```python
macro_tickers = ["^GSPC", "^IXIC", "^VIX", "GC=F", "CL=F"]
for ticker in macro_tickers:
    news = yf.Ticker(ticker).news
```

---

## Step 4: 新闻处理

### 4a. 去重

同一新闻可能出现在多只股票的 feed 中。按 `link` 字段去重，但保留所有 `relatedTickers`。

### 4b. 时效过滤

默认仅保留 48 小时内的新闻。用户要求"这周"则扩展到 7 天。

### 4c. 重要性排序

综合以下因素排序：

| 因素 | 权重 | 说明 |
|---|---|---|
| 来源权威性 | 高 | Reuters > CNBC > 小型财经站 |
| 关联持仓数 | 高 | 关联 3 只持仓股 > 关联 1 只 |
| 时效性 | 中 | 越新越靠前 |
| 话题重要性 | 中 | 财报、并购、监管 > 一般报道 |

**来源权威性参考：**

| 等级 | 来源 |
|---|---|
| 顶级 | Reuters, Bloomberg, WSJ, FT |
| 一级 | CNBC, MarketWatch, Barron's, The Economist |
| 二级 | Yahoo Finance, Seeking Alpha, Investopedia |
| 中文顶级 | 财联社, 证券时报, 中国证券报 |
| 中文一级 | 华尔街见闻, 36氪, 界面新闻 |

### 4d. 话题聚类

多条新闻讨论同一事件时，聚合为一个话题：

```python
# 简单聚类：标题关键词重叠 + relatedTickers 重叠
# 例："AAPL iPhone 16 sales beat" 和 "Apple posts strong Q3 iPhone revenue" → 同一话题
```

---

## Step 5: 影响分析

对每条重要新闻或每个话题，分析对用户持仓的潜在影响：

### 影响判断框架

| 新闻类型 | 直接影响 | 间接影响 |
|---|---|---|
| 个股财报 | 该股票 | 同业、上下游 |
| 并购/拆分 | 涉及公司 | 竞争对手、板块 |
| 监管政策 | 被监管公司 | 整个行业 |
| 宏观数据 | 指数/ETF | 利率敏感股、商品 |
| 地缘政治 | 涉及地区公司 | 能源、国防、黄金 |
| 科技突破 | 技术公司 | 应用层、竞争者 |
| CEO/高管变动 | 该公司 | 短期波动 |

### 影响标注

对每条新闻标注：
- **影响方向**：利好 📈 / 利空 📉 / 中性 ➖
- **影响程度**：高 / 中 / 低
- **关联持仓**：具体哪些持仓可能受影响

---

## Step 6: 输出报告

### 全量模式

```
## 财经新闻汇总 | 2026-06-18

**覆盖范围**: 15 只持仓 + 23 只关注标的
**新闻数量**: 42 条 (过去 48h) | 去重后 28 条 | 聚合为 12 个话题

---

### 重要新闻 (与持仓直接相关)

#### 📈 苹果发布 AI 功能路线图，分析师上调目标价
> **来源**: Bloomberg · 3h前
> Apple announced expanded AI capabilities for iPhone, with analysts raising price targets...
> **关联持仓**: GOOG (AI竞争格局), AAPL (关注列表)
> **影响**: 科技板块整体利好，AI 主题延续

#### 📉 中国海洋石油公告: Q3 产量指引低于预期
> **来源**: 财联社 · 6h前
> 中海油下调Q3产量指引至1.4亿桶油当量...
> **关联持仓**: 0883 (中国海洋石油) — 直接影响
> **影响**: 短期利空，关注是否因检修计划导致

---

### 市场大事件

#### 美联储 FOMC 决议即将公布
> 多条报道汇总 | Reuters, CNBC, Bloomberg
> 市场普遍预期维持利率不变，关注点阵图和鲍威尔讲话...

---

### 其他新闻速览

| 标的 | 标题 | 来源 | 时间 | 影响 |
|------|------|------|------|------|
| NVDA | AI 芯片出口限制可能放松 | Reuters | 8h前 | 📈 中 |
| PDD | 拼多多 Temu 欧洲市场增速放缓 | FT | 12h前 | 📉 低 |
...
```

### 精简模式（嵌入每日播报）

```
### 新闻速览
- 📈 苹果 AI 路线图利好科技板块 (Bloomberg, 3h前)
- 📉 中海油下调产量指引 → 持仓 0883 注意 (财联社, 6h前)
- ➖ FOMC 决议今晚公布，市场观望 (多源)
```

---

## Reference Files

- `references/news_sources.md` — 新闻来源权威性评级、OpenCLI 财经新闻命令列表
