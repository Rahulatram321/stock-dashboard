"""Data collection module for fetching and processing stock data using yfinance."""

import logging
from datetime import datetime
from typing import List

import numpy as np
import pandas as pd
import yfinance as yf
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import StockPrice, SessionLocal, create_tables, is_db_empty

logger = logging.getLogger(__name__)

STOCK_SYMBOLS: List[str] = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "WIPRO.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BAJFINANCE.NS",
]

COMPANY_NAMES: dict = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "INFY.NS": "Infosys",
    "HDFCBANK.NS": "HDFC Bank",
    "WIPRO.NS": "Wipro",
    "ICICIBANK.NS": "ICICI Bank",
    "SBIN.NS": "State Bank of India",
    "BAJFINANCE.NS": "Bajaj Finance",
}


def fetch_stock_data(symbol: str) -> pd.DataFrame:
    """
    Fetch 1 year of daily OHLCV data for a given stock symbol.

    Args:
        symbol: Yahoo Finance stock symbol (e.g., 'RELIANCE.NS')

    Returns:
        DataFrame with raw OHLCV data
    """
    try:
        logger.info(f"Fetching data for {symbol}...")
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")

        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return pd.DataFrame()

        logger.info(f"Fetched {len(df)} rows for {symbol}")
        return df

    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def clean_and_calculate(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Clean data and add calculated columns.

    Args:
        df: Raw OHLCV DataFrame from yfinance
        symbol: Stock symbol for logging

    Returns:
        Cleaned DataFrame with calculated columns
    """
    if df.empty:
        return df

    try:
        # Drop rows with NaN in essential columns
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

        # Ensure Date is datetime
        df.index = pd.to_datetime(df.index)

        # Sort by date
        df = df.sort_index()

        # Reset index to make Date a column
        df = df.reset_index()
        df = df.rename(columns={"index": "Date"})

        if "Date" not in df.columns and df.index.name == "Date":
            df = df.reset_index()

        # Ensure Date column exists
        if "Date" not in df.columns:
            df["Date"] = df.index

        # Calculate derived columns
        # 1. Daily return as percentage: (Close - Open) / Open * 100
        df["daily_return"] = ((df["Close"] - df["Open"]) / df["Open"]) * 100

        # 2. 7-day moving average of Close
        df["moving_avg_7"] = df["Close"].rolling(window=7).mean()

        # 3. 52-week high (252 trading days, minimum 30 periods for stability)
        df["week52_high"] = df["Close"].rolling(window=252, min_periods=30).max()

        # 4. 52-week low (252 trading days, minimum 30 periods for stability)
        df["week52_low"] = df["Close"].rolling(window=252, min_periods=30).min()

        # 5. Volatility score: 30-day coefficient of variation as percentage
        rolling_std = df["Close"].rolling(window=30).std()
        rolling_mean = df["Close"].rolling(window=30).mean()
        df["volatility_score"] = (rolling_std / rolling_mean) * 100

        # Add symbol column
        df["symbol"] = symbol

        # Standardize column names to match DB schema
        df = df.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )

        logger.info(
            f"Cleaned data for {symbol}: {len(df)} rows, columns: {list(df.columns)}"
        )
        return df

    except Exception as e:
        logger.error(f"Error cleaning data for {symbol}: {e}")
        return pd.DataFrame()


def store_in_database(df: pd.DataFrame, symbol: str, db: Session) -> int:
    """
    Store cleaned stock data in the database.

    Args:
        df: Cleaned DataFrame with stock data
        symbol: Stock symbol
        db: SQLAlchemy session

    Returns:
        Number of rows stored
    """
    if df.empty:
        logger.warning(f"No data to store for {symbol}")
        return 0

    try:
        # Delete existing data for this symbol to avoid duplicates
        db.query(StockPrice).filter(StockPrice.symbol == symbol).delete()

        rows_stored = 0
        for _, row in df.iterrows():
            stock_price = StockPrice(
                symbol=str(row.get("symbol", symbol)),
                date=pd.to_datetime(row["date"]),
                open=float(row["open"]) if pd.notna(row.get("open")) else None,
                high=float(row["high"]) if pd.notna(row.get("high")) else None,
                low=float(row["low"]) if pd.notna(row.get("low")) else None,
                close=float(row["close"]) if pd.notna(row.get("close")) else None,
                volume=float(row["volume"]) if pd.notna(row.get("volume")) else None,
                daily_return=float(row["daily_return"])
                if pd.notna(row.get("daily_return"))
                else None,
                moving_avg_7=float(row["moving_avg_7"])
                if pd.notna(row.get("moving_avg_7"))
                else None,
                week52_high=float(row["week52_high"])
                if pd.notna(row.get("week52_high"))
                else None,
                week52_low=float(row["week52_low"])
                if pd.notna(row.get("week52_low"))
                else None,
                volatility_score=float(row["volatility_score"])
                if pd.notna(row.get("volatility_score"))
                else None,
            )
            db.add(stock_price)
            rows_stored += 1

        db.commit()
        logger.info(f"Successfully stored {rows_stored} rows for {symbol}")
        return rows_stored

    except Exception as e:
        db.rollback()
        logger.error(f"Error storing data for {symbol}: {e}")
        return 0


def backfill_missing_derived_metrics(db: Session) -> int:
    """
    Recalculate derived metrics for existing rows when stale data is detected.

    Args:
        db: SQLAlchemy session

    Returns:
        Number of rows updated
    """
    stale_symbols = [
        symbol
        for symbol, filled_highs, filled_lows in db.query(
            StockPrice.symbol,
            func.count(StockPrice.week52_high),
            func.count(StockPrice.week52_low),
        )
        .group_by(StockPrice.symbol)
        .all()
        if filled_highs == 0 or filled_lows == 0
    ]

    if not stale_symbols:
        return 0

    logger.info(
        "Found stale derived metrics for %d symbols. Backfilling from stored prices.",
        len(stale_symbols),
    )

    try:
        updated_rows = 0

        for symbol in stale_symbols:
            records = (
                db.query(StockPrice)
                .filter(StockPrice.symbol == symbol)
                .order_by(StockPrice.date.asc())
                .all()
            )

            if not records:
                continue

            df = pd.DataFrame(
                [
                    {
                        "open": record.open,
                        "close": record.close,
                    }
                    for record in records
                ]
            )

            df["daily_return"] = ((df["close"] - df["open"]) / df["open"]) * 100
            df["moving_avg_7"] = df["close"].rolling(window=7).mean()
            df["week52_high"] = df["close"].rolling(
                window=252, min_periods=30
            ).max()
            df["week52_low"] = df["close"].rolling(
                window=252, min_periods=30
            ).min()

            rolling_std = df["close"].rolling(window=30).std()
            rolling_mean = df["close"].rolling(window=30).mean()
            df["volatility_score"] = (rolling_std / rolling_mean) * 100

            for record, row in zip(records, df.itertuples(index=False)):
                record.daily_return = (
                    float(row.daily_return) if pd.notna(row.daily_return) else None
                )
                record.moving_avg_7 = (
                    float(row.moving_avg_7) if pd.notna(row.moving_avg_7) else None
                )
                record.week52_high = (
                    float(row.week52_high) if pd.notna(row.week52_high) else None
                )
                record.week52_low = (
                    float(row.week52_low) if pd.notna(row.week52_low) else None
                )
                record.volatility_score = (
                    float(row.volatility_score)
                    if pd.notna(row.volatility_score)
                    else None
                )

            updated_rows += len(records)

        db.commit()
        logger.info("Backfilled derived metrics for %d rows.", updated_rows)
        return updated_rows

    except Exception as e:
        db.rollback()
        logger.error(f"Error backfilling derived metrics: {e}")
        return 0


def run_data_collection() -> None:
    """
    Fetch, clean, and store data for all 8 stocks on startup if DB is empty.
    """
    logger.info("Starting data collection process...")

    # Create tables if they don't exist
    create_tables()

    db = SessionLocal()
    try:
        # Check if DB already has data
        if not is_db_empty():
            repaired_rows = backfill_missing_derived_metrics(db)
            if repaired_rows:
                logger.info(
                    "Database already contains data. Repaired %d stale rows.",
                    repaired_rows,
                )
            else:
                logger.info("Database already contains data. Skipping collection.")
            return

        total_rows = 0
        for symbol in STOCK_SYMBOLS:
            # Fetch raw data
            raw_df = fetch_stock_data(symbol)
            if raw_df.empty:
                logger.warning(f"Skipping {symbol} due to empty data")
                continue

            # Clean and calculate
            clean_df = clean_and_calculate(raw_df, symbol)
            if clean_df.empty:
                logger.warning(f"Skipping {symbol} due to cleaning failure")
                continue

            # Store in database
            rows = store_in_database(clean_df, symbol, db)
            total_rows += rows

        logger.info(
            f"Data collection complete. Total rows stored: {total_rows} across {len(STOCK_SYMBOLS)} stocks"
        )

    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        raise
    finally:
        db.close()


def get_company_name(symbol: str) -> str:
    """
    Get the full company name for a symbol.

    Args:
        symbol: Stock symbol

    Returns:
        Full company name
    """
    return COMPANY_NAMES.get(symbol, symbol)
