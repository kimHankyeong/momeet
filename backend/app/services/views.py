"""응답 JSON 조립. 다른 참여자의 조건·개인 정보는 여기서 절대 내보내지 않는다."""
from sqlalchemy.orm import Session

from app.config import get_settings
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
    """로그인 전에 보이는 정보. 입장 코드/호스트 정보/참여자 목록은 포함하지 않는다."""
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
        # 시안: 모집 중에도 참여자가 각자 조건을 입력한다 ("입력 중" / "입력완료")
        if me.input_status != "submitted":
            return act("submit_conditions", "내 조건을 입력하고 제출하세요.")
        if host:
            ready = all(p.input_status == "submitted" for p in people)
            if ready and len(people) >= get_settings().min_participants_to_close:
                return act("close_recruiting", "모든 참여자가 준비됐어요. 모집을 마감하세요.")
            return act("wait_conditions", "다른 참여자의 입력을 기다리는 중입니다. 링크로 참여자를 더 초대할 수 있어요.")
        return act("wait_recruiting", "모집이 마감되기를 기다리는 중입니다.")

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
            answered = {r.participant_id for r in proposal.responses}
            rejected = any(r.response == "reject" for r in proposal.responses if r.participant_id in {p.id for p in people})
            if people and all(p.id in answered for p in people) and rejected:
                # 전원이 응답했는데 거절이 있다: 확정되지 않았다 -> 호스트가 다른 후보를 다시 제안
                if host:
                    return act("repropose", "이번 제안은 확정되지 않았어요. 다른 후보를 다시 제안하세요.")
                return act("wait_reproposal", "주최자의 새 제안을 기다리는 중입니다.")
            all_accepted = bool(people) and all(p.id in answered for p in people) and not rejected
            if all_accepted:
                if host:
                    return act("confirm_proposal", "모두 동의했어요. 약속을 확정하세요.")
                return act("wait_confirm", "모두 동의했어요. 주최자의 확정을 기다리는 중입니다.")
            if me.id not in answered:
                return act("respond_to_proposal", "제안에 동의 또는 거절하세요.")
            if host:
                return act("wait_responses", "다른 참여자의 응답을 기다리는 중입니다. 지금 확정할 수도 있어요.")
            return act("wait_responses", "다른 참여자의 응답을 기다리는 중입니다.")
        return act("repropose", "다른 후보를 제안하세요.") if host else act("wait_reproposal", "주최자의 새 제안을 기다리는 중입니다.")

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
            "rejected_count": sum(1 for p in people if responses.get(p.id) == "reject"),
            "responded_count": sum(1 for p in people if p.id in responses),
            "total": len(people),
        }
        # 시안: "이번 제안은 확정되지 않았어요" (전원 응답 + 거절 있음). 거절한 사람은 계속 수정할 수 있다.
        prop["needs_replan"] = (
            proposal.status == "pending"
            and bool(people)
            and prop["responded_count"] == len(people)
            and prop["rejected_count"] > 0
        )

    out = {
        "meeting": {**meeting_summary(meeting), "join_code": meeting.join_code},
        "me": {"participant_id": me.id, "nickname": me.nickname, "is_host": me.is_host},
        "participants": plist,
        "proposal": prop,
        "next_action": _next_action(db, meeting, me, people),
        # 시안: "참여자 2/4 완료"
        "progress": {"submitted": sum(1 for p in people if p.input_status == "submitted"), "total": len(people)},
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
