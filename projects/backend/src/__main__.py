"""Запуск API: python -m src"""

import uvicorn

from src.config import config

if __name__ == "__main__":
    uvicorn.run("src.app:app", host=config.host, port=config.port)
