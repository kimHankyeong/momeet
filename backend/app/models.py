from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.security import utcnow

# 단계 (D1 공동 합의 대상: B도 이 값을 그대로 사용)
STAGE_RECRUITING = "recruiting"
STAGE_INPUT = "input"
STAGE_RECOMMENDED = "recommended"
STAGE_PROPOSED = "proposed"
STAGE_CONFIRMED = "confirmed"
STAGES = (STAGE_RECRUITING, STAGE_INPUT, STAGE_RECOMMENDED, STAGE_PROPOSED, STAGE_CONFIRMED)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    date_start: Mapped[date] = mapped_column(Date)
    date_end: Mapped[date] = mapped_column(Date)
    max_participants: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(16), default=STAGE_RECRUITING)

    pin_hash: Mapped[str] = mapped_column(String(100))
    host_password_hash: Mapped[str] = mapped_column(String(100))

    confirmed_candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    participants: Mapped[list["Participant"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True
    )
    proposals: Mapped[list["Proposal"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True, order_by="Proposal.version"
    )
    join_requests: Mapped[list["JoinRequest"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan", passive_deletes=True
    )


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("meeting_id", "nickname", name="uq_participant_nickname"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(24))
    is_host: Mapped[bool] = mapped_column(Boolean, default=False)
    # active / excluded
    status: Mapped[str] = mapped_column(String(12), default="active")
    # 조건 입력 상태. 값은 B의 조건 API가 갱신한다 (none / draft / submitted)
    input_status: Mapped[str] = mapped_column(String(12), default="none")

    # 토큰 원문은 저장하지 않는다 (sha256만)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="participants")


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (UniqueConstraint("meeting_id", "version", name="uq_proposal_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    # pending / accepted / rejected / superseded
    status: Mapped[str] = mapped_column(String(12), default="pending")
    proposed_by: Mapped[int | None] = mapped_column(ForeignKey("participants.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="proposals")
    responses: Mapped[list["ProposalResponse"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan", passive_deletes=True
    )


class ProposalResponse(Base):
    __tablename__ = "proposal_responses"
    __table_args__ = (UniqueConstraint("proposal_id", "participant_id", name="uq_response_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    # accept / reject
    response: Mapped[str] = mapped_column(String(8))
    responded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    proposal: Mapped[Proposal] = relationship(back_populates="responses")


class JoinRequest(Base):
    """마감 후 참여 신청 (호스트 승인 필요)."""

    __tablename__ = "join_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(24))
    secret_hash: Mapped[str] = mapped_column(String(64))
    # pending / approved / rejected
    status: Mapped[str] = mapped_column(String(10), default="pending")
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id", ondelete="SET NULL"), nullable=True)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="join_requests")


class Condition(Base):
    """참여자 1명의 조건 (출발 가능 시간·출발역·이동 조건). 내용은 본인만 조회할 수 있다."""

    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 참여자/약속방이 삭제되면 조건도 함께 삭제된다 ("내 데이터 삭제")
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), unique=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    # fairness.validate_conditions 가 정리한 JSON
    data: Mapped[dict] = mapped_column(JSON)
    # draft / submitted
    status: Mapped[str] = mapped_column(String(10), default="draft")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecommendationResult(Base):
    """약속방의 최신 추천 결과 (fairness.recommend 반환 JSON 그대로).

    모든 참여자의 경로가 들어 있으므로 원본을 응답으로 내보내지 않는다 (view_for 로 본인 경로만 노출).
    """

    __tablename__ = "recommendation_results"

    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthAttempt(Base):
    """PIN / 호스트 비밀번호 실패 횟수 (약속방 + 종류 + 클라이언트별)."""

    __tablename__ = "auth_attempts"
    __table_args__ = (UniqueConstraint("meeting_id", "kind", "client_key", name="uq_auth_attempt"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    client_key: Mapped[str] = mapped_column(String(64))
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
