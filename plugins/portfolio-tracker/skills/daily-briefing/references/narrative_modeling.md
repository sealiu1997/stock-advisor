# PKS 市场叙事建模指南

## 概述

市场叙事（narrative）是 daily-briefing 的核心认知单元。每条叙事由一簇 PKS Claims 构成，
形成"事实 → 推断 → 传导 → 影响"的完整证据链。

本文档定义 PKS 中市场领域的标准建模约定。

---

## Claim 类型映射

| 层级 | PKS claim type | 用途 | 最低证据要求 |
|------|---------------|------|------------|
| L0 数据事实 | `factual` | 官方数据、价格、利率 | 1 evidence (数据来源) |
| L1 市场叙事 | `inference` | 主线判断、趋势解读 | 1 evidence + 1 supporting claim |
| L2 传导机制 | `inference` | 因子如何影响资产类别 | 1 supporting claim (叙事) |
| L3 持仓映射 | `inference` | 叙事对具体持仓的影响 | 1 supporting claim (传导) |

---

## 标准 Subject 命名约定

### 宏观数据 (factual)

| subject | 含义 | predicate 示例 |
|---------|------|---------------|
| `us_cpi` | 美国 CPI | `reading` |
| `us_nfp` | 非农就业 | `reading` |
| `us_ppi` | PPI | `reading` |
| `us_gdp` | GDP | `reading` |
| `us_pce` | PCE 物价指数 | `reading` |
| `us_retail_sales` | 零售销售 | `reading` |
| `us_jobless_claims` | 初请失业金 | `reading` |
| `us_ism_mfg` | ISM 制造业 PMI | `reading` |
| `us_ism_svc` | ISM 服务业 PMI | `reading` |
| `fomc` | FOMC 会议 | `decision` / `statement` / `dot_plot` |

### 市场价格 (factual)

| subject | 含义 | predicate 示例 |
|---------|------|---------------|
| `ust_2y` | 2年期美债 | `yield` / `yield_change` |
| `ust_5y` | 5年期美债 | `yield` / `yield_change` |
| `ust_10y` | 10年期美债 | `yield` / `yield_change` |
| `dxy` | 美元指数 | `level` / `change` |
| `vix` | VIX 恐慌指数 | `level` / `change` |
| `gold` | 黄金 | `price` / `change` |
| `oil_wti` | WTI 原油 | `price` / `change` |
| `btc` | 比特币 | `price` / `change` |
| `spx` | S&P 500 | `close` / `change` |
| `ndx` | 纳斯达克 | `close` / `change` |
| `hsi` | 恒生指数 | `close` / `change` |

### 叙事 (inference)

| subject | predicate | 含义 |
|---------|-----------|------|
| `market_narrative` | `active_theme` | 当前活跃的市场交易主线 |
| `{narrative_id}` | `transmission` | 该叙事的传导机制 |
| `{narrative_id}` | `portfolio_impact` | 该叙事对持仓的影响 |
| `{narrative_id}` | `risk_factor` | 该叙事面临的风险/反转条件 |

### 分析记录 (inference)

| subject | predicate | 含义 |
|---------|-----------|------|
| `daily_briefing` | `main_theme` | 当日播报选定的主线 |
| `daily_briefing` | `analyzed_tickers` | 当日分析了哪些标的 |
| `daily_briefing` | `skipped_reason` | 为何跳过某些标的 |

---

## qualifier 使用约定

qualifier 用于区分同一 subject+predicate 的不同时间实例：

- 宏观数据：`"2026-06"` (月度), `"2026-Q2"` (季度), `"2026-W25"` (周度)
- 市场价格：`"2026-06-20"` (日期)
- 叙事：`"2026-Q3"` 或 `"2026-06~"` (起始月)
- 日报：`"2026-06-20"` (日期)

---

## 标准 Tag 体系

| Tag | 用途 |
|-----|------|
| `macro` | 宏观经济数据 |
| `rates` | 利率与债券 |
| `fx` | 外汇 |
| `commodity` | 商品 |
| `equity` | 股票/指数 |
| `crypto` | 加密货币 |
| `geopolitical` | 地缘政治 |
| `narrative` | 市场叙事 |
| `transmission` | 传导机制 |
| `portfolio` | 持仓相关 |
| `briefing` | 日报记录 |
| `data-release` | 经济数据发布 |
| `fed` | 美联储相关 |
| `china` | 中国/港股相关 |
| `sector:{name}` | 特定板块，如 `sector:tech` |

---

## 完整建模示例

### 场景：CPI 低于预期，市场交易降息预期

#### L0: 数据事实

```bash
pks claim add \
  --subject "us_cpi" \
  --predicate "reading" \
  --object "Jun 2026: 3.1% YoY (consensus 3.2%), Core 3.3% (consensus 3.4%)" \
  --qualifier "2026-06" \
  --type factual \
  --domain research \
  --tag macro,data-release,inflation \
  --evidence-source "BLS" \
  --evidence-excerpt "CPI-U 12-month change 3.1 percent, seasonally adjusted" \
  --confidence 1.0
```

```bash
pks claim add \
  --subject "ust_10y" \
  --predicate "yield_change" \
  --object "fell 8bp to 4.17% (biggest daily drop in 2 weeks)" \
  --qualifier "2026-06-18" \
  --type factual \
  --domain research \
  --tag rates,macro \
  --evidence-source "market data" \
  --evidence-excerpt "10Y Treasury yield 4.17%, -8bp" \
  --confidence 1.0
```

#### L1: 市场叙事

```bash
pks claim add \
  --subject "market_narrative" \
  --predicate "active_theme" \
  --object "Disinflation trade: CPI 连续 3 月低于预期，市场定价 H2 降息 2-3 次，长端利率回落推动成长股估值修复" \
  --qualifier "2026-Q3" \
  --type inference \
  --domain research \
  --tag narrative,fed,rates,macro \
  --evidence-source "Reuters" \
  --evidence-excerpt "Fed funds futures now price in 75bp of cuts by year-end, up from 50bp before CPI" \
  --confidence 0.85 \
  --supports "{us_cpi_claim_id}" \
  --supports "{ust_10y_claim_id}"
```

#### L2: 传导机制

```bash
pks claim add \
  --subject "disinflation_trade" \
  --predicate "transmission" \
  --object "长端利率回落 → 贴现率下降 → 成长股估值空间打开; 美元走弱 → 新兴市场资金回流; 实际利率下降 → 黄金受益" \
  --type inference \
  --domain research \
  --tag narrative,transmission,rates,equity,commodity \
  --supports "{narrative_claim_id}" \
  --confidence 0.80
```

#### L3: 持仓映射

```bash
pks claim add \
  --subject "disinflation_trade" \
  --predicate "portfolio_impact" \
  --object "GOOG/MSFT 受益于估值修复 (高成长高估值); COPX 受益于美元走弱+铜需求; 黄金(GC=F)受益于实际利率下降; 港股受益于全球风险偏好改善" \
  --type inference \
  --domain research \
  --tag narrative,portfolio \
  --supports "{transmission_claim_id}" \
  --confidence 0.75
```

---

## 叙事生命周期管理

### 延续 (refresh)

当新数据继续支持已有叙事时，不新建叙事，而是给已有叙事追加 evidence：

```bash
pks claim verify {narrative_claim_id} \
  --evidence-source "BLS" \
  --evidence-excerpt "Jul CPI 2.9% YoY, further decline"
```

同时可上调 confidence。

### 减弱 (weaken)

当新数据部分矛盾时，降低 confidence 或添加 risk_factor claim：

```bash
pks claim add \
  --subject "disinflation_trade" \
  --predicate "risk_factor" \
  --object "油价因中东局势上行可能推高 headline CPI，但 core CPI 趋势仍向下" \
  --type inference \
  --domain research \
  --tag narrative,risk \
  --supports "{narrative_claim_id}"
```

### 替代 (supersede)

当主线发生根本转变时：

```bash
pks claim supersede {old_narrative_id} \
  --subject "market_narrative" \
  --predicate "active_theme" \
  --object "Stagflation fear: CPI 反弹 + 就业放缓，市场从降息交易转向滞胀担忧" \
  --qualifier "2026-Q4" \
  --type inference \
  --domain research \
  --tag narrative,macro,fed
```

### 过期 (expire)

叙事超过 `stale_days_inference`（默认 14 天）未被 verify 或追加 evidence，
PKS 自动标记为 stale。Agent 在下次 briefing 时发现 stale 叙事后应判断：
- 仍然成立 → `pks claim verify` 刷新
- 已不相关 → `pks claim expire`

---

## 查询约定

### 获取当前活跃叙事

```bash
pks claim list --status accepted --tag narrative --domain research
```

### 获取最近的数据事实

```bash
pks claim list --status accepted --type factual --domain research --tag macro
```

### 获取某叙事的完整证据链

```bash
pks claim list --status accepted --subject "disinflation_trade" --domain research
```

### 获取最近的日报记录

```bash
pks claim list --status accepted --subject "daily_briefing" --domain research
```
