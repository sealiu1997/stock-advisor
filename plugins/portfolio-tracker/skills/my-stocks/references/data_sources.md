# 数据源 API 参考

## 1. yfinance (美股 / 外汇 / 商品)

### 批量下载

```python
import yfinance as yf

# 批量下载多只股票，2天数据用于计算涨跌
data = yf.download(["AAPL", "GOOG", "MSFT"], period="2d", progress=False)
# data["Close"] → DataFrame, 列为 ticker
# data["Close"].iloc[-1] → 最新收盘价
# data["Close"].iloc[-2] → 前一日收盘价
```

### 单只股票详细信息

```python
t = yf.Ticker("AAPL")
t.info                  # 完整信息字典 (marketCap, pe, sector, etc.)
t.fast_info             # 轻量级: last_price, market_cap, 50d/200d avg
t.history(period="1mo") # OHLCV DataFrame
t.calendar              # 下次财报日、除息日等
t.news                  # 最新新闻列表
```

### 外汇和商品 symbol 格式

| 类型 | yfinance symbol | 示例 |
|---|---|---|
| 外汇对 | `{PAIR}=X` | `EURUSD=X`, `GBPUSD=X`, `USDJPY=X` |
| 黄金期货 | `GC=F` | |
| 原油期货 | `CL=F` | |
| 黄金 ETF | `GLD` | |
| 美元指数 | `DX-Y.NYB` | |

### 常见错误与处理

| 错误 | 原因 | 处理 |
|---|---|---|
| 返回空 DataFrame | symbol 不存在或被下线 | 跳过并标注 |
| HTTPError 429 | 频率限制 | sleep 2s 后重试一次 |
| 盘后数据 | `.info["postMarketPrice"]` | 优先使用盘后价格，标注 [盘后] |

---

## 2. 腾讯财经 (港股)

### 接口格式

```
GET http://qt.gtimg.cn/q=r_hk{code}
```

- `code` 为 5 位港股代码，不足补零，如 `01810`
- 返回编码: GBK
- 返回格式: `v_r_hk01810="1~小米集团-W~01810~32.500~..."`
- 字段以 `~` 分隔

### 关键字段索引

| 索引 | 含义 |
|---|---|
| 1 | 股票名称 |
| 2 | 代码 |
| 3 | 当前价格 |
| 4 | 昨收价 |
| 5 | 开盘价 |
| 6 | 最高价 |
| 7 | 最低价 |
| 32 | 涨跌幅 (%) |

### 降级方案

腾讯接口失败时，使用 yfinance：

```python
t = yf.Ticker("1810.HK")
price = t.fast_info.last_price
```

---

## 3. Binance (加密货币)

### 24h 行情

```
GET https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}
```

- 无需 API key
- `symbol` 格式: `BTCUSDT`, `ETHUSDT`, `SOLUSDT` (全大写)

### 关键返回字段

| 字段 | 含义 |
|---|---|
| `lastPrice` | 最新价格 |
| `priceChangePercent` | 24h 涨跌幅 (%) |
| `highPrice` | 24h 最高 |
| `lowPrice` | 24h 最低 |
| `volume` | 24h 成交量 (base asset) |
| `quoteVolume` | 24h 成交额 (quote asset, 通常 USDT) |

### 批量查询

```
GET https://api.binance.com/api/v3/ticker/24hr
```

无参数返回所有交易对（较慢，数据量大）。建议逐个查询或用 `symbols` 参数：

```
GET https://api.binance.com/api/v3/ticker/24hr?symbols=["BTCUSDT","ETHUSDT"]
```

### 降级方案

Binance 不可用时（如某些地区网络限制），使用 CoinGecko：

```
GET https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true
```

---

## 4. Stooq (美股降级)

### CSV 接口

```
GET https://stooq.com/q/l/?s={symbol}.us&f=sd2ohlcv&h&e=csv
```

- 返回 CSV 格式
- 列: Symbol, Date, Open, High, Low, Close, Volume
- 无涨跌幅字段，需自行计算
- 仅作为 yfinance 不可用时的降级方案
