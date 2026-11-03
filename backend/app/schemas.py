import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import get_settings

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class Strict(BaseModel):
    # 정의하지 않은 필드는 거부 (권한/상태 필드를 몰래 넣는 요청 차단)
    model_config = ConfigDict(extra="forbid")


def _clean_text(v: str, field: str, *, allow_empty: bool = False) -> str:
    v = v.strip()
    if _CONTROL.search(v):
        raise ValueError(f"{field}에 제어 문자를 쓸 수 없습니다")
    if not v and not allow_empty:
        raise ValueError(f"{field}이(가) 비어 있습니다")
    return v


class MeetingCreate(Strict):
    title: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    date_start: date
    date_end: date
    max_participants: int = Field(default=10, ge=2)
    host_nickname: str = Field(min_length=1, max_length=20)
    # 참여자가 입력하는 4~6자리 숫자
    pin: str = Field(pattern=r"^\d{4,6}$")
    host_password: str = Field(min_length=8, max_length=72)

    @field_validator("title", "host_nickname")
    @classmethod
    def _text(cls, v: str, info) -> str:
        return _clean_text(v, info.field_name)

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return None if v is None else (_clean_text(v, "description", allow_empty=True) or None)

    @field_validator("host_password")
    @classmethod
    def _pw_bytes(cls, v: str) -> str:
        # bcrypt는 72바이트를 넘는 부분을 무시한다 (한글은 글자당 3바이트)
        if len(v.encode("utf-8")) > 72:
            raise ValueError("host_password는 72바이트 이하여야 합니다")
        return v

    @model_validator(mode="after")
    def _range(self):
        s = get_settings()
        if self.date_end < self.date_start:
            raise ValueError("date_end는 date_start 이후여야 합니다")
        if (self.date_end - self.date_start).days + 1 > s.max_date_range_days:
            raise ValueError(f"날짜 범위는 {s.max_date_range_days}일 이하여야 합니다")
        if self.max_participants > s.max_participants_limit:
            raise ValueError(f"max_participants는 {s.max_participants_limit} 이하여야 합니다")
        return self


class JoinBody(Strict):
    nickname: str = Field(min_length=1, max_length=20)
    pin: str = Field(pattern=r"^\d{4,6}$")

    @field_validator("nickname")
    @classmethod
    def _nick(cls, v: str) -> str:
        return _clean_text(v, "nickname")


class HostLoginBody(Strict):
    host_password: str = Field(min_length=1, max_length=72)


class ProposalCreate(Strict):
    # B 형식: c_<날짜 8자리>_<시작 HHMM>_<역명>  예) c_20261107_1500_창동
    # 역명에는 점이 들어간 곳도 있다(4.19민주묘지). 실제 존재 여부는 저장된 추천 결과로 확인한다.
    candidate_id: str = Field(pattern=r"^c_\d{8}_\d{4}_[^\s/\\?#%]{1,30}$", max_length=60)


class ProposalRespond(Strict):
    response: Literal["accept", "reject"]


class ClaimBody(Strict):
    request_secret: str = Field(min_length=10, max_length=128)
