"""Database configuration and SQLAlchemy models for stock data."""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///stock_data.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class StockPrice(Base):
    """SQLAlchemy model for the stock_prices table."""

    __tablename__ = "stock_prices"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    daily_return = Column(Float, nullable=True)
    moving_avg_7 = Column(Float, nullable=True)
    week52_high = Column(Float, nullable=True)
    week52_low = Column(Float, nullable=True)
    volatility_score = Column(Float, nullable=True)


def create_tables() -> None:
    """Create all tables in the database if they don't exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully.")


def get_db() -> Session:
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_db_empty() -> bool:
    """Check if the stock_prices table is empty."""
    db = SessionLocal()
    try:
        count = db.query(StockPrice).count()
        return count == 0
    except Exception as e:
        logger.error(f"Error checking database: {e}")
        return True
    finally:
        db.close()