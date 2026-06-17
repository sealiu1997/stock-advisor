# Stock Advisor

基于 [Agent Skills](https://github.com/anthropics/agent-skills) 开放标准的智能股票分析助手，面向 Hermes / OpenClaw / Claude Code 等 AI Agent 平台。

> **声明：** 本项目仅供研究和教育目的，不构成投资建议。所有分析输出仅为参考，不执行任何交易操作。

## 功能概览

| 插件组 | Skill | 说明 |
|---|---|---|
| **portfolio-tracker** | `my-stocks` | 持仓行情播报 — 港美股 + 加密货币，自动识别播报时段，异动告警 |
| **market-analysis** | `market-overview` | 大盘综述 — 全球指数、宏观指标、板块热力图、情绪评估 |
| | `event-calendar` | 经济事件日历 — FOMC/CPI/NFP 等事前预警 + 事后解读，持仓财报日提醒 |
| | `stock-valuation` | 个股估值 — DCF + 相对估值 + SOTP，敏感性分析，Bull/Base/Bear 场景 |
| | `earnings-analysis` | 财报分析 — 自动检测前瞻/复盘模式，批量财报季概览 |
| **news-sentiment** | `market-news` | 财经新闻 — yfinance + OpenCLI 双通道，话题聚类，持仓影响标注 |
| | `stock-sentiment` | 社交情绪 — Reddit/Twitter/雪球多平台采集，多空评分 -100~+100 |
| **source-readers** | `source-manager` | 信息源管理 — 给一个博主 URL，自动识别平台并加入追踪列表 |
| | `source-feed` | 信息源聚合 — 定期扫描追踪源，去重、关联持仓、汇总分析 |

## 项目结构

```
stock-advisor/
├── .claude-plugin/
│   └── marketplace.json           # 插件市场注册
├── config/
│   ├── portfolio.json             # 实盘持仓（港美股 + 加密）
│   ├── watchlist.json             # 关注列表
│   ├── events.json                # 宏观事件配置
│   └── sources.json               # 博主/信息源追踪列表
├── plugins/
│   ├── portfolio-tracker/         # 持仓追踪
│   ├── market-analysis/           # 市场分析（4 个 skill）
│   ├── news-sentiment/            # 新闻与情绪（2 个 skill）
│   └── source-readers/            # 信息源管理（2 个 skill）
└── DESIGN.md                      # 完整产品设计文档
```

每个 skill 目录包含：
- `SKILL.md` — 技能定义（YAML frontmatter + 分步指令）
- `references/` — 数据源 API 参考、指标解读等重型文档

## 数据源

| 类型 | 主数据源 | 降级路径 | 需要 API Key |
|---|---|---|---|
| 美股行情 | yfinance | Stooq | 否 |
| 港股行情 | 腾讯财经 API | yfinance (.HK) | 否 |
| 加密货币 | Binance 公开 API | — | 否 |
| 外汇/商品 | yfinance | — | 否 |
| 财务数据 | yfinance | — | 否 |
| 新闻 | yfinance + OpenCLI | RSS | 否 |
| 社交情绪 | OpenCLI (Reddit/Twitter/雪球) | Reddit JSON API | 否 |
| 博主追踪 | OpenCLI (12+ 平台) | RSS / 公开 API | 否 |

所有数据源均遵循 `主路径 → 降级路径 → 标记不可用` 的策略。

## 使用方式

### Hermes / OpenClaw

将 `stock-advisor/` 目录注册为 skill 目录，平台会自动发现所有 SKILL.md。通过 Routine/Schedule 功能设置定时播报。

### Claude Code

```bash
# 手动查询
"帮我看看今天的行情"           # → my-stocks
"大盘怎么样"                   # → market-overview
"近期有什么重要数据发布"        # → event-calendar
"帮我估值一下 NVDA"            # → stock-valuation
"TSLA 财报分析"                # → earnings-analysis
"最近有什么财经新闻"            # → market-news
"Reddit 上怎么看 AAPL"         # → stock-sentiment

# 信息源管理
"追踪这个博主 https://x.com/WallStreetCN"  # → source-manager
"看看我关注的博主最近说了什么"                # → source-feed
```

## 配置

编辑 `config/` 下的 JSON 文件来自定义：

- **portfolio.json** — 持仓标的、数量、成本价
- **watchlist.json** — 关注但未持仓的标的
- **events.json** — 关注的宏观事件类型及预警提前量
- **sources.json** — 追踪的博主和信息源

## 依赖

- **Python 3.9+** + `yfinance` — 行情与财务数据
- **[OpenCLI](https://github.com/jackwener/OpenCLI)**（可选）— 社交媒体和新闻采集，需配合 Chrome + Browser Bridge 插件

## 设计文档

详见 [DESIGN.md](DESIGN.md)，包含完整的架构设计、Skill 协作模式、定时播报机制、数据源矩阵和扩展性指南。

## License

MIT
