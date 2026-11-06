from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_participant, get_meeting, require_host
from app.integrations.candidates import CandidateProvider, get_candidate_provider
from app.models import Meeting, Participant
from app.schemas import ClaimBody, ProposalCreate, ProposalRespond
from app.security import isoformat
from app.services import joins
from app.services import proposals as svc
from app.services import views

router = APIRouter(prefix="/meetings/{meeting_id}", tags=["proposal"])


def _proposal(meeting: Meeting, p, provider: CandidateProvider, me: Participant) -> dict:
    return {
        "id": p.id,
        "version": p.version,
        "status": p.status,
        "candidate_id": p.candidate_id,
        "candidate": provider.get(meeting.id, p.candidate_id),
        "my_route": provider.my_route(meeting.id, p.candidate_id, me.id),
        "stage": meeting.stage,
    }


@router.post("/proposal", status_code=201)
def create_proposal(
    body: ProposalCreate,
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
    provider: CandidateProvider = Depends(get_candidate_provider),
):
    p = svc.propose(db, meeting, host, body.candidate_id, provider.get)
    return _proposal(meeting, p, provider, host)


@router.post("/proposal/response")
def respond(
    body: ProposalRespond,
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
    provider: CandidateProvider = Depends(get_candidate_provider),
):
    p = svc.respond(db, meeting, me, body.response)
    return _proposal(meeting, p, provider, me)


@router.post("/proposal/confirm")
def confirm_proposal(
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
    provider: CandidateProvider = Depends(get_candidate_provider),
):
    """호스트가 진행 중인 제안을 확정한다. 거절이 있으면 409 HAS_REJECTION."""
    p = svc.confirm(db, meeting, host)
    return _proposal(meeting, p, provider, host)


# ---- 마감 후 참여 승인 / 참여자 제외 (후순위)
@router.get("/join-requests")
def list_join_requests(
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
):
    return {
        "requests": [
            {"id": r.id, "nickname": r.nickname, "created_at": isoformat(r.created_at)}
            for r in joins.list_pending(db, meeting)
        ]
    }


@router.post("/join-requests/{request_id}/approve")
def approve_join(
    request_id: int,
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
):
    r = joins.decide(db, meeting, request_id, True)
    return {"id": r.id, "status": r.status}


@router.post("/join-requests/{request_id}/reject")
def reject_join(
    request_id: int,
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
):
    r = joins.decide(db, meeting, request_id, False)
    return {"id": r.id, "status": r.status}


@router.post("/join-requests/{request_id}/claim")
def claim_join(
    request_id: int,
    body: ClaimBody,
    meeting: Meeting = Depends(get_meeting),
    db: Session = Depends(get_db),
):
    """신청자가 승인 여부를 확인한다 (인증 토큰 대신 request_secret 사용)."""
    req, token, p = joins.claim(db, meeting, request_id, body.request_secret)
    if token is None:
        return {"status": req.status}
    return {
        "status": "approved",
        "meeting_id": meeting.id,
        "access_token": token,
        "token_type": "bearer",
        "expires_at": isoformat(p.token_expires_at),
        "participant": {"id": p.id, "nickname": p.nickname, "is_host": p.is_host},
    }


@router.post("/participants/{participant_id}/exclude")
def exclude(
    participant_id: int,
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
):
    p = joins.exclude(db, meeting, participant_id)
    return {"id": p.id, "status": p.status}
