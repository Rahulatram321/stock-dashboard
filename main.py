"""FastAPI application for Stock Data Intelligence Dashboard."""

import logging
from contextlib import asynccontextmanager
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import StockPrice, SessionLocal, create_tables, get_db, is_db_empty
from data_collector import run_data_collection, get_company_name
from models import (
    CompanyInfo,
    StockDataPoint,
    StockSummary,
    CompareDataPoint,
    ComparisonResponse,
    MoversData,
    TopMoversResponse,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI application."""
    logger.info("Starting up Stock Data Intelligence Dashboard...")
    create_tables()
    run_data_collection()
    logger.info("Startup complete. Serving requests.")
    yield
    logger.info("Shutting down application.")


app = FastAPI(
    title="Stock Data Intelligence Dashboard",
    description="A comprehensive stock analytics platform providing real-time data, "
    "technical indicators, and comparative analysis for major Indian stocks.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_session() -> Session:
    """Dependency to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get(
    "/companies",
    response_model=List[CompanyInfo],
    tags=["Companies"],
    summary="Get all companies with latest stock data",
    description="Returns a list of all 8 tracked Indian stocks with their current price, "
    "daily return percentage, and volatility score based on the latest data in the database.",
)
def get_companies(db: Session = Depends(get_db_session)) -> List[CompanyInfo]:
    """Get all companies with their latest stock information."""
    try:
        # Get the latest date in the database
        latest_date_subquery = (
            db.query(StockPrice.symbol, func.max(StockPrice.date).label("max_date"))
            .group_by(StockPrice.symbol)
            .subquery()
        )

        # Get the latest row for each symbol
        latest_prices = (
            db.query(StockPrice)
            .join(
                latest_date_subquery,
                (StockPrice.symbol == latest_date_subquery.c.symbol)
                & (StockPrice.date == latest_date_subquery.c.max_date),
            )
            .all()
        )

        companies: List[CompanyInfo] = []
        for price in latest_prices:
            company = CompanyInfo(
                symbol=price.symbol,
                name=get_company_name(price.symbol),
                current_price=round(price.close, 2) if price.close else None,
                daily_return=round(price.daily_return, 4)
                if price.daily_return
                else None,
                volatility_score=round(price.volatility_score, 4)
                if price.volatility_score
                else None,
            )
            companies.append(company)

        companies.sort(key=lambda x: x.symbol)
        return companies

    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch companies: {str(e)}"
        )


@app.get(
    "/data/{symbol}",
    response_model=List[StockDataPoint],
    tags=["Stock Data"],
    summary="Get historical stock data",
    description="Returns the last N days (default 30) of stock data for the specified symbol, "
    "including OHLCV, daily return, and 7-day moving average. Sorted by date ascending.",
)
def get_stock_data(
    symbol: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db_session),
) -> List[StockDataPoint]:
    """Get historical stock data for a specific symbol."""
    try:
        records = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == symbol)
            .order_by(StockPrice.date.desc())
            .limit(days)
            .all()
        )

        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {symbol}",
            )

        # Sort by date ascending
        records.reverse()

        data_points: List[StockDataPoint] = []
        for record in records:
            point = StockDataPoint(
                date=record.date,
                open=round(record.open, 2) if record.open else None,
                high=round(record.high, 2) if record.high else None,
                low=round(record.low, 2) if record.low else None,
                close=round(record.close, 2) if record.close else None,
                volume=record.volume if record.volume else None,
                daily_return=round(record.daily_return, 4)
                if record.daily_return
                else None,
                moving_avg_7=round(record.moving_avg_7, 2)
                if record.moving_avg_7
                else None,
            )
            data_points.append(point)

        return data_points

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch data for {symbol}: {str(e)}",
        )


@app.get(
    "/summary/{symbol}",
    response_model=StockSummary,
    tags=["Stock Data"],
    summary="Get stock summary statistics",
    description="Returns aggregate statistics for the specified stock including 52-week "
    "high/low, average close, average daily return, average volatility, and total trading days.",
)
def get_summary(
    symbol: str, db: Session = Depends(get_db_session)
) -> StockSummary:
    """Get summary statistics for a specific stock."""
    try:
        records = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == symbol)
            .all()
        )

        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {symbol}",
            )

        # Calculate aggregates
        closes = [r.close for r in records if r.close is not None]
        returns = [r.daily_return for r in records if r.daily_return is not None]
        volatilities = [
            r.volatility_score for r in records if r.volatility_score is not None
        ]
        highs = [r.week52_high for r in records if r.week52_high is not None]
        lows = [r.week52_low for r in records if r.week52_low is not None]

        summary = StockSummary(
            symbol=symbol,
            week52_high=round(max(highs), 2) if highs else None,
            week52_low=round(min(lows), 2) if lows else None,
            avg_close=round(sum(closes) / len(closes), 2) if closes else None,
            avg_daily_return=round(sum(returns) / len(returns), 4)
            if returns
            else None,
            avg_volatility=round(sum(volatilities) / len(volatilities), 4)
            if volatilities
            else None,
            total_trading_days=len(records),
        )

        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching summary for {symbol}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch summary for {symbol}: {str(e)}",
        )


@app.get(
    "/compare",
    response_model=ComparisonResponse,
    tags=["Comparison"],
    summary="Compare two stocks",
    description="Returns the last 90 days of closing prices for two stocks aligned by date, "
    "plus the Pearson correlation coefficient between their daily returns.",
)
def compare_stocks(
    symbol1: str = Query(..., description="First stock symbol to compare"),
    symbol2: str = Query(..., description="Second stock symbol to compare"),
    db: Session = Depends(get_db_session),
) -> ComparisonResponse:
    """Compare two stocks' performance over the last 90 days."""
    try:
        # Get last 90 days for symbol1
        records1 = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == symbol1)
            .order_by(StockPrice.date.desc())
            .limit(90)
            .all()
        )

        # Get last 90 days for symbol2
        records2 = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == symbol2)
            .order_by(StockPrice.date.desc())
            .limit(90)
            .all()
        )

        if not records1:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {symbol1}",
            )
        if not records2:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {symbol2}",
            )

        # Sort by date ascending
        records1.reverse()
        records2.reverse()

        # Build data points
        data1 = [
            CompareDataPoint(date=r.date, close=round(r.close, 2) if r.close else None)
            for r in records1
        ]
        data2 = [
            CompareDataPoint(date=r.date, close=round(r.close, 2) if r.close else None)
            for r in records2
        ]

        # Calculate correlation of daily returns
        returns1 = [r.daily_return for r in records1 if r.daily_return is not None]
        returns2 = [r.daily_return for r in records2 if r.daily_return is not None]

        correlation: Optional[float] = None
        if len(returns1) > 1 and len(returns2) > 1:
            # Align the lengths
            min_len = min(len(returns1), len(returns2))
            corr_value = np.corrcoef(returns1[:min_len], returns2[:min_len])[0, 1]
            if not np.isnan(corr_value):
                correlation = round(float(corr_value), 4)

        return ComparisonResponse(
            symbol1=symbol1,
            symbol2=symbol2,
            data1=data1,
            data2=data2,
            correlation=correlation,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing {symbol1} and {symbol2}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compare stocks: {str(e)}",
        )


@app.get(
    "/top-movers",
    response_model=TopMoversResponse,
    tags=["Market"],
    summary="Get top gainers and losers",
    description="Returns the top 3 gainers and top 3 losers by daily return percentage "
    "for the most recent trading date available in the database.",
)
def get_top_movers(db: Session = Depends(get_db_session)) -> TopMoversResponse:
    """Get top 3 gainers and top 3 losers by daily return."""
    try:
        # Get the latest date in the database
        latest_date = (
            db.query(func.max(StockPrice.date)).scalar()
        )

        if not latest_date:
            raise HTTPException(
                status_code=404,
                detail="No data available in database",
            )

        # Get all records for the latest date
        latest_records = (
            db.query(StockPrice)
            .filter(StockPrice.date == latest_date)
            .all()
        )

        if not latest_records:
            raise HTTPException(
                status_code=404,
                detail="No data found for the latest date",
            )

        # Sort by daily_return (handle None values)
        valid_records = [r for r in latest_records if r.daily_return is not None]
        valid_records.sort(key=lambda x: x.daily_return, reverse=True)

        # Top 3 gainers
        gainers = []
        for record in valid_records[:3]:
            gainer = MoversData(
                symbol=record.symbol,
                name=get_company_name(record.symbol),
                current_price=round(record.close, 2) if record.close else None,
                daily_return=round(record.daily_return, 4),
            )
            gainers.append(gainer)

        # Bottom 3 losers
        losers = []
        for record in valid_records[-3:]:
            loser = MoversData(
                symbol=record.symbol,
                name=get_company_name(record.symbol),
                current_price=round(record.close, 2) if record.close else None,
                daily_return=round(record.daily_return, 4),
            )
            losers.append(loser)

        # Sort losers by daily_return ascending (most negative first)
        losers.sort(key=lambda x: x.daily_return)

        return TopMoversResponse(
            top_gainers=gainers,
            top_losers=losers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching top movers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch top movers: {str(e)}",
        )


@app.get("/", tags=["Health"], summary="Health check")
def root() -> dict:
    """Health check endpoint. Returns API status message."""
    return {"status": "ok", "message": "Stock Data Intelligence Dashboard API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)