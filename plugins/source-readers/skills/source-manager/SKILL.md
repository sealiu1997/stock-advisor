---
name: source-manager
description: >
  管理信息源追踪列表。当用户给出一个博主、账号或网站的链接说"关注这个"、
  "追踪这个博主"、"把这个加到信息源"时使用此技能。也用于查看、编辑、删除
  已追踪的信息源。触发词包括："关注这个博主"、"追踪"、"track this"、
  "follow this source"、"添加信息源"、"add source"、"我的信息源"、
  "删除信息源"、"remove source"、"信息源列表"、"source list"、
  或用户粘贴了一个社交媒体/博客/新闻站点的链接并暗示想持续关注。
  支持的平台：Twitter/X、Reddit、YouTube、微博、小红书、雪球、
  Substack、Medium、知乎、Bilibili、RSS/Atom feed、以及 OpenCLI 支持的其他站点。
---

# Source Manager — 信息源管理

解析用户提供的 URL 或账号信息，自动识别平台类型，添加到 `config/sources.json` 追踪列表中。
也支持查看、编辑和删除已有信息源。

---

## Step 1: 判断操作类型

| 用户意图 | 操作 |
|---|---|
| 给了一个 URL 或账号名 + "关注/追踪" | **添加**信息源 |
| "我的信息源" / "source list" | **列出**所有信息源 |
| "删除 xxx" / "不再关注 xxx" | **删除**信息源 |
| "修改 xxx 的标签" | **编辑**信息源 |

---

## Step 2: 添加信息源 — URL 解析

### 平台识别规则

根据 URL 模式自动识别平台和提取账号信息：

| URL 模式 | 平台 | 提取内容 | opencli 命令 |
|---|---|---|---|
| `x.com/{user}` 或 `twitter.com/{user}` | twitter | username | `opencli twitter tweets {user}` |
| `reddit.com/r/{sub}` | reddit_sub | subreddit 名 | `opencli reddit subreddit r/{sub}` |
| `reddit.com/user/{user}` | reddit_user | username | `opencli reddit user-posts {user}` |
| `youtube.com/@{channel}` 或 `youtube.com/channel/{id}` | youtube | channel handle/id | `opencli youtube channel {handle}` |
| `weibo.com/u/{uid}` 或 `weibo.com/{user}` | weibo | uid 或用户名 | `opencli weibo user {uid}` |
| `xiaohongshu.com/user/profile/{id}` | xiaohongshu | user id | `opencli xiaohongshu user {id}` |
| `xueqiu.com/u/{uid}` | xueqiu | uid | `opencli xueqiu user {uid}` |
| `zhihu.com/people/{user}` | zhihu | user slug | `opencli zhihu user {user}` |
| `bilibili.com/space/{uid}` | bilibili | uid | `opencli bilibili user {uid}` |
| `{user}.substack.com` | substack | username | `opencli substack posts {user}` |
| `medium.com/@{user}` | medium | username | `opencli medium user {user}` |
| 包含 `/feed` 或 `/rss` 或 `/atom.xml` | rss | feed URL | `curl` 直接抓取 |
| `linkedin.com/in/{user}` | linkedin | profile slug | `opencli linkedin posts {user}` |

### 无法识别的 URL

如果 URL 不匹配上述任何模式：
1. 检查 OpenCLI 是否支持该域名：`opencli list | grep {domain}`
2. 如果支持 → 用 opencli 的通用命令
3. 如果不支持 → 尝试检测 RSS/Atom feed（检查 `{url}/feed`, `{url}/rss`, `<link rel="alternate" type="application/rss+xml">`）
4. 都不行 → 告知用户该平台暂不支持，建议提供 RSS 链接

### 信息补全

识别平台后，尝试获取更多信息用于标注：

```bash
# 例：Twitter 账号，获取 profile 信息
opencli twitter profile {username} -f json
# 提取: name, bio, followers
```

然后请用户确认或补充：
- **标签 (label)**：显示名称（如果能自动获取就用自动值，否则问用户）
- **分类 (category)**：从 `macro` / `stocks` / `crypto` / `tech` / `news` / `general` 中选择（可由 agent 根据 bio 推断）

---

## Step 3: 写入 sources.json

读取 `{baseDir}/../../config/sources.json`，向 `sources` 数组追加新条目：

### 条目结构

```json
{
  "id": "twitter:zaborxyz",
  "platform": "twitter",
  "handle": "zaborxyz",
  "label": "付鹏",
  "category": "macro",
  "url": "https://x.com/zaborxyz",
  "opencli_cmd": "opencli twitter tweets zaborxyz --limit 10 -f json",
  "fallback_cmd": null,
  "added_at": "2026-06-18T15:30:00+08:00",
  "last_scanned": null,
  "enabled": true
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 唯一标识：`{platform}:{handle}` |
| `platform` | 是 | 平台标识符 |
| `handle` | 是 | 平台上的用户名/ID |
| `label` | 是 | 显示名称 |
| `category` | 是 | 内容分类 |
| `url` | 是 | 原始 URL |
| `opencli_cmd` | 是 | 主抓取命令（完整的 opencli 命令） |
| `fallback_cmd` | 否 | 备用抓取命令（opencli 不可用时的替代） |
| `added_at` | 是 | ISO 8601 格式的添加时间 |
| `last_scanned` | 否 | 上次扫描时间（由 source-feed 更新） |
| `enabled` | 是 | 是否启用 |

### 备用抓取路径 (fallback_cmd)

为每个平台设计备用方案，当 OpenCLI 不可用时使用：

| 平台 | 备用方案 |
|---|---|
| twitter | `curl` + nitter 实例（如可用） |
| reddit | Reddit JSON API: `curl 'https://www.reddit.com/r/{sub}/new.json?limit=10'` |
| youtube | `yt-dlp --flat-playlist --print title,url` 或 YouTube RSS: `https://www.youtube.com/feeds/videos.xml?channel_id={id}` |
| xueqiu | 雪球公开 API: `curl 'https://xueqiu.com/statuses/original/timeline.json?user_id={uid}'` |
| substack | RSS: `https://{user}.substack.com/feed` |
| medium | RSS: `https://medium.com/feed/@{user}` |
| rss | `curl` 直接抓取 feed URL |
| 其他 | 无备用，标注 `null` |

**写入 sources.json 时的检查：**
1. 检查 `id` 是否已存在 → 已存在则提示用户，不重复添加
2. 写入后打印确认信息

---

## Step 4: 列出信息源

读取 `config/sources.json`，输出表格：

```
### 我的信息源 (共 5 个)

| # | 平台 | 标签 | 分类 | 状态 | 上次扫描 |
|---|------|------|------|------|---------|
| 1 | twitter | 付鹏 @zaborxyz | macro | ✅ | 2h前 |
| 2 | twitter | 华尔街见闻 @WallStreetCN | news | ✅ | 2h前 |
| 3 | reddit | r/wallstreetbets | stocks | ✅ | 5h前 |
| 4 | xueqiu | 某大V | stocks | ✅ | 从未 |
| 5 | substack | 某博主 | macro | ⏸ 已禁用 | - |
```

---

## Step 5: 删除/编辑信息源

**删除：** 根据用户指定的标签/平台/序号，从 `sources` 数组中移除。

**编辑：** 修改 label、category、enabled 等字段。

**禁用/启用：** 设置 `enabled` 为 `false`/`true`，禁用的源在扫描时跳过。

---

## Step 6: 输出确认

操作完成后，输出简要确认：

```
✅ 已添加信息源: 付鹏 (@zaborxyz) [Twitter · 宏观]
   抓取命令: opencli twitter tweets zaborxyz --limit 10 -f json
   备用路径: 无 (需要 OpenCLI)
   下次扫描时将自动包含此源。
```

---

## Reference Files

- `references/platform_adapters.md` — 各平台的 URL 解析规则、opencli 命令映射、备用路径、输出字段映射
