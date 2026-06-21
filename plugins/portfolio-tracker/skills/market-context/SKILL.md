---
name: market-context
description: >
  查看和管理市场认知状态 — PKS 中的宏观叙事、数据事实和分析记录。
  当用户询问"当前的市场叙事是什么"、"宏观认知"、"market context"、
  "最近的分析记录"、"有哪些活跃叙事"、"更新市场判断"、"修正叙事"、
  "这个判断不对"、"添加一个新的市场观点"、"expire narrative"时使用此技能。
  提供 PKS 市场认知层的查看、修正、新增、过期等管理操作。
---

# Market Context — 市场认知管理

查看和管理 PKS 中存储的市场认知状态：活跃叙事、宏观数据事实、分析历史。
用于人工审计和修正 daily-briefing 产生的自动分析。

---

## Step 1: 环境检测

```
!`command -v pks >/dev/null 2>&1 && pks context 2>/dev/null | head -1 && echo "PKS_OK" || echo "PKS_MISSING"`
```

如果 `PKS_MISSING`：

> 此技能需要 PKS (Personal Knowledge State)。
> 请先运行 daily-briefing 技能完成 PKS 安装，或手动安装：
> ```
> git clone https://github.com/sealiu1997/personal_knowledge_state ~/personal_knowledge_state
> cd ~/personal_knowledge_state && pip install -e .
> pks init-home
> ```

---

## Step 2: 确定操作类型

根据用户请求判断操作：

| 用户意图 | 操作 |
|---------|------|
| "目前有哪些活跃叙事" / "市场认知" | → **查看叙事** |
| "最近的宏观数据" | → **查看数据** |
| "最近的分析记录" | → **查看日报历史** |
| "这个叙事应该过期了" / "降息交易已经结束" | → **过期叙事** |
| "我觉得应该加一个 XXX 叙事" | → **新增叙事** |
| "这个判断不对" / "修正 XXX" | → **修正叙事** |
| "市场认知健康检查" | → **健康检查** |

---

## Step 3: 查看操作

### 3a. 查看活跃叙事

```bash
pks claim list --status accepted --tag narrative --domain research
```

输出格式：

```markdown
## 当前活跃的市场叙事

### 1. {叙事标题}
- **状态**：active | confidence: {0.0-1.0}
- **核心判断**：{object 字段}
- **证据**：{evidence 列表}
- **传导机制**：{transmission claim}
- **影响持仓**：{portfolio_impact claim}
- **创建时间**：{created_at}
- **最近验证**：{last_verified}

### 2. ...
```

同时检查 stale claims：

```bash
pks health market-context
```

如果有 stale 叙事，标注提醒用户决定是 verify 还是 expire。

### 3b. 查看数据事实

```bash
pks claim list --status accepted --type factual --domain research --tag macro
```

输出为表格：

```markdown
| 数据 | 最新读数 | 时期 | 录入时间 |
|------|---------|------|---------|
| CPI | 3.1% YoY | 2026-06 | 2026-06-18 |
| 10Y | 4.17% | 2026-06-20 | 2026-06-20 |
```

### 3c. 查看日报历史

```bash
pks claim list --status accepted --subject "daily_briefing" --domain research
```

输出最近 7 次播报的主线摘要。

---

## Step 4: 修改操作

### 4a. 过期叙事

用户认为某个叙事已不成立时：

```bash
pks claim expire {claim_id}
```

需要用户确认。

### 4b. 新增叙事

用户要求添加新的市场观点时，按 `references/narrative_modeling.md` 的约定构建 claim 簇。

需要用户提供：
1. **核心判断**：一句话描述叙事（如"市场开始交易衰退风险"）
2. **证据**：支持这个判断的事实或新闻
3. **传导机制**（可选）：怎么影响各类资产
4. **持仓影响**（可选）：对你的持仓有什么影响

Agent 帮助用户结构化输入，然后：

```bash
# L1: 叙事
pks claim add \
  --subject "market_narrative" \
  --predicate "active_theme" \
  --object "{用户的核心判断}" \
  --qualifier "{当前季度}" \
  --type inference \
  --domain research \
  --tag narrative,{相关 tags} \
  --evidence-source "{来源}" \
  --evidence-excerpt "{摘要}" \
  --confidence {用户评估的置信度}
```

如果用户提供了传导和影响，继续创建 L2、L3 claims。

### 4c. 修正叙事

用户认为某个叙事的判断需要修正（如 confidence 需要调整，或描述不准确）时：

```bash
# 用新 claim supersede 旧 claim
pks claim supersede {old_claim_id} \
  --subject "market_narrative" \
  --predicate "active_theme" \
  --object "{修正后的判断}" \
  --type inference \
  --domain research \
  --tag narrative
```

### 4d. 验证/刷新叙事

用户确认某个叙事仍然成立：

```bash
pks claim verify {claim_id}
```

可以同时追加新 evidence。

---

## Step 5: 健康检查

```bash
pks health market-context
```

输出：
- 有多少条 accepted claims
- 有多少条 stale claims（超过阈值未验证）
- 有多少条 expired claims
- evidence 完整性

对 stale claims 给出建议：
- 如果叙事仍然成立 → 建议 verify
- 如果叙事已过时 → 建议 expire
- 如果数据已过期 → 无需操作（数据事实自然过期）

---

## Step 6: 输出

所有操作完成后，输出操作摘要。

对于查看操作：
```markdown
## Market Context 概览 | {日期}

**活跃叙事**：{N} 条
**数据事实**：{N} 条
**近期日报**：{N} 条
**健康状态**：{OK / 有 N 条 stale claims 需要处理}

{详细内容}
```

对于修改操作：
```
✓ 已{操作类型}：{claim 摘要}
```

---

## Reference Files

- `../daily-briefing/references/narrative_modeling.md` — PKS 叙事建模约定
