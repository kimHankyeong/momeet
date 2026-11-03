"""개발용 시드 데이터. 프론트 연동/발표 시연에서 단계별 화면을 바로 볼 수 있게 약속방을 만든다.
조건 제출 -> 추천(B의 실제 계산) -> 제안 -> 동의까지 실제 서비스 코드를 그대로 통과한다.

사용: python -m scripts.seed --yes
출력된 토큰은 개발용이다 (운영 DB에서 실행하지 말 것).
"""
import sys
from datetime import date, timedelta

from app.database import SessionLocal, init_db
from app.integrations.candidates import CandidateProvider
from app.models import Meeting, Participant
from app.schemas import MeetingCreate
from app.services import conditions as cond
from app.services import meetings as svc
from app.services import proposals

PIN = "123456"
HOST_PASSWORD = "demo-password"
STATIONS = ["쌍문", "강남", "신촌"]  # 호스트, 첫 번째 참여자, 두 번째 참여자


def _room(db, title: str, names: list[str]) -> tuple[Meeting, Participant, str, list[tuple[Participant, str]]]:
    today = date.today()
    meeting, host, host_token = svc.create_meeting(
        db,
        MeetingCreate(
            title=title,
            description="시드 데이터",
            date_start=today,
            date_end=today + timedelta(days=6),
            host_nickname="호스트",
            pin=PIN,
            host_password=HOST_PASSWORD,
        ),
    )
    members = []
    for n in names:
        _, p, t = svc.join(db, meeting, n, PIN, "seed")
        members.append((p, t))
    return meeting, host, host_token, members


def _conditions(meeting: Meeting, station: str) -> dict:
    d0 = meeting.date_start.isoformat()
    return {"availability": {d0: [13, 14, 15]}, "default_station": station}


def _submit_all(db, meeting, host, members) -> None:
    for p, st in zip([host] + [m[0] for m in members], STATIONS):
        cond.submit(db, meeting, p, _conditions(meeting, st))


def main() -> None:
    if "--yes" not in sys.argv:
        print("개발용 시드 데이터를 현재 DATABASE_URL에 추가합니다. 계속하려면 --yes 를 붙이세요.")
        return
    init_db()
    db = SessionLocal()
    try:
        out = []
        names = ["민수", "지은"]

        m, h, ht, mem = _room(db, "시드1 모집", names)
        out.append((m, ht, mem))

        m, h, ht, mem = _room(db, "시드2 입력", names)
        svc.close_recruiting(db, m)
        cond.submit(db, m, h, _conditions(m, STATIONS[0]))
        cond.save_draft(db, m, mem[0][0], _conditions(m, STATIONS[1]))
        out.append((m, ht, mem))

        m, h, ht, mem = _room(db, "시드3 추천", names)
        svc.close_recruiting(db, m)
        _submit_all(db, m, h, mem)
        cond.run_recommendation(db, m)
        out.append((m, ht, mem))

        m, h, ht, mem = _room(db, "시드4 제안", names)
        svc.close_recruiting(db, m)
        _submit_all(db, m, h, mem)
        best = cond.run_recommendation(db, m)["best"]
        proposals.propose(db, m, h, best, CandidateProvider(db).get)
        proposals.respond(db, m, mem[0][0], "accept")
        out.append((m, ht, mem))

        m, h, ht, mem = _room(db, "시드5 확정", names)
        svc.close_recruiting(db, m)
        _submit_all(db, m, h, mem)
        best = cond.run_recommendation(db, m)["best"]
        proposals.propose(db, m, h, best, CandidateProvider(db).get)
        for p in [h] + [x[0] for x in mem]:
            proposals.respond(db, m, p, "accept")
        out.append((m, ht, mem))

        print(f"PIN={PIN}  호스트 비밀번호={HOST_PASSWORD}")
        for meeting, host_token, members in out:
            print(f"\n{meeting.title}  id={meeting.id}  stage={meeting.stage}")
            print(f"  host   token={host_token}")
            for p, t in members:
                print(f"  {p.nickname:<4} token={t}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
