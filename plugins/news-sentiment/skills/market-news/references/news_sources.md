# 新闻来源参考

## yfinance 新闻 API

```python
import yfinance as yf
t = yf.Ticker("AAPL")
news = t.news
# 返回 list[dict], 每条包含:
# title, publisher, link, providerPublishTime, type, relatedTickers
```

**注意事项：**
- 通常返回 8-15 条新闻
- 时间跨度约 1-7 天（取决于该股票的新闻活跃度）
- `providerPublishTime` 是 Unix timestamp，需转换
- `relatedTickers` 是列表，可用于交叉关联
- 部分新闻来自 Yahoo Finance 自有内容，质量参差

## OpenCLI 财经新闻命令

### 国际财经媒体

```bash
# Bloomberg
opencli bloomberg markets --limit 10 -f json
opencli bloomberg technology --limit 10 -f json

# Reuters
opencli reuters business --limit 10 -f json
opencli reuters markets --limit 10 -f json

# BBC Business
opencli bbc business --limit 10 -f json

# CNBC (如支持)
opencli cnbc markets --limit 10 -f json
```

### 中文财经媒体

```bash
# 东方财富
opencli eastmoney hot --limit 10 -f json         # 热门
opencli eastmoney news --limit 10 -f json         # 财经新闻

# 雪球
opencli xueqiu hot --limit 10 -f json             # 热门讨论
opencli xueqiu news --limit 10 -f json            # 新闻

# 新浪财经 (如支持)
opencli sinafinance news --limit 10 -f json
```

### 通用新闻聚合

```bash
# HackerNews (科技/创业视角)
opencli hackernews top --limit 10 -f json

# Reddit 财经子版
opencli reddit subreddit r/investing --sort hot --limit 10 -f json
opencli reddit subreddit r/stocks --sort hot --limit 10 -f json
```

**使用前先检查命令是否存在：**
```bash
opencli list | grep -i bloomberg
```

## 新闻来源权威性评级

### 顶级 (Tier 1) — 原创报道，专业编辑
- Reuters, Bloomberg, Wall Street Journal, Financial Times
- Associated Press (AP), Dow Jones Newswires

### 一级 (Tier 2) — 专业财经媒体
- CNBC, MarketWatch, Barron's, The Economist, Forbes
- Nikkei Asia, South China Morning Post

### 二级 (Tier 3) — 综合/社区型
- Yahoo Finance, Seeking Alpha, Investopedia, Motley Fool
- Business Insider, TechCrunch (科技)

### 中文顶级
- 财联社, 证券时报, 中国证券报, 上海证券报
- 经济日报, 人民日报经济版

### 中文一级
- 华尔街见闻, 36氪, 界面新闻, 第一财经
- 东方财富, 同花顺

### 中文二级/社区
- 雪球, 虎扑财经, 集思录

## 新闻话题分类关键词

用于自动分类新闻话题：

| 分类 | 关键词示例 |
|---|---|
| 财报 | earnings, revenue, EPS, beat, miss, guidance, 财报, 业绩, 营收 |
| 并购 | merger, acquisition, deal, buyout, 收购, 合并, 拆分 |
| 监管 | regulation, SEC, antitrust, fine, 监管, 罚款, 反垄断 |
| 宏观 | Fed, CPI, GDP, inflation, rate, 美联储, 通胀, 利率 |
| 科技 | AI, chip, semiconductor, cloud, 芯片, 人工智能, 云计算 |
| 地缘 | tariff, sanction, war, trade, 关税, 制裁, 贸易 |
| 人事 | CEO, resign, appoint, board, 辞职, 任命, 董事会 |
| 产品 | launch, release, recall, 发布, 上市, 召回 |
