from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import (
    STAGE_CONFIRMED,
    STAGE_PROPOSED,
    STAGE_RECOMMENDED,
    Meeting,
    Participant,
    Proposal,
    ProposalResponse,
)
from app.security import utcnow
from app.services import state
from app.services.meetings import active_participants

CandidateLookup = Callable[[str, str], dict | None]


def latest_proposal(meeting: Meeting) -> Proposal | None:
    return meeting.proposals[-1] if meeting.proposals else None


def current_pending(meeting: Meeting) -> Proposal | None:
    p = latest_proposal(meeting)
    return p if p is not None and p.status == "pending" else None


def propose(db: Session, meeting: Meeting, host: Participant, candidate_id: str, lookup: CandidateLookup) -> Proposal:
    state.require_stage(meeting, STAGE_RECOMMENDED, STAGE_PROPOSED)

    # 후보 검증은 B의 get_candidate (구현 전에는 임시 함수)
    if lookup(meeting.id, candidate_id) is None:
        raise AppError("INVALID_CANDIDATE", "추천 결과에 없는 후보입니다.", 422)

    # 진행 중이던 제안은 교체 처리. 새 제안은 응답 없이 시작한다 (= 응답 초기화).
    for old in meeting.proposals:
        if old.status == "pending":
            old.status = "superseded"

    version = (latest_proposal(meeting).version + 1) if meeting.proposals else 1
    proposal = Proposal(meeting_id=meeting.id, candidate_id=candidate_id, version=version, proposed_by=host.id)
    db.add(proposal)
    state.transition(meeting, STAGE_PROPOSED)
    db.commit()
    db.refresh(meeting)
    return proposal


def confirm(db: Session, meeting: Meeting, host: Participant) -> Proposal:
    """호스트가 진행 중인 제안을 확정한다 (전원 동의로 자동 확정하지 않음).

    - 아직 응답하지 않은 사람이 있어도 확정할 수 있다 (응답 없는 사람 때문에 멈추지 않게).
    - 거절한 사람이 있으면 확정할 수 없다 → 거절한 사람이 동의로 바꾸거나 호스트가 다른 후보를 다시 제안.
    - 확정하는 호스트는 동의한 것으로 기록한다.
    """
    state.require_stage(meeting, STAGE_PROPOSED)
    proposal = current_pending(meeting)
    if proposal is None:
        raise AppError("NO_ACTIVE_PROPOSAL", "확정할 수 있는 제안이 없습니다.", 409)
    active_ids = {p.id for p in active_participants(db, meeting.id)}
    if any(r.response == "reject" and r.participant_id in active_ids for r in proposal.responses):
        raise AppError("HAS_REJECTION", "거절한 참여자가 있어 확정할 수 없어요. 다른 후보를 다시 제안해 주세요.", 409)

    mine = next((r for r in proposal.responses if r.participant_id == host.id), None)
    if mine is None:
        db.add(ProposalResponse(proposal_id=proposal.id, participant_id=host.id, response="accept"))
    else:
        mine.response = "accept"
        mine.responded_at = utcnow()
    proposal.status = "accepted"
    meeting.confirmed_candidate_id = proposal.candidate_id
    state.transition(meeting, STAGE_CONFIRMED)
    db.commit()
    db.refresh(proposal)
    return proposal


def respond(db: Session, meeting: Meeting, me: Participant, response: str) -> Proposal:
    state.require_stage(meeting, STAGE_PROPOSED)
    proposal = current_pending(meeting)
    if proposal is None:
        raise AppError("NO_ACTIVE_PROPOSAL", "응답할 수 있는 제안이 없습니다.", 409)

    existing = db.scalar(
        select(ProposalResponse).where(
            ProposalResponse.proposal_id == proposal.id, ProposalResponse.participant_id == me.id
        )
    )
    if existing is None:
        db.add(ProposalResponse(proposal_id=proposal.id, participant_id=me.id, response=response))
    else:
        existing.response = response
        existing.responded_at = utcnow()
    db.commit()
    db.refresh(proposal)
    return proposal
