import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # LLM provider: "ollama" or "groq"
    llm_provider: str = field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "ollama"))

    # Ollama settings
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "qwen2.5:14b"))
    ollama_temperature: float = 0.0

    # Groq settings
    groq_model: str = field(default_factory=lambda: os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))
    groq_temperature: float = 0.0

    # Agent settings
    max_iterations: int = 10
    max_retries_on_fake: int = 2

    # History settings
    max_history_messages: int = 20
    max_history_tokens: int = 4096

    # Notion
    notion_parent_page_id: str = field(
        default_factory=lambda: os.environ.get("NOTION_PARENT_PAGE_ID", "")
    )

    # Default timezone
    default_timezone: str = "Asia/Manila"

    # Logging
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO").upper())


cfg = Config()
