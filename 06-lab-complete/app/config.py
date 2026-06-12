"""Production config — 12-Factor: tất cả từ environment variables."""
import os
import logging
from dataclasses import dataclass, field


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Legal Compliance Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    # Vertex AI
    vertex_project: str = field(default_factory=lambda: os.getenv("VERTEX_PROJECT", "vinuni-project"))
    vertex_location: str = field(default_factory=lambda: os.getenv("VERTEX_LOCATION", "us-central1"))
    vertex_model: str = field(default_factory=lambda: os.getenv("VERTEX_MODEL", "gemini-2.5-flash"))
    google_credentials_json: str = field(default_factory=lambda: os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", ""))

    # Security
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    allowed_origins: list = field(
        default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(",")
    )

    # Rate limiting
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    )

    # Budget
    daily_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "5.0"))
    )

    def validate(self):
        logger = logging.getLogger(__name__)
        if self.environment == "production" and self.agent_api_key == "dev-key-change-me":
            raise ValueError("AGENT_API_KEY must be set in production!")
        if not self.google_credentials_json:
            logger.warning("GOOGLE_APPLICATION_CREDENTIALS_JSON not set — Vertex AI may fail")
        return self


settings = Settings().validate()
