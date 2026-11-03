from datetime import date, timedelta

from sqlalchemy import func, select

from app import models
from app.security import utcnow
from tests.conftest import auth, new_room


# ---------------------------------------------------------------- 생성 / 입력 검증
def test_create_returns_host_token_and_hides_secrets(client):
    r = client.post(
        "/meetings",
        json={
            "title": "모임",
            "date_start": "2026-12-01",
            "date_end": "2026-12-07",
            "host_nickname": "한경",
            "pin": "4821",
            "host_password": "super-secret-pw",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["participant"]["is_host"] is True
    assert body["meeting"]["stage"] == "recruiting"
    assert body["meeting"]["max_participants"] == 10
    text = r.text
    for secret in ("4821", "super-secret-pw", "$2b$", "pin_hash", "password_hash"):
        assert secret not in text


def test_secrets_are_stored_hashed_not_plain(client, db):
    room = new_room(client, pin="9876", password="another-password")
    m = db.get(models.Meeting, room.id)
    assert m.pin_hash.startswith("$2") and "9876" not in m.pin_hash
    assert m.host_password_hash.startswith("$2") and "another-password" not in m.host_password_hash
    p = db.get(models.Participant, room.host_id)
    assert p.token_hash and p.token_hash != room.host_token and len(p.token_hash) == 64


def _bad(client, **over):
    base = {
        "title": "모임", "date_start": "2026-12-01", "date_end": "2026-12-07",
        "host_nickname": "한경", "pin": "1234", "host_password": "long-enough-pw",
    }
    base.update(over)
    return client.post("/meetings", json=base)


def test_create_validation(client):
    for over in (
        {"pin": "12"}, {"pin": "abcd"}, {"pin": "1234567"},
        {"host_password": "short"},
        {"host_password": "가" * 25},  # 75바이트: bcrypt 72바이트 한도 초과
        {"title": ""}, {"title": "  "}, {"title": "x" * 51},
        {"host_nickname": "a\nb"},
        {"date_start": "2026-12-10", "date_end": "2026-12-01"},
        {"date_start": "2026-01-01", "date_end": "2026-12-31"},
        {"max_participants": 1}, {"max_participants": 31},
        {"is_host": True}, {"stage": "confirmed"},  # 허용되지 않은 필드
    ):
        r = _bad(client, **over)
        assert r.status_code == 422, over
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validation_error_does_not_echo_pin_or_password(client):
    r = _bad(client, pin="12", host_password="Zq9!x")
    assert "Zq9!x" not in r.text and '"12"' not in r.text
    assert all("field" in f and "reason" in f for f in r.json()["error"]["fields"])


def test_unknown_route_and_method_use_error_shape(client):
    assert client.get("/nope").json()["error"]["code"] == "NOT_FOUND"
    assert client.get("/meetings/x/join").json()["error"]["code"] == "METHOD_NOT_ALLOWED"


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
    assert room.pin not in r.text and "호스트" not in r.text  # 호스트 닉네임·참여자 목록 비노출


def test_unknown_meeting_404(client):
    assert client.get("/meetings/does-not-exist/public").json()["error"]["code"] == "MEETING_NOT_FOUND"


def test_expired_meeting_blocks_all_access(client, room, db):
    m = db.get(models.Meeting, room.id)
    m.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    for r in (
        client.get(f"/meetings/{room.id}/public"),
        client.get(f"/meetings/{room.id}", headers=room.host),
        client.post(f"/meetings/{room.id}/join", json={"nickname": "a", "pin": room.pin}),
        client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.password}),
    ):
        assert r.status_code == 410
        assert r.json()["error"]["code"] == "MEETING_EXPIRED"


# ---------------------------------------------------------------- 참여
def test_join_issues_token_and_dashboard_works(client, room):
    p = room.add("민수")
    d = room.get(headers=p["h"]).json()
    assert d["me"]["nickname"] == "민수" and d["me"]["is_host"] is False
    assert d["next_action"]["code"] == "wait_recruiting"


def test_duplicate_nicknames_get_suffix(client, room):
    names = [room.add("민수")["nickname"] for _ in range(3)]
    assert names == ["민수", "민수(2)", "민수(3)"]
    assert room.add("호스트")["nickname"] == "호스트(2)"  # 호스트 닉네임과도 구분


def test_join_wrong_pin(client, room):
    r = room.client.post(f"/meetings/{room.id}/join", json={"nickname": "a", "pin": "0000"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_PIN"


def test_pin_lockout_after_repeated_failures_even_with_correct_pin(client, room):
    for _ in range(5):
        assert client.post(f"/meetings/{room.id}/join", json={"nickname": "a", "pin": "0000"}).status_code == 401
    r = client.post(f"/meetings/{room.id}/join", json={"nickname": "a", "pin": room.pin})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
    assert int(r.headers["Retry-After"]) > 0


def test_lockout_expires_and_success_resets_counter(client, room, db):
    for _ in range(5):
        client.post(f"/meetings/{room.id}/join", json={"nickname": "a", "pin": "0000"})
    row = db.scalar(select(models.AuthAttempt))
    row.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post(f"/meetings/{room.id}/join", json={"nickname": "a", "pin": room.pin}).status_code == 201
    assert db.scalar(select(func.count()).select_from(models.AuthAttempt)) == 0

    # 4번 실패 후 성공하면 횟수가 초기화된다 (이후 4번 더 틀려도 잠기지 않음)
    for _ in range(4):
        client.post(f"/meetings/{room.id}/join", json={"nickname": "b", "pin": "0000"})
    assert client.post(f"/meetings/{room.id}/join", json={"nickname": "b", "pin": room.pin}).status_code == 201
    for _ in range(4):
        assert client.post(f"/meetings/{room.id}/join", json={"nickname": "c", "pin": "0000"}).status_code == 401


def test_lockout_is_per_client_key(db, client, room):
    from app.models import Meeting
    from app.services.meetings import guard_attempts, record_failure

    m = db.get(Meeting, room.id)
    for _ in range(5):
        record_failure(db, m, "pin", "1.1.1.1")
    try:
        guard_attempts(db, m, "pin", "1.1.1.1")
        raise AssertionError("잠겨야 한다")
    except Exception as e:  # noqa: BLE001
        assert getattr(e, "code", "") == "TOO_MANY_ATTEMPTS"
    guard_attempts(db, m, "pin", "2.2.2.2")  # 다른 클라이언트는 영향 없음


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


def test_pin_and_host_password_counters_are_independent(client, room):
    for _ in range(5):
        client.post(f"/meetings/{room.id}/join", json={"nickname": "a", "pin": "0000"})
    assert client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.password}).status_code == 200


def test_pin_is_not_a_host_password(client, room):
    r = client.post(f"/meetings/{room.id}/host-login", json={"host_password": room.pin})
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
    assert "access_token" not in r.text
    pub = client.get(f"/meetings/{room.id}/public").json()
    assert pub["can_join"] is False and pub["can_request_join"] is True

    advance_to_recommended(session_factory, room)
    r = room.join("더늦은사람")
    assert r.status_code == 409 and r.json()["error"]["code"] == "JOIN_CLOSED"


def test_wrong_pin_after_close_reveals_nothing_extra(client, room):
    room.add("민수")
    room.post("/close")
    r = client.post(f"/meetings/{room.id}/join", json={"nickname": "x", "pin": "0000"})
    assert r.status_code == 401


# ---------------------------------------------------------------- 대시보드
def test_dashboard_next_actions_through_input_stage(client, room, db):
    p = room.add("민수")
    assert room.get().json()["next_action"]["code"] == "close_recruiting"
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
    for secret in (room.pin, room.password, room.host_token, p["token"], "$2b$", "token_hash", "pin_hash"):
        assert secret not in text
    d = room.get(headers=p["h"]).json()
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
