import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        DB_HOST = os.getenv('DB_HOST', 'localhost')
        DB_PORT = os.getenv('DB_PORT', '5432')
        DB_NAME = os.getenv('DB_NAME', 'flight_prices')
        DB_USER = os.getenv('DB_USER', 'flight_user')
        DB_PASSWORD = os.getenv('DB_PASSWORD', 'flight_password')

        self.db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        if DB_PASSWORD == "":
            self.db_url = f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    @property
    def DATABASE_URL(self):
        return self.db_url

config = Config()
