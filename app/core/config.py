from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://finance_user:finance_pass@postgres:5432/finance_alerts"
    sync_database_url: str = "postgresql+psycopg2://finance_user:finance_pass@postgres:5432/finance_alerts"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Telegram
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""

    # Scoring
    impact_threshold: int = 60

    # Admin
    admin_token: str = "change_me"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_basic_price_id: str = ""
    stripe_pro_price_id: str = ""

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    sentry_dsn: str = ""


settings = Settings()
