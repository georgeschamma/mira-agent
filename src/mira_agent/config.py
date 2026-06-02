from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    api_port: int = 8123
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    supabase_url: str = "http://127.0.0.1:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    llm_provider: str = "openai-compatible"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str | None = None
    exa_api_key: str = ""
    exa_num_results: int = Field(default=5, ge=1, le=10)

    static_dir: Path = Path("ui/dist")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def has_supabase_runtime_config(self) -> bool:
        return bool(
            self.supabase_url
            and self.supabase_anon_key
            and not self.supabase_anon_key.startswith("replace-with")
        )

    @property
    def has_llm_config(self) -> bool:
        return bool(self.llm_model and self.llm_api_key)

    @property
    def has_exa_config(self) -> bool:
        return bool(self.exa_api_key)

    @property
    def postgrest_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/rest/v1"

    @property
    def auth_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
