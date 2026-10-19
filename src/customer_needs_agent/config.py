"""应用配置及环境变量读取。"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行配置；敏感信息只从环境变量或本地 ``.env`` 读取。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    siliconflow_api_key: SecretStr = SecretStr("")
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = ""
    database_url: str = "sqlite:///./customer_needs_agent.db"
    log_level: str = "INFO"
    log_file: str = "logs/agent.jsonl"
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    max_agent_steps: int = Field(default=4, ge=1, le=10)

    @property
    def llm_configured(self) -> bool:
        """真实模型调用所需的两项配置是否齐全。"""

        return bool(self.siliconflow_api_key.get_secret_value() and self.siliconflow_model)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回进程级配置单例。"""

    return Settings()
