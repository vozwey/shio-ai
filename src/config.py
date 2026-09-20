from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: str = Field(..., description="Токен Telegram-бота")

    openai_api_key: str = Field(..., description="API-ключ OpenAI-совместимого сервиса")
    openai_base_url: str = Field(..., description="Базовый URL API")
    openai_model: str = Field("gpt-4o-mini", description="Имя модели")
    openai_temperature: float = Field(
        0.7, ge=0.0, le=2.0, description="Температура генерации"
    )
    openai_max_tokens: int = Field(
        1500, ge=1, description="Лимит токенов ответа через API"
    )
    openai_reasoning_effort: str | None = Field(
        None, description="reasoning_effort для reasoning-моделей (minimal/low/medium/high)"
    )

    memory_db_path: str = Field("memory.db", description="Путь к SQLite-базе памяти (загружается при старте)")
    log_level: str = Field("INFO", description="Уровень логирования")

    context_size: int = Field(20, ge=1, description="Размер per-user контекста диалога (сообщений в RAM)")
    snippet_context_chars: int = Field(25, ge=1, description="Символов контекста вокруг найденного слова в search_memory")
    search_max_results: int = Field(20, ge=1, description="Максимум сниппетов, возвращаемых search_memory")

    answer_max_char: int = Field(
        4000, ge=1, description="Жёсткий лимит символов финального ответа"
    )
    tool_result_max_char: int = Field(
        2000, ge=1, description="Лимит символов результата тула для модели"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

TELEGRAM_BOT_TOKEN = settings.telegram_bot_token
OPENAI_API_KEY = settings.openai_api_key
OPENAI_BASE_URL = settings.openai_base_url
OPENAI_MODEL = settings.openai_model
OPENAI_TEMPERATURE = settings.openai_temperature
OPENAI_MAX_TOKENS = settings.openai_max_tokens
OPENAI_REASONING_EFFORT = settings.openai_reasoning_effort
MEMORY_DB_PATH = settings.memory_db_path
LOG_LEVEL = settings.log_level
ANSWER_MAX_CHAR = settings.answer_max_char
CONTEXT_SIZE = settings.context_size
SNIPPET_CONTEXT_CHARS = settings.snippet_context_chars
SEARCH_MAX_RESULTS = settings.search_max_results
TOOL_RESULT_MAX_CHAR = settings.tool_result_max_char
