"""Database configuration and SQLAlchemy models for stock data."""

import logging
from collections.abc import Generator

from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

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
    sector = Column(String, nullable=True, index=True)
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


def ensure_stock_prices_schema() -> None:
    """Patch older SQLite files so the ORM schema matches the live table."""

    inspector = inspect(engine)
    if "stock_prices" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("stock_prices")
    }

    with engine.begin() as connection:
        if "sector" not in existing_columns:
            connection.execute(text("ALTER TABLE stock_prices ADD COLUMN sector VARCHAR"))
            logger.info("Added missing 'sector' column to stock_prices.")

        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_stock_prices_sector "
                "ON stock_prices (sector)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_stock_prices_symbol "
                "ON stock_prices (symbol)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_stock_prices_date "
                "ON stock_prices (date)"
            )
        )


def create_tables() -> None:
    """Create all tables in the database if they don't exist."""

    Base.metadata.create_all(bind=engine)
    ensure_stock_prices_schema()
    logger.info("Database tables are ready.")


def get_db() -> Generator[Session, None, None]:
    """Get a database session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_db_empty() -> bool:
    """Check whether the stock_prices table is empty."""

    inspector = inspect(engine)
    if "stock_prices" not in inspector.get_table_names():
        return True

    try:
        with engine.connect() as connection:
            count = connection.execute(text("SELECT COUNT(*) FROM stock_prices")).scalar()
        return int(count or 0) == 0
    except Exception as exc:
        logger.error("Error checking database contents: %s", exc)
        return True
