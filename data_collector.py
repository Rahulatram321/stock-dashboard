"""Data collection module for fetching and processing stock data using yfinance."""

import logging
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import StockPrice, SessionLocal, create_tables, is_db_empty

logger = logging.getLogger(__name__)

STOCKS: Dict[str, List[str]] = {
    "IT": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS"],
    "Banking": [
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "SBIN.NS",
        "AXISBANK.NS",
        "KOTAKBANK.NS",
    ],
    "Energy": ["RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "COALINDIA.NS"],
    "Finance": [
        "BAJFINANCE.NS",
        "BAJAJFINSV.NS",
        "HDFCLIFE.NS",
        "SBILIFE.NS",
        "ICICIGI.NS",
    ],
    "Consumer": [
        "HINDUNILVR.NS",
        "ITC.NS",
        "NESTLEIND.NS",
        "BRITANNIA.NS",
        "DABUR.NS",
    ],
    "Auto": [
        "MARUTI.NS",
        "TMCV.NS",
        "M&M.NS",
        "BAJAJ-AUTO.NS",
        "EICHERMOT.NS",
    ],
}

SECTOR_STOCKS = STOCKS
STOCK_SYMBOLS: List[str] = [
    symbol for sector_symbols in STOCKS.values() for symbol in sector_symbols
]
SECTOR_BY_SYMBOL: Dict[str, str] = {
    symbol: sector for sector, symbols in STOCKS.items() for symbol in symbols
}
SYMBOL_ALIASES: Dict[str, str] = {
    "TATAMOTORS": "TMCV.NS",
    "TATAMOTORS.NS": "TMCV.NS",
}

COMPANY_NAMES: Dict[str, str] = {
    "TCS.NS": "Tata Consultancy Services",
    "INFY.NS": "Infosys",
    "WIPRO.NS": "Wipro",
    "HCLTECH.NS": "HCL Technologies",
    "TECHM.NS": "Tech Mahindra",
    "HDFCBANK.NS": "HDFC Bank",
    "ICICIBANK.NS": "ICICI Bank",
    "SBIN.NS": "State Bank of India",
    "AXISBANK.NS": "Axis Bank",
    "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "RELIANCE.NS": "Reliance Industries",
    "ONGC.NS": "Oil & Natural Gas Corporation",
    "NTPC.NS": "NTPC Limited",
    "POWERGRID.NS": "Power Grid Corporation",
    "COALINDIA.NS": "Coal India",
    "BAJFINANCE.NS": "Bajaj Finance",
    "BAJAJFINSV.NS": "Bajaj Finserv",
    "HDFCLIFE.NS": "HDFC Life Insurance",
    "SBILIFE.NS": "SBI Life Insurance",
    "ICICIGI.NS": "ICICI Lombard General Insurance",
    "HINDUNILVR.NS": "Hindustan Unilever",
    "ITC.NS": "ITC Limited",
    "NESTLEIND.NS": "Nestle India",
    "BRITANNIA.NS": "Britannia Industries",
    "DABUR.NS": "Dabur India",
    "MARUTI.NS": "Maruti Suzuki India",
    "TMCV.NS": "Tata Motors Limited",
    "M&M.NS": "Mahindra & Mahindra",
    "BAJAJ-AUTO.NS": "Bajaj Auto",
    "EICHERMOT.NS": "Eicher Motors",
}


def canonical_symbol(symbol: str) -> str:
    """Resolve known legacy tickers to the working Yahoo Finance symbol."""

    normalized = symbol.strip().upper()
    return SYMBOL_ALIASES.get(normalized, normalized)


def get_sector(symbol: str) -> Optional[str]:
    """Get the sector for a given stock symbol."""

    return SECTOR_BY_SYMBOL.get(canonical_symbol(symbol))


def fetch_stock_data(symbol: str) -> pd.DataFrame:
    """Fetch 1 year of daily OHLCV data for a given stock symbol."""

    try:
        logger.info("Fetching data for %s...", symbol)
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")

        if df.empty:
            logger.warning("No data returned for %s", symbol)
            return pd.DataFrame()

        logger.info("Fetched %d rows for %s", len(df), symbol)
        return df

    except Exception as exc:
        logger.error("Error fetching data for %s: %s", symbol, exc)
        return pd.DataFrame()


def clean_and_calculate(
    df: pd.DataFrame, symbol: str, sector: Optional[str] = None
) -> pd.DataFrame:
    """Clean data and add calculated columns."""

    if df.empty:
        return df

    try:
        cleaned = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
        cleaned.index = pd.to_datetime(cleaned.index)
        cleaned = cleaned.sort_index().reset_index()

        if "Date" not in cleaned.columns:
            date_column = cleaned.columns[0]
            cleaned = cleaned.rename(columns={date_column: "Date"})

        cleaned["daily_return"] = (
            (cleaned["Close"] - cleaned["Open"]) / cleaned["Open"]
        ) * 100
        cleaned["moving_avg_7"] = cleaned["Close"].rolling(window=7).mean()
        cleaned["week52_high"] = cleaned["Close"].rolling(
            window=252, min_periods=30
        ).max()
        cleaned["week52_low"] = cleaned["Close"].rolling(
            window=252, min_periods=30
        ).min()

        rolling_std = cleaned["Close"].rolling(window=30).std()
        rolling_mean = cleaned["Close"].rolling(window=30).mean()
        cleaned["volatility_score"] = (rolling_std / rolling_mean) * 100

        cleaned["symbol"] = symbol
        cleaned["sector"] = sector or get_sector(symbol)

        cleaned = cleaned.rename(
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
            "Cleaned data for %s: %d rows ready for storage.",
            symbol,
            len(cleaned),
        )
        return cleaned

    except Exception as exc:
        logger.error("Error cleaning data for %s: %s", symbol, exc)
        return pd.DataFrame()


def store_in_database(
    df: pd.DataFrame, symbol: str, db: Session, sector: Optional[str] = None
) -> int:
    """Store cleaned stock data in the database."""

    if df.empty:
        logger.warning("No data to store for %s", symbol)
        return 0

    try:
        resolved_sector = sector or get_sector(symbol)

        db.query(StockPrice).filter(StockPrice.symbol == symbol).delete()

        rows_stored = 0
        for _, row in df.iterrows():
            stock_price = StockPrice(
                symbol=str(row.get("symbol", symbol)),
                sector=str(row.get("sector", resolved_sector))
                if row.get("sector", resolved_sector) is not None
                else None,
                date=pd.to_datetime(row["date"]).to_pydatetime(),
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
        logger.info("Stored %d rows for %s", rows_stored, symbol)
        return rows_stored

    except Exception as exc:
        db.rollback()
        logger.error("Error storing data for %s: %s", symbol, exc)
        return 0


def backfill_missing_derived_metrics(db: Session) -> int:
    """Recalculate derived metrics for rows missing 52-week values."""

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
        "Found stale derived metrics for %d symbols. Recomputing from stored prices.",
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

            frame = pd.DataFrame(
                [{"open": record.open, "close": record.close} for record in records]
            )

            frame["daily_return"] = ((frame["close"] - frame["open"]) / frame["open"]) * 100
            frame["moving_avg_7"] = frame["close"].rolling(window=7).mean()
            frame["week52_high"] = frame["close"].rolling(
                window=252, min_periods=30
            ).max()
            frame["week52_low"] = frame["close"].rolling(
                window=252, min_periods=30
            ).min()

            rolling_std = frame["close"].rolling(window=30).std()
            rolling_mean = frame["close"].rolling(window=30).mean()
            frame["volatility_score"] = (rolling_std / rolling_mean) * 100

            for record, row in zip(records, frame.itertuples(index=False)):
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

    except Exception as exc:
        db.rollback()
        logger.error("Error backfilling derived metrics: %s", exc)
        return 0


def backfill_sector_metadata(db: Session) -> int:
    """Populate the sector column for legacy rows after a schema upgrade."""

    updated_rows = 0

    try:
        for symbol, sector in SECTOR_BY_SYMBOL.items():
            result = db.execute(
                text(
                    "UPDATE stock_prices "
                    "SET sector = :sector "
                    "WHERE symbol = :symbol "
                    "AND (sector IS NULL OR sector <> :sector)"
                ),
                {"symbol": symbol, "sector": sector},
            )
            updated_rows += int(result.rowcount or 0)

        db.commit()

        if updated_rows:
            logger.info("Backfilled sector metadata for %d rows.", updated_rows)

        return updated_rows

    except Exception as exc:
        db.rollback()
        logger.error("Error backfilling sector metadata: %s", exc)
        return 0


def get_existing_symbols(db: Session) -> set[str]:
    """Return the set of symbols already present in the database."""

    rows = db.execute(text("SELECT DISTINCT symbol FROM stock_prices")).scalars().all()
    return {str(symbol) for symbol in rows}


def collect_symbol(symbol: str, sector: str, db: Session) -> int:
    """Fetch, transform, and store a single stock symbol."""

    raw_df = fetch_stock_data(symbol)
    if raw_df.empty:
        logger.warning("Skipping %s due to empty source data", symbol)
        return 0

    clean_df = clean_and_calculate(raw_df, symbol, sector)
    if clean_df.empty:
        logger.warning("Skipping %s due to cleaning failure", symbol)
        return 0

    return store_in_database(clean_df, symbol, db, sector)


def run_data_collection() -> None:
    """Fetch, clean, and store data for all tracked stocks when needed."""

    logger.info("Starting data collection process...")
    create_tables()

    db = SessionLocal()
    try:
        repaired_rows = backfill_missing_derived_metrics(db)
        sector_rows = backfill_sector_metadata(db)

        symbols_to_collect: List[str]
        if is_db_empty():
            logger.info("Database is empty. Collecting all %d tracked stocks.", len(STOCK_SYMBOLS))
            symbols_to_collect = list(STOCK_SYMBOLS)
        else:
            existing_symbols = get_existing_symbols(db)
            symbols_to_collect = [
                symbol for symbol in STOCK_SYMBOLS if symbol not in existing_symbols
            ]

            if symbols_to_collect:
                logger.info(
                    "Database has %d/%d tracked symbols. Collecting %d missing symbols.",
                    len(existing_symbols & set(STOCK_SYMBOLS)),
                    len(STOCK_SYMBOLS),
                    len(symbols_to_collect),
                )
            elif repaired_rows or sector_rows:
                logger.info(
                    "Database already contains tracked symbols. Repaired %d rows and updated %d sector values.",
                    repaired_rows,
                    sector_rows,
                )
                return
            else:
                logger.info("Database already contains all tracked symbols. Skipping collection.")
                return

        total_rows = 0
        for sector, sector_symbols in STOCKS.items():
            logger.info("Processing sector %s (%d stocks)", sector, len(sector_symbols))
            for symbol in sector_symbols:
                if symbol not in symbols_to_collect:
                    continue
                total_rows += collect_symbol(symbol, sector, db)

        logger.info(
            "Data collection complete. Stored %d rows across %d tracked symbols in %d sectors.",
            total_rows,
            len(STOCK_SYMBOLS),
            len(STOCKS),
        )

    except Exception as exc:
        logger.error("Data collection failed: %s", exc)
        raise
    finally:
        db.close()


def get_company_name(symbol: str) -> str:
    """Get the full company name for a symbol."""

    canonical = canonical_symbol(symbol)
    return COMPANY_NAMES.get(canonical, canonical)
