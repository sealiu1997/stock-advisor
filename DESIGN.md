# Stock Advisor — 产品设计文档

> 基于 Agent Skills 开放标准的智能股票分析助手，面向 Hermes / OpenClaw 等 AI Agent 平台。

---

## 1. 产品定位

**Stock Advisor** 是一套模块化的 Agent Skills，旨在将"股票行情播报"升级为"有分析深度的投资助手"。

**核心价值主张：**
- 不只是看价格 — 提供估值、财报、宏观等多维度分析
- 不只是被动查询 — 定时主动播报，关键事件节点自动预警
- 不只是单一数据源 — 聚合行情、新闻、社交情绪等多信源
- 不只是固定模板 — 可扩展架构，随时加入新的分析模块和信息源

**目标用户：** 个人投资者（本项目作者），港美股 + 加密货币为主，关注宏观经济走势和个股基本面。

**重要声明：** 本项目仅供研究和教育目的，不构成投资建议。所有分析输出仅为参考，不执行任何交易操作。

---

## 2. 系统架构

### 2.1 整体结构

```
stock-advisor/
├── .claude-plugin/
│   └── marketplace.json              # 插件市场注册（Claude 生态）
│
├── plugins/                           # 所有 skill 按插件组组织
│   ├── portfolio-tracker/             # 插件组 1: 持仓追踪与智能播报
│   │   ├── plugin.json
│   │   └── skills/
│   │       ├── my-stocks/             # 轻量级持仓数据查看
│   │       │   ├── SKILL.md
│   │       │   └── references/
│   │       ├── daily-briefing/        # 主线驱动的智能每日播报 (v2)
│   │       │   ├── SKILL.md
│   │       │   └── references/
│   │       │       ├── analysis_rules.md      # 分析规则引擎
│   │       │       └── narrative_modeling.md   # PKS 叙事建模约定
│   │       └── market-context/        # 市场认知状态管理
│   │           └── SKILL.md
│   │
│   ├── market-analysis/               # 插件组 2: 市场分析
│   │   ├── plugin.json
│   │   └── skills/
│   │       ├── market-overview/       # 大盘综述与宏观概览
│   │       ├── stock-valuation/       # 个股估值 (P2)
│   │       ├── earnings-analysis/     # 财报分析 (P2)
│   │       └── event-calendar/        # 经济事件日历与节点播报
│   │
│   ├── news-sentiment/                # 插件组 3: 新闻与情绪 (P3)
│   │   ├── plugin.json
│   │   └── skills/
│   │       ├── market-news/           # 财经新闻抓取与解读
│   │       └── stock-sentiment/       # 社交媒体情绪分析
│   │
│   └── source-readers/                # 插件组 4: 信息源管理与聚合 (P3)
│       ├── plugin.json
│       └── skills/
│           ├── source-manager/        # 信息源管理（添加/删除/列表博主追踪）
│           │   └── references/
│           │       └── platform_adapters.md  # 平台 URL 解析 + OpenCLI 命令映射
│           └── source-feed/           # 信息源聚合阅读（定期扫描 + 汇总分析）
│
├── config/                            # 用户个人配置
│   ├── portfolio.json                 # 实盘持仓
│   ├── watchlist.json                 # 关注列表
│   ├── events.json                    # 关注的宏观事件
│   ├── sources.json                   # 关注的博主/信息源 (P3)
│   └── briefing.json                  # 播报配置：触发阈值、新闻源分层、输出偏好 (v2)
│
└── legacy_reference/                  # 旧版代码，仅供参考
```

### 2.2 技术栈选型

| 层面 | 选型 | 理由 |
|---|---|---|
| Skill 标准 | Agent Skills (SKILL.md) | 开放标准，Hermes / Claude Code / OpenClaw 均支持 |
| 运行时代码 | Python 3.9+ | yfinance 生态最完整，agent 内联执行 |
| 行情数据 | yfinance (主) + 腾讯财经 (港股备用) + Binance (加密) | 免费、无需 API key、覆盖港美股+加密 |
| 经济日历 | yfinance `.calendar` + `references/` 静态日程 | 财报日动态抓取，央行日程静态维护 |
| 新闻数据 | yfinance `.news` (主) + OpenCLI 财经媒体 (增强) | 免费，多源覆盖中英文 |
| 社交/情绪 | OpenCLI (Reddit/Twitter/雪球) (主) + Reddit JSON API (降级) | OpenCLI 复用真实浏览器会话，规避反爬 |
| 博主追踪 | OpenCLI (12+ 平台) (主) + RSS/公开API (降级) | 统一管理，config/sources.json 驱动 |
| 配置格式 | JSON | 简单直观，agent 可直接读写 |

### 2.3 Skill 协作模式

Skills 之间不硬编码依赖，而是通过**共享配置文件**松耦合：

```
config/portfolio.json  ──→  my-stocks (读取持仓)
                       ──→  event-calendar (读取持仓以查询财报日)
                       ──→  earnings-analysis (读取持仓以分析财报)

config/watchlist.json  ──→  my-stocks (读取关注列表)
                       ──→  market-overview (读取关注列表以筛选板块)

config/events.json     ──→  event-calendar (读取关注事件清单)

config/sources.json    ──→  source-manager (管理关注源)
                       ──→  source-feed (扫描并聚合关注源动态)
                       ──→  market-news (读取关注源以发现新闻)
                       ──→  stock-sentiment (读取关注源以采集情绪)
```

---

## 3. Skill 详细设计

### 3.1 my-stocks — 持仓行情播报

**触发场景：** "我的股票怎么样"、"查看行情"、"盈亏情况"、"持仓播报"、定时早/晚报

**核心能力：**
1. 读取 `config/portfolio.json` 和 `config/watchlist.json`
2. 通过 yfinance / 腾讯财经 / Binance 批量抓取实时行情
3. 计算持仓盈亏（支持成本价录入）
4. 根据当前时间自动判断播报模式（美股早报 / 港股晚报 / 周末加密特报）
5. 异动告警（股票 >=3%、加密 >=5%）
6. 基于行情数据给出简要市场点评

**输出格式：**
```
## 美股早报 | 2026-06-18 08:00

### 持仓盈亏
| 标的 | 现价 | 涨跌幅 | 持仓 | 市值 | 日盈亏 |
...

### 关注列表速览
| 标的 | 现价 | 涨跌幅 | 备注 |
...

### 异动告警
- 暴涨 xxx +5.2%
- 暴跌 yyy -4.1%

### 市场点评
（agent 基于数据生成的简要分析）
```

**数据源优先级：**
- 美股：yfinance (Yahoo Finance API) → Stooq (降级)
- 港股：腾讯财经 API → yfinance (`.HK` 后缀)
- 加密货币：Binance 公开 API
- 外汇/商品：yfinance

---

### 3.2 market-overview — 大盘综述

**触发场景：** "大盘怎么样"、"市场概况"、"宏观分析"、"今天行情如何"

**核心能力：**
1. 抓取全球主要指数：标普 500、纳指、道指、恒指、上证、日经
2. 抓取宏观指标：VIX 恐慌指数、10Y 美债收益率、美元指数 (DXY)、黄金、原油
3. 板块热力图：美股 11 大 GICS 板块 ETF 涨跌一览
4. 资金流向信号：主要 ETF 成交量异常检测
5. 综合市场情绪评估 + 短期展望

**关键数据标的 (hardcoded in references)：**

| 类别 | 代码 | 说明 |
|---|---|---|
| 美股指数 | ^GSPC, ^IXIC, ^DJI | 标普/纳指/道指 |
| 亚太指数 | ^HSI, 000001.SS, ^N225 | 恒指/上证/日经 |
| 恐慌指数 | ^VIX | CBOE 波动率 |
| 美债 | ^TNX, ^FVX | 10Y/5Y 国债收益率 |
| 美元 | DX-Y.NYB | 美元指数 |
| 商品 | GC=F, CL=F | 黄金/原油期货 |
| 板块 ETF | XLK, XLF, XLE, XLV... | 11 大 GICS 板块 |

**输出格式：**
```
## 全球市场概览 | 2026-06-18

### 主要指数
| 指数 | 点位 | 涨跌幅 | 趋势 |
...

### 宏观风向标
| 指标 | 当前值 | 变动 | 信号 |
| VIX  | 18.5   | -1.2 | 市场平稳 |
| 10Y  | 4.25%  | +3bp | 利率微升 |
...

### 板块热力图
| 板块 | ETF | 涨跌幅 | 强弱 |
...

### 市场情绪综合评估
（agent 基于以上数据的综合分析：贪婪/恐惧/中性、主要驱动因素、短期展望）
```

---

### 3.3 event-calendar — 经济事件日历

**触发场景：** "近期有什么重要数据"、"美联储什么时候开会"、"我的股票什么时候发财报"、"本周经济日历"、定时自动检测

**核心能力：**

#### A. 宏观经济事件
1. 读取 `config/events.json` 获取用户关注的宏观事件类型
2. 读取 `references/fed_schedule.md` 获取美联储年度日程
3. 抓取近期经济数据发布日历（investing.com 或静态维护）
4. **事前预警**：数据发布前 N 小时（可配置），输出：
   - 事件名称与发布时间
   - 上期值、市场预期值
   - 历史数据趋势（近 6 期）
   - 如果高于/低于预期可能的市场影响分析
5. **事后解读**：数据发布后，抓取实际值，分析偏差

#### B. 个股财报日
1. 读取 `config/portfolio.json` 遍历所有持仓
2. 通过 yfinance `ticker.calendar` 获取下次财报日期
3. 财报发布前 2 天发出预警：
   - 分析师预期 EPS/营收
   - 前几季的 beat/miss 记录
   - 期权隐含波动率（如果可用）
4. 财报发布后提供实际 vs 预期对比

#### C. 数据结构

**config/events.json:**
```json
{
  "macro_events": [
    {
      "name": "CPI (美国消费者物价指数)",
      "id": "us_cpi",
      "importance": "high",
      "alert_hours_before": 12,
      "description": "衡量通胀水平的核心指标，直接影响美联储加息/降息决策"
    },
    {
      "name": "Non-Farm Payrolls (非农就业)",
      "id": "us_nfp",
      "importance": "high",
      "alert_hours_before": 12,
      "description": "美国就业市场健康度的关键指标"
    },
    {
      "name": "FOMC Rate Decision (美联储利率决议)",
      "id": "fomc_rate",
      "importance": "critical",
      "alert_hours_before": 24,
      "description": "直接决定利率走向，影响所有资产定价"
    },
    {
      "name": "PMI (采购经理人指数)",
      "id": "us_pmi",
      "importance": "medium",
      "alert_hours_before": 6
    },
    {
      "name": "GDP (国内生产总值)",
      "id": "us_gdp",
      "importance": "high",
      "alert_hours_before": 12
    },
    {
      "name": "Initial Jobless Claims (初请失业金)",
      "id": "us_jobless",
      "importance": "medium",
      "alert_hours_before": 6
    }
  ],
  "earnings_alert_days_before": 2
}
```

**references/fed_schedule.md** (每年年初手动更新)：
```
# 2026 FOMC Meeting Schedule

| Meeting | Date | Type |
|---|---|---|
| 1 | Jan 27-28 | Regular |
| 2 | Mar 17-18 | SEP + Dot Plot |
| ... |
```

**输出格式（事前预警）：**
```
## 经济事件预警 | CPI 数据将于明日发布

### 事件信息
- 发布时间：2026-06-19 20:30 (北京时间)
- 重要性：高

### 市场预期
- 上期值 (5月): 3.2% (YoY)
- 市场预期 (6月): 3.1% (YoY)
- 核心 CPI 预期: 3.4% (YoY)

### 历史趋势
| 月份 | CPI (YoY) | 核心 CPI | 预期偏差 |
| 1月  | 3.0%      | 3.3%     | +0.1%    |
...

### 场景分析
- 若低于预期 (<3.0%): 利好股市，降息预期升温...
- 若符合预期 (3.1%): 市场影响有限...
- 若高于预期 (>3.2%): 市场承压，利率敏感资产下跌...

### 对你持仓的潜在影响
- TQQQ (三倍做多纳指): CPI 超预期将导致剧烈波动，注意风险
- GLD (黄金 ETF): 通胀高于预期利好黄金
...
```

---

## 4. 定时播报机制

### 4.1 场景化播报时间表

| 时段 | 触发时间 | 播报内容 | 触发 Skills |
|---|---|---|---|
| 美股盘后复盘 | 工作日 08:00 (北京) | 隔夜美股表现 + 持仓盈亏 + 今日港股展望 | my-stocks + market-overview |
| 港股收盘总结 | 工作日 17:00 (北京) | 港股收盘 + 持仓盈亏 + 今晚美股前瞻 | my-stocks + market-overview |
| 事件预警 | 事件前 N 小时 | 针对性的事件背景和影响分析 | event-calendar |
| 财报预警 | 财报前 2 天 | 分析师预期 + 历史表现 | event-calendar |
| 周末复盘 | 周六 10:00 | 本周回顾 + 加密市场 + 下周日历 | my-stocks + market-overview + event-calendar |

### 4.2 平台对接方式

**Hermes (推荐):**
- 使用 Hermes 的 Routine/Schedule 功能设置定时任务
- 每个时段对应一条 prompt，例如：
  ```
  "[美股早报] 请执行 my-stocks 和 market-overview 技能，以美股早报模式输出"
  ```

**OpenClaw:**
- 通过 OpenClaw 的定时触发配置（cron 语法）
- 触发消息与 Hermes 类似

**Claude Code:**
- 使用 `/schedule` 功能设置 cron 任务
- 或手动触发："帮我看看今天的行情"

---

## 5. 配置文件设计

### 5.1 portfolio.json — 实盘持仓

```json
{
  "HK": [
    {
      "symbol": "1810",
      "name": "小米集团",
      "holdings": 1000,
      "cost_price": 32.50,
      "currency": "HKD"
    }
  ],
  "US": [
    {
      "symbol": "GOOG",
      "name": "谷歌",
      "holdings": 10,
      "cost_price": 170.00,
      "currency": "USD"
    }
  ],
  "CRYPTO": [
    {
      "symbol": "BTCUSDT",
      "name": "比特币",
      "holdings": 0.5,
      "cost_price": 60000
    }
  ]
}
```

**相比旧版改进：**
- 新增 `cost_price` 字段，支持计算浮动盈亏
- 新增 `currency` 字段，支持汇率换算
- 美股 symbol 去掉 `.US` 后缀（yfinance 原生格式）
- 港股统一为数字格式（腾讯接口），yfinance 查询时自动补 `.HK`

### 5.2 watchlist.json — 关注列表

结构同旧版，但 symbol 格式与 portfolio.json 对齐。

### 5.3 events.json — 宏观事件配置

见上方 3.3 节。

### 5.4 sources.json — 信息源配置 (P3)

```json
{
  "sources": [
    {
      "id": "twitter-wallstreetcn",
      "platform": "twitter",
      "handle": "WallStreetCN",
      "label": "华尔街见闻",
      "category": "news",
      "url": "https://x.com/WallStreetCN",
      "fetch": {
        "opencli": {"adapter": "twitter", "action": "timeline", "target": "@WallStreetCN"},
        "fallback": null
      },
      "added_at": "2026-06-18T00:00:00Z",
      "last_scanned": null,
      "enabled": true
    }
  ],
  "scan_settings": {
    "default_limit": 10,
    "max_age_hours": 48,
    "dedup_window_hours": 72
  }
}
```

**相比旧版改进：**
- 所有平台统一为 `sources[]` 数组，而非按平台分组
- 每个源携带结构化 `fetch` 配置（`opencli` 主路径 + `fallback` 降级路径），运行时由白名单 dispatcher 拼装命令，避免任意 shell 执行
- `source-manager` skill 负责 URL → 标准化条目的自动转换
- 支持 12+ 平台：Twitter, Reddit, YouTube, 微博, 小红书, 雪球, 知乎, B站, Substack, Medium, LinkedIn, RSS

---

## 6. 数据源与 API 设计

### 6.1 数据源矩阵

| 数据类型 | 主数据源 | 备用数据源 | 需要 API Key |
|---|---|---|---|
| 美股行情 | yfinance | Stooq | 否 |
| 港股行情 | 腾讯财经 (qt.gtimg.cn) | yfinance (.HK) | 否 |
| 加密货币 | Binance 公开 API | CoinGecko | 否 |
| 外汇/商品 | yfinance | — | 否 |
| 财务报表 | yfinance | — | 否 |
| 分析师预期 | yfinance | — | 否 |
| 财报日期 | yfinance `.calendar` | — | 否 |
| 新闻 | yfinance `.news` + OpenCLI 财经站 | RSS | 否 |
| 社交情绪 | OpenCLI (Reddit/Twitter/雪球) | Reddit JSON API | 否 |
| 博主追踪 | OpenCLI (12+ 平台) | RSS / 公开 API | 否 |
| 经济日历 | 静态维护 + investing.com | — | 否 |

### 6.2 降级策略

每个数据获取步骤都遵循统一的降级模式：

```
主数据源 → 备用数据源 → 缓存数据(标注时效) → 明确提示"数据不可用"
```

SKILL.md 中通过 Step 1 检测流程实现：先检测可用工具，再决定走哪条数据路径。

---

## 7. 交付计划

### Phase 1 — 核心可用（当前阶段）

| 交付物 | 说明 |
|---|---|
| 项目骨架 | 目录结构、plugin.json、marketplace.json、config 文件 |
| my-stocks SKILL.md | 持仓播报，替换旧版 finance_spy.py |
| market-overview SKILL.md | 大盘综述，全新能力 |
| event-calendar SKILL.md | 经济事件日历，全新能力 |
| references/ 文件 | 数据源参考、美联储日程、宏观指标字典等 |

**P1 完成后可实现：**
- 每日定时播报持仓行情 + 大盘分析
- 关键宏观数据发布前自动预警
- 持仓个股财报日自动提醒
- 手动查询任意时刻的市场概况

### Phase 2 — 分析深度

| 交付物 | 说明 |
|---|---|
| stock-valuation SKILL.md | DCF + 相对估值 + 敏感性分析 |
| earnings-analysis SKILL.md | 财报前瞻与复盘 |

### Phase 3 — 信息广度（OpenCLI 驱动）

| 交付物 | 说明 |
|---|---|
| source-manager SKILL.md | 信息源管理：用户给一个 URL，自动识别平台并加入追踪列表 |
| source-feed SKILL.md | 信息源聚合阅读：定期扫描追踪源，汇总、去重、分析 |
| market-news SKILL.md | 财经新闻抓取与影响分析（yfinance + OpenCLI 双通道） |
| stock-sentiment SKILL.md | 社交媒体情绪分析（Reddit/Twitter/雪球多平台） |
| platform_adapters.md | 12+ 平台的 URL 解析正则 + OpenCLI 命令映射 + 降级路径 |
| news_sources.md | 新闻源权威性评级 + OpenCLI 财经媒体命令 |
| sources.json | 重构后的统一信息源配置 |

### Phase 4 — 认知连续性（PKS 集成）

| 交付物 | 说明 |
|---|---|
| daily-briefing SKILL.md | 主线驱动的智能播报，替代定时场景中的 my-stocks |
| market-context SKILL.md | PKS 市场认知层的查看、修正、管理 |
| analysis_rules.md | 分析规则引擎：主线检测、触发阈值、证据链标准、报告结构 |
| narrative_modeling.md | PKS 中市场叙事的建模约定：命名、层级、生命周期 |
| briefing.json | 播报配置：驱动因素、触发阈值、新闻源分层、输出偏好 |

**P4 完成后可实现：**
- 每次播报先定主线，再筛标的，围绕主题展开有证据链的分析
- 市场认知跨会话持久化（叙事、数据事实、传导逻辑）
- 港股早报自动继承隔夜美股主线，无需重新推导
- 人类通过 PKS Dashboard 审计和修正 Agent 的市场判断
- 无证据的分析不输出，避免"站不住脚"的归因

---

## 8. P3 架构：OpenCLI 驱动的信息采集

### 8.1 OpenCLI 概述

[OpenCLI](https://github.com/jackwener/OpenCLI) 是一个通用 CLI 工具，通过 Chrome DevTools Protocol (CDP) + Browser Bridge 浏览器插件复用用户的真实浏览器会话，将 300+ 网站的内容桥接到终端。核心优势：

- **规避反爬**：复用已登录的浏览器 session，不是模拟请求
- **统一接口**：`opencli <platform> <action> [args] -f json` 标准化输出
- **覆盖广**：Twitter, Reddit, YouTube, 微博, 小红书, 雪球, 知乎, B站, Substack, Medium, LinkedIn 等

### 8.2 信息源管理工作流

```
用户给一个博主 URL
        │
        ▼
  source-manager skill
   ├── URL 正则解析 → 识别平台 + 提取 handle
   ├── opencli <platform> profile <handle> → 获取博主信息
   └── 写入 config/sources.json（标准化条目）
        │
        ▼
  source-feed skill（定期触发）
   ├── 遍历 sources.json 中所有 enabled 的源
   ├── opencli <platform> timeline/posts <handle> → 拉取最新内容
   ├── 降级路径：fallback_cmd (RSS / 公开 API)
   ├── 去重 (dedup_window_hours) + 时效过滤 (max_age_hours)
   ├── 关联持仓/关注列表标的 → 标记高相关性内容
   └── 汇总输出：高相关 → 一般 → 观点提取 + 多空分歧
```

### 8.3 降级策略（P3 社交/新闻数据）

每个平台都有三级数据路径：

| 平台 | 主路径 (OpenCLI) | 降级路径 | 最终降级 |
|---|---|---|---|
| Twitter | `opencli twitter timeline/search` | 无 (需登录) | 标记不可用 |
| Reddit | `opencli reddit subreddit/search` | Reddit 公开 JSON API | 标记不可用 |
| YouTube | `opencli youtube channel` | YouTube RSS feed | 标记不可用 |
| 微博 | `opencli weibo user` | 无 | 标记不可用 |
| 雪球 | `opencli xueqiu user/search` | 无 | 标记不可用 |
| Substack | `opencli substack profile` | Substack RSS feed | 标记不可用 |
| Medium | `opencli medium user` | Medium RSS feed | 标记不可用 |
| RSS | 直接 curl 抓取 | — | 标记不可用 |

**OpenCLI 退出码约定：**
- `0`: 成功
- `66`: 结果为空（平台可用但无新内容）
- `69`: 浏览器不可用
- `77`: 需要认证

### 8.4 新闻与情绪采集架构

```
                    ┌──────────────┐
                    │ market-news  │── yfinance .news (主)
                    │   skill      │── OpenCLI 财经媒体 (增强)
                    └──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        去重/时效过滤   话题聚类    影响力评估
              │            │            │
              └────────────┼────────────┘
                           ▼
                   结构化新闻报告
                   (按话题分组 + 持仓影响标注)


                    ┌──────────────┐
                    │stock-sentiment│── OpenCLI Reddit (主)
                    │   skill      │── OpenCLI Twitter (主)
                    └──────────────┘── OpenCLI 雪球 (中文)
                           │         └─ yfinance .news (补充)
                           ▼
                    多空情绪标注 + 聚合
                    (关键词辅助 + 上下文理解)
                           │
                           ▼
                   情绪评分 (-100 ~ +100)
                   + 跨平台对比 + 核心论点提取
```

---

## 9. P4 架构：PKS 市场认知层

### 9.1 设计动机

P1-P3 的每次播报都是"无状态"的——相当于一个失忆的分析师每天重新看盘。
真正的分析师脑子里有一个持续更新的宏观图景：美联储处于什么周期、市场在交易什么叙事、哪些风险在累积。

P4 通过集成 [PKS (Personal Knowledge State)](https://github.com/sealiu1997/personal_knowledge_state) 解决这个问题。

### 9.2 核心概念映射

| PKS 概念 | 市场认知层对应 |
|---|---|
| Claim (factual) | 数据事实："2026-06 CPI 3.1% YoY" |
| Claim (inference) | 市场叙事："市场交易 disinflation → 降息预期" |
| Evidence | 来源标注：Bloomberg / BLS / Reuters |
| Supporting Claims | 证据链：叙事 ← 数据事实 |
| Lifecycle | 叙事状态：active → stale → expired / superseded |
| confidence | 分析置信度 0.0-1.0 |
| Capsule | MarketContext 胶囊 |

### 9.3 叙事建模层级

```
L0 数据事实 (factual)     "10Y yield fell 8bp to 4.17%"
      ↑ supports
L1 市场叙事 (inference)    "Disinflation trade: 市场定价 H2 降息 2-3 次"
      ↑ supports
L2 传导机制 (inference)    "长端利率下 → 成长股估值修复"
      ↑ supports
L3 持仓映射 (inference)    "GOOG/MSFT 受益; 黄金受益于实际利率下降"
```

每一层都可以独立验证、独立过期、独立被人类 dispute。

### 9.4 数据流

```
                      PKS (知识状态层)
                    ┌─────────────────────┐
                    │  MarketContext 胶囊   │
                    │  ┌─ factual claims   │◄── 数据事实（自动 accept）
                    │  ├─ inference claims │◄── 叙事 + 传导 + 影响
                    │  ├─ evidence refs    │◄── 新闻来源标注
                    │  └─ claim queries    │──► 宏观认知摘要
                    └────────┬────────────┘
                    CLI read/write│
                             │
    ┌────────────────────────┼────────────────────────┐
    │              daily-briefing skill                │
    │  1. 读 PKS claims → 获取活跃叙事和历史数据       │
    │  2. 抓新数据 + 新闻 → yfinance + OpenCLI         │
    │  3. 对比新旧 → 延续/更新/新增/过期叙事           │
    │  4. 写回 PKS → pks claim add/verify/supersede    │
    │  5. 基于活跃叙事 → 筛标的 → 主题化分析           │
    │  6. 输出播报                                     │
    └─────────────────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │  PKS Dashboard  │◄── 人类审计：review / dispute / correct
                    └─────────────────┘
```

### 9.5 连续性机制

- 周一早报写入 CPI 数据 + 降息叙事 → 存入 PKS
- 周二早报读取 PKS → 看到"降息叙事 active, confidence 0.85" → 延续分析
- 新数据支持 → `pks claim verify` 刷新，追加 evidence，confidence 上调
- 新数据矛盾 → `pks claim supersede`，建立新叙事
- 叙事超过 14 天未刷新 → PKS 自动标记 stale → Agent 下次播报时决定 verify 或 expire
- 人类打开 Dashboard → 审计本周所有 claim，修正不准的推断

### 9.6 播报架构变化

| | my-stocks (P1) | daily-briefing (P4) |
|---|---|---|
| 定位 | 数据查看 | 智能分析 |
| 分析方式 | 逐 ticker 平铺 | 主线驱动，有选择 |
| 证据 | 无要求 | 因子→传导→个股链条 |
| 连续性 | 无 | PKS 跨会话持久化 |
| 跳过机制 | 无（全部覆盖）| 低波动+无关主线 → 跳过 |
| 归因质量 | 可能硬凑 | 无证据则不输出 |

---

## 10. 扩展性设计

### 10.1 新增 Skill 的标准流程

1. 在对应 `plugins/<group>/skills/` 下新建目录
2. 编写 SKILL.md（frontmatter + 分步指令 + 引用 references）
3. 如有重型参考资料，放入 `references/` 子目录
4. 更新 `plugin.json` 的描述（可选）

无需修改任何其他 skill 或全局配置。

### 10.2 新增数据源的标准流程

1. 在 SKILL.md 的 Step 1 检测流程中加入新数据源的检测
2. 在 Decision Tree 中加入新路径
3. 将 API 文档放入 `references/` 供 agent 参考

### 10.3 新增信息源平台

1. 在 `source-manager/references/platform_adapters.md` 中添加新平台的 URL 正则和 OpenCLI 命令
2. `source-manager` skill 自动支持新平台的 URL 解析和追踪
3. `source-feed` skill 自动通过 `opencli_cmd` / `fallback_cmd` 拉取新平台内容
4. 无需新建 skill — 统一由 source-manager + source-feed 处理

---

## 11. 约束与原则

1. **只读原则**：所有 skill 均为只读，永远不执行交易操作
2. **免费优先**：优先使用免费数据源，付费 API 作为可选增强
3. **优雅降级**：任何数据源不可用时，明确标注而非静默失败
4. **时效透明**：所有数据必须标注时效（实时 / 延迟15分钟 / 昨日收盘 / 缓存）
5. **配置驱动**：持仓、关注列表、事件偏好等全部由 config/ 文件控制
6. **平台无关**：SKILL.md 标准格式，兼容 Hermes / Claude Code / OpenClaw
7. **风险声明**：每个分析 skill 的输出末尾附带投资风险提示
