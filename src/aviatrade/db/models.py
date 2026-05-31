"""SQLAlchemy ORM models for flight price data."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class FlightPrice(Base):
    """Model representing a flight price record."""

    __tablename__ = "flight_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    origin = Column(String(100), nullable=False, index=True)
    destination = Column(String(100), nullable=False, index=True)
    departure_date = Column(Date, nullable=False, index=True)
    airline = Column(String(200))
    flight_number = Column(String(50))
    departure_time = Column(String(20))
    arrival_time = Column(String(20))
    duration = Column(String(50))
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    stops = Column(Integer, default=0)
    # scraped_at входит в первичный ключ: TimescaleDB требует, чтобы колонка
    # партиционирования гипертаблицы была частью PK / любого UNIQUE-ограничения.
    scraped_at = Column(
        DateTime, primary_key=True, default=datetime.utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<FlightPrice(id={self.id}, {self.origin}->{self.destination}, "
            f"{self.departure_date}, {self.price} {self.currency})>"
        )


class Watchlist(Base):
    """A route tracked for continuous multi-direction price monitoring.

    This is a plain relational table (not a TimescaleDB hypertable): it is a
    small registry of routes to monitor, not time-series data. Price history
    itself still lives in ``flight_prices``.
    """

    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint(
            "origin", "destination", "departure_date", name="uq_watchlist_route"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    origin = Column(String(100), nullable=False, index=True)
    destination = Column(String(100), nullable=False, index=True)
    departure_date = Column(Date, nullable=False, index=True)
    # Per-route collection interval in minutes; the monitor falls back to a
    # global default when scheduling.
    interval_min = Column(Integer, nullable=False, default=60)
    # Allows pausing a route without losing its collected history.
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        state = "on" if self.enabled else "off"
        return (
            f"<Watchlist(id={self.id}, {self.origin}->{self.destination}, "
            f"{self.departure_date}, every {self.interval_min}m, {state})>"
        )
