"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Find and load .env file from project root or configs directory
_project_root = Path(__file__).parent.parent.parent.parent
_env_locations = [
    _project_root / ".env",
    _project_root / "configs" / ".env",
]

for env_path in _env_locations:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()  # Try default locations


class Config:
    """Application configuration."""

    def __init__(self):
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "flight_prices")
        db_user = os.getenv("DB_USER", "flight_user")
        db_password = os.getenv("DB_PASSWORD", "flight_password")

        if db_password:
            self._db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        else:
            self._db_url = f"postgresql://{db_user}@{db_host}:{db_port}/{db_name}"

    @property
    def DATABASE_URL(self) -> str:
        """Get the database connection URL."""
        return self._db_url


# Global config instance
config = Config()
