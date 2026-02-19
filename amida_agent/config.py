from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    # Anthropic
    anthropic_api_key: str = ""

    # Proxycurl
    proxycurl_api_key: str = ""

    # Hunter.io
    hunter_api_key: str = ""

    # Apify
    apify_api_key: str = ""

    # Smartlead
    smartlead_api_key: str = ""

    # Database
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'amida.db'}"

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000

    # Scout thresholds
    enrichment_threshold: float = 0.40
    notification_threshold: float = 0.65
    scout_news_interval_hours: int = 12


settings = Settings()
