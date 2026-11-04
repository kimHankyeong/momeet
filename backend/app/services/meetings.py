from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import (
    STAGE_INPUT,
    STAGE_RECRUITING,
    AuthAttempt,
    JoinAttempt,
    JoinRequest,
    Meeting,
    Participant,
)
from app.schemas import MeetingCreate
from app.security import (
    burn_verify,
    hash_secret,
    is_valid_join_code,
    new_join_code,
    new_meeting_id,
    new_token,
    normalize_join_code,
    token_digest,
    utcnow,
    verify_secret,
)
from app.services import state


# ---------------------------------------------------------------- 인증 시도 제한
def _attempt(db: Session, meeting_id: str, kind: str, client: str) -> AuthAttempt | None:
    return db.scalar(
        select(AuthAttempt).where(
            AuthAttempt.meeting_id == meeting_id, AuthAttempt.kind == kind, AuthAttempt.client_key == client
        )
    )


def guard_attempts(db: Session, meeting: Meeting, kind: str, client: str) -> None:
    """잠금 중이면 429. 잠금 시간이 지났으면 기록을 초기화한다."""
    row = _attempt(db, meeting.id, kind, client)
    if row is None or row.locked_until is None:
        return
    now = utcnow()
    if row.locked_until > now:
        wait = int((row.locked_until - now).total_seconds()) + 1
        raise AppError("TOO_MANY_ATTEMPTS", "시도 횟수를 초과했습니다. 잠시 후 다시 시도하세요.", 429, {"retry_after": wait})
    row.failures = 0
    row.locked_until = None
    db.commit()


def record_failure(db: Session, meeting: Meeting, kind: str, client: str) -> None:
    s = get_settings()
    row = _attempt(db, meeting.id, kind, client)
    if row is None:
        row = AuthAttempt(meeting_id=meeting.id, kind=kind, client_key=client, failures=0)
        db.add(row)
    row.failures += 1
    if row.failures >= s.max_auth_failures:
        row.locked_until = utcnow() + timedelta(minutes=s.auth_lock_minutes)
    # 오류를 던지기 전에 반드시 저장한다 (롤백되면 제한이 무력화됨)
    db.commit()


def clear_failures(db: Session, meeting: Meeting, kind: str, client: str) -> None:
    row = _attempt(db, meeting.id, kind, client)
    if row is not None:
        db.delete(row)
        db.commit()


def check_secret(db: Session, meeting: Meeting, kind: str, plain: str, hashed: str, client: str) -> None:
    guard_attempts(db, meeting, kind, client)
    if not verify_secret(plain, hashed):
        record_failure(db, meeting, kind, client)
        raise AppError("INVALID_CREDENTIALS", "비밀번호가 올바르지 않습니다.", 401)
    clear_failures(db, meeting, kind, client)


# ---------------------------------------------------------------- 토큰 / 참여자
def issue_token(db: Session, meeting: Meeting, participant: Participant) -> str:
    """새 개인 토큰을 발급한다. 이전 토큰은 즉시 무효가 된다."""
    token = new_token()
    ttl = utcnow() + timedelta(days=get_settings().token_ttl_days)
    participant.token_hash = token_digest(token)
    participant.token_expires_at = min(ttl, meeting.expires_at)
    db.commit()
    return token


def active_participants(db: Session, meeting_id: str) -> list[Participant]:
    return list(
        db.scalars(
            select(Participant)
            .where(Participant.meeting_id == meeting_id, Participant.status == "active")
            .order_by(Participant.id)
        )
    )


def _active_count(db: Session, meeting_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(Participant).where(Participant.meeting_id == meeting_id, Participant.status == "active")
    ) or 0


def unique_nickname(db: Session, meeting_id: str, base: str) -> str:
    """중복 닉네임에는 접미사를 붙인다: 민수 -> 민수(2) -> 민수(3)."""
    taken = set(db.scalars(select(Participant.nickname).where(Participant.meeting_id == meeting_id)))
    # 20자 + 접미사 4자 = 24자(컬럼 길이)
    if base not in taken:
        return base
    n = 2
    while f"{base}({n})" in taken:
        n += 1
    return f"{base}({n})"


def _add_participant(db: Session, meeting: Meeting, nickname: str, *, is_host: bool) -> Participant:
    # 동시에 같은 닉네임이 들어오면 UNIQUE 제약이 막는다 -> 접미사를 다시 계산해 재시도
    for _ in range(5):
        p = Participant(meeting_id=meeting.id, nickname=unique_nickname(db, meeting.id, nickname), is_host=is_host)
        db.add(p)
        try:
            db.flush()
            return p
        except IntegrityError:
            db.rollback()
    raise AppError("NICKNAME_CONFLICT", "닉네임을 정하지 못했습니다. 다시 시도하세요.", 409)


# ---------------------------------------------------------------- 입장 코드
def _guard_code_attempts(db: Session, client: str) -> None:
    row = db.get(JoinAttempt, client)
    if row is None or row.locked_until is None:
        return
    now = utcnow()
    if row.locked_until > now:
        wait = int((row.locked_until - now).total_seconds()) + 1
        raise AppError("TOO_MANY_ATTEMPTS", "시도 횟수를 초과했습니다. 잠시 후 다시 시도하세요.", 429, {"retry_after": wait})
    row.failures, row.locked_until, row.window_start = 0, None, now
    db.commit()


def _record_code_failure(db: Session, client: str) -> None:
    s = get_settings()
    now = utcnow()
    row = db.get(JoinAttempt, client)
    if row is None:
        row = JoinAttempt(client_key=client, failures=0, window_start=now)
        db.add(row)
    elif now - row.window_start > timedelta(minutes=s.code_fail_window_minutes):
        row.failures, row.window_start = 0, now
    row.failures += 1
    if row.failures >= s.max_code_failures:
        row.locked_until = now + timedelta(minutes=s.auth_lock_minutes)
    db.commit()  # 오류를 던지기 전에 저장 (롤백되면 제한이 무력화됨)


def find_meeting_by_code(db: Session, raw_code: str, client: str) -> Meeting:
    """입장 코드로 약속방을 찾는다. 없거나 만료된 방은 같은 응답(404)이고 실패로 센다."""
    _guard_code_attempts(db, client)
    code = normalize_join_code(raw_code)
    meeting = db.scalar(select(Meeting).where(Meeting.join_code == code)) if is_valid_join_code(code) else None
    if meeting is None or meeting.expires_at <= utcnow():
        _record_code_failure(db, client)
        raise AppError("INVALID_CODE", "입장 코드를 찾을 수 없습니다.", 404)
    return meeting


# ---------------------------------------------------------------- 생성 / 참여
def create_meeting(db: Session, data: MeetingCreate) -> tuple[Meeting, Participant, str]:
    s = get_settings()
    now = utcnow()
    meeting = None
    for _ in range(10):  # 코드가 겹치면(확률 매우 낮음) 새 코드로 다시 시도
        candidate = Meeting(
            id=new_meeting_id(),
            title=data.title,
            description=data.description,
            date_start=data.date_start,
            date_end=data.date_end,
            max_participants=data.max_participants,
            stage=STAGE_RECRUITING,
            join_code=new_join_code(),
            host_password_hash=hash_secret(data.host_password),
            created_at=now,
            expires_at=now + timedelta(days=s.meeting_ttl_days),
        )
        db.add(candidate)
        try:
            db.flush()
            meeting = candidate
            break
        except IntegrityError:
            db.rollback()
    if meeting is None:
        raise AppError("CODE_GENERATION_FAILED", "입장 코드를 만들지 못했습니다. 다시 시도하세요.", 503)
    host = Participant(meeting_id=meeting.id, nickname=data.host_nickname, is_host=True)
    db.add(host)
    db.flush()
    token = issue_token(db, meeting, host)
    return meeting, host, token


def join(db: Session, meeting: Meeting, nickname: str):
    """코드가 확인된 방에 입장. 모집 중이면 즉시 참여(토큰 발급), 입력 단계면 호스트 승인 대기(JoinRequest)."""
    if meeting.stage == STAGE_RECRUITING:
        if _active_count(db, meeting.id) >= meeting.max_participants:
            raise AppError("MEETING_FULL", "정원이 가득 찼습니다.", 409)
        p = _add_participant(db, meeting, nickname, is_host=False)
        token = issue_token(db, meeting, p)
        return "joined", p, token

    if meeting.stage == STAGE_INPUT:
        if _active_count(db, meeting.id) >= meeting.max_participants:
            raise AppError("MEETING_FULL", "정원이 가득 찼습니다.", 409)
        secret = new_token()
        taken = set(db.scalars(select(Participant.nickname).where(Participant.meeting_id == meeting.id)))
        pending = set(
            db.scalars(
                select(JoinRequest.nickname).where(JoinRequest.meeting_id == meeting.id, JoinRequest.status == "pending")
            )
        )
        base, n, candidate = nickname, 2, nickname
        while candidate in taken or candidate in pending:
            candidate = f"{base}({n})"
            n += 1
        req = JoinRequest(meeting_id=meeting.id, nickname=candidate, secret_hash=token_digest(secret))
        db.add(req)
        db.commit()
        return "pending", req, secret

    raise AppError("JOIN_CLOSED", "더 이상 참여할 수 없습니다.", 409, {"stage": meeting.stage})


def host_login(db: Session, meeting: Meeting, password: str, client: str) -> tuple[Participant, str]:
    check_secret(db, meeting, "host", password, meeting.host_password_hash, client)
    host = db.scalar(select(Participant).where(Participant.meeting_id == meeting.id, Participant.is_host.is_(True)))
    if host is None:  # 데이터 불일치 방어 (정상적으로는 발생하지 않음)
        raise AppError("HOST_NOT_FOUND", "호스트 정보를 찾을 수 없습니다.", 404)
    return host, issue_token(db, meeting, host)


def burn_for_unknown_meeting(plain: str) -> None:
    """존재하지 않는 약속방에도 bcrypt 비용을 써서 응답 시간 차이를 줄인다."""
    burn_verify(plain)


# ---------------------------------------------------------------- 단계 전이 / 관리
def close_recruiting(db: Session, meeting: Meeting) -> Meeting:
    state.require_stage(meeting, STAGE_RECRUITING)
    if _active_count(db, meeting.id) < get_settings().min_participants_to_close:
        raise AppError(
            "NOT_ENOUGH_PARTICIPANTS",
            f"참여자가 {get_settings().min_participants_to_close}명 이상이어야 마감할 수 있습니다.",
            409,
        )
    state.transition(meeting, STAGE_INPUT)
    meeting.closed_at = utcnow()
    db.commit()
    return meeting


def revoke(db: Session, participant: Participant) -> None:
    participant.token_hash = None
    participant.token_expires_at = None


def delete_my_data(db: Session, meeting: Meeting, me: Participant) -> None:
    """내 데이터 삭제 + 토큰 무효화. 응답/조건 등 FK 하위 데이터는 CASCADE로 함께 삭제된다."""
    if me.is_host:
        raise AppError("HOST_CANNOT_LEAVE", "호스트는 나갈 수 없습니다. 약속방을 삭제하세요.", 409)
    db.delete(me)
    db.commit()


def delete_meeting(db: Session, meeting: Meeting) -> None:
    db.delete(meeting)
    db.commit()
