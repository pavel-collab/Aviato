"""Database session management and operations."""

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from aviatrade.core.config import config
from aviatrade.db.models import Base, FlightPrice


class Database:
    """Database connection and operations manager."""

    def __init__(self, db_url: str | None = None):
        """Initialize database connection.

        Args:
            db_url: Optional database URL. If not provided, uses config.DATABASE_URL.
        """
        self.engine = create_engine(db_url or config.DATABASE_URL, echo=False)
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
