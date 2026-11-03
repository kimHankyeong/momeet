import os

# app.* 를 import하기 전에 설정한다 (설정은 캐시됨)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["MAX_AUTH_FAILURES"] = "5"
os.environ["AUTH_LOCK_MINUTES"] = "5"

from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def engine():
    # 메모리 DB를 모든 연결이 공유하도록 고정
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    from app import models  # noqa: F401

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    yield s
    s.close()


@pytest.fixture()
def app(session_factory):
    application = create_app()

    def _get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    application.dependency_overrides[get_db] = _get_db
    return application


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------- 헬퍼
def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# 테스트용 조건: 서로 다른 출발역, 같은 시간대
STATIONS = ["쌍문", "강남", "신촌", "잠실", "수유"]


def conditions(station: str, d0: str, hours=(13, 14, 15), **extra) -> dict:
    body = {"availability": {d0: list(hours)}, "default_station": station}
    body.update(extra)
    return body


class Room:
    """테스트용 약속방 조작 헬퍼."""

    def __init__(self, client: TestClient, data: dict, pin: str, password: str):
        self.client = client
        self.id = data["meeting_id"]
        self.pin = pin
        self.password = password
        self.host_token = data["access_token"]
        self.host_id = data["participant"]["id"]
        self.date0 = data["meeting"]["date_start"]
        self.cands: list[str] = []

    @property
    def host(self) -> dict:
        return auth(self.host_token)

    def join(self, nickname: str):
        return self.client.post(f"/meetings/{self.id}/join", json={"nickname": nickname, "pin": self.pin})

    def add(self, nickname: str) -> dict:
        r = self.join(nickname)
        assert r.status_code == 201, r.text
        d = r.json()
        return {"id": d["participant"]["id"], "nickname": d["participant"]["nickname"], "token": d["access_token"], "h": auth(d["access_token"])}

    def get(self, path: str = "", headers: dict | None = None):
        return self.client.get(f"/meetings/{self.id}{path}", headers=headers or self.host)

    def post(self, path: str, json: dict | None = None, headers: dict | None = None):
        return self.client.post(f"/meetings/{self.id}{path}", json=json if json is not None else {}, headers=headers or self.host)

    def submit(self, headers: dict, station: str, **extra):
        r = self.client.post(f"/meetings/{self.id}/conditions/me/submit", json=conditions(station, self.date0, **extra), headers=headers)
        assert r.status_code == 200, r.text
        return r

    def recommend(self) -> dict:
        r = self.post("/recommendations")
        assert r.status_code == 200, r.text
        body = r.json()
        self.cands = [c["candidate_id"] for c in body["candidates"]]
        return body


def new_room(client: TestClient, pin: str = "123456", password: str = "host-password-1", **over) -> Room:
    today = date.today()
    body = {
        "title": "금요일 저녁 모임",
        "description": "다 같이 보자",
        "date_start": today.isoformat(),
        "date_end": (today + timedelta(days=6)).isoformat(),
        "max_participants": 10,
        "host_nickname": "호스트",
        "pin": pin,
        "host_password": password,
    }
    body.update(over)
    r = client.post("/meetings", json=body)
    assert r.status_code == 201, r.text
    return Room(client, r.json(), pin, password)


def advance_to_recommended(session_factory, room: Room) -> None:
    """단계만 올린다 (추천 결과 없이). 단계 규칙만 확인하는 테스트용."""
    from app.models import Meeting
    from app.services import hooks

    s = session_factory()
    try:
        hooks.mark_recommended(s, s.get(Meeting, room.id))
    finally:
        s.close()


def run_pipeline(room: Room, people: list[dict]) -> None:
    """실제 흐름: 전원 조건 제출 -> 호스트 추천 실행 (B의 fairness 로직 사용)."""
    room.submit(room.host, STATIONS[0])
    for i, p in enumerate(people, start=1):
        room.submit(p["h"], STATIONS[i % len(STATIONS)])
    body = room.recommend()
    assert body["status"] == "ok" and len(room.cands) >= 2, body


@pytest.fixture()
def room(client):
    return new_room(client)
