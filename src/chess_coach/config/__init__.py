"""Configuration management for Chess Coach."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str:
    """Find .env file by walking up from this file to the project root."""
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        env_file = parent / ".env"
        if env_file.exists():
            return str(env_file)
    return ".env"  # fallback


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Configuration
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    default_llm_provider: str = "openai"
    default_llm_model: str = "qwen3.5-35b-a3b"
    llm_base_url: Optional[str] = None  # For LM Studio, Ollama, or other local servers

    # Stockfish Configuration
    stockfish_path: str = "auto"
    stockfish_depth: int = 20
    stockfish_time_limit: float = 2.0

    # Data Directories
    data_dir: Path = Field(default_factory=lambda: Path("./data"))
    cache_dir: Path = Field(default_factory=lambda: Path("./data/cache"))
    logs_dir: Path = Field(default_factory=lambda: Path("./data/logs"))

    # Logging
    log_level: str = "INFO"

    # API Authentication
    api_username: str = "admin"
    api_password_hash: str = ""  # bcrypt hash; set via 'chess-coach api-setup'
    api_secret_key: str = ""    # JWT signing secret; set via 'chess-coach api-setup'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
