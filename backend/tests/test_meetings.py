from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app import models
from app.errors import AppError
from app.security import utcnow
from tests.conftest import auth, new_room


# ---------------------------------------------------------------- 생성 / 입력 검증
def test_create_returns_host_token_join_code_and_hides_secrets(client):
    r = client.post(
        "/meetings",
        json={
            "title": "모임",
            "date_start": "2026-12-01",
            "date_end": "2026-12-07",
            "host_nickname": "한경",
            "host_password": "super-secret-pw",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["participant"]["is_host"] is True
    assert body["meeting"]["stage"] == "recruiting"
    assert body["meeting"]["max_participants"] == 10
    assert len(body["join_code"]) == 8  # 서버가 발급한 입장 코드
    for secret in ("super-secret-pw", "$2b$", "password_hash"):
        assert secret not in r.text


def test_secrets_are_stored_hashed_not_plain(client, db):
    room = new_room(client, password="another-password")
    m = db.get(models.Meeting, room.id)
    assert m.host_password_hash.startswith("$2") and "another-password" not in m.host_password_hash
    assert m.join_code == room.code
    p = db.get(models.Participant, room.host_id)
    assert p.token_hash and p.token_hash != room.host_token and len(p.token_hash) == 64


def _bad(client, **over):
    base = {
        "title": "모임", "date_start": "2026-12-01", "date_end": "2026-12-07",
        "host_nickname": "한경", "host_password": "long-enough-pw",
    }
    base.update(over)
    return client.post("/meetings", json=base)


def test_create_validation(client):
    for over in (
        {"pin": "123456"},  # 옛 클라이언트: PIN은 더 이상 받지 않는다 (코드는 서버가 발급)
        {"join_code": "abcd2345"},  # 클라이언트가 코드를 정할 수 없다
        {"host_password": "short"},
        {"host_password": "가" * 25},  # 75바이트: bcrypt 72바이트 한도 초과
        {"title": ""}, {"title": "  "}, {"title": "가" * 13},  # 시안: 약속 이름 최대 12자
        {"host_nickname": "a\nb"}, {"host_nickname": "가" * 9},  # 시안: 닉네임 최대 8자
        {"date_start": "2026-12-10", "date_end": "2026-12-01"},
        {"date_start": "2026-01-01", "date_end": "2026-12-31"},
        {"max_participants": 1}, {"max_participants": 11}, {"max_participants": 31},
        {"is_host": True}, {"stage": "confirmed"},  # 허용되지 않은 필드
    ):
        r = _bad(client, **over)
        assert r.status_code == 422, over
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_error_does_not_echo_password(client):
    r = _bad(client, host_password="Zq9!x")
    assert "Zq9!x" not in r.text
    assert all("field" in f and "reason" in f for f in r.json()["error"]["fields"])


def test_unknown_route_and_method_use_error_shape(client):
    assert client.get("/nope").json()["error"]["code"] == "NOT_FOUND"
    assert client.get("/meetings").json()["error"]["code"] == "METHOD_NOT_ALLOWED"  # POST만 있는 경로


# ---------------------------------------------------------------- 공개 정보
def test_public_view_has_no_sensitive_data(client, room):
    room.add("민수")
    r = client.get(f"/meetings/{room.id}/public")
    assert r.status_code == 200
    d = r.json()
    assert d["participant_count"] == 2 and d["can_join"] is True and d["can_request_join"] is False
    assert set(d) == {
        "id", "title", "description", "date_start", "date_end", "stage",
        "participant_count", "max_participants", "can_join", "can_request_join",
    }
    assert room.code not in r.text and "호스트" not in r.text  # 입장 코드·호스트 닉네임·참여자 목록 비노출


def test_unknown_meeting_404(client):
    assert client.get("/meetings/does-not-exist/public").json()["error"]["code"] == "MEETING_NOT_FOUND"


def test_expired_meeting_blocks_all_access(client, room, db):
    m = db.get(models.Meeting, room.id)
    m.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    for r in (
        client.get(f"/meetings/{room.id}/public"),
        client.get(f"/meetings/{room.id}", headers=room.host),
        client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.password}),
    ):
        assert r.status_code == 410
        assert r.json()["error"]["code"] == "MEETING_EXPIRED"
    # 코드로는 만료된 방의 존재를 알려 주지 않는다 (없는 코드와 같은 응답)
    for r in (client.get(f"/join/{room.code}"), client.post(f"/join/{room.code}", json={"nickname": "a"})):
        assert r.status_code == 404 and r.json()["error"]["code"] == "INVALID_CODE"


# ---------------------------------------------------------------- 참여
def test_join_issues_token_and_dashboard_works(client, room):
    p = room.add("민수")
    d = room.get(headers=p["h"]).json()
    assert d["me"]["nickname"] == "민수" and d["me"]["is_host"] is False
    # 시안: 모집 중에도 각자 조건을 입력한다
    assert d["next_action"]["code"] == "submit_conditions"
    assert d["progress"] == {"submitted": 0, "total": 2}


def test_duplicate_nicknames_get_suffix(client, room):
    names = [room.add("민수")["nickname"] for _ in range(3)]
    assert names == ["민수", "민수(2)", "민수(3)"]
    assert room.add("호스트")["nickname"] == "호스트(2)"  # 호스트 닉네임과도 구분


def _join(client, code, nickname="a"):
    return client.post(f"/join/{code}", json={"nickname": nickname})


def test_join_code_is_server_issued_unique_and_unambiguous(client):
    from app.security import JOIN_CODE_ALPHABET, JOIN_CODE_LENGTH

    codes = {new_room(client).code for _ in range(25)}
    assert len(codes) == 25  # 겹치지 않는다
    for c in codes:
        assert len(c) == JOIN_CODE_LENGTH and set(c) <= set(JOIN_CODE_ALPHABET)
        assert not set(c) & set("ilo01")  # 헷갈리는 문자는 쓰지 않는다


def test_preview_by_code(client, room):
    room.add("민수")
    r = client.get(f"/join/{room.code}")
    assert r.status_code == 200
    d = r.json()
    assert d["meeting_id"] == room.id and d["title"] == "금요일 저녁 모임"
    assert d["can_join"] is True and d["participant_count"] == 2
    assert "join_code" not in d and room.password not in r.text


def test_code_input_is_forgiving(client, room):
    for variant in (room.code.upper(), f"  {room.code}  ", f"MOMEET-{room.code}", f"momeet - {room.code[:4]}-{room.code[4:]}"):
        assert client.get(f"/join/{variant}").status_code == 200, variant


def test_unknown_or_malformed_code_is_404_without_hints(client, room):
    for bad in ("zzzzzzzz", "abc", "k7m2x9q", "k7m2x9qak", "00000000", "momeet", "a" * 50):
        r = client.get(f"/join/{bad}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "INVALID_CODE", bad
    assert _join(client, "zzzzzzzz").json()["error"]["code"] == "INVALID_CODE"


def test_meeting_id_alone_cannot_join(client, room):
    """방 ID(링크의 일부)만으로는 참여할 수 없다. 입장 코드가 열쇠다."""
    r = client.post(f"/meetings/{room.id}/join", json={"nickname": "a"})
    assert r.status_code in (404, 405)
    r = _join(client, room.id)  # ID를 코드 자리에 넣어도 거부
    assert r.status_code == 404 and r.json()["error"]["code"] == "INVALID_CODE"


def test_code_guessing_is_rate_limited_and_not_reset_by_success(client, room):
    for i in range(10):
        assert client.get("/join/zzzzzzzz").status_code == 404
        if i in (0, 3, 6):  # 유효한 코드를 섞어도 실패 횟수는 초기화되지 않는다
            assert client.get(f"/join/{room.code}").status_code == 200
    r = client.get(f"/join/{room.code}")  # 이제 올바른 코드도 잠긴다
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
    assert int(r.headers["Retry-After"]) > 0
    assert _join(client, room.code).status_code == 429


def test_code_lock_expires_and_failure_window_resets(client, room, db):
    for _ in range(10):
        client.get("/join/zzzzzzzz")
    assert client.get(f"/join/{room.code}").status_code == 429
    row = db.scalar(select(models.JoinAttempt))
    row.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get(f"/join/{room.code}").status_code == 200  # 잠금 해제

    for _ in range(9):
        client.get("/join/zzzzzzzz")
    row = db.scalar(select(models.JoinAttempt))
    row.window_start = utcnow() - timedelta(minutes=11)  # 시간 창이 지나면 횟수가 새로 시작된다
    db.commit()
    for _ in range(9):
        assert client.get("/join/zzzzzzzz").status_code == 404  # 잠기지 않는다


def test_code_limit_is_per_client(db):
    from app.services.meetings import _guard_code_attempts, _record_code_failure

    for _ in range(10):
        _record_code_failure(db, "1.1.1.1")
    with pytest.raises(AppError) as e:
        _guard_code_attempts(db, "1.1.1.1")
    assert e.value.code == "TOO_MANY_ATTEMPTS"
    _guard_code_attempts(db, "2.2.2.2")  # 다른 클라이언트는 영향 없음


def test_host_password_lockout_expires_and_success_resets_counter(client, room, db):
    def wrong():
        return client.post(f"/meetings/{room.id}/host-login", json={"host_password": "wrong-password"})

    def right():
        return client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.password})

    for _ in range(5):
        wrong()
    assert right().status_code == 429
    row = db.scalar(select(models.AuthAttempt))
    row.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert right().status_code == 200
    assert db.scalar(select(func.count()).select_from(models.AuthAttempt)) == 0  # 성공하면 초기화

    for _ in range(4):
        wrong()
    assert right().status_code == 200
    for _ in range(4):
        assert wrong().status_code == 401  # 초기화되어 잠기지 않음


def test_host_password_limit_is_per_client_key(db, client, room):
    from app.models import Meeting
    from app.services.meetings import guard_attempts, record_failure

    m = db.get(Meeting, room.id)
    for _ in range(5):
        record_failure(db, m, "host", "1.1.1.1")
    with pytest.raises(AppError) as e:
        guard_attempts(db, m, "host", "1.1.1.1")
    assert e.value.code == "TOO_MANY_ATTEMPTS"
    guard_attempts(db, m, "host", "2.2.2.2")  # 다른 클라이언트는 영향 없음


def test_meeting_full(client):
    room = new_room(client, max_participants=2)
    room.add("a")
    r = room.join("b")
    assert r.status_code == 409 and r.json()["error"]["code"] == "MEETING_FULL"


# ---------------------------------------------------------------- 호스트 로그인 / 토큰
def test_host_login_rotates_token(client, room):
    r = client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.password})
    assert r.status_code == 200 and r.json()["participant"]["is_host"] is True
    new_token = r.json()["access_token"]
    assert new_token != room.host_token
    assert room.get(headers=auth(new_token)).status_code == 200
    assert room.get(headers=room.host).status_code == 401  # 이전 토큰은 무효


def test_host_login_wrong_password_and_lockout(client, room):
    for _ in range(5):
        r = client.post(f"/meetings/{room.id}/host-login", json={"host_password": "wrong-password"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.password})
    assert r.status_code == 429


def test_code_failures_do_not_block_host_login(client, room):
    for _ in range(10):
        client.get("/join/zzzzzzzz")
    assert client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.password}).status_code == 200


def test_join_code_is_not_a_host_password(client, room):
    r = client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.code})
    assert r.status_code == 401


def test_auth_required_and_malformed_headers(client, room):
    assert client.get(f"/meetings/{room.id}").status_code == 401
    for h in ("Bearer", "Basic abc", "Bearer  ", "abc", "Bearer not-a-real-token"):
        r = client.get(f"/meetings/{room.id}", headers={"Authorization": h})
        assert r.status_code == 401, h
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_token_is_bound_to_its_meeting(client, room):
    other = new_room(client)
    assert client.get(f"/meetings/{room.id}", headers=other.host).status_code == 401
    assert client.get(f"/meetings/{other.id}", headers=other.host).status_code == 200


def test_expired_token_rejected(client, room, db):
    p = db.get(models.Participant, room.host_id)
    p.token_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert room.get().status_code == 401


def test_token_expiry_never_exceeds_meeting_expiry(client, room, db):
    p = db.get(models.Participant, room.host_id)
    m = db.get(models.Meeting, room.id)
    assert p.token_expires_at <= m.expires_at


def test_host_only_endpoints_reject_participants(client, room):
    p = room.add("민수")
    for method, path in (("post", "/close"), ("delete", ""), ("post", "/proposal"), ("get", "/join-requests")):
        r = client.request(method.upper(), f"/meetings/{room.id}{path}", json={"candidate_id": "c1"} if method == "post" else None, headers=p["h"])
        assert r.status_code == 403, (method, path)
        assert r.json()["error"]["code"] == "HOST_ONLY"


# ---------------------------------------------------------------- 모집 마감
def test_close_requires_enough_participants(client, room):
    r = room.post("/close")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_ENOUGH_PARTICIPANTS"
    room.add("민수")
    r = room.post("/close")
    assert r.status_code == 200 and r.json()["meeting"]["stage"] == "input"
    assert r.json()["meeting"]["closed_at"].endswith("Z")
    assert room.post("/close").status_code == 409  # 다시 마감할 수 없다


def test_join_after_close_becomes_request_and_after_recommend_is_closed(client, room, session_factory):
    from tests.conftest import advance_to_recommended

    room.add("민수")
    room.post("/close")
    r = room.join("늦은사람")
    assert r.status_code == 202 and r.json()["status"] == "pending" and r.json()["request_secret"]
    assert r.json()["meeting_id"] == room.id  # claim 호출에 필요
    assert "access_token" not in r.text
    pub = client.get(f"/meetings/{room.id}/public").json()
    assert pub["can_join"] is False and pub["can_request_join"] is True

    advance_to_recommended(session_factory, room)
    r = room.join("더늦은사람")
    assert r.status_code == 409 and r.json()["error"]["code"] == "JOIN_CLOSED"


def test_wrong_code_after_close_reveals_nothing_extra(client, room):
    room.add("민수")
    room.post("/close")
    assert client.get("/join/zzzzzzzz").status_code == 404
    assert room.join("늦은사람").status_code == 202  # 올바른 코드는 호스트 승인 신청으로 이어진다


# ---------------------------------------------------------------- 대시보드
def test_dashboard_next_actions_while_recruiting(client, room):
    """모집 중: 각자 조건 입력 -> 전원 입력하면 호스트에게 '모집 마감'을 안내."""
    p = room.add("민수")
    assert room.get().json()["next_action"]["code"] == "submit_conditions"
    room.submit(room.host, "쌍문")
    assert room.get().json()["next_action"]["code"] == "wait_conditions"  # 민수 입력 대기
    assert room.get(headers=p["h"]).json()["next_action"]["code"] == "submit_conditions"
    assert room.get().json()["progress"] == {"submitted": 1, "total": 2}

    room.submit(p["h"], "강남")
    assert room.get().json()["next_action"]["code"] == "close_recruiting"
    assert room.get(headers=p["h"]).json()["next_action"]["code"] == "wait_recruiting"
    assert room.get().json()["progress"] == {"submitted": 2, "total": 2}


def test_dashboard_next_actions_through_input_stage(client, room, db):
    p = room.add("민수")
    room.post("/close")
    assert room.get().json()["next_action"]["code"] == "submit_conditions"
    assert room.get(headers=p["h"]).json()["next_action"]["code"] == "submit_conditions"

    from app.services import hooks

    for pid, status in ((room.host_id, "submitted"), (p["id"], "draft")):
        hooks.set_input_status(db, db.get(models.Participant, pid), status)
    assert room.get().json()["next_action"]["code"] == "wait_conditions"
    assert room.get(headers=p["h"]).json()["next_action"]["code"] == "submit_conditions"

    hooks.set_input_status(db, db.get(models.Participant, p["id"]), "submitted")
    assert room.get().json()["next_action"]["code"] == "run_recommendation"
    assert room.get(headers=p["h"]).json()["next_action"]["code"] == "wait_recommendation"


def test_dashboard_never_leaks_secrets_or_other_people_data(client, room):
    p = room.add("민수")
    text = room.get(headers=p["h"]).text
    for secret in (room.password, room.host_token, p["token"], "$2b$", "token_hash", "password_hash"):
        assert secret not in text
    d = room.get(headers=p["h"]).json()
    assert d["meeting"]["join_code"] == room.code  # 시안: 참여자도 링크/코드를 공유할 수 있다
    allowed = {"id", "nickname", "is_host", "is_me", "input_status"}
    assert all(set(x) <= allowed for x in d["participants"])
    assert "host" not in d  # 참여자에게는 호스트 전용 블록이 없다
    assert "host" in room.get().json()


# ---------------------------------------------------------------- 삭제
def test_delete_me_removes_data_and_invalidates_token(client, room, db):
    p = room.add("민수")
    assert client.delete(f"/meetings/{room.id}/me", headers=p["h"]).status_code == 204
    assert room.get(headers=p["h"]).status_code == 401
    assert db.get(models.Participant, p["id"]) is None
    names = [x["nickname"] for x in room.get().json()["participants"]]
    assert "민수" not in names


def test_host_cannot_leave_but_can_delete_meeting(client, room, db):
    p = room.add("민수")
    r = client.delete(f"/meetings/{room.id}/me", headers=room.host)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HOST_CANNOT_LEAVE"
    assert client.delete(f"/meetings/{room.id}", headers=room.host).status_code == 204
    assert client.get(f"/meetings/{room.id}/public").status_code == 404
    for model in (models.Participant, models.Proposal, models.ProposalResponse, models.JoinRequest, models.AuthAttempt):
        assert db.scalar(select(func.count()).select_from(model)) == 0
    assert db.get(models.Meeting, room.id) is None
    _ = p


def test_two_meetings_are_isolated(client):
    a, b = new_room(client), new_room(client)
    a.add("x")
    assert len(b.get().json()["participants"]) == 1
    assert client.delete(f"/meetings/{a.id}", headers=a.host).status_code == 204
    assert b.get().status_code == 200


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    _ = date


def test_design_limits_boundaries_are_accepted(client):
    """시안의 최대치: 약속 이름 12자, 닉네임 8자."""
    room = new_room(client, title="가" * 12, host_nickname="나" * 8)
    p = room.add("다" * 8)
    assert p["nickname"] == "다" * 8
    assert room.join("다" * 9).status_code == 422
    assert room.join("라").status_code == 201


def test_team_limits_10_people_and_7_days(client):
    """팀 결정: 최대 10명, 날짜 범위 7일 (경계값은 허용, 초과는 거부)."""
    room = new_room(client, max_participants=10, date_start="2026-12-01", date_end="2026-12-07")  # 7일
    pub = client.get(f"/meetings/{room.id}/public").json()
    assert pub["max_participants"] == 10 and (pub["date_start"], pub["date_end"]) == ("2026-12-01", "2026-12-07")
    r = _bad(client, date_start="2026-12-01", date_end="2026-12-08")  # 8일
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _bad(client, max_participants=11).status_code == 422
    assert _bad(client, date_start="2026-12-01", date_end="2026-12-01").status_code == 201  # 하루도 가능


def test_unexpected_error_is_logged_with_cause_but_response_is_generic(client, app, caplog):
    """원인 보고를 위해 예기치 못한 오류는 서버 로그에 남지만, 응답에는 내부 상세가 없다."""
    import logging

    from app.database import get_db

    def _boom():
        raise RuntimeError("db password=hunter2 connection refused")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _boom
    with caplog.at_level(logging.ERROR, logger="momeet"):
        r = client.get("/meetings/abc/public")
    assert r.status_code == 500 and r.json() == {"error": {"code": "INTERNAL_ERROR", "message": "서버 오류가 발생했습니다."}}
    assert "hunter2" not in r.text
    assert any("GET /meetings/abc/public" in rec.getMessage() for rec in caplog.records)  # 어떤 요청이었는지 로그에 있다
    assert any(rec.exc_info for rec in caplog.records)  # 원인(스택)이 로그에 있다
