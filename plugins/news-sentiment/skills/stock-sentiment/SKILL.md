---
name: stock-sentiment
description: >
  分析特定股票在社交媒体上的讨论热度和情绪倾向。
  当用户询问"TSLA的市场情绪怎么样"、"大家怎么看NVDA"、"Reddit上怎么说"、
  "推特上对AAPL什么态度"、"散户情绪"、"social sentiment"、"market buzz"、
  "热度怎么样"、"bullish还是bearish"、"多空情绪"、"舆论分析"、
  "stock sentiment"、"WSB在讨论什么"、"雪球上怎么看"时使用此技能。
  数据来源：OpenCLI (Reddit/Twitter/雪球) 为主，yfinance 新闻为辅。
  此技能为只读，不发布任何内容。
---

# Stock Sentiment — 社交情绪分析

分析特定股票在 Reddit、Twitter/X、雪球等社交平台上的讨论热度和多空情绪，
帮助了解市场参与者的态度和预期。

**声明：社交情绪是研究信号，不是交易信号。仅供参考，不构成投资建议。**

---

## Step 1: 环境检测

```
!`(command -v opencli && opencli doctor 2>&1 | head -3 && echo "OPENCLI_OK") 2>/dev/null || echo "OPENCLI_MISSING"`
```

```
!`python3 -c "import yfinance; print('YFINANCE_OK')" 2>/dev/null || echo "YFINANCE_MISSING"`
```

OpenCLI 是社交数据的主要来源。如果不可用，降级到 Reddit 公开 API + yfinance 新闻。

---

## Step 2: 确定分析标的

- 用户指定了具体 ticker → 分析该 ticker
- 用户说"我的股票的情绪" → 读取 `config/portfolio.json`，分析所有持仓
- 用户说"市场情绪" → 分析主要指数 ETF (SPY, QQQ) + 热门讨论

---

## Step 3: 多平台情绪采集

对每个目标 ticker，从多个平台采集讨论数据：

### A. Reddit（散户情绪风向标）

```bash
# 搜索特定股票的讨论
opencli reddit search "{TICKER}" --sort new --limit 20 -f json

# WSB (WallStreetBets) — 散户情绪的代表
opencli reddit subreddit r/wallstreetbets --sort hot --limit 20 -f json

# r/stocks — 相对理性的讨论
opencli reddit subreddit r/stocks --sort hot --limit 20 -f json

# r/investing — 长期投资视角
opencli reddit subreddit r/investing --sort hot --limit 20 -f json
```

**备用路径（OpenCLI 不可用时）：**
```bash
# Reddit 公开 JSON API
curl -s -H "User-Agent: StockAdvisor/1.0" \
  "https://www.reddit.com/search.json?q={TICKER}&sort=new&limit=20&restrict_sr=off"
```

**提取字段：** `title`, `selftext`, `score`, `num_comments`, `created_utc`, `subreddit`

### B. Twitter/X（机构和 KOL 声音）

```bash
# 搜索 cashtag
opencli twitter search "\${TICKER}" --filter live --limit 20 -f json

# 搜索公司名
opencli twitter search "{COMPANY_NAME} stock" --filter live --limit 20 -f json
```

**需要 Chrome 登录 x.com。无备用路径。**

**提取字段：** `text`, `author`, `likes`, `retweets`, `created_at`

### C. 雪球（中文投资社区）

```bash
# 搜索股票讨论
opencli xueqiu search "{TICKER}" --limit 20 -f json

# 港股用中文名搜索
opencli xueqiu search "小米集团" --limit 20 -f json
```

**提取字段：** `text`, `user`, `reply_count`, `like_count`, `created_at`

### D. yfinance 新闻（补充数据）

```python
import yfinance as yf
t = yf.Ticker(TICKER)
news = t.news  # 新闻标题可用于情绪分析
```

---

## Step 4: 情绪分析

### 4a. 文本情绪标注

对每条帖子/推文，由 agent 判断情绪倾向：

| 情绪 | 特征 |
|---|---|
| 看多 (Bullish) 📈 | "买入"、"加仓"、"看好"、"to the moon"、"undervalued"、"buy"、"long" |
| 看空 (Bearish) 📉 | "卖出"、"减仓"、"看跌"、"overvalued"、"sell"、"short"、"puts" |
| 中性 (Neutral) ➖ | 客观分析、提问、信息分享 |

**关键词辅助判断：**

```python
BULLISH_KEYWORDS = [
    "buy", "long", "calls", "bull", "moon", "undervalued", "accumulate",
    "买入", "加仓", "看多", "抄底", "低估", "利好", "起飞"
]
BEARISH_KEYWORDS = [
    "sell", "short", "puts", "bear", "overvalued", "dump", "crash",
    "卖出", "减仓", "看空", "高估", "利空", "暴跌", "套牢"
]
```

注意：关键词只是辅助，agent 应理解上下文（如反讽、引用、提问 vs 断言）。

### 4b. 情绪聚合

```python
total = len(posts)
bullish = sum(1 for p in posts if p["sentiment"] == "bullish")
bearish = sum(1 for p in posts if p["sentiment"] == "bearish")
neutral = total - bullish - bearish

bullish_pct = bullish / total * 100
bearish_pct = bearish / total * 100

# 情绪评分: -100 (极度看空) 到 +100 (极度看多)
sentiment_score = (bullish - bearish) / total * 100
```

### 4c. 热度评估

```python
# 讨论量 (mentions)
mention_count = total

# 互动量 (engagement)
total_engagement = sum(p.get("score", 0) + p.get("likes", 0) + p.get("comments", 0) for p in posts)

# 热度等级
if mention_count > 50: buzz = "极高"
elif mention_count > 20: buzz = "高"
elif mention_count > 10: buzz = "中等"
else: buzz = "低"
```

### 4d. 跨平台对比

如果多个平台都有数据，对比不同群体的态度差异：

| 平台 | 代表群体 | 特点 |
|---|---|---|
| Reddit (WSB) | 美国散户 | 激进、期权偏好、YOLO 文化 |
| Reddit (r/investing) | 长期投资者 | 相对理性、基本面导向 |
| Twitter | 机构、KOL、媒体 | 信息更快、观点多元 |
| 雪球 | 中国投资者 | 港美股视角、政策敏感 |

---

## Step 5: 输出报告

### 单只股票情绪报告

```
## NVDA 社交情绪分析 | 2026-06-18

### 情绪概览

| 指标 | 数值 |
|------|------|
| 情绪评分 | +42 / 100 (偏多) |
| 看多比例 | 58% |
| 看空比例 | 16% |
| 中性比例 | 26% |
| 讨论热度 | 极高 (87 条提及 / 24h) |
| 互动总量 | 12.4K |

### 跨平台对比

| 平台 | 样本 | 看多% | 看空% | 热度 | 主要论点 |
|------|------|-------|-------|------|---------|
| Reddit (WSB) | 32 | 65% | 12% | 极高 | 财报前看涨期权活跃 |
| Reddit (r/stocks) | 15 | 53% | 20% | 中 | 估值争议，但基本面强 |
| Twitter | 28 | 54% | 18% | 高 | AI 需求确认，分析师上调 |
| 雪球 | 12 | 50% | 25% | 中 | 对出口限制担忧 |

### 多空核心论点

**看多方 📈:**
1. AI 数据中心资本支出持续增长，NVDA 是最大受益者
2. 下一代 Blackwell 芯片需求强劲，产能紧张
3. 分析师普遍上调目标价至 $150+

**看空方 📉:**
1. 估值过高，前瞻 P/E > 40x
2. 出口管制风险（中国市场受限）
3. AMD 和自研芯片竞争加剧

### 值得关注的高影响帖子

| 来源 | 内容摘要 | 互动 | 情绪 |
|------|---------|------|------|
| @某知名分析师 (Twitter) | "NVDA 的 AI 护城河比市场认知的更深..." | ❤️ 5.2K | 📈 |
| u/某用户 (WSB) | "财报前 IV 太高，卖 put 比买 call 划算" | ⬆️ 2.3K | ➖ |

### 情绪 vs 基本面交叉验证

（agent 结合估值数据和新闻面，判断当前情绪是否合理）

- 情绪偏多 + 基本面支撑 → 趋势可能延续
- 情绪极度偏多 + 估值偏高 → 注意回调风险（情绪过热）
- 情绪偏空 + 基本面良好 → 可能是逆向机会
```

### 多标的情绪对比模式

当分析多只股票时，输出对比表：

```
### 持仓情绪对比

| 标的 | 情绪评分 | 看多% | 热度 | 趋势 | 备注 |
|------|---------|-------|------|------|------|
| NVDA | +42 | 58% | 极高 | ↑ 升温 | 财报前看涨期权活跃 |
| GOOG | +15 | 45% | 中 | → 稳定 | AI 搜索担忧 vs 云增长 |
| 小米 (1810) | +28 | 52% | 高 | ↑ 升温 | 汽车交付超预期 |
| 中海油 (0883) | -10 | 35% | 低 | ↓ 降温 | 产量指引下调 |
```

---

## Step 6: 注意事项

### 必须附带的免责声明
- 社交媒体情绪是**研究信号**，不是交易信号
- 散户讨论可能存在信息不对称、跟风、操纵
- 高热度不等于方向正确 — 极端情绪往往是反向信号
- 样本有偏差：Reddit 偏美国散户，雪球偏中国投资者
- 此技能为只读，不发布任何内容
- 非投资建议

---

## Reference Files

- 共用 `source-manager` 的 `references/platform_adapters.md` — OpenCLI 命令参考
