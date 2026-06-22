# Stock Advisor 改动计划：两层知识治理架构

> 源自试运行反馈清单 B1–B9。依赖 PKS P4 计划（A1–A6）。
>
> **Phase 1 状态: ✅ 已完成** (2026-06-22)
> - B1 两层架构 (MaterialStore + daemon 重构): ✅
> - B7 稳定去重 (sha256 stable_id): ✅
> - B4 Price signal 类型修正 (overview 写 material 不写 PKS): ✅

---

## 背景

试运行暴露的核心架构问题：market_watcher 把所有原始新闻（Jin10 flash、RSS、price snapshot、calendar）直接写成 PKS candidate，导致：

- candidate queue 膨胀至数百条/天
- WebUI Review 页不可用
- durable knowledge 被当日临时新闻淹没
- price move 被错误建模为 inference
- inference 由 keyword analyzer 自动大量生成，噪音大

## 目标架构：两层分离

```
Layer 1: Daily Raw Material (本地文件)
┌────────────────────────────────────────┐
│ data/daily_materials/YYYY-MM-DD/       │
│   raw_jin10.jsonl      # Jin10 快讯    │
│   raw_rss.jsonl        # RSS 新闻      │
│   raw_calendar.jsonl   # 经济日历      │
│   raw_prices.jsonl     # 价格快照      │
│   raw_overview.jsonl   # 宏观信号      │
│   selected_facts.json  # 日选 facts    │
│   selected_inferences.json             │
│   selection_report.json                │
│   briefing_context.md  # 播报上下文    │
└──────────────┬─────────────────────────┘
               │ daily selector (规则初筛 + agent 精选)
               ▼
Layer 2: Durable PKS Claims
┌────────────────────────────────────────┐
│ PKS market-context capsule             │
│   factual claims  <= 20/day            │
│   inference claims <= 5/day            │
│   有 valid_until / metadata / evidence │
│   可进入 projection / future briefing  │
└────────────────────────────────────────┘
```

## 分步实施

### Phase 1: 基础重构（优先级 P0）

#### B1 — 两层架构：raw material 与 durable claim 分离

**改动范围**：

1. **新增 `material.py`** — daily material 管理器
   - `MaterialStore` 类：按日期目录管理 JSONL 文件
   - `append(date, source, items)` — 追加原始数据
   - `load(date, source)` — 读取指定日期/源的数据
   - `list_dates()` — 列出所有日期目录
   - `cleanup(keep_days=7)` — 清理过期材料

2. **修改 `daemon.py`** — 扫描结果写入 material 而非 PKS
   - Jin10 flash → `raw_jin10.jsonl`
   - RSS → `raw_rss.jsonl`
   - Calendar → `raw_calendar.jsonl`
   - Price/Overview → `raw_prices.jsonl` / `raw_overview.jsonl`
   - 扫描后不再调用 `pks.py` 写入 candidate

3. **修改 `pks.py`** — 只由 daily selector 调用
   - 移除 `write_market_event()` 等直接写入函数
   - 新增 `write_selected_fact()` 和 `write_selected_inference()`
   - 每条写入必须带 `valid_until` + `metadata` + `evidence`

**验收**：
- 一天 500 条 raw news 不会产生 500 PKS candidate
- raw material 存在 `data/daily_materials/` 下
- PKS candidate queue 只包含经过筛选的 facts/inferences

#### B7 — 稳定去重

**当前问题**：`hash(str(item))` 在不同进程间不稳定。

**改动**：

```python
# 替换所有 hash() 调用
import hashlib
def stable_id(source: str, title: str, published: str) -> str:
    raw = f"{source}:{title}:{published}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

应用于：
- `daemon.py` 的 seen_ids 判断
- Jin10 flash (用 url 或 content hash)
- RSS (用 link 或 title+published)
- Calendar (用 event_name + release_time)
- Overview/Price (用 asset + date)

**验收**：watcher 重启后不重复写入已见数据。

#### B4 — Price signal 类型修正

**当前问题**：`overview.py` 写入 price move 为 `type: inference`。

**改动**：

- `core/overview.py`：price/index/commodity move 改为 `type: factual`
- 只写入 material，不直接写 PKS
- 真正的 inference（如 "黄金走弱反映中东风险缓和"）由 agent selector 生成

**验收**：`raw_overview.jsonl` 中所有 price 信号标记为 factual。

### Phase 2: 智能筛选（优先级 P1）

#### B2 — Daily claim 数量上限

**新增 `selector.py`** — daily selector 模块

```
raw material → 规则评分 → 排序 → top N → 写入 PKS
```

评分维度：
- 是否影响持仓 / watchlist（+3）
- 是否为关键宏观事件 (FOMC/CPI/PCE/NFP)（+3）
- 是否有显著 price reaction（+2）
- source credibility（+1）
- 是否影响主要关注市场 (US/HK/gold/BTC)（+1）

上限：
- `factual_max: 20`
- `inference_max: 5`

输出 `selection_report.json`：

```json
{
  "date": "2026-06-22",
  "factual_selected": 18,
  "inference_selected": 4,
  "discarded_to_material": 312,
  "top_themes": ["fed_policy", "tariff_escalation"]
}
```

#### B3 — Calendar 两阶段模型

**改动**：

1. `core/calendar.py` 输出两种类型的 material：
   - `scheduled_event`：即将发布的经济数据，带 metadata
   - `actual_release`：已发布的实际数据，带 surprise 判断

2. Metadata 结构（依赖 PKS P4.2）：
   ```json
   {
     "event_name": "US Core PCE",
     "release_time": "2026-06-25T20:30:00+08:00",
     "period": "2026-05",
     "previous": "2.8%",
     "consensus": "2.7%",
     "actual": null,
     "status": "scheduled"
   }
   ```

3. Scheduled event 写入 material，日选时根据重要性决定是否进 PKS
4. Actual release 如有 surprise 则高优进 PKS factual claim

#### B5 — Inference 两层筛选

**Layer 1: 规则引擎初筛** (`selector.py`)

- 读取当日 material 中的 themes（由现有 `analyzer.py` 检测）
- 按持仓/watchlist/市场相关性过滤
- 输出 theme 候选列表（不直接写 PKS）

**Layer 2: Agent 精选** (可配置定时任务)

- 读取当日 material + theme 候选 + 持仓
- Agent (Hermes) 判断主线，生成 <= 5 条 inference
- 每条 inference 必须：
  - 引用 2-5 条 evidence/fact/material
  - 有 confidence 评分
  - 有 valid_until
  - 标注影响范围 (US/HK/gold/BTC/holdings)
- 写入 PKS inference candidate

**配置**：

```json
{
  "selector": {
    "factual_max": 20,
    "inference_max": 5,
    "agent_inference": {
      "enabled": true,
      "schedule": "18:00",
      "hermes_prompt_template": "..."
    }
  }
}
```

#### B6 — News 默认不进 PKS

这是 B1 的自然结果。改动后的数据流：

```
Jin10 flash  → raw_jin10.jsonl    ─┐
RSS          → raw_rss.jsonl       ├── daily selector ── selected facts ── PKS
Calendar     → raw_calendar.jsonl  │
Price        → raw_prices.jsonl   ─┘
```

默认：所有 raw news 只进 material，不进 PKS。

### Phase 3: 运维与投影（优先级 P2）

#### B8 — Daily cleanup job

在 `daemon.py` 的调度循环中新增每日清理任务：

- 清理 > 7 天的 raw material 目录
- 通过 PKS `maintain` 过期 intraday facts
- 通过 PKS `maintain` 过期 past scheduled events
- 刷新 projections
- 输出 cleanup report

#### B9 — Projection 消费 selected claims

修改 daily-briefing skill 的数据源：

优先读取：
1. `selected_facts.json` — 当日精选 facts
2. `selected_inferences.json` — 当日精选 inferences
3. PKS accepted durable claims — 长期有效的认知

不再读取：
- raw headline
- 全量 candidate queue

生成 `briefing_context.md`：结构化的播报上下文，不超过 20 facts + 5 inferences。

---

## 依赖关系

```
PKS P4.1 (market domain)  ───┐
PKS P4.2 (metadata)       ───┤
                              ├── B1 (两层架构) ── B2 (selector) ── B5 (inference 筛选)
B7 (稳定去重)             ───┤                                  ── B3 (calendar 两阶段)
B4 (price factual)        ───┘
                                                                ── B6 (news 不进 PKS)
                                                                ── B8 (daily cleanup)
                                                                ── B9 (projection)
```

**关键路径**：PKS P4.1 + P4.2 → B1 + B7 + B4 → B2 → B5

B1 可以在 PKS P4.5 (scratchpad) 完成前先用本地 `data/daily_materials/` 实现，不被阻塞。

## 执行顺序

1. **先做 PKS P4.1 + P4.2**（market domain + metadata）
2. **然后 PKS P4.3**（lifecycle 增强）
3. **然后 B1 + B7 + B4**（stock-advisor 核心重构）
4. **然后 B2 + B3 + B5**（selector + calendar + inference）
5. **然后 PKS P4.4**（WebUI 性能，此时有真实数据可测）
6. **最后 B6 + B8 + B9**（收尾）

## 不在本计划范围

- PKS 侧改动细节（见 PKS P4 计划）
- Hermes 侧的接收/分析/推送逻辑
- 回测框架
