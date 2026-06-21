---
name: daily-briefing
description: >
  智能每日市场播报 + 市场认知管理。
  播报模式：当用户询问"今日播报"、"早报"、"晚报"、"收盘报"、"daily briefing"、
  "今天市场怎么样"、"帮我分析今天行情"、"morning report"、
  "今天发生了什么"、"market recap"时触发。
  认知管理模式：当用户询问"当前的市场叙事是什么"、"宏观认知"、"market context"、
  "最近的分析记录"、"有哪些活跃叙事"、"更新市场判断"、"修正叙事"、
  "这个判断不对"、"添加新的市场观点"、"expire narrative"时触发。
  也用于定时场景：每日自动生成主题化播报。
  与 my-stocks 的区别：my-stocks 是轻量级数据查看，
  daily-briefing 是有主线、有证据链、有连续性的深度分析。
  需要 PKS (Personal Knowledge State) 来维护市场认知连续性。
  后台由 market_watcher 守护进程自动采集数据并更新 PKS。
---

# Daily Briefing — 智能每日播报 + 市场认知管理

两种操作模式：
- **播报模式**（默认）：生成有主线、有证据链、有市场连续性的每日投研播报
- **认知管理模式**：查看和管理 PKS 中的市场叙事、数据事实、分析历史

播报不是逐 ticker 平铺，而是"先定主线，再筛标的，再给证据"。

**核心原则：**
- 每条分析必须有证据链：因子 → 传导 → 个股
- 找不到证据宁可不写，不硬凑
- 围绕主线展开，不散
- 利用 PKS 保持跨会话连续性
- 后台 `market_watcher` 已持续采集数据到 PKS，播报时直接读取

---

## Step 0: 模式判定

根据用户意图判断操作模式：

| 用户意图 | 模式 |
|---------|------|
| "今日播报" / "daily briefing" / "今天市场" | → **播报模式**（跳到 Step 1） |
| "目前有哪些活跃叙事" / "市场认知" / "market context" | → **认知管理 — 查看** |
| "最近的宏观数据" | → **认知管理 — 查看数据** |
| "最近的分析记录" | → **认知管理 — 查看历史** |
| "这个叙事应该过期了" / "expire" | → **认知管理 — 过期叙事** |
| "加一个 XXX 叙事" / "新增" | → **认知管理 — 新增叙事** |
| "修正 XXX" / "这个判断不对" | → **认知管理 — 修正叙事** |
| "认知健康检查" | → **认知管理 — 健康检查** |

### 认知管理操作

**查看叙事：**
```bash
pks claim list --status accepted --tag narrative --domain research
pks health market-context
```
输出活跃叙事列表，标注 stale claims 提醒用户 verify 或 expire。

**查看数据事实：**
```bash
pks claim list --status accepted --type factual --domain research --tag macro
```

**查看日报历史：**
```bash
pks claim list --status accepted --subject "daily_briefing" --domain research
```

**过期叙事：** 需要用户确认 → `pks claim expire {claim_id}`

**新增叙事：** 收集用户输入（核心判断、证据、传导、影响），按 `references/narrative_modeling.md` 构建 L1-L3 claims。

**修正叙事：** `pks claim supersede {old_claim_id} --subject ... --object "{修正后的判断}"`

**验证/刷新叙事：** `pks claim verify {claim_id}`

**健康检查：** `pks health market-context` → 输出 accepted/stale/expired 统计 + 建议操作。

认知管理操作完成后输出摘要，不执行播报流程。

---

以下 Step 1-8 为**播报模式**流程：

---

## Step 1: 环境检测与 PKS 初始化

### 1a. 检测基础依赖

```
!`python3 -c "import yfinance; print('YFINANCE_OK')" 2>/dev/null || echo "YFINANCE_MISSING"`
```

如果 `YFINANCE_MISSING`：提示用户运行 `pip install -r requirements.txt`，本次无法执行。

### 1b. 检测 PKS

```
!`command -v pks >/dev/null 2>&1 && pks context 2>/dev/null | head -1 && echo "PKS_OK" || echo "PKS_MISSING"`
```

**如果 `PKS_MISSING`：**

提示用户：

> daily-briefing 需要 PKS (Personal Knowledge State) 来维护市场认知连续性。
> 是否允许我从 GitHub 下载并安装？
> 安装命令：
> ```
> git clone https://github.com/sealiu1997/personal_knowledge_state ~/personal_knowledge_state
> cd ~/personal_knowledge_state && pip install -e .
> pks init-home
> ```
> 如果你希望自行安装，可以稍后运行以上命令。

- 如果用户同意 → 执行安装
- 如果用户拒绝 → 进入**无状态降级模式**：跳过 PKS 读写步骤，每次播报独立生成（无连续性）
- 如果安装过程中需要用户手动操作（如网络问题、权限问题）→ 提示用户具体操作

### 1c. 检测 MarketContext 胶囊

```
!`pks project list 2>/dev/null | grep -q "market-context" && echo "CAPSULE_OK" || echo "CAPSULE_MISSING"`
```

**如果 `CAPSULE_MISSING`：**

```bash
pks new market-context --type MarketContext --domain research
```

### 1d. 检测 OpenCLI（可选，用于增强新闻抓取）

```
!`command -v opencli >/dev/null 2>&1 && echo "OPENCLI_OK" || echo "OPENCLI_MISSING"`
```

OpenCLI 不可用不阻塞执行，仅影响新闻来源丰富度。

---

## Step 2: 读取 PKS 宏观认知

**（如果 PKS 可用）**

读取当前活跃的市场叙事和最近的分析记录：

```bash
# 活跃叙事
pks claim list --status accepted --tag narrative --domain research

# 最近的数据事实（7 天内）
pks claim list --status accepted --type factual --domain research --tag macro

# 上一次日报记录
pks claim list --status accepted --subject "daily_briefing" --domain research
```

从以上输出中提取：
- **活跃叙事**：当前市场在交易什么？上次播报的主线是什么？
- **数据背景**：最近一期的 CPI/NFP/FOMC 等是什么结果？
- **连续性线索**：上次播报关注的变量，这次需要跟进

**（如果 PKS 不可用）**

跳过此步骤。后续分析没有历史上下文。

---

## Step 3: 获取框架数据

### 3a. 优先从 PKS 读取（market_watcher 已采集）

如果 PKS 可用，market_watcher 守护进程已持续将框架数据写入 PKS：

```bash
# 最近的价格异动
pks claim list --status accepted --tag price --domain research --limit 20

# 最近的宏观数据
pks claim list --status accepted --tag macro,data --domain research --limit 20

# 最近的新闻
pks claim list --status accepted --subject jin10_flash --domain research --limit 20
```

### 3b. 实时补充抓取

PKS 中的数据可能滞后几分钟到几小时。对关键框架指标做实时补充：

```python
import yfinance as yf
import json

with open("config/briefing.json") as f:
    cfg = json.load(f)

symbols = (
    cfg["framework_symbols"]["us_indices"]
    + cfg["framework_symbols"]["asia_indices"]
    + list(cfg["framework_symbols"]["rates"].values())
    + list(cfg["framework_symbols"]["macro"].values())
)

data = yf.download(symbols, period="5d", group_by="ticker", progress=False)
```

提取每个标的的：
- 最新收盘价 / 最新价
- 日涨跌幅 (%)
- 5 日变化趋势

特别关注：
- **美债收益率变动**：2Y/5Y/10Y 的绝对变化（bp）和曲线形态（2s10s spread）
- **VIX 水平**：< 15 低波动，15-20 正常，20-25 偏高，> 25 恐慌
- **DXY 方向**：与黄金/新兴市场的反向关系

---

## Step 4: 新闻汇总

### 4a. 从 PKS 读取 watcher 采集的新闻

market_watcher 已通过 Jin10 MCP + RSS 持续采集新闻并存入 PKS。直接读取：

```bash
pks claim list --status accepted --tag news --domain research --limit 30
```

### 4b. yfinance 个股新闻（补充）

```python
import yfinance as yf

with open("config/portfolio.json") as f:
    portfolio = json.load(f)

all_news = []
for market in portfolio:
    for stock in portfolio[market]:
        symbol = stock["symbol"]
        yf_symbol = f"{symbol}.HK" if market == "HK" else symbol
        try:
            t = yf.Ticker(yf_symbol)
            news = t.news or []
            for n in news:
                n["_ticker"] = symbol
            all_news.extend(news)
        except Exception:
            pass
```

### 4c. OpenCLI 新闻（增强路径，如果可用）

```bash
opencli bloomberg markets --limit 5 -f json
opencli reuters business --limit 5 -f json
opencli eastmoney hot --limit 5 -f json
```

### 4d. 新闻分层标注

按 `config/briefing.json` 中 `news_source_tiers` 对新闻标注层级：
- tier_1 → 可用于定调归因
- tier_2 → 可补充个股细节
- tier_3 → 仅作情绪旁证

**只使用 24 小时内的新闻。**

---

## Step 5: 定主线

这是整个播报最关键的步骤。

### 5a. 候选主线识别

按 `config/briefing.json` 中 `driver_types` 和 `references/analysis_rules.md` 中的检测标准，
逐类扫描：

1. **宏观数据**：过去 24h 是否有重大数据发布？实际值 vs 预期的偏差多大？
2. **利率驱动**：美债收益率变动 > 5bp？DXY 变动 > 0.5%？
3. **地缘政治**：一级新闻源是否报道重大地缘事件？
4. **商品驱动**：黄金/原油/铜变动 > 1.5%？
5. **行业驱动**：某板块 ETF 变动 > 2%？
6. **个股事件**：持仓中有财报/并购/监管等？

### 5b. 连续性判断

对比 Step 2 中的活跃叙事：
- 今天的数据是否**延续**某个已有叙事？→ 引用并刷新该叙事
- 今天的数据是否**矛盾**已有叙事？→ 标注转折
- 今天是否出现**全新驱动因素**？→ 新建叙事

### 5c. 确定主线

从候选中选择 1-2 个最强的。必须满足：
- 至少有 1 条一级新闻源或官方数据支撑
- 能解释当日市场多数资产的走势方向

输出格式：

```
今日主线：{一句话概括}
驱动类型：{macro_data / rates / geopolitical / commodity / sector / stock_specific}
证据来源：{来源名称 + 关键引述}
```

如果找不到明确主线：

```
今日主线：市场缺乏明确方向催化，主要指数窄幅震荡。
```

---

## Step 6: 更新 PKS

**（如果 PKS 可用）**

### 6a. 写入数据事实

将 Step 3 中的关键数据写入 PKS（factual claims）：

只写入**有意义变动**的数据（如美债收益率变动 > 3bp、VIX 变动 > 1 点），
不把所有数据都灌进去。

参考 `references/narrative_modeling.md` 中的 subject/predicate 约定。

### 6b. 管理叙事

- 今天的主线延续已有叙事 → `pks claim verify {id}` 刷新，追加新 evidence
- 今天的主线是新叙事 → 按 `references/narrative_modeling.md` 创建 L1-L3 claims
- 已有叙事今天没有新证据支撑 → 不操作（等自然 stale）
- 已有叙事与今天数据矛盾 → `pks claim supersede`

### 6c. 记录日报元数据

```bash
pks claim add \
  --subject "daily_briefing" \
  --predicate "main_theme" \
  --object "{今日主线一句话}" \
  --qualifier "{今天日期}" \
  --type inference \
  --domain research \
  --tag briefing
```

---

## Step 7: 筛标的并生成分析

### 7a. 读取持仓和关注列表

```python
with open("config/portfolio.json") as f:
    portfolio = json.load(f)
with open("config/watchlist.json") as f:
    watchlist = json.load(f)
```

### 7b. 抓取持仓行情

对所有持仓批量抓取当日行情（复用 my-stocks 的数据源逻辑）：
- 美股：yfinance
- 港股：腾讯财经 API → yfinance (.HK)
- 加密：Binance API

### 7c. 分层触发

读取 `config/briefing.json` 中 `trigger_thresholds`，按 `references/analysis_rules.md` 的规则分为：

- **A 层**（必须详细分析）
- **B 层**（一句话简述）
- **C 层**（跳过）

### 7d. 生成 A 层分析

对每个 A 层标的，按以下链条生成分析：

```
一级因子：{今日主线相关的事件/数据}
传导机制：{为什么影响该类资产}
个股映射：{为什么具体影响这只标的，业务关联/敞口}
```

**硬规则：**
- 必须能回溯到 Step 5 的主线
- 如果该标的的波动与主线无关，且找不到独立的一级因子 → 降级为 B 层或 C 层
- 不使用 `references/analysis_rules.md` 中列出的禁止归因模式

### 7e. 标注置信度

| 等级 | 输出标记 |
|------|---------|
| 高 | （不标注，默认即高） |
| 中 | `[间接推断]` |
| 低 | 不输出 |

---

## Step 8: 输出播报

### 判定播报模式

根据当前时间（北京时间）：
- 06:00-10:00 → 美股盘后复盘 + 港股前瞻
- 16:00-18:00 → 港股收盘 + 美股前瞻
- 周末 → 一周回顾 + 下周日历
- 其他时间或用户手动触发 → 根据最近收盘的市场播报

### 完整模式输出

```markdown
## {市场}播报 | {日期}

### 1. 今日主线
> {一句话定调} —— {证据来源}

### 2. 宏观关键信号

| 指标 | 当前值 | 变动 | 与主线的关系 |
|------|--------|------|-------------|
（只列与今日主线最相关的 3-5 项）

### 3. 重要新闻

- [{来源}] {标题/摘要} → {对市场的影响}
- [{来源}] ...
（2-4 条，一级源优先）

### 4. 持仓与关注

#### 值得关注的标的

**{TICKER} {涨跌幅}**
- 一级因子：...
- 传导机制：...
- 个股映射：...

**{TICKER} {涨跌幅}** [间接推断]
- ...

（A 层详细，B 层一句话）

#### 其余标的
> {skip_message}

### 5. 下一时段关注

- {最值得关注的 1-2 个变量}
- {来自 PKS 活跃叙事的风险因素}

---
*数据来源：yfinance / 腾讯财经 / Binance | 新闻来源：{列出使用的来源}*
*市场认知连续性：PKS market-context | 本报告不构成投资建议*
```

### 紧凑模式（cron 触发）

```markdown
## {市场}速报 | {日期}

> **主线**：{一句话}

| 指标 | 值 | 变动 |
（3-4 项关键数据）

**异动持仓**：
- {TICKER} {涨跌幅}：{一句话归因}
（最多 3 条 A 层）

**关注**：{下一时段变量}
```

---

## Reference Files

- `references/analysis_rules.md` — 主线检测标准、触发阈值、归因证据链规范、报告结构模板
- `references/narrative_modeling.md` — PKS 中市场叙事的建模约定、标准命名、生命周期管理
- `references/macro_indicators.md` — 宏观指标解读
- `references/macro_data_guide.md` — 经济数据影响机制
- `../my-stocks/references/data_sources.md` — yfinance / 腾讯财经 / Binance API 参考
