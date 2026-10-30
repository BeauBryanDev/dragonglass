
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=ROOT / ".env",
                                      env_file_encoding="utf-8",
                                      extra="ignore")

    app_name: str = "dragonglass"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    data_dir: Path = ROOT / "data"
    cors_origins: list[str] = ["http://localhost:5173"]

    llm_model: str = "claude-haiku-5-5"
    llm_max_tokens: int = 16000
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1536

    anthropic_api_key: SecretStr = Field(min_length=1)
    google_api_key: SecretStr = Field(alias="Google_APi_KEY", min_length=1)

    @property
    def clean_dir(self):

        return self.data_dir / "clean"

    @property
    def index_dir(self):

        return self.data_dir / "index"


settings = Settings()
