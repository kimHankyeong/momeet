from app.errors import AppError
from app.models import (
    STAGE_CONFIRMED,
    STAGE_INPUT,
    STAGE_PROPOSED,
    STAGE_RECOMMENDED,
    STAGE_RECRUITING,
    Meeting,
)

# 허용되는 단계 전이.
# recommended -> recommended : 추천 재실행 (B)
# proposed    -> proposed    : 거절/교체 후 재제안
ALLOWED: dict[str, set[str]] = {
    STAGE_RECRUITING: {STAGE_INPUT},
    STAGE_INPUT: {STAGE_RECOMMENDED},
    STAGE_RECOMMENDED: {STAGE_RECOMMENDED, STAGE_PROPOSED},
    STAGE_PROPOSED: {STAGE_PROPOSED, STAGE_CONFIRMED},
    STAGE_CONFIRMED: set(),
}


def require_stage(meeting: Meeting, *stages: str) -> None:
    if meeting.stage not in stages:
        raise AppError(
            "INVALID_STAGE",
            "지금 단계에서는 할 수 없는 작업입니다.",
            409,
            {"stage": meeting.stage, "allowed_stages": list(stages)},
        )


def transition(meeting: Meeting, to: str) -> None:
    if to not in ALLOWED.get(meeting.stage, set()):
        raise AppError(
            "INVALID_STAGE",
            "허용되지 않는 단계 전이입니다.",
            409,
            {"stage": meeting.stage, "to": to},
        )
    meeting.stage = to
