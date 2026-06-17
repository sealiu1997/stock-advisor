---
name: my-stocks
description: >
  查看实盘持仓行情、计算浮动盈亏并获取股市简报。当用户询问"我的股票怎么样"、
  "查看行情"、"盈亏情况"、"持仓播报"、"portfolio"、"holdings"、"P&L"、
  "美股早报"、"港股晚报"、"周末加密特报"、"今天赚了多少"、"持仓市值"、
  或提及特定持仓股票的状态时，使用此技能。也用于定时播报场景：
  每日早报（美股盘后复盘）、每日晚报（港股收盘总结）、周末加密货币报告。
---

# My Stocks — 持仓行情播报

实盘持仓管家，支持港美股、外汇、商品和加密货币的行情抓取与盈亏分析。

**声明：仅供研究和教育目的，不构成投资建议。**

---

## Step 1: 环境检测与播报模式判定

### 检测 Python 和 yfinance

```
!`python3 -c "import yfinance; print('YFINANCE_OK')" 2>/dev/null || echo "YFINANCE_MISSING"`
```

如果 `YFINANCE_MISSING`，先安装：

```python
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "yfinance"])
```

### 判定播报模式

根据当前北京时间自动判定：

| 条件 | 模式 | 语气 |
|---|---|---|
| 工作日 06:00-12:00 | **美股早报** | "早安"，复盘隔夜美股，展望港股 |
| 工作日 16:00-22:00 | **港股晚报** | "晚间总结"，复盘港股，展望美股 |
| 周末 | **加密特报** | 轻松专业，聚焦加密货币 |
| 其他时段 / 用户手动查询 | **全市场模式** | 中性，按需展示全部 |

如果用户明确指定了模式（如"给我看美股"），以用户指定为准。

---

## Step 2: 读取配置文件

读取以下两个配置文件：

- `{baseDir}/../../config/portfolio.json` — 持仓数据
- `{baseDir}/../../config/watchlist.json` — 关注列表

**portfolio.json 结构：**

```json
{
  "HK": [
    {"symbol": "1810", "name": "小米集团", "holdings": 1000, "cost_price": 32.50}
  ],
  "US": [
    {"symbol": "GOOG", "name": "谷歌", "holdings": 10, "cost_price": 170.00}
  ],
  "CRYPTO": [
    {"symbol": "BTCUSDT", "name": "比特币", "holdings": 0.5, "cost_price": 60000}
  ]
}
```

**watchlist.json 结构：**

```json
{
  "HK": [{"symbol": "00700", "name": "腾讯控股"}, ...],
  "US": [{"symbol": "NVDA", "name": "英伟达"}, ...],
  "FX_COMM": [{"symbol": "EURUSD", "name": "欧元/美元"}, ...],
  "CRYPTO": [{"symbol": "BTCUSDT", "name": "比特币"}, ...],
  "CRYPTO_RATIOS": [{"symbol": "ETHBTC", "name": "ETH/BTC"}, ...]
}
```

如果文件不存在，提示用户创建并给出模板。

---

## Step 3: 批量抓取行情数据

根据 symbol 的市场类型选择数据源。编写并执行 Python 代码，一次性抓取所有标的。

### 数据获取路由

| 市场 | 方法 | 说明 |
|---|---|---|
| US | `yf.download([symbols], period='2d')` | 批量下载，取最后一行为最新价，倒数第二行计算涨跌 |
| HK | 腾讯财经 `http://qt.gtimg.cn/q=r_hk{code}` | 逐个请求，解析 `~` 分隔文本。如失败，用 yfinance `{code}.HK` |
| CRYPTO | Binance `https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}` | 24h 涨跌幅 |
| CRYPTO_RATIOS | 同 CRYPTO | 汇率对，仅看价格和涨跌 |
| FX_COMM | yfinance | 如 `EURUSD=X`, `GC=F`, `CL=F` |

### 代码模板

```python
import yfinance as yf
import json, urllib.request, datetime

# 读取配置
with open("config/portfolio.json") as f:
    portfolio = json.load(f)
with open("config/watchlist.json") as f:
    watchlist = json.load(f)

now = datetime.datetime.now()

# --- 美股批量抓取 ---
us_symbols = list(set(
    [s["symbol"] for s in portfolio.get("US", [])] +
    [s["symbol"] for s in watchlist.get("US", [])]
))
if us_symbols:
    data = yf.download(us_symbols, period="2d", progress=False)
    # 提取最新价和涨跌幅...

# --- 港股逐个抓取 ---
def get_hk(code):
    code = code.zfill(5)
    url = f"http://qt.gtimg.cn/q=r_hk{code}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10).read().decode("gbk")
        parts = resp.split("~")
        if len(parts) > 32:
            return {"price": float(parts[3]), "change_pct": float(parts[32]), "name": parts[1]}
    except:
        pass
    return None

# --- 加密货币批量抓取 ---
def get_crypto(symbol):
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())
        return {"price": float(data["lastPrice"]), "change_pct": float(data["priceChangePercent"])}
    except:
        return None
```

### 盈亏计算

如果 `cost_price` 存在，计算：
- **浮动盈亏** = (现价 - 成本价) × 持仓数
- **盈亏比例** = (现价 / 成本价 - 1) × 100%
- **日盈亏** = 涨跌幅 × 现价 × 持仓数 / 100

如果 `cost_price` 不存在，仅显示当日涨跌。

---

## Step 4: 异动检测

扫描所有标的，标记超过阈值的涨跌：

| 市场类型 | 异动阈值 | 标记 |
|---|---|---|
| 股票 (US/HK) | >=3% | 暴涨/暴跌 |
| 加密货币 | >=5% | 暴涨/暴跌 |

---

## Step 5: 生成报告并输出

### 输出结构

按以下顺序组织报告：

**1. 标题与时间**
- 根据播报模式选择标题（美股早报 / 港股晚报 / 加密特报 / 全市场报告）
- 标注生成时间和数据时效

**2. 持仓盈亏表**

| 标的 | 现价 | 日涨跌 | 持仓 | 市值 | 浮动盈亏 | 盈亏% |
|---|---|---|---|---|---|---|

- 按市场分组（美股 / 港股 / 加密）
- 根据播报模式过滤：早报主要展示美股，晚报主要展示港股
- 末行汇总：总市值、总日盈亏

**3. 关注列表速览**

| 标的 | 现价 | 涨跌幅 |
|---|---|---|

- 不含持仓已覆盖的标的，避免重复
- 外汇/商品单独分组

**4. 加密货币资金指标**（如有 CRYPTO_RATIOS 数据）

- ETH/BTC、SOL/ETH 等汇率变化
- 稳定币脱锚监测

**5. 异动告警**

- 列出所有超过阈值的标的
- 如无异动，输出"市场波动平稳"

**6. 市场点评**

基于以上数据，给出 3-5 句简要分析：
- 整体市场情绪（涨多跌少？权重股领涨？）
- 持仓中值得关注的变化
- 如果有异动标的，简要分析可能原因
- 如果是早报，提示今日港股可能的联动；如果是晚报，提示今晚美股关注点

### 数据时效标注

所有价格数据必须标注时效：

| 场景 | 标注 |
|---|---|
| 美股在早报模式 | [昨收] 或 [盘后] |
| 港股在晚报模式 | [今收] |
| 加密货币 | [实时] |
| 外汇/商品 | [延迟15min] |

---

## Reference Files

- `references/data_sources.md` — 各数据源的 API 详情、请求格式、错误码和降级方案
