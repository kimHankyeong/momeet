from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from app.core import subway
from app.database import get_db
from app.deps import client_key, get_current_participant, get_meeting, require_host
from app.models import Meeting, Participant
from app.schemas import Strict
from app.security import isoformat
from app.services import conditions as svc
from app.services import places as places_svc

router = APIRouter(tags=["conditions"])


class ConditionsBody(Strict):
    """조건 입력 JSON. 값의 의미 검증(역 존재, 날짜 범위, 제약 형식)은 B의 validate_conditions 가 한다.
    여기서는 크기와 큰 틀만 제한한다."""

    model_config = ConfigDict(extra="forbid")

    availability: dict[str, list[StrictInt]] | None = Field(default=None, max_length=62)
    default_station: str | None = Field(default=None, max_length=30)
    # 출발 위치 {lat, lng} 또는 {address}. 형식·범위 검증은 B의 validate_conditions, 주소 변환은 services/access_walk.py
    default_origin: dict[str, Any] | None = Field(default=None, max_length=3)
    exception_stations: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    constraints: dict[str, Any] | None = Field(default=None, max_length=10)

    def to_data(self) -> dict:
        return self.model_dump(exclude_none=True)


def _row(c) -> dict:
    return {"status": c.status, "conditions": c.data, "updated_at": isoformat(c.updated_at)}


@router.get("/stations")
def search_stations(q: str = Query(min_length=1, max_length=20), limit: int = Query(default=10, ge=1, le=20)):
    """역 자동완성 (공개 데이터, 인증 불필요)."""
    return {"stations": subway.search_stations(q, limit)}


@router.get("/places")
def search_places(request: Request, q: str = Query(min_length=2, max_length=50)):
    """출발지 장소·주소 검색 (최대 5건, 인증 불필요). 응답의 lat/lng를 default_origin에 그대로 보내면 된다."""
    return {"places": places_svc.search(client_key(request), q)}


@router.get("/meetings/{meeting_id}/conditions/me")
def my_conditions(
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
):
    r = svc.get_my_condition(db, me)
    if r["status"] != "none":
        r["updated_at"] = isoformat(r["updated_at"])
    return r


@router.put("/meetings/{meeting_id}/conditions/me/draft")
def save_draft(
    body: ConditionsBody,
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
):
    return _row(svc.save_draft(db, meeting, me, body.to_data()))


@router.post("/meetings/{meeting_id}/conditions/me/submit")
def submit(
    body: ConditionsBody | None = None,
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
):
    """제출/재제출. 본문을 생략하면 저장해 둔 초안을 제출한다."""
    return _row(svc.submit(db, meeting, me, body.to_data() if body is not None else None))


# 추천은 동기 함수로 둔다: 계산이 오래 걸려도 이벤트 루프를 막지 않고 스레드 풀에서 실행된다.
@router.post("/meetings/{meeting_id}/recommendations")
def run_recommendations(
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
):
    svc.run_recommendation(db, meeting)
    return svc.view_recommendations(db, meeting, host)


@router.get("/meetings/{meeting_id}/recommendations")
def get_recommendations(
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
):
    return svc.view_recommendations(db, meeting, me)
