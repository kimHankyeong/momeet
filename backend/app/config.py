from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./momeet.db"
    cors_origins: str = "http://localhost:5173"

    meeting_ttl_days: int = 30
    token_ttl_days: int = 30

    # 운영은 12 이상. 테스트에서만 낮춘다.
    bcrypt_rounds: int = 12

    # PIN / 호스트 비밀번호 무차별 대입 방어
    max_auth_failures: int = 5
    auth_lock_minutes: int = 5

    min_participants_to_close: int = 2
    default_max_participants: int = 10
    max_participants_limit: int = 30
    max_date_range_days: int = 31

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
