"""응답 JSON 조립. 다른 참여자의 조건·개인 정보는 여기서 절대 내보내지 않는다."""
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    STAGE_CONFIRMED,
    STAGE_INPUT,
    STAGE_PROPOSED,
    STAGE_RECOMMENDED,
    STAGE_RECRUITING,
    Meeting,
    Participant,
)
from app.security import isoformat
from app.services import joins
from app.services.meetings import active_participants
from app.integrations.candidates import CandidateProvider
from app.services.proposals import latest_proposal


def meeting_summary(meeting: Meeting) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "description": meeting.description,
        "date_start": meeting.date_start.isoformat(),
        "date_end": meeting.date_end.isoformat(),
        "stage": meeting.stage,
        "max_participants": meeting.max_participants,
        "closed_at": isoformat(meeting.closed_at),
        "expires_at": isoformat(meeting.expires_at),
    }


def public_view(db: Session, meeting: Meeting) -> dict:
    """로그인 전에 보이는 정보. PIN/호스트 정보/참여자 목록은 포함하지 않는다."""
    count = len(active_participants(db, meeting.id))
    return {
        "id": meeting.id,
        "title": meeting.title,
        "description": meeting.description,
        "date_start": meeting.date_start.isoformat(),
        "date_end": meeting.date_end.isoformat(),
        "stage": meeting.stage,
        "participant_count": count,
        "max_participants": meeting.max_participants,
        "can_join": meeting.stage == STAGE_RECRUITING and count < meeting.max_participants,
        "can_request_join": meeting.stage == STAGE_INPUT and count < meeting.max_participants,
    }


def _next_action(db: Session, meeting: Meeting, me: Participant, people: list[Participant]) -> dict:
    host = me.is_host
    stage = meeting.stage

    def act(code: str, message: str) -> dict:
        return {"code": code, "message": message}

    if stage == STAGE_RECRUITING:
        return act("close_recruiting", "참여자가 모이면 모집을 마감하세요.") if host else act("wait_recruiting", "모집이 마감되기를 기다리는 중입니다.")

    if stage == STAGE_INPUT:
        if me.input_status != "submitted":
            return act("submit_conditions", "내 조건을 입력하고 제출하세요.")
        if host:
            if all(p.input_status == "submitted" for p in people):
                return act("run_recommendation", "모두 제출했습니다. 추천을 실행하세요.")
            return act("wait_conditions", "다른 참여자의 제출을 기다리는 중입니다.")
        return act("wait_recommendation", "호스트의 추천 실행을 기다리는 중입니다.")

    if stage == STAGE_RECOMMENDED:
        return act("propose_candidate", "추천 결과에서 하나를 골라 제안하세요.") if host else act("wait_proposal", "호스트의 제안을 기다리는 중입니다.")

    if stage == STAGE_PROPOSED:
        proposal = latest_proposal(meeting)
        if proposal is not None and proposal.status == "pending":
            mine = next((r for r in proposal.responses if r.participant_id == me.id), None)
            if mine is None:
                return act("respond_to_proposal", "제안에 동의 또는 거절하세요.")
            return act("wait_responses", "다른 참여자의 응답을 기다리는 중입니다.")
        return act("repropose", "제안이 거절되었습니다. 다시 제안하세요.") if host else act("wait_reproposal", "호스트의 재제안을 기다리는 중입니다.")

    return act("view_confirmed", "확정되었습니다. 확정 내용을 확인하세요.")


def dashboard(db: Session, meeting: Meeting, me: Participant, provider: CandidateProvider) -> dict:
    people = active_participants(db, meeting.id)
    proposal = latest_proposal(meeting)
    show_resp = proposal is not None and meeting.stage in (STAGE_PROPOSED, STAGE_CONFIRMED)
    responses = {r.participant_id: r.response for r in proposal.responses} if show_resp else {}

    plist = []
    for p in people:
        item = {
            "id": p.id,
            "nickname": p.nickname,
            "is_host": p.is_host,
            "is_me": p.id == me.id,
            "input_status": p.input_status,
        }
        if show_resp:
            item["response"] = responses.get(p.id, "pending")
        plist.append(item)

    prop = None
    if proposal is not None:
        prop = {
            "id": proposal.id,
            "version": proposal.version,
            "status": proposal.status,
            "candidate_id": proposal.candidate_id,
            "candidate": provider.get(meeting.id, proposal.candidate_id),
            "my_route": provider.my_route(meeting.id, proposal.candidate_id, me.id),
            "accepted_count": sum(1 for p in people if responses.get(p.id) == "accept"),
            "total": len(people),
        }

    out = {
        "meeting": meeting_summary(meeting),
        "me": {"participant_id": me.id, "nickname": me.nickname, "is_host": me.is_host},
        "participants": plist,
        "proposal": prop,
        "next_action": _next_action(db, meeting, me, people),
    }
    if me.is_host:
        out["host"] = {"pending_join_requests": len(joins.list_pending(db, meeting))}
    return out


def confirmed_view(db: Session, meeting: Meeting, me: Participant, provider: CandidateProvider) -> dict:
    if meeting.stage != STAGE_CONFIRMED or meeting.confirmed_candidate_id is None:
        raise AppError("NOT_CONFIRMED", "아직 확정되지 않았습니다.", 409, {"stage": meeting.stage})
    return {
        "meeting": meeting_summary(meeting),
        "candidate_id": meeting.confirmed_candidate_id,
        "candidate": provider.get(meeting.id, meeting.confirmed_candidate_id),
        "my_route": provider.my_route(meeting.id, meeting.confirmed_candidate_id, me.id),
        "participants": [{"id": p.id, "nickname": p.nickname, "is_host": p.is_host} for p in active_participants(db, meeting.id)],
    }
