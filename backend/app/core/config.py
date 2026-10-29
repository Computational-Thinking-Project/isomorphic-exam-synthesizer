from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # AI Service
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_API_KEY_1: SecretStr = SecretStr("")
    GEMINI_API_KEY_2: SecretStr = SecretStr("")
    GEMINI_API_KEY_3: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_MAX_CONCURRENCY: int = Field(default=3, ge=1, le=3)
    GEMINI_REQUEST_TIMEOUT_SECONDS: float = Field(default=120, gt=0, allow_inf_nan=False)
    GEMINI_KEY_COOLDOWN_SECONDS: float = Field(default=30, gt=0, allow_inf_nan=False)

    def get_gemini_api_keys(self) -> list[str]:
        """Return distinct configured keys without exposing them in settings repr."""
        secrets = (
            self.GEMINI_API_KEY,
            self.GEMINI_API_KEY_1,
            self.GEMINI_API_KEY_2,
            self.GEMINI_API_KEY_3,
        )
        return list(
            dict.fromkeys(
                value for secret in secrets if (value := secret.get_secret_value().strip())
            )
        )

    # Supabase Credentials
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: SecretStr = SecretStr("")

    # Security & Limits
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    MAX_UPLOAD_SIZE_MB: int = 10
    ADMIN_EMAILS: str = ""  # Comma-separated list of admin emails (SEC-08 / TASK-207c)

    # Ports
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
