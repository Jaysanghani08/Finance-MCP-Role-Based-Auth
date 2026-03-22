from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "ps2-mcp-server"
    app_env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000

    auth0_domain: str = Field(default="example.us.auth0.com")
    auth0_audience: str = Field(default="https://ps2-mcp-api")
    auth0_issuer: str = Field(default="https://example.us.auth0.com/")

    free_rate_limit_per_hour: int = 30
    premium_rate_limit_per_hour: int = 150
    analyst_rate_limit_per_hour: int = 500

    news_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    data_gov_api_key: str | None = None


settings = Settings()
