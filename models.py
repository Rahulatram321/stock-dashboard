"""Pydantic models for API request/response schemas."""

from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class CompanyInfo(BaseModel):
    """Response model for company information."""

    symbol: str
    name: str
    current_price: Optional[float] = None
    daily_return: Optional[float] = None
    volatility_score: Optional[float] = None


class StockDataPoint(BaseModel):
    """Response model for a single day's stock data."""

    date: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    daily_return: Optional[float] = None
    moving_avg_7: Optional[float] = None


class StockSummary(BaseModel):
    """Response model for stock summary statistics."""

    symbol: str
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    avg_close: Optional[float] = None
    avg_daily_return: Optional[float] = None
    avg_volatility: Optional[float] = None
    total_trading_days: int = 0


class CompareDataPoint(BaseModel):
    """Response model for a single data point in comparison."""

    date: datetime
    close: Optional[float] = None


class ComparisonResponse(BaseModel):
    """Response model for stock comparison."""

    symbol1: str
    symbol2: str
    data1: List[CompareDataPoint]
    data2: List[CompareDataPoint]
    correlation: Optional[float] = None


class MoversData(BaseModel):
    """Response model for a single mover (gainer/loser)."""

    symbol: str
    name: str
    current_price: Optional[float] = None
    daily_return: Optional[float] = None


class TopMoversResponse(BaseModel):
    """Response model for top movers."""

    top_gainers: List[MoversData]
    top_losers: List[MoversData]


class StockPriceDB(BaseModel):
    """Full database row model for stock prices."""

    id: int
    symbol: str
    date: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    daily_return: Optional[float] = None
    moving_avg_7: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    volatility_score: Optional[float] = None

    model_config = {"from_attributes": True}