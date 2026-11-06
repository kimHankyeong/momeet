"""백B(조건 입력·추천)가 호출하는 진입점. 이 파일의 시그니처는 공동 합의 대상이다.

B는 이 함수들만 사용하고 단계/입력 상태 컬럼을 직접 수정하지 않는다.
인증은 `app.deps.get_current_participant` / `require_host`를 그대로 쓴다.
"""
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import STAGE_INPUT, STAGE_RECOMMENDED, Meeting, Participant
from app.services import state
from app.services.meetings import active_participants

INPUT_STATUSES = ("none", "draft", "submitted")

__all__ = ["require_stage", "set_input_status", "all_inputs_submitted", "mark_recommended", "STAGE_INPUT", "STAGE_RECOMMENDED"]

require_stage = state.require_stage


def set_input_status(db: Session, participant: Participant, status: str) -> None:
    """조건 초안 저장/제출/재제출 시 호출. 대시보드의 참여자 입력 상태에 반영된다."""
    if status not in INPUT_STATUSES:
        raise AppError("INVALID_INPUT_STATUS", "알 수 없는 입력 상태입니다.", 500)
    participant.input_status = status
    db.commit()


def all_inputs_submitted(db: Session, meeting: Meeting) -> bool:
    people = active_participants(db, meeting.id)
    return bool(people) and all(p.input_status == "submitted" for p in people)


def mark_recommended(db: Session, meeting: Meeting) -> None:
    """추천 실행(POST /recommendations) 성공 직후 호출 -> input/recommended 단계에서 recommended로."""
    state.require_stage(meeting, STAGE_INPUT, STAGE_RECOMMENDED)
    state.transition(meeting, STAGE_RECOMMENDED)
    db.commit()
