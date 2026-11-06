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

    # 호스트 비밀번호 무차별 대입 방어 (방 + 클라이언트별)
    max_auth_failures: int = 5
    auth_lock_minutes: int = 5
    # 입장 코드 추측 방어 (클라이언트별, 시간 창 안의 실패 횟수)
    max_code_failures: int = 10
    code_fail_window_minutes: int = 10

    min_participants_to_close: int = 2
    default_max_participants: int = 10
    # 팀 결정(11/4): 최대 인원 10명, 날짜 범위 7일
    max_participants_limit: int = 10
    max_date_range_days: int = 7

    # 티맵 보행자 경로·주소 변환 (출발 위치 → 출발역 도보). 키가 없거나 실패하면 B의 직선거리 추정을 쓴다.
    tmap_app_key: str = ""
    tmap_timeout_sec: float = 5.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
