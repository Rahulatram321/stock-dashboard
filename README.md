# StockIQ - NSE Market Intelligence Platform

![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-Frontend-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)
![Render](https://img.shields.io/badge/Deployed_on-Render-4B5563?style=for-the-badge&logo=render&logoColor=white)

StockIQ is a single-page NSE market dashboard built with FastAPI, SQLite, and Chart.js. It tracks 30 major stocks across 6 sectors, exposes market intelligence APIs, and ships with a fintech-style frontend for overview, sector, comparison, and forecast workflows.

## Features

- [x] 30 NSE stocks tracked in one platform
- [x] 6 sectors: IT, Banking, Energy, Finance, Consumer, Auto
- [x] 7 core REST endpoints for dashboard workflows
- [x] 7-day price prediction using linear regression
- [x] Sector heatmap with grouped stock tiles
- [x] Live deployment on Render and GitHub Pages

## Architecture

StockIQ follows a 4-layer flow:

1. Data Collection
   `data_collector.py` fetches 1 year of OHLCV data from Yahoo Finance, computes derived fields, and maps every symbol to a sector.
2. SQLite Database
   `stock_data.db` stores historical prices plus daily return, 7-day moving average, 52-week high, 52-week low, volatility score, and sector.
3. FastAPI API
   `main.py` exposes clean JSON endpoints for company lists, historical series, summaries, comparisons, sector views, movers, and prediction.
4. Chart.js Frontend
   `docs/index.html` is a single-file UI with overview cards, a simulated candlestick chart, comparison analytics, and a sector heatmap.

```text
Data Collection -> SQLite DB -> FastAPI -> Chart.js Frontend
```

## API Endpoints

These are the 7 core dashboard endpoints. A separate forecast route is documented in Custom Metrics below.

### 1. `GET /companies`

Returns the latest snapshot for every tracked company.

```json
[
  {
    "symbol": "TCS.NS",
    "name": "Tata Consultancy Services",
    "sector": "IT",
    "current_price": 2358.9,
    "daily_return": -0.6821,
    "volatility_score": 5.0122
  }
]
```

### 2. `GET /data/{symbol}?days=30`

Returns recent OHLCV history with daily return and 7-day moving average.

```json
[
  {
    "date": "2026-03-27T00:00:00",
    "open": 2375.0,
    "high": 2381.9,
    "low": 2348.55,
    "close": 2358.9,
    "volume": 5117420.0,
    "daily_return": -0.6821,
    "moving_avg_7": 2412.64
  }
]
```

### 3. `GET /summary/{symbol}`

Returns long-range summary statistics for one stock.

```json
{
  "symbol": "TCS.NS",
  "week52_high": 4585.8,
  "week52_low": 2358.9,
  "avg_close": 3361.8,
  "avg_daily_return": -0.0422,
  "avg_volatility": 4.7973,
  "total_trading_days": 248
}
```

### 4. `GET /compare?symbol1=TCS.NS&symbol2=INFY.NS`

Returns aligned closing-price series for both symbols plus their correlation coefficient.

```json
{
  "symbol1": "TCS.NS",
  "symbol2": "INFY.NS",
  "data1": [{ "date": "2026-01-02T00:00:00", "close": 3192.66 }],
  "data2": [{ "date": "2026-01-02T00:00:00", "close": 1404.95 }],
  "correlation": 0.6241
}
```

### 5. `GET /top-movers`

Returns the top 3 gainers and top 3 losers from the latest market snapshot.

```json
{
  "top_gainers": [
    {
      "symbol": "EICHERMOT.NS",
      "name": "Eicher Motors",
      "current_price": 6825.5,
      "daily_return": 0.5599
    }
  ],
  "top_losers": [
    {
      "symbol": "BAJFINANCE.NS",
      "name": "Bajaj Finance",
      "current_price": 6466.2,
      "daily_return": -3.5439
    }
  ]
}
```

### 6. `GET /sectors`

Returns one row per sector with the latest average return, volatility, and stock count.

```json
[
  {
    "sector": "IT",
    "avg_daily_return": -1.1362,
    "avg_volatility": 4.0453,
    "stock_count": 5
  }
]
```

### 7. `GET /sector/{sector_name}`

Returns every company in the requested sector with the latest market values.

```json
{
  "sector": "Auto",
  "stocks": [
    {
      "symbol": "TMCV.NS",
      "name": "Tata Motors Limited",
      "current_price": 394.8,
      "daily_return": -3.9088,
      "volatility_score": 7.6541
    }
  ]
}
```

## Custom Metrics

### Volatility Score

The volatility score is the 30-day coefficient of variation:

```text
volatility_score = (30-day rolling std / 30-day rolling mean) * 100
```

Higher values indicate wider price swings; lower values indicate steadier movement.

### Prediction Model

`GET /predict/{symbol}?days=7` fits a degree-1 line with `numpy.polyfit` over the last 60 closing prices and extends the line forward.

```json
{
  "symbol": "TMCV.NS",
  "historical": [{ "date": "2026-03-25", "close": 402.6 }],
  "predicted": [{ "date": "2026-04-02", "predicted_close": 392.14 }],
  "trend": "bearish"
}
```

- `trend = "bullish"` when slope > 0
- `trend = "bearish"` when slope <= 0

## Setup

### Prerequisites

- Python 3.11+
- `pip`

### Install and Run

1. Open the project folder:

   ```bash
   cd stock_dashboard
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Start the API:

   ```bash
   python main.py
   ```

4. Open the frontend:

   - Local file: `docs/index.html`
   - Local API docs: `http://localhost:8000/docs`

On startup, the app creates or migrates the SQLite schema, backfills sector metadata, and collects missing tracked symbols.

## Live Links

- Backend: [https://stock-dashboard-sykz.onrender.com](https://stock-dashboard-sykz.onrender.com)
- Frontend: [https://rahulatram321.github.io/stock-dashboard/](https://rahulatram321.github.io/stock-dashboard/)
- API Docs: [https://stock-dashboard-sykz.onrender.com/docs](https://stock-dashboard-sykz.onrender.com/docs)

## Notes

- As of April 1, 2026, Yahoo Finance no longer resolves `TATAMOTORS.NS` reliably. StockIQ keeps Tata Motors coverage by collecting `TMCV.NS` and accepting `TATAMOTORS.NS` as a compatibility alias in the API.
- The checked-in SQLite file now contains the full 30-stock, 6-sector dataset.
