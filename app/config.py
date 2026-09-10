"""Application configuration, loaded from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Object Hub"
    database_url: str = "postgresql+psycopg://objecthub:objecthub@localhost:5432/objecthub"

    # Local persistent storage for uploaded photos.
    data_dir: Path = Path("/data")

    # Public base URL, used only to render human-readable hints next to labels.
    # QR payloads themselves stay relative so a stack can be reached by any hostname.
    base_url: str = ""

    max_upload_bytes: int = 25 * 1024 * 1024
    thumbnail_size: int = 480

    items_per_page: int = 50

    @property
    def photos_dir(self) -> Path:
        return self.data_dir / "photos"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.photos_dir.mkdir(parents=True, exist_ok=True)
    settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)
    return settings
