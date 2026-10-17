"""Configuración del servicio desde variables de entorno o un archivo .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    provided_service_base_url: str = "https://temp.didacteca.site"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"

    max_instructions_chars: int = Field(default=6000, ge=1)
    max_identifier_chars: int = Field(default=128, ge=1)
    max_quiz_questions: int = Field(default=10, ge=1)
    max_team_size: int = Field(default=8, ge=2)
    max_activity_minutes: int = Field(default=120, ge=1)
    max_context_chars: int = Field(default=60000, ge=1)

    context_timeout_seconds: float = Field(default=10, gt=0)
    ai_timeout_seconds: float = Field(default=30, gt=0)
    execution_timeout_seconds: float = Field(default=110, gt=0)

    extraction_max_output_tokens: int = Field(default=2000, ge=1)
    generation_max_output_tokens: int = Field(default=8000, ge=1)
    max_repairs_per_execution: int = Field(default=1, ge=0)
    max_model_calls_per_execution: int = Field(default=3, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Obtiene y reutiliza la configuración cargada para este proceso."""

    return Settings()
