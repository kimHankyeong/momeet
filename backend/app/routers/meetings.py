from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import client_key, get_current_participant, get_meeting, require_host
from app.errors import AppError
from app.integrations.candidates import CandidateProvider, get_candidate_provider
from app.models import Meeting, Participant
from app.schemas import HostLoginBody, JoinBody, MeetingCreate
from app.security import isoformat
from app.services import meetings as svc
from app.services import views

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _participant(p: Participant) -> dict:
    return {"id": p.id, "nickname": p.nickname, "is_host": p.is_host}


def _token(meeting: Meeting, p: Participant, token: str) -> dict:
    return {
        "meeting_id": meeting.id,
        "access_token": token,
        "token_type": "bearer",
        "expires_at": isoformat(p.token_expires_at),
        "participant": _participant(p),
    }


@router.post("", status_code=201)
def create_meeting(body: MeetingCreate, db: Session = Depends(get_db)):
    meeting, host, token = svc.create_meeting(db, body)
    return {**_token(meeting, host, token), "meeting": views.meeting_summary(meeting)}


@router.get("/{meeting_id}/public")
def public(meeting: Meeting = Depends(get_meeting), db: Session = Depends(get_db)):
    return views.public_view(db, meeting)


@router.post("/{meeting_id}/join")
def join(
    body: JoinBody,
    request: Request,
    response: Response,
    meeting: Meeting = Depends(get_meeting),
    db: Session = Depends(get_db),
):
    kind, obj, secret = svc.join(db, meeting, body.nickname, body.pin, client_key(request))
    if kind == "joined":
        response.status_code = 201
        return _token(meeting, obj, secret)
    # 마감 후: 호스트 승인 대기. request_secret은 이때 한 번만 보여준다.
    response.status_code = 202
    return {
        "status": "pending",
        "request_id": obj.id,
        "nickname": obj.nickname,
        "request_secret": secret,
    }


@router.post("/{meeting_id}/host-login")
def host_login(
    body: HostLoginBody,
    request: Request,
    meeting: Meeting = Depends(get_meeting),
    db: Session = Depends(get_db),
):
    host, token = svc.host_login(db, meeting, body.host_password, client_key(request))
    return _token(meeting, host, token)


@router.get("/{meeting_id}")
def dashboard(
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
    provider: CandidateProvider = Depends(get_candidate_provider),
):
    return views.dashboard(db, meeting, me, provider)


@router.get("/{meeting_id}/confirmed")
def confirmed(
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
    provider: CandidateProvider = Depends(get_candidate_provider),
):
    return views.confirmed_view(db, meeting, me, provider)


@router.post("/{meeting_id}/close")
def close(
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
):
    svc.close_recruiting(db, meeting)
    return {"meeting": views.meeting_summary(meeting)}


@router.delete("/{meeting_id}/me", status_code=204)
def delete_me(
    meeting: Meeting = Depends(get_meeting),
    me: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db),
):
    """내 데이터 삭제 + 토큰 무효화 (호스트는 약속방 삭제를 사용)."""
    svc.delete_my_data(db, meeting, me)
    # 나간 사람이 빠지면 남은 사람이 모두 동의한 상태가 될 수 있다
    from app.services.proposals import evaluate

    evaluate(db, meeting)
    return Response(status_code=204)


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(
    meeting: Meeting = Depends(get_meeting),
    host: Participant = Depends(require_host),
    db: Session = Depends(get_db),
):
    svc.delete_meeting(db, meeting)
    return Response(status_code=204)
