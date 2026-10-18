import os

from pydantic import Field, SecretStr

from mini_agent.types import Record


class Settings(Record):
    api_key: SecretStr | None = None
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    max_steps: int = Field(default=24, ge=1, le=100)
    max_output_tokens: int = Field(default=4000, ge=1, le=16000)
    request_timeout: float = Field(default=60, gt=0, le=300)
    max_input_bytes: int = Field(default=12000, ge=1000)

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        return cls(
            api_key=SecretStr(key) if key else None,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
            **overrides,
        )
