from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    inspect_eval_model: str = Field(default="openai/gpt-5.4-nano", alias="INSPECT_EVAL_MODEL")
    wikigame_user_agent: str = Field(
        default="wikigame-agent/0.1 (https://github.com/anthropics/claude-code)",
        alias="WIKIGAME_USER_AGENT",
    )
    wikigame_log_dir: Path = Field(default=Path("logs"), alias="WIKIGAME_LOG_DIR")
    wikigame_request_timeout: float = Field(default=30.0, alias="WIKIGAME_REQUEST_TIMEOUT")


settings = Settings()
