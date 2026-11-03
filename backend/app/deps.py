from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.models import Meeting, Participant
from app.security import token_digest, utcnow


def client_key(request: Request) -> str:
    # 프록시 뒤에서는 배포 환경에서 신뢰할 수 있는 프록시 헤더 처리를 따로 설정해야 한다
    return request.client.host if request.client else "unknown"


def get_meeting(meeting_id: str, db: Session = Depends(get_db)) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise AppError("MEETING_NOT_FOUND", "약속방을 찾을 수 없습니다.", 404)
    if meeting.expires_at <= utcnow():
        # 만료된 약속방은 존재 여부와 관계없이 모든 접근을 막는다
        raise AppError("MEETING_EXPIRED", "만료된 약속방입니다.", 410)
    return meeting


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise AppError("UNAUTHENTICATED", "인증 토큰이 필요합니다.", 401)
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise AppError("UNAUTHENTICATED", "인증 토큰이 필요합니다.", 401)
    return value.strip()


def get_current_participant(
    meeting: Meeting = Depends(get_meeting),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Participant:
    """토큰으로 현재 참여자를 식별한다. 다른 약속방의 토큰은 통하지 않는다."""
    digest = token_digest(_bearer(authorization))
    p = db.scalar(select(Participant).where(Participant.token_hash == digest))
    if (
        p is None
        or p.meeting_id != meeting.id
        or p.status != "active"
        or p.token_expires_at is None
        or p.token_expires_at <= utcnow()
    ):
        raise AppError("UNAUTHENTICATED", "유효하지 않거나 만료된 토큰입니다.", 401)
    return p


def require_host(me: Participant = Depends(get_current_participant)) -> Participant:
    if not me.is_host:
        raise AppError("HOST_ONLY", "호스트만 할 수 있습니다.", 403)
    return me
