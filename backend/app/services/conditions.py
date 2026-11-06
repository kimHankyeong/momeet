"""조건 입력(초안/제출/재제출)과 추천 실행. 계산·검증 자체는 B의 app.core.fairness 를 호출한다."""
import threading
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import fairness
from app.errors import AppError
from app.models import (
    STAGE_INPUT,
    STAGE_RECOMMENDED,
    STAGE_RECRUITING,
    Condition,
    Meeting,
    Participant,
    RecommendationResult,
)
from app.security import utcnow
from app.services import hooks, state
from app.services.meetings import active_participants

# 추천 계산은 CPU를 오래 쓴다. 동시에 몇 개까지만 돌리고 나머지는 기다리게 한다.
_RECOMMEND_SLOTS = threading.BoundedSemaphore(2)


def meeting_dates(meeting: Meeting) -> list[str]:
    days = (meeting.date_end - meeting.date_start).days
    return [(meeting.date_start + timedelta(days=i)).isoformat() for i in range(days + 1)]


def get_my_condition(db: Session, me: Participant) -> dict:
    row = db.scalar(select(Condition).where(Condition.participant_id == me.id))
    if row is None:
        return {"status": "none", "conditions": None}
    return {"status": row.status, "conditions": row.data, "updated_at": row.updated_at}


def _validate(meeting: Meeting, data: dict, final: bool) -> dict:
    errors, clean = fairness.validate_conditions(data, meeting_dates(meeting), final=final)
    if errors:
        raise AppError("CONDITIONS_INVALID", "조건을 확인해 주세요.", 422, {"errors": errors})
    return clean


def _save(db: Session, meeting: Meeting, me: Participant, clean: dict, status: str) -> Condition:
    row = db.scalar(select(Condition).where(Condition.participant_id == me.id))
    if row is None:
        row = Condition(participant_id=me.id, meeting_id=meeting.id, data=clean, status=status)
        db.add(row)
    else:
        row.data, row.status, row.updated_at = clean, status, utcnow()
    me.input_status = status  # 대시보드의 입력 상태
    db.commit()
    return row


def save_draft(db: Session, meeting: Meeting, me: Participant, data: dict) -> Condition:
    state.require_stage(meeting, STAGE_RECRUITING, STAGE_INPUT)
    clean = _validate(meeting, data, final=False)
    return _save(db, meeting, me, clean, "draft")


def submit(db: Session, meeting: Meeting, me: Participant, data: dict | None) -> Condition:
    """제출/재제출. data가 없으면 저장해 둔 초안을 제출한다."""
    state.require_stage(meeting, STAGE_RECRUITING, STAGE_INPUT)
    if data is None:
        row = db.scalar(select(Condition).where(Condition.participant_id == me.id))
        if row is None:
            raise AppError("NO_DRAFT", "제출할 조건이 없습니다. 조건을 입력해 주세요.", 409)
        data = row.data
    clean = _validate(meeting, data, final=True)
    return _save(db, meeting, me, clean, "submitted")


def run_recommendation(db: Session, meeting: Meeting) -> dict:
    """호스트가 실행. 전원 제출 후에만 가능하며, 같은 단계에서 다시 실행할 수 있다."""
    state.require_stage(meeting, STAGE_INPUT, STAGE_RECOMMENDED)
    people = active_participants(db, meeting.id)
    conds = {c.participant_id: c for c in db.scalars(select(Condition).where(Condition.meeting_id == meeting.id))}

    pending = [
        p.nickname
        for p in people
        if p.id not in conds or conds[p.id].status != "submitted" or p.input_status != "submitted"
    ]
    if pending:
        raise AppError(
            "CONDITIONS_INCOMPLETE",
            "아직 조건을 제출하지 않은 참여자가 있습니다.",
            409,
            {"pending_nicknames": pending},
        )

    participants = [{"id": str(p.id), **conds[p.id].data} for p in people]
    with _RECOMMEND_SLOTS:
        result = fairness.recommend(participants, meeting_dates(meeting))

    row = db.get(RecommendationResult, meeting.id)
    if row is None:
        db.add(RecommendationResult(meeting_id=meeting.id, result=result))
    else:
        row.result, row.generated_at = result, utcnow()
    db.commit()
    # 후보가 없으면(no_candidate) 단계를 올리지 않는다. 사유를 보여 주고 조건을 고쳐 다시 실행하게 한다.
    if result["status"] == "ok":
        hooks.mark_recommended(db, meeting)
    return result


def view_recommendations(db: Session, meeting: Meeting, me: Participant) -> dict:
    """본인 경로만 포함한 추천 결과 (다른 참여자의 출발역·경로·조건은 B의 view_for 가 제거)."""
    row = db.get(RecommendationResult, meeting.id)
    view = fairness.view_for(row.result if row else None, str(me.id))
    return {**view, "stage": meeting.stage}
