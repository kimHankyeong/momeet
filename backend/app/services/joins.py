"""마감 후 참여 승인 / 참여자 제외 (후순위 기능)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import STAGE_INPUT, JoinRequest, Meeting, Participant
from app.security import digests_equal, token_digest
from app.services import state
from app.services.meetings import _active_count, issue_token, revoke
from app.services.proposals import evaluate


def _get_request(db: Session, meeting: Meeting, request_id: int) -> JoinRequest:
    req = db.get(JoinRequest, request_id)
    if req is None or req.meeting_id != meeting.id:
        raise AppError("JOIN_REQUEST_NOT_FOUND", "참여 신청을 찾을 수 없습니다.", 404)
    return req


def list_pending(db: Session, meeting: Meeting) -> list[JoinRequest]:
    return list(
        db.scalars(
            select(JoinRequest)
            .where(JoinRequest.meeting_id == meeting.id, JoinRequest.status == "pending")
            .order_by(JoinRequest.id)
        )
    )


def decide(db: Session, meeting: Meeting, request_id: int, approve: bool) -> JoinRequest:
    req = _get_request(db, meeting, request_id)
    if req.status != "pending":
        raise AppError("ALREADY_DECIDED", "이미 처리된 신청입니다.", 409)

    if not approve:
        req.status = "rejected"
        db.commit()
        return req

    # 추천이 시작된 뒤에는 참여자 구성이 바뀌면 결과가 달라지므로 입력 단계에서만 승인한다
    state.require_stage(meeting, STAGE_INPUT)
    if _active_count(db, meeting.id) >= meeting.max_participants:
        raise AppError("MEETING_FULL", "정원이 가득 찼습니다.", 409)

    taken = set(db.scalars(select(Participant.nickname).where(Participant.meeting_id == meeting.id)))
    nickname, n = req.nickname, 2
    while nickname in taken:
        nickname = f"{req.nickname}({n})"
        n += 1
    p = Participant(meeting_id=meeting.id, nickname=nickname)
    db.add(p)
    db.flush()
    req.status = "approved"
    req.participant_id = p.id
    db.commit()
    return req


def claim(db: Session, meeting: Meeting, request_id: int, secret: str) -> tuple[JoinRequest, str | None, Participant | None]:
    """신청자가 결과를 확인한다. 승인되었으면 이때 토큰을 한 번만 발급한다."""
    req = _get_request(db, meeting, request_id)
    if not digests_equal(token_digest(secret), req.secret_hash):
        # 신청 존재 여부를 숨기기 위해 없는 신청과 같은 응답을 쓴다
        raise AppError("JOIN_REQUEST_NOT_FOUND", "참여 신청을 찾을 수 없습니다.", 404)
    if req.status != "approved":
        return req, None, None
    if req.claimed:
        raise AppError("ALREADY_CLAIMED", "이미 토큰을 받았습니다.", 409)
    p = db.get(Participant, req.participant_id) if req.participant_id else None
    if p is None:
        raise AppError("JOIN_REQUEST_NOT_FOUND", "참여 신청을 찾을 수 없습니다.", 404)
    token = issue_token(db, meeting, p)
    req.claimed = True
    db.commit()
    return req, token, p


def exclude(db: Session, meeting: Meeting, participant_id: int) -> Participant:
    p = db.get(Participant, participant_id)
    if p is None or p.meeting_id != meeting.id:
        raise AppError("PARTICIPANT_NOT_FOUND", "참여자를 찾을 수 없습니다.", 404)
    if p.is_host:
        raise AppError("CANNOT_EXCLUDE_HOST", "호스트는 제외할 수 없습니다.", 409)
    if p.status == "excluded":
        return p
    p.status = "excluded"
    revoke(db, p)
    db.commit()
    # 제외로 남은 사람이 모두 동의한 상태가 될 수 있다
    evaluate(db, meeting)
    return p
