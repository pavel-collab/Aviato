from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import config

Base = declarative_base()

class FlightPrice(Base):
    __tablename__ = 'flight_prices'

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
    currency = Column(String(10), default='RUB')
    stops = Column(Integer, default=0)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<FlightPrice(id={self.id}, {self.origin}->{self.destination}, {self.departure_date}, {self.price} {self.currency})>"

class Database:
    def __init__(self):
        self.engine = create_engine(config.DATABASE_URL, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_tables(self):
        Base.metadata.create_all(self.engine)

    def get_session(self):
        return self.SessionLocal()

    def add_flight_price(self, flight_data):
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

    def get_price_history(self, origin, destination, departure_date=None):
        session = self.get_session()

        try:
            query = session.query(FlightPrice).filter(
                FlightPrice.origin == origin,
                FlightPrice.destination == destination
            )

            if departure_date:
                query = query.filter(FlightPrice.departure_date == departure_date)

            results = query.order_by(FlightPrice.scraped_at).all()
            return results

        finally:
            session.close()