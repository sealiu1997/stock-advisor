# 平台适配器参考

## URL 解析正则表达式

```python
import re

PLATFORM_PATTERNS = [
    # Twitter / X
    (r'(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/(@?\w+)/?$', 'twitter', 'handle'),
    
    # Reddit - subreddit
    (r'(?:https?://)?(?:www\.)?reddit\.com/r/(\w+)', 'reddit_sub', 'subreddit'),
    # Reddit - user
    (r'(?:https?://)?(?:www\.)?reddit\.com/user?/(\w+)', 'reddit_user', 'username'),
    
    # YouTube - @handle
    (r'(?:https?://)?(?:www\.)?youtube\.com/@([\w.-]+)', 'youtube', 'handle'),
    # YouTube - channel ID
    (r'(?:https?://)?(?:www\.)?youtube\.com/channel/(UC[\w-]+)', 'youtube', 'channel_id'),
    
    # 微博
    (r'(?:https?://)?(?:www\.)?weibo\.com/u/(\d+)', 'weibo', 'uid'),
    (r'(?:https?://)?(?:www\.)?weibo\.com/(\w+)', 'weibo', 'handle'),
    
    # 小红书
    (r'(?:https?://)?(?:www\.)?xiaohongshu\.com/user/profile/([a-f0-9]+)', 'xiaohongshu', 'user_id'),
    
    # 雪球
    (r'(?:https?://)?xueqiu\.com/u/(\d+)', 'xueqiu', 'uid'),
    
    # 知乎
    (r'(?:https?://)?(?:www\.)?zhihu\.com/people/([\w-]+)', 'zhihu', 'user_slug'),
    
    # Bilibili
    (r'(?:https?://)?space\.bilibili\.com/(\d+)', 'bilibili', 'uid'),
    
    # Substack
    (r'(?:https?://)?([\w-]+)\.substack\.com', 'substack', 'username'),
    
    # Medium
    (r'(?:https?://)?(?:www\.)?medium\.com/@([\w.-]+)', 'medium', 'username'),
    
    # LinkedIn
    (r'(?:https?://)?(?:www\.)?linkedin\.com/in/([\w-]+)', 'linkedin', 'profile_slug'),
    
    # RSS/Atom (通用)
    (r'.+/(?:feed|rss|atom)(?:\.xml)?/?$', 'rss', 'feed_url'),
]
```

## OpenCLI 命令映射

### Twitter

```bash
# 获取用户最新推文
opencli twitter tweets {username} --limit 10 -f json

# 搜索特定话题
opencli twitter search "{query}" --filter live --limit 10 -f json

# 获取用户资料（用于添加时获取 label）
opencli twitter profile {username} -f json
```

**输出字段：** `id`, `author`, `text`, `created_at`, `likes`, `retweets`, `replies`, `views`, `url`

**认证要求：** 需要在 Chrome 中登录 x.com（Strategy: COOKIE）

### Reddit

```bash
# 获取 subreddit 最新帖子
opencli reddit subreddit r/{name} --sort new --limit 10 -f json

# 获取用户帖子
opencli reddit user-posts {username} --limit 10 -f json

# 搜索
opencli reddit search "{query}" --sort new --limit 10 -f json
```

**输出字段：** `title`, `author`, `score`, `comments`, `url`, `created_at`, `subreddit`

**认证要求：** 公开数据无需登录（Strategy: PUBLIC）

**备用路径：**
```bash
curl -s -H "User-Agent: StockAdvisor/1.0" "https://www.reddit.com/r/{sub}/new.json?limit=10"
# 解析 data.children[].data 获取帖子
```

### YouTube

```bash
# 获取频道最新视频
opencli youtube channel {handle} --limit 10 -f json

# 搜索
opencli youtube search "{query}" --limit 10 -f json
```

**输出字段：** `title`, `channel`, `views`, `published`, `url`, `duration`

**备用路径 (RSS)：**
```
https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}
```
注意：需要 channel_id (UCxxxx 格式)，不是 @handle。

### 微博

```bash
opencli weibo user {uid} --limit 10 -f json
```

**认证要求：** 需要在 Chrome 中登录微博（Strategy: COOKIE）

### 小红书

```bash
opencli xiaohongshu user {user_id} --limit 10 -f json
```

**认证要求：** 需要登录（Strategy: COOKIE）
**注意：** 搜索可能触发登录墙，用户主页相对稳定

### 雪球

```bash
opencli xueqiu user {uid} --limit 10 -f json
```

**认证要求：** 可能需要登录（Strategy: COOKIE）

**备用路径：**
```bash
curl -s "https://xueqiu.com/statuses/original/timeline.json?user_id={uid}&count=10" \
  -H "Cookie: xq_a_token=..." -H "User-Agent: Mozilla/5.0"
```
需要 cookie，不如 OpenCLI 方便。

### Substack

```bash
opencli substack posts {username} --limit 10 -f json
```

**备用路径 (RSS)：**
```
https://{username}.substack.com/feed
```

### Medium

```bash
opencli medium user {username} --limit 10 -f json
```

**备用路径 (RSS)：**
```
https://medium.com/feed/@{username}
```

### Bilibili

```bash
opencli bilibili user {uid} --limit 10 -f json
```

**认证要求：** 公开数据不需要，但登录可获取更多内容

### 知乎

```bash
opencli zhihu user {user_slug} --limit 10 -f json
```

**认证要求：** 可能需要登录

### LinkedIn

```bash
opencli linkedin posts {profile_slug} --limit 10 -f json
```

**认证要求：** 必须登录（Strategy: UI）
**注意：** LinkedIn 反爬严格，OpenCLI 通过真实浏览器会话规避

### RSS / Atom

不使用 OpenCLI，直接用 Python 或 curl：

```python
import urllib.request
import xml.etree.ElementTree as ET

resp = urllib.request.urlopen(feed_url, timeout=15)
tree = ET.fromstring(resp.read())

# RSS 2.0
for item in tree.findall('.//item'):
    title = item.find('title').text
    link = item.find('link').text
    pub_date = item.find('pubDate').text

# Atom
for entry in tree.findall('.//{http://www.w3.org/2005/Atom}entry'):
    title = entry.find('{http://www.w3.org/2005/Atom}title').text
    link = entry.find('{http://www.w3.org/2005/Atom}link').get('href')
```

## 退出码处理

| OpenCLI 退出码 | 含义 | 处理 |
|---|---|---|
| 0 | 成功 | 正常处理输出 |
| 66 | 结果为空 | 标注"无新内容"，不报错 |
| 69 | 浏览器不可用 | 尝试备用路径 |
| 75 | 超时 | 重试一次，失败则跳过 |
| 77 | 需要登录 | 提示用户在 Chrome 中登录该站点 |
| 其他 | 未知错误 | 尝试备用路径，失败则跳过并标注 |
