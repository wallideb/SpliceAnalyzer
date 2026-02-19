from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://rmats:rmats@db:5432/rmatsdb"
    CORS_ORIGINS: str = '["http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            return json.loads(self.CORS_ORIGINS)
        except Exception:
            return [self.CORS_ORIGINS]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
