---
name: source-feed
description: >
  扫描所有已追踪的信息源，抓取最新内容，汇总摘要并提供分析。
  当用户询问"我关注的博主最近说了什么"、"信息源更新"、"source feed"、
  "博主动态"、"有什么新消息"、"scan sources"、"信息源摘要"、
  "digest"、"最近有什么值得关注的观点"时使用此技能。
  也用于定时场景：每日自动扫描所有启用的信息源，筛选与持仓/市场相关的内容，
  输出汇总摘要和关键观点提取。
---

# Source Feed — 信息源扫描与汇总

扫描 `config/sources.json` 中所有启用的信息源，通过 OpenCLI 抓取最新内容，
去重、筛选、汇总，输出结构化的信息摘要和分析。

---

## Step 1: 环境检测

```
!`(command -v opencli && opencli doctor 2>&1 | head -3 && echo "OPENCLI_OK") 2>/dev/null || echo "OPENCLI_MISSING"`
```

- `OPENCLI_OK` → 主路径可用（OpenCLI + Browser Bridge）
- `OPENCLI_MISSING` → 仅使用备用路径（RSS、公开 API）

如果 OpenCLI 不可用，不阻塞执行，而是对每个源降级到 `fetch.fallback` 路径。

---

## Step 2: 加载配置

```python
import json
from datetime import datetime, timedelta

with open("config/sources.json") as f:
    config = json.load(f)

sources = [s for s in config["sources"] if s.get("enabled", True)]
settings = config.get("scan_settings", {})

default_limit = settings.get("default_limit", 10)
max_age_hours = settings.get("max_age_hours", 48)
dedup_hours   = settings.get("dedup_window_hours", 72)
```

如果 `sources` 为空，提示用户：
> "你还没有添加任何信息源。使用 source-manager 技能添加：给我一个博主的链接，我就能帮你追踪。"

---

## Step 3: 逐源抓取

对每个启用的源，按以下优先级执行抓取：

```
1. fetch.opencli (主路径，需要 OpenCLI + Browser Bridge)
   ↓ 失败
2. fetch.fallback (备用路径，RSS / 公开 API，由白名单 dispatcher 构建命令)
   ↓ 失败
3. 标记为 "抓取失败"，跳过该源
```

### 执行模式

```bash
# 执行 opencli 命令，捕获 JSON 输出
result=$(opencli twitter tweets zaborxyz --limit 10 -f json 2>/dev/null)
exit_code=$?

# 根据退出码决定下一步
case $exit_code in
  0)   # 成功，解析 JSON
  66)  # 结果为空，标记"无新内容"
  69)  # 浏览器不可用，降级到 fallback
  77)  # 需要登录，降级到 fallback 并提示
  *)   # 其他错误，降级到 fallback
esac
```

### Python 封装

```python
import subprocess, json

ALLOWED_COMMANDS = {"opencli", "curl"}

def build_cmd(fetch_config, limit=10):
    """从结构化 fetch 配置构建命令参数列表（白名单校验，禁止任意 shell 执行）"""
    adapter = fetch_config["adapter"]
    action = fetch_config["action"]
    target = fetch_config["target"]
    # 只允许字母数字、下划线、连字符、点和斜线
    for val in [adapter, action, target]:
        if not all(c.isalnum() or c in "-_./@ " for c in str(val)):
            raise ValueError(f"Invalid character in fetch config: {val}")
    return ["opencli", adapter, action, target, "--limit", str(limit), "-f", "json"]

def build_fallback_cmd(fallback_config):
    """从结构化 fallback 配置构建命令（仅允许白名单命令）"""
    cmd_type = fallback_config.get("type")  # "rss", "reddit_api", "youtube_rss"
    url = fallback_config.get("url", "")
    if cmd_type == "rss":
        return ["curl", "-s", "-L", "--max-time", "15", url]
    elif cmd_type == "reddit_api":
        return ["curl", "-s", "-H", "User-Agent: StockAdvisor/1.0", url]
    elif cmd_type == "youtube_rss":
        return ["curl", "-s", "-L", "--max-time", "15", url]
    return None

def fetch_source(source, opencli_available=True, limit=10):
    """抓取单个信息源"""
    result = {"source_id": source["id"], "items": [], "status": "ok", "method": "opencli"}
    fetch = source.get("fetch", {})
    
    # 主路径: OpenCLI（从结构化配置构建命令）
    if opencli_available and fetch.get("opencli"):
        try:
            cmd = build_cmd(fetch["opencli"], limit)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode == 0 and proc.stdout.strip():
                result["items"] = json.loads(proc.stdout)
                return result
            elif proc.returncode == 66:
                result["status"] = "empty"
                return result
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
            pass
    
    # 备用路径（从结构化配置构建，不使用 shell=True）
    if fetch.get("fallback"):
        result["method"] = "fallback"
        try:
            cmd = build_fallback_cmd(fetch["fallback"])
            if cmd and cmd[0] in ALLOWED_COMMANDS:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if proc.returncode == 0 and proc.stdout.strip():
                    result["items"] = json.loads(proc.stdout)
                    return result
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
    
    result["status"] = "failed"
    return result
```

### 更新 last_scanned

每个源抓取完毕后，更新 `config/sources.json` 中该源的 `last_scanned` 时间戳。

---

## Step 4: 内容处理

### 4a. 统一格式化

不同平台的输出字段不同，统一为标准格式：

```python
{
    "source_id": "twitter:zaborxyz",
    "platform": "twitter",
    "author": "付鹏 @zaborxyz",
    "title": null,            # tweet 没有标题，文章/视频有
    "text": "今天的CPI数据...", # 正文或摘要
    "url": "https://x.com/zaborxyz/status/...",
    "published_at": "2026-06-18T10:30:00Z",
    "engagement": {            # 各平台格式不同，统一提取
        "likes": 1200,
        "comments": 85,
        "shares": 340
    }
}
```

### 字段映射

| 平台 | 标题字段 | 正文字段 | 时间字段 | 互动字段 |
|---|---|---|---|---|
| twitter | (无) | `text` | `created_at` | `likes`, `retweets`, `replies` |
| reddit | `title` | `selftext` 或 URL | `created_at` | `score`, `comments` |
| youtube | `title` | (无文本) | `published` | `views` |
| weibo | (无) | `text` | `created_at` | `likes`, `comments`, `reposts` |
| xueqiu | `title` 或 (无) | `text` | `created_at` | `reply_count`, `like_count` |
| substack | `title` | `subtitle` | `published` | (无) |
| rss | `title` | `description` | `pubDate` | (无) |

### 4b. 去重

在 `dedup_window_hours` 时间窗口内，按以下规则去重：
- 同一 `source_id` + 同一 `url` → 去重
- 同一 `source_id` + 文本相似度 >90% → 去重（简单实现：前 100 字符匹配）

### 4c. 时效过滤

仅保留 `max_age_hours` 内的内容。超过的标记为旧内容，仅在用户明确要求时展示。

### 4d. 相关性标注

读取 `config/portfolio.json` 和 `config/watchlist.json`，提取所有持仓和关注的股票名称/代码。
对每条内容做关键词匹配：

```python
# 构建关键词集合
keywords = set()
for market in portfolio.values():
    for s in market:
        keywords.add(s["symbol"].upper())
        keywords.add(s["name"])
for market in watchlist.values():
    for s in market:
        keywords.add(s["symbol"].upper())
        keywords.add(s["name"])

# 标注
for item in all_items:
    text = (item.get("title") or "") + " " + (item.get("text") or "")
    item["matched_keywords"] = [kw for kw in keywords if kw.upper() in text.upper()]
    item["relevance"] = "high" if item["matched_keywords"] else "general"
```

---

## Step 5: 汇总输出

### 输出结构

按优先级组织输出（高相关性在前）：

```
## 信息源摘要 | 2026-06-18

**扫描范围**: 5 个信息源 | 成功 4 个 | 失败 1 个
**新内容**: 23 条 (过去 48 小时) | 与持仓相关: 7 条

---

### 与持仓/关注相关的内容

#### 付鹏 @zaborxyz [Twitter · 宏观]
> "美联储明天的决议大概率维持不变，但点阵图才是关键..."
> — 2h前 · ❤️ 1.2K · 🔄 340
> 关联: FOMC, 美联储

#### r/wallstreetbets [Reddit · 股票]
> **NVDA earnings play: IV is through the roof**
> "Consider selling puts instead of buying calls at this IV level..."
> — 5h前 · ⬆️ 2.3K · 💬 456
> 关联: NVDA (英伟达)

---

### 其他更新

#### 某宏观博主 [Substack · 宏观]
> **本周市场展望：通胀数据与美联储博弈**
> "核心CPI的走势将决定下半年的利率路径..."
> — 8h前

#### 某财经号 [微博 · 新闻]
> "港股午后拉升，恒指收涨1.2%，科技股领涨..."
> — 3h前 · ❤️ 856

---

### 抓取状态

| 信息源 | 状态 | 方法 | 新内容 |
|--------|------|------|--------|
| @zaborxyz | ✅ | opencli | 3 条 |
| r/wallstreetbets | ✅ | opencli | 8 条 |
| 某博主 (Substack) | ✅ | RSS | 1 条 |
| 某财经号 (微博) | ✅ | opencli | 6 条 |
| @某大V (雪球) | ❌ 需登录 | - | - |
```

### 关键观点提取

在汇总之后，agent 应执行以下分析：

1. **观点聚类**：多个信息源讨论同一话题 → 合并提炼核心观点
2. **多空分歧**：不同博主对同一标的看法不同 → 对比展示
3. **与持仓关联**：哪些讨论直接影响用户持仓 → 高亮提示
4. **行动信号**：是否有值得关注的风险提示或机会（以"值得关注"而非"建议买卖"的措辞）

```
### 关键观点提取

1. **美联储决议 (FOMC)** — 多数信源认为维持不变，但点阵图可能暗示年内降息次数减少
   - 付鹏: 关注点阵图 | r/wallstreetbets: 关注鲍威尔讲话措辞
   - 对持仓影响: TQQQ (纳指杠杆) 和 MSFT (科技大盘) 可能受利率预期影响

2. **NVDA 财报前期权定价** — WSB 讨论活跃，隐含波动率偏高
   - 关联持仓: 关注列表中有 NVDA
```

---

## Step 6: 定时运行模式

在定时场景中（如每日早报/晚报附带信息源摘要）：

1. 自动扫描所有启用的源
2. 仅输出与持仓/关注相关的高价值内容（精简版）
3. 如果无新内容或无相关内容，输出一行："信息源无新的相关更新。"
4. 完整版可由用户手动触发

**精简版输出**（嵌入到每日播报中）：

```
### 博主动态速览
- 付鹏: "美联储明天大概率..." (2h前, 关联 FOMC)
- r/wsb: NVDA 期权讨论活跃 (5h前, 关联 NVDA)
- 某宏观博主: 本周市场展望 (8h前)
```

---

## Reference Files

- 共用 `source-manager` 的 `references/platform_adapters.md` — 各平台的命令和输出字段映射
