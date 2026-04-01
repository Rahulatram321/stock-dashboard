"""FastAPI application for the StockIQ dashboard."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from data_collector import SECTOR_STOCKS, canonical_symbol, get_company_name, run_data_collection
from database import SessionLocal, StockPrice, create_tables
from models import (
    CompanyInfo,
    CompareDataPoint,
    ComparisonResponse,
    HistoricalPrice,
    MoversData,
    PredictionResponse,
    PredictedPrice,
    SectorDetail,
    SectorInfo,
    SectorStockInfo,
    StockDataPoint,
    StockSummary,
    TopMoversResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SECTOR_ORDER = ["IT", "Banking", "Energy", "Finance", "Consumer", "Auto"]


def normalize_symbol(symbol: str) -> str:
    """Normalize symbols so both INFY and INFY.NS resolve to the NSE form."""

    normalized = symbol.strip().upper()
    if not normalized.endswith(".NS"):
        normalized = f"{normalized}.NS"
    return canonical_symbol(normalized)


def resolve_sector_name(sector_name: str) -> Optional[str]:
    """Resolve sector names case-insensitively."""

    target = sector_name.strip().lower()
    for sector in SECTOR_STOCKS:
        if sector.lower() == target:
            return sector
    return None


def build_latest_rows_subquery(db: Session):
    """Return a subquery with the latest available row for each symbol."""

    return (
        db.query(
            StockPrice.symbol.label("symbol"),
            func.max(StockPrice.date).label("max_date"),
        )
        .group_by(StockPrice.symbol)
        .subquery()
    )


def get_latest_rows(db: Session, sector_name: Optional[str] = None) -> List[StockPrice]:
    """Fetch the latest record for each tracked symbol."""

    latest_rows_subquery = build_latest_rows_subquery(db)
    query = db.query(StockPrice).join(
        latest_rows_subquery,
        (StockPrice.symbol == latest_rows_subquery.c.symbol)
        & (StockPrice.date == latest_rows_subquery.c.max_date),
    )

    if sector_name:
        query = query.filter(StockPrice.sector == sector_name)

    return query.all()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI application."""

    logger.info("Starting up StockIQ...")
    create_tables()
    run_data_collection()
    logger.info("Startup complete. Serving requests.")
    yield
    logger.info("Shutting down application.")


app = FastAPI(
    title="StockIQ - NSE Market Intelligence Platform",
    description=(
        "A stock analytics platform for major Indian equities with sector summaries, "
        "comparisons, technical metrics, and linear-regression forecasts."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

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
)
def get_companies(db: Session = Depends(get_db_session)) -> List[CompanyInfo]:
    """Get all companies with their latest stock information."""

    try:
        latest_prices = get_latest_rows(db)
        if not latest_prices:
            raise HTTPException(status_code=404, detail="No company data available")

        companies = [
            CompanyInfo(
                symbol=price.symbol,
                name=get_company_name(price.symbol),
                sector=price.sector,
                current_price=round(price.close, 2) if price.close is not None else None,
                daily_return=round(price.daily_return, 4)
                if price.daily_return is not None
                else None,
                volatility_score=round(price.volatility_score, 4)
                if price.volatility_score is not None
                else None,
            )
            for price in latest_prices
        ]

        companies.sort(
            key=lambda company: (
                SECTOR_ORDER.index(company.sector)
                if company.sector in SECTOR_ORDER
                else len(SECTOR_ORDER),
                company.symbol,
            )
        )
        return companies

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching companies: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch companies: {exc}"
        ) from exc


@app.get(
    "/data/{symbol}",
    response_model=List[StockDataPoint],
    tags=["Stock Data"],
    summary="Get historical stock data",
)
def get_stock_data(
    symbol: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db_session),
) -> List[StockDataPoint]:
    """Get historical stock data for a specific symbol."""

    try:
        normalized_symbol = normalize_symbol(symbol)
        records = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == normalized_symbol)
            .order_by(StockPrice.date.desc())
            .limit(days)
            .all()
        )

        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {normalized_symbol}",
            )

        records.reverse()
        return [
            StockDataPoint(
                date=record.date,
                open=round(record.open, 2) if record.open is not None else None,
                high=round(record.high, 2) if record.high is not None else None,
                low=round(record.low, 2) if record.low is not None else None,
                close=round(record.close, 2) if record.close is not None else None,
                volume=record.volume if record.volume is not None else None,
                daily_return=round(record.daily_return, 4)
                if record.daily_return is not None
                else None,
                moving_avg_7=round(record.moving_avg_7, 2)
                if record.moving_avg_7 is not None
                else None,
            )
            for record in records
        ]

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching data for %s: %s", symbol, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch data for {symbol}: {exc}"
        ) from exc


@app.get(
    "/summary/{symbol}",
    response_model=StockSummary,
    tags=["Stock Data"],
    summary="Get stock summary statistics",
)
def get_summary(symbol: str, db: Session = Depends(get_db_session)) -> StockSummary:
    """Get summary statistics for a specific stock."""

    try:
        normalized_symbol = normalize_symbol(symbol)
        records = db.query(StockPrice).filter(StockPrice.symbol == normalized_symbol).all()

        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {normalized_symbol}",
            )

        closes = [record.close for record in records if record.close is not None]
        returns = [
            record.daily_return for record in records if record.daily_return is not None
        ]
        volatilities = [
            record.volatility_score
            for record in records
            if record.volatility_score is not None
        ]
        highs = [record.week52_high for record in records if record.week52_high is not None]
        lows = [record.week52_low for record in records if record.week52_low is not None]

        return StockSummary(
            symbol=normalized_symbol,
            week52_high=round(max(highs), 2) if highs else None,
            week52_low=round(min(lows), 2) if lows else None,
            avg_close=round(sum(closes) / len(closes), 2) if closes else None,
            avg_daily_return=round(sum(returns) / len(returns), 4) if returns else None,
            avg_volatility=round(sum(volatilities) / len(volatilities), 4)
            if volatilities
            else None,
            total_trading_days=len(records),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching summary for %s: %s", symbol, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch summary for {symbol}: {exc}"
        ) from exc


@app.get(
    "/compare",
    response_model=ComparisonResponse,
    tags=["Comparison"],
    summary="Compare two stocks",
)
def compare_stocks(
    symbol1: str = Query(..., description="First stock symbol to compare"),
    symbol2: str = Query(..., description="Second stock symbol to compare"),
    db: Session = Depends(get_db_session),
) -> ComparisonResponse:
    """Compare two stocks over the last 90 trading days."""

    try:
        normalized_symbol1 = normalize_symbol(symbol1)
        normalized_symbol2 = normalize_symbol(symbol2)

        records1 = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == normalized_symbol1)
            .order_by(StockPrice.date.desc())
            .limit(90)
            .all()
        )
        records2 = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == normalized_symbol2)
            .order_by(StockPrice.date.desc())
            .limit(90)
            .all()
        )

        if not records1:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {normalized_symbol1}",
            )
        if not records2:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {normalized_symbol2}",
            )

        frame_1 = pd.DataFrame(
            [
                {
                    "date": record.date,
                    "close_1": record.close,
                    "daily_return_1": record.daily_return,
                }
                for record in records1
            ]
        )
        frame_2 = pd.DataFrame(
            [
                {
                    "date": record.date,
                    "close_2": record.close,
                    "daily_return_2": record.daily_return,
                }
                for record in records2
            ]
        )

        aligned = pd.merge(frame_1, frame_2, on="date", how="inner").sort_values("date")

        data1 = [
            CompareDataPoint(
                date=pd.to_datetime(row.date).to_pydatetime(),
                close=round(row.close_1, 2) if pd.notna(row.close_1) else None,
            )
            for row in aligned.itertuples(index=False)
        ]
        data2 = [
            CompareDataPoint(
                date=pd.to_datetime(row.date).to_pydatetime(),
                close=round(row.close_2, 2) if pd.notna(row.close_2) else None,
            )
            for row in aligned.itertuples(index=False)
        ]

        correlation: Optional[float] = None
        returns_frame = aligned.dropna(subset=["daily_return_1", "daily_return_2"])
        if len(returns_frame) > 1:
            corr_value = np.corrcoef(
                returns_frame["daily_return_1"], returns_frame["daily_return_2"]
            )[0, 1]
            if not np.isnan(corr_value):
                correlation = round(float(corr_value), 4)

        return ComparisonResponse(
            symbol1=normalized_symbol1,
            symbol2=normalized_symbol2,
            data1=data1,
            data2=data2,
            correlation=correlation,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error comparing %s and %s: %s", symbol1, symbol2, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to compare stocks: {exc}"
        ) from exc


@app.get(
    "/top-movers",
    response_model=TopMoversResponse,
    tags=["Market"],
    summary="Get top gainers and losers",
)
def get_top_movers(db: Session = Depends(get_db_session)) -> TopMoversResponse:
    """Get the top three gainers and losers from the latest per-symbol snapshot."""

    try:
        latest_records = [
            record for record in get_latest_rows(db) if record.daily_return is not None
        ]
        if not latest_records:
            raise HTTPException(status_code=404, detail="No market data available")

        gainers = sorted(
            [record for record in latest_records if record.daily_return > 0],
            key=lambda record: record.daily_return,
            reverse=True,
        )[:3]
        losers = sorted(
            [record for record in latest_records if record.daily_return < 0],
            key=lambda record: record.daily_return,
        )[:3]

        return TopMoversResponse(
            top_gainers=[
                MoversData(
                    symbol=record.symbol,
                    name=get_company_name(record.symbol),
                    current_price=round(record.close, 2)
                    if record.close is not None
                    else None,
                    daily_return=round(record.daily_return, 4),
                )
                for record in gainers
            ],
            top_losers=[
                MoversData(
                    symbol=record.symbol,
                    name=get_company_name(record.symbol),
                    current_price=round(record.close, 2)
                    if record.close is not None
                    else None,
                    daily_return=round(record.daily_return, 4),
                )
                for record in losers
            ],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching top movers: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch top movers: {exc}"
        ) from exc


@app.get(
    "/sectors",
    response_model=List[SectorInfo],
    tags=["Sectors"],
    summary="Get all sectors with performance metrics",
)
def get_sectors(db: Session = Depends(get_db_session)) -> List[SectorInfo]:
    """Get sector averages from the latest available snapshot."""

    try:
        latest_records = get_latest_rows(db)
        if not latest_records:
            raise HTTPException(status_code=404, detail="No sector data available")

        grouped: dict[str, list[StockPrice]] = {}
        for record in latest_records:
            sector = record.sector or "Unknown"
            grouped.setdefault(sector, []).append(record)

        sector_summaries = []
        for sector, records in grouped.items():
            returns = [
                record.daily_return for record in records if record.daily_return is not None
            ]
            volatilities = [
                record.volatility_score
                for record in records
                if record.volatility_score is not None
            ]
            sector_summaries.append(
                SectorInfo(
                    sector=sector,
                    avg_daily_return=round(sum(returns) / len(returns), 4)
                    if returns
                    else None,
                    avg_volatility=round(sum(volatilities) / len(volatilities), 4)
                    if volatilities
                    else None,
                    stock_count=len(records),
                )
            )

        sector_summaries.sort(
            key=lambda item: (
                SECTOR_ORDER.index(item.sector)
                if item.sector in SECTOR_ORDER
                else len(SECTOR_ORDER),
                item.sector,
            )
        )
        return sector_summaries

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching sectors: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch sectors: {exc}"
        ) from exc


@app.get(
    "/sector/{sector_name}",
    response_model=SectorDetail,
    tags=["Sectors"],
    summary="Get sector detail with individual stocks",
)
def get_sector_detail(
    sector_name: str, db: Session = Depends(get_db_session)
) -> SectorDetail:
    """Get the latest company snapshot for a specific sector."""

    try:
        resolved_sector = resolve_sector_name(sector_name)
        if not resolved_sector:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Sector '{sector_name}' not found. Valid sectors: "
                    f"{list(SECTOR_STOCKS.keys())}"
                ),
            )

        records = get_latest_rows(db, resolved_sector)
        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No companies found for sector: {resolved_sector}",
            )

        stocks = [
            SectorStockInfo(
                symbol=record.symbol,
                name=get_company_name(record.symbol),
                current_price=round(record.close, 2)
                if record.close is not None
                else None,
                daily_return=round(record.daily_return, 4)
                if record.daily_return is not None
                else None,
                volatility_score=round(record.volatility_score, 4)
                if record.volatility_score is not None
                else None,
            )
            for record in records
        ]
        stocks.sort(key=lambda stock: stock.symbol)

        return SectorDetail(sector=resolved_sector, stocks=stocks)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching sector detail for %s: %s", sector_name, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch sector detail: {exc}"
        ) from exc


@app.get(
    "/predict/{symbol}",
    response_model=PredictionResponse,
    tags=["Prediction"],
    summary="Get price prediction using linear regression",
)
def predict_price(
    symbol: str,
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db_session),
) -> PredictionResponse:
    """Predict future prices using a degree-1 polynomial fit over the last 60 closes."""

    try:
        normalized_symbol = normalize_symbol(symbol)
        records = (
            db.query(StockPrice)
            .filter(StockPrice.symbol == normalized_symbol, StockPrice.close.isnot(None))
            .order_by(StockPrice.date.desc())
            .limit(60)
            .all()
        )

        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {normalized_symbol}",
            )

        history_records = list(reversed(records))
        if len(history_records) < 10:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Insufficient data for prediction. Need at least 10 closing prices."
                ),
            )

        x_values = np.arange(len(history_records))
        y_values = np.array([float(record.close) for record in history_records])
        slope, intercept = np.polyfit(x_values, y_values, 1)

        historical = [
            HistoricalPrice(
                date=record.date.strftime("%Y-%m-%d"),
                close=round(float(record.close), 2),
            )
            for record in history_records
        ]

        last_date = history_records[-1].date
        future_x = np.arange(len(history_records), len(history_records) + days)
        predicted_values = (slope * future_x) + intercept
        predicted = [
            PredictedPrice(
                date=(last_date + timedelta(days=offset + 1)).strftime("%Y-%m-%d"),
                predicted_close=round(float(predicted_close), 2),
            )
            for offset, predicted_close in enumerate(predicted_values)
        ]

        return PredictionResponse(
            symbol=normalized_symbol,
            historical=historical,
            predicted=predicted,
            trend="bullish" if slope > 0 else "bearish",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error predicting price for %s: %s", symbol, exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to predict price for {symbol}: {exc}"
        ) from exc


@app.get("/", tags=["Health"], summary="Health check")
def root() -> dict:
    """Health check endpoint."""

    return {"status": "ok", "message": "StockIQ - NSE Market Intelligence Platform API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
