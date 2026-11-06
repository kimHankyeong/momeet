"""백B(fairness.py) 연동 지점: 저장된 추천 결과에서 후보를 검증·조회한다.

B의 함수는 `get_candidate(result, candidate_id)` 형태(추천 결과 dict를 인자로 받음)라서,
약속방별 최신 결과를 DB(recommendation_results)에서 읽어 넘기는 얇은 어댑터를 둔다.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core import fairness
from app.database import get_db
from app.models import RecommendationResult


class CandidateProvider:
    """요청 하나 동안 쓰는 후보 조회기. 같은 약속방 결과는 한 번만 읽는다."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[str, dict | None] = {}

    def result(self, meeting_id: str) -> dict | None:
        if meeting_id not in self._cache:
            row = self.db.get(RecommendationResult, meeting_id)
            self._cache[meeting_id] = row.result if row else None
        return self._cache[meeting_id]

    def get(self, meeting_id: str, candidate_id: str) -> dict | None:
        """이번 추천 결과에 있는 후보면 공개 가능한 정보(dict), 없으면 None. (참여자 개인 경로 없음)"""
        return fairness.get_candidate(self.result(meeting_id), candidate_id)

    def my_route(self, meeting_id: str, candidate_id: str, participant_id: int) -> dict | None:
        """제안/확정 화면의 '내 이동·환승·도보·경로'. 추천 이후 참여한 사람은 None."""
        return fairness.get_my_route(self.result(meeting_id), candidate_id, str(participant_id))


def get_candidate_provider(db: Session = Depends(get_db)) -> CandidateProvider:
    """FastAPI 의존성. 테스트에서 dependency_overrides 로 교체할 수 있다."""
    return CandidateProvider(db)
