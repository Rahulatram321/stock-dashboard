# Stock Data Intelligence Dashboard

A comprehensive, production-ready stock analytics platform that fetches, processes, and visualizes daily data for 8 major Indian stocks. Built with FastAPI, SQLAlchemy, and Chart.js, this dashboard provides real-time metrics, technical indicators, comparative analysis, and market movers — all served through a clean, self-contained frontend interface with zero build steps required.

## Tech Stack

| Library              | Purpose                                                     |
| -------------------- | ----------------------------------------------------------- |
| **FastAPI**          | REST API framework with automatic OpenAPI/Swagger docs      |
| **Uvicorn**          | ASGI server for running the FastAPI application             |
| **SQLAlchemy**       | ORM for SQLite database operations                          |
| **yfinance**         | Fetching historical OHLCV stock data from Yahoo Finance     |
| **Pandas**           | Data manipulation, cleaning, and calculated columns         |
| **NumPy**            | Correlation coefficient computation for stock comparison    |
| **Chart.js**         | Client-side charting library for interactive visualizations |
| **Requests**         | HTTP client library (available for extensions)              |
| **Python-Multipart** | Form data parsing support for FastAPI                       |
| **Python-Dotenv**    | Environment variable management                             |
| **Pydantic**         | Data validation and serialization for API schemas           |

## Setup Instructions

### Prerequisites

- Python 3.9 or higher
- pip package manager

### Installation

1. **Navigate to the project directory:**

   ```bash
   cd stock_dashboard
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Start the backend server:**

   ```bash
   python main.py
   ```

   The server will start on `http://localhost:8000`. On first run, it will automatically fetch 1 year of data for all 8 stocks and store it in a SQLite database (`stock_data.db`). This initial data collection may take 1-3 minutes depending on your internet connection.

4. **Open the frontend:**
   Simply open `frontend/index.html` in your web browser. You can do this by:
   - Double-clicking the file in your file explorer
   - Running: `start frontend/index.html` (Windows) or `open frontend/index.html` (Mac)

5. **Access API documentation:**
   Visit `http://localhost:8000/docs` for the interactive Swagger UI with all endpoints documented and testable.

## API Endpoints

### GET `/companies`

Returns a list of all 8 tracked companies with their latest stock data.

**Response:**

```json
[
  {
    "symbol": "RELIANCE.NS",
    "name": "Reliance Industries",
    "current_price": 2456.75,
    "daily_return": 1.23,
    "volatility_score": 2.15
  }
]
```

**Example curl:**

```bash
curl http://localhost:8000/companies
```

---

### GET `/data/{symbol}?days=30`

Returns the last N days (default 30) of stock data for a given symbol, sorted by date ascending.

**Path Parameters:**

- `symbol` (required): Stock symbol (e.g., `RELIANCE.NS`, `TCS.NS`)

**Query Parameters:**

- `days` (optional): Number of days to return (1-365, default: 30)

**Example curl:**

```bash
curl "http://localhost:8000/data/INFY.NS?days=60"
```

---

### GET `/summary/{symbol}`

Returns aggregate statistics for a stock over its entire history in the database.

**Response:**

```json
{
  "symbol": "TCS.NS",
  "week52_high": 4049.5,
  "week52_low": 3056.75,
  "avg_close": 3562.34,
  "avg_daily_return": 0.05,
  "avg_volatility": 1.87,
  "total_trading_days": 245
}
```

**Example curl:**

```bash
curl http://localhost:8000/summary/HDFCBANK.NS
```

---

### GET `/compare?symbol1=INFY.NS&symbol2=TCS.NS`

Compares two stocks by returning their last 90 days of closing prices aligned by date, plus the Pearson correlation coefficient between their daily returns.

**Query Parameters:**

- `symbol1` (required): First stock symbol
- `symbol2` (required): Second stock symbol

**Response:**

```json
{
  "symbol1": "INFY.NS",
  "symbol2": "TCS.NS",
  "data1": [{ "date": "2025-01-15T00:00:00", "close": 1823.45 }],
  "data2": [{ "date": "2025-01-15T00:00:00", "close": 3789.2 }],
  "correlation": 0.7834
}
```

**Example curl:**

```bash
curl "http://localhost:8000/compare?symbol1=INFY.NS&symbol2=TCS.NS"
```

---

### GET `/top-movers`

Returns the top 3 gainers and top 3 losers by daily return percentage for the most recent trading date in the database.

**Response:**

```json
{
  "top_gainers": [
    {
      "symbol": "SBIN.NS",
      "name": "State Bank of India",
      "current_price": 623.4,
      "daily_return": 2.45
    }
  ],
  "top_losers": [
    {
      "symbol": "WIPRO.NS",
      "name": "Wipro",
      "current_price": 445.8,
      "daily_return": -1.87
    }
  ]
}
```

**Example curl:**

```bash
curl http://localhost:8000/top-movers
```

---

### GET `/`

Health check endpoint.

**Example curl:**

```bash
curl http://localhost:8000/
```

## Custom Metric: Volatility Score

The **volatility_score** is a custom metric calculated as the **30-day coefficient of variation expressed as a percentage**:

```
volatility_score = (30-day rolling_std / 30-day rolling_mean) × 100
```

### What it means:

- It measures the relative dispersion of closing prices over a rolling 30-day window
- A **higher volatility score** (e.g., 5%+) indicates the stock price fluctuates significantly relative to its average — implying higher risk and potentially higher reward
- A **lower volatility score** (e.g., <1%) indicates stable, predictable price movements

### Why it's useful:

1. **Risk Assessment**: Unlike raw standard deviation, the coefficient of variation normalizes volatility relative to price level, making it comparable across stocks with different price ranges (e.g., comparing a ₹500 stock to a ₹4000 stock)
2. **Portfolio Construction**: Helps identify which stocks are more stable vs. speculative, aiding in balanced portfolio allocation
3. **Trend Detection**: A rising volatility score often precedes significant price movements, serving as an early warning signal

## Screenshots

_Placeholders — replace with actual screenshots once the application is running._

### Dashboard Overview

![Dashboard Overview](screenshots/dashboard-overview.png)

### Stock Detail View

![Stock Detail](screenshots/stock-detail.png)

### Stock Comparison

![Stock Comparison](screenshots/stock-comparison.png)

## Future Improvements

1. **ML-Based Prediction**: Integrate machine learning models (LSTM, Random Forest, or Prophet) to predict next-day closing prices and generate buy/sell signals based on historical patterns and technical indicators.

2. **WebSocket Live Data**: Replace batch data collection with real-time WebSocket connections to a live market data provider (e.g., Kite Connect, Upstox) for intraday price streaming and live dashboard updates.

3. **Deployment on Render**: Package the application with a `Dockerfile` and deploy on Render.com or Railway.app with a managed PostgreSQL database, environment-based configuration, and CI/CD pipelines for automated deployments.

4. **Additional Technical Indicators**: Add RSI (Relative Strength Index), MACD (Moving Average Convergence Divergence), Bollinger Bands, and Volume-weighted Average Price (VWAP) for deeper technical analysis.

5. **User Authentication & Watchlists**: Implement JWT-based authentication with personalized watchlists, alerts, and portfolio tracking features for individual user accounts.
