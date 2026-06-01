"""Database session management and operations."""

from datetime import datetime
from typing import Any

from shared.core.settings import DatabaseSettings
from shared.db.models import Base, FlightPrice, Watchlist
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Database connection and operations manager."""

    def __init__(self, dsn: str | None = None):
        """Initialize database connection.

        Args:
            dsn: SQLAlchemy connection string. If not provided, falls back to the
                default ``DatabaseSettings().dsn`` (convenient for dev/CLI/tests).
                Services pass an explicit dsn from their loaded YAML config.
        """
        self.engine = create_engine(dsn or DatabaseSettings().dsn, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_tables(self) -> None:
        """Create all database tables if they don't exist."""
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def add_flight_price(self, flight_data: dict[str, Any]) -> int:
        """Add a flight price record to the database.

        Args:
            flight_data: Dictionary with flight price data.

        Returns:
            ID of the created record.

        Raises:
            Exception: If database operation fails.
        """
        session = self.get_session()

        try:
            flight_price = FlightPrice(**flight_data)
            session.add(flight_price)
            session.commit()
            return flight_price.id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_price_history(
        self,
        origin: str,
        destination: str,
        departure_date: Any | None = None,
    ) -> list[FlightPrice]:
        """Get price history for a route.

        Args:
            origin: Origin airport IATA code.
            destination: Destination airport IATA code.
            departure_date: Optional departure date filter.

        Returns:
            List of FlightPrice records ordered by scraped_at.
        """
        session = self.get_session()

        try:
            query = session.query(FlightPrice).filter(
                FlightPrice.origin == origin,
                FlightPrice.destination == destination,
            )

            if departure_date:
                query = query.filter(FlightPrice.departure_date == departure_date)

            return query.order_by(FlightPrice.scraped_at).all()

        finally:
            session.close()

    # ------------------------------------------------------------------
    # Watchlist management (multi-direction monitoring)
    # ------------------------------------------------------------------

    def add_watch(
        self,
        origin: str,
        destination: str,
        departure_date: Any,
        interval_min: int = 60,
    ) -> Watchlist:
        """Add a route to the watchlist (or re-enable/update an existing one).

        Args:
            origin: Origin airport IATA code.
            destination: Destination airport IATA code.
            departure_date: Departure date (``date`` or ``YYYY-MM-DD`` string).
            interval_min: Per-route collection interval in minutes.

        Returns:
            The created or updated Watchlist record.
        """
        departure_date = self._coerce_date(departure_date)
        session = self.get_session()

        try:
            existing = (
                session.query(Watchlist)
                .filter(
                    Watchlist.origin == origin,
                    Watchlist.destination == destination,
                    Watchlist.departure_date == departure_date,
                )
                .one_or_none()
            )

            if existing is not None:
                existing.interval_min = interval_min
                existing.enabled = True
                record = existing
            else:
                record = Watchlist(
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    interval_min=interval_min,
                    enabled=True,
                )
                session.add(record)

            session.commit()
            session.refresh(record)
            session.expunge(record)
            return record
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def remove_watch(
        self, origin: str, destination: str, departure_date: Any
    ) -> bool:
        """Remove a route from the watchlist.

        Returns:
            True if a record was deleted, False if no match was found.
        """
        departure_date = self._coerce_date(departure_date)
        session = self.get_session()

        try:
            deleted = (
                session.query(Watchlist)
                .filter(
                    Watchlist.origin == origin,
                    Watchlist.destination == destination,
                    Watchlist.departure_date == departure_date,
                )
                .delete()
            )
            session.commit()
            return deleted > 0
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_watchlist(self, enabled_only: bool = True) -> list[Watchlist]:
        """Return watchlist routes.

        Args:
            enabled_only: If True, return only enabled routes.

        Returns:
            List of Watchlist records ordered by creation time.
        """
        session = self.get_session()

        try:
            query = session.query(Watchlist)
            if enabled_only:
                query = query.filter(Watchlist.enabled.is_(True))
            records = query.order_by(Watchlist.created_at).all()
            for record in records:
                session.expunge(record)
            return records
        finally:
            session.close()

    @staticmethod
    def _coerce_date(value: Any) -> Any:
        """Coerce a YYYY-MM-DD string to a date; pass through date objects."""
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        return value
