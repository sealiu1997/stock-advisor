# Stock Advisor

基于 [Agent Skills](https://github.com/anthropics/agent-skills) 开放标准的智能股票分析助手，面向 Hermes / OpenClaw 等 AI Agent 平台。

> **声明：** 本项目仅供研究和教育目的，不构成投资建议。所有分析输出仅为参考，不执行任何交易操作。

## 架构概览

系统分为**后台信息管理**和**前台交互技能**两部分：

```
┌───────────────────────────────────────────────────────────────┐
│  market_watcher (后台守护进程, launchd)                         │
│  持续采集 → 影响评分 → 宏观评估 → 主题检测 → 写入 PKS → 唤醒通知  │
│                                                               │
│  数据源: FRED / Jin10 MCP / RSS / yfinance                     │
│  分析层: overview(宏观信号) / calendar(日历) / analyzer(主题)     │
│  存储: PKS market-context 胶囊                                  │
│  通知: 唤醒 Hermes → Hermes 分析 → 飞书推送                      │
└─────────────────────┬─────────────────────────────────────────┘
                      │ 读取 PKS
┌─────────────────────▼─────────────────────────────────────────┐
│  Hermes Agent Skills (前台交互, 飞书对话)                        │
│                                                               │
│  daily-briefing    读 PKS + 实时补充 → 主线驱动的深度播报          │
│  my-stocks         查持仓行情 / 浮动盈亏                         │
│  stock-valuation   个股估值 (DCF / 相对估值 / SOTP)              │
│  earnings-analysis 财报分析                                     │
│  source-feed       信息源博主动态扫描                             │
└───────────────────────────────────────────────────────────────┘
```

**核心理念：** market_watcher 是信息管理系统，负责所有重活（采集、评分、主题检测、叙事管理）。daily-briefing 等 skills 是薄展示层，主要从 PKS 读取已加工好的信息，只做轻量级实时补充。

## 功能一览

| 插件组 | Skill | 说明 |
|---|---|---|
| **portfolio-tracker** | `daily-briefing` | 智能每日播报 + 市场认知管理 — 主线驱动，证据链，PKS 认知连续性 |
| | `my-stocks` | 轻量级持仓数据查看 — 港美股 + 加密货币行情和盈亏 |
| **market-analysis** | `stock-valuation` | 个股估值 — DCF + 相对估值 + SOTP，敏感性分析 |
| | `earnings-analysis` | 财报分析 — 前瞻/复盘模式，批量财报季概览 |
| **source-readers** | `source-manager` | 信息源管理 — 给一个博主 URL，自动识别平台并追踪 |
| | `source-feed` | 信息源聚合 — 定期扫描追踪源，去重、关联持仓、汇总分析 |

> 大盘综述、经济日历、财经新闻、社交情绪等功能已整合进 market_watcher 后台，不再作为独立 skill。

## 安装部署

### 前置条件

- macOS (Mac mini 部署)
- Python 3.10+
- [PKS](https://github.com/sealiu1997/personal_knowledge_state) — 市场认知持久化
- Hermes / OpenClaw — Agent 平台（连接飞书）

### Step 1: 克隆与安装依赖

```bash
git clone <repo-url> ~/stock-advisor
cd ~/stock-advisor
pip install -r requirements.txt
```

### Step 2: 安装 PKS

如果 Mac mini 上还没有 PKS：

```bash
git clone https://github.com/sealiu1997/personal_knowledge_state ~/personal_knowledge_state
cd ~/personal_knowledge_state && pip install -e .
pks init-home
```

初始化 market-context 胶囊：

```bash
pks new market-context --type MarketContext --domain research
```

### Step 3: 配置

```bash
cp config/watcher.example.json config/watcher.json
```

编辑 `config/watcher.json`，填写以下必填项：

| 配置项 | 说明 | 获取方式 |
|--------|------|---------|
| `fred.api_key` | FRED 宏观经济数据 | [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/api_key.html) 免费注册 |
| `jin10.bearer_token` | Jin10 财经快讯 MCP | Jin10 MCP 服务申请 |
| `notification.hermes.hermes_dir` | Hermes 安装目录 | 填写 Mac mini 上 Hermes 的实际路径 |
| `notification.hermes.hermes_cmd` | Hermes CLI 命令 | 默认 `hermes run`，根据实际安装调整 |

其他配置文件（按需编辑）：

- `config/portfolio.json` — 持仓标的、数量、成本价
- `config/watchlist.json` — 关注但未持仓的标的
- `config/briefing.json` — 播报触发阈值、新闻源分层、驱动因素类型
- `config/sources.json` — 追踪的博主和信息源

### Step 4: 测试数据源

逐个测试，确保 API 连通：

```bash
PYTHONPATH=scripts python3 -m market_watcher test fred          # FRED 宏观数据
PYTHONPATH=scripts python3 -m market_watcher test jin10         # Jin10 快讯
PYTHONPATH=scripts python3 -m market_watcher test jin10-calendar # Jin10 经济日历
PYTHONPATH=scripts python3 -m market_watcher test rss           # RSS 新闻
PYTHONPATH=scripts python3 -m market_watcher test price         # 价格异动检测
PYTHONPATH=scripts python3 -m market_watcher test overview      # 宏观信号评估
```

### Step 5: 运行完整扫描

```bash
PYTHONPATH=scripts python3 -m market_watcher scan
```

预期输出：events > 0, signals > 0, errors 为空。

### Step 6: 测试 Hermes 唤醒（可选）

确认 `hermes_dir` 配置后，手动测试通知通路：

```bash
# 先测试 Hermes 本身能否被唤醒
cd /path/to/hermes && hermes run --prompt "测试消息，请回复收到"

# 再测试完整通知链路
PYTHONPATH=scripts python3 -c "
from market_watcher.trigger import notify_agent
import json
with open('config/watcher.json') as f:
    cfg = json.load(f)
events = [{'type': 'test', 'level': 'critical', 'description': '测试通知'}]
notify_agent(events, cfg)
"
```

### Step 7: 部署为 launchd 守护进程

```bash
# 编辑 plist 中的路径（如果安装位置不同）
vim deploy/com.stockadvisor.market-watcher.plist

# 安装并启动
cp deploy/com.stockadvisor.market-watcher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.stockadvisor.market-watcher.plist

# 查看日志
tail -f data/watcher.log
```

### Step 8: 在 Hermes 中安装插件

将 `plugins/` 目录注册到 Hermes 的 skill 搜索路径。具体方式取决于 Hermes 的配置，通常是将路径加入 Hermes 的 `skills_dirs` 或建立符号链接。

安装后 Hermes 会自动发现所有 SKILL.md，用户即可通过飞书对话触发。

## 使用方式

### 用户通过飞书对 Hermes 说

| 对话内容 | 匹配 Skill | 说明 |
|---------|-----------|------|
| "今日播报" / "daily briefing" / "今天市场怎么样" | daily-briefing | 主线驱动的深度播报 |
| "早报" / "晚报" / "收盘报" | daily-briefing | 按时段自动选择播报模式 |
| "目前有哪些活跃叙事" / "market context" | daily-briefing (认知管理) | 查看 PKS 中的市场叙事 |
| "这个叙事过期了" / "加一个新观点" | daily-briefing (认知管理) | 修正/新增/过期叙事 |
| "我的股票怎么样" / "持仓盈亏" | my-stocks | 拉行情、算盈亏 |
| "帮我估值一下 NVDA" | stock-valuation | DCF / 相对估值 |
| "TSLA 财报分析" | earnings-analysis | 财报数据解读 |
| "信息源更新了什么" | source-feed | 博主动态扫描 |

### market_watcher 自动推送

当 market_watcher 检测到 Critical/High 级别事件时，自动唤醒 Hermes：

```
watcher 检测到异动 (如 VIX > 30)
    → 写入 PKS
    → 唤醒 Hermes，传递事件摘要
        → Hermes 读取 PKS，分析影响，结合持仓
        → Hermes 通过飞书推送给用户
```

watcher 只负责"叫醒" Hermes 并告知发生了什么，消息的组织、分析和发送完全由 Hermes 自主完成。

### market_watcher CLI

```bash
PYTHONPATH=scripts python3 -m market_watcher <command>

run         启动守护循环（生产模式）
scan        运行一次完整扫描
status      查看各数据源最后扫描时间
context     查看 PKS 中的完整市场认知
narratives  查看活跃叙事
health      PKS 健康检查
maintain    手动触发 PKS 维护
test <src>  测试单个数据源 (fred/jin10/jin10-calendar/rss/price/overview)
```

## Market Watcher 扫描周期

| 数据源 | 频率 | 采集内容 |
|--------|------|---------|
| Jin10 MCP 快讯 | 10 分钟 | 中文财经快讯（美联储、非农、CPI 等突发） |
| yfinance 价格 | 15 分钟 | VIX / 美债 / 美元 / 黄金 / 原油 / 铜 / 主要指数 |
| RSS 新闻 | 30 分钟 | CNBC / MarketWatch / Seeking Alpha |
| FRED API | 60 分钟 | 14 个美国宏观序列（CPI/NFP/GDP/PCE/失业率等） |
| PKS 维护 | 6 小时 | 过期清理、证据校验 |

每次扫描的处理流水线：

```
采集 → 评分(Critical/High/Medium/Low) → 宏观信号评估 → 主题检测 → 叙事管理 → 写入PKS → 通知
```

## 项目结构

```
stock-advisor/
├── scripts/
│   └── market_watcher/                # 后台信息管理系统
│       ├── sources/                   # 数据采集层
│       │   ├── fred.py                #   FRED 宏观经济 API
│       │   ├── jin10.py               #   Jin10 MCP 财经快讯
│       │   ├── rss.py                 #   RSS 新闻聚合
│       │   └── price.py               #   yfinance 价格异动
│       ├── core/                      # 分析层
│       │   ├── overview.py            #   宏观信号评估 (VIX/利率/美元/商品/指数)
│       │   ├── calendar.py            #   经济日历监控
│       │   └── analyzer.py            #   主题检测 + 叙事生命周期
│       ├── daemon.py                  # 主调度循环
│       ├── scorer.py                  # 4 级影响评分引擎
│       ├── trigger.py                 # Hermes 唤醒通知
│       ├── pks.py                     # PKS 读写接口
│       └── __main__.py                # CLI 入口
├── config/
│   ├── portfolio.json                 # 持仓配置
│   ├── watchlist.json                 # 关注列表
│   ├── briefing.json                  # 播报配置
│   ├── sources.json                   # 信息源追踪
│   ├── events.json                    # 宏观事件配置
│   ├── watcher.example.json           # watcher 配置模板
│   └── watcher.json                   # watcher 配置 (gitignored, 含 API key)
├── plugins/
│   ├── portfolio-tracker/             # 持仓追踪与智能播报
│   │   └── skills/
│   │       ├── daily-briefing/        #   主线驱动播报 + 市场认知管理
│   │       └── my-stocks/             #   轻量持仓数据查看
│   ├── market-analysis/               # 市场分析
│   │   └── skills/
│   │       ├── stock-valuation/       #   个股估值
│   │       └── earnings-analysis/     #   财报分析
│   └── source-readers/                # 信息源管理
│       └── skills/
│           ├── source-manager/        #   信息源追踪管理
│           └── source-feed/           #   信息源聚合扫描
├── deploy/
│   └── *.plist                        # macOS launchd 部署配置
├── data/                              # 运行时数据 (gitignored)
├── DESIGN.md                          # 完整产品设计文档
└── README.md
```

## 数据源

| 类型 | 主数据源 | 降级路径 | 需要 API Key |
|---|---|---|---|
| 美股行情 | yfinance | — | 否 |
| 港股行情 | 腾讯财经 API | yfinance (.HK) | 否 |
| 加密货币 | Binance 公开 API | — | 否 |
| 外汇/商品 | yfinance | — | 否 |
| 宏观经济 | FRED API | — | 是 (免费) |
| 财经快讯 | Jin10 MCP | — | 是 |
| 新闻 | RSS (CNBC/MarketWatch) | yfinance | 否 |
| 博主追踪 | OpenCLI | RSS / 公开 API | 否 |

## 设计文档

详见 [DESIGN.md](DESIGN.md)。

## License

MIT
