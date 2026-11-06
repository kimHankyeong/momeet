"""단계 전이 · 제안 · 동의 · 확정 · 참여 승인 · 제외. 후보는 B의 추천 로직이 만든 실제 결과를 쓴다."""
import pytest
from sqlalchemy import select

from app import models
from app.models import Meeting
from app.services import hooks
from tests.conftest import advance_to_recommended, auth, new_room, run_pipeline

FAKE_BUT_VALID_ID = "c_20990101_1500_창동"  # 형식은 맞지만 추천 결과에 없는 후보


def make_ready(client, session_factory, names=("민수", "지은"), **room_over):
    """모집 -> 마감 -> 조건 제출 -> 추천 실행 까지 진행한 약속방."""
    room = new_room(client, **room_over)
    people = [room.add(n) for n in names]
    assert room.post("/close").status_code == 200
    run_pipeline(room, people)
    return room, people


def propose(room, n=0):
    cid = room.cands[n] if room.cands else FAKE_BUT_VALID_ID
    return room.post("/proposal", {"candidate_id": cid})


def respond(room, who, response):
    return room.post("/proposal/response", {"response": response}, headers=who["h"] if "h" in who else who)


def confirm(room, who=None):
    return room.post("/proposal/confirm", {}, **({"headers": who["h"]} if who else {}))


# ---------------------------------------------------------------- 단계 머신
def test_stage_order_is_enforced(client, session_factory, db):
    room = new_room(client)
    room.add("민수")

    # recruiting 에서는 제안/응답/추천 모두 불가
    assert propose(room).status_code == 409
    assert room.post("/proposal/response", {"response": "accept"}).status_code == 409
    assert room.post("/recommendations").status_code == 409
    with pytest.raises(Exception) as e:
        hooks.mark_recommended(db, db.get(Meeting, room.id))
    assert getattr(e.value, "code", "") == "INVALID_STAGE"

    room.post("/close")
    assert propose(room).status_code == 409  # input 단계 (아직 추천 전)

    advance_to_recommended(session_factory, room)
    assert room.get().json()["meeting"]["stage"] == "recommended"
    assert room.post("/close").status_code == 409  # 거꾸로 갈 수 없다
    assert room.get().json()["next_action"]["code"] == "propose_candidate"


def test_recommendation_can_be_rerun_but_not_after_proposal(client, session_factory, db):
    room, _ = make_ready(client, session_factory)
    assert room.post("/recommendations").status_code == 200  # recommended 에서 재실행 가능
    assert propose(room).status_code == 201
    assert room.post("/recommendations").status_code == 409  # 제안 이후에는 불가
    db.expire_all()
    with pytest.raises(Exception) as e:
        hooks.mark_recommended(db, db.get(Meeting, room.id))
    assert getattr(e.value, "code", "") == "INVALID_STAGE"


def test_confirmed_view_requires_confirmation(client, session_factory):
    room, _ = make_ready(client, session_factory)
    r = room.get("/confirmed")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_CONFIRMED"


# ---------------------------------------------------------------- 제안
def test_only_host_can_propose_and_candidate_must_come_from_recommendation(client, session_factory):
    room, people = make_ready(client, session_factory)
    assert room.post("/proposal", {"candidate_id": room.cands[0]}, headers=people[0]["h"]).status_code == 403
    assert room.post("/proposal", {"candidate_id": "bad id!"}).status_code == 422  # 형식 오류
    assert room.post("/proposal", {"candidate_id": "c1"}).status_code == 422

    r = room.post("/proposal", {"candidate_id": FAKE_BUT_VALID_ID})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_CANDIDATE"
    assert room.get().json()["meeting"]["stage"] == "recommended"  # 실패하면 단계 불변

    r = propose(room, 1)
    assert r.status_code == 201
    body = r.json()
    assert body["candidate_id"] == room.cands[1] and body["version"] == 1 and body["status"] == "pending"
    assert body["candidate"]["station"]["name"] in room.cands[1]
    assert body["my_route"]["origin"] == "쌍문"  # 호스트의 출발역
    assert room.get().json()["meeting"]["stage"] == "proposed"


def test_dashboard_proposal_shows_only_my_own_route(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    mine = {}
    for name, who in (("host", room.host), ("a", a["h"]), ("b", b["h"])):
        d = room.get(headers=who).json()
        mine[name] = d["proposal"]["my_route"]["origin"]
        assert "legs" not in str(d)  # 다른 사람의 이동 정보 원본이 새지 않는다
    assert len(set(mine.values())) == 3  # 사람마다 자기 출발역


# ---------------------------------------------------------------- 동의 / 확정
def test_host_confirms_after_everyone_accepts(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room, 1)

    assert respond(room, a, "accept").json()["status"] == "pending"
    assert respond(room, b, "accept").json()["status"] == "pending"
    assert respond(room, room.host, "accept").json()["status"] == "pending"  # 전원 동의해도 자동 확정 안 함
    assert room.get().json()["meeting"]["stage"] == "proposed"
    assert room.get().json()["next_action"]["code"] == "confirm_proposal"
    assert room.get(headers=a["h"]).json()["next_action"]["code"] == "wait_confirm"

    assert confirm(room, a).status_code == 403  # 참여자는 확정할 수 없다
    r = confirm(room)
    assert r.status_code == 200
    assert r.json()["status"] == "accepted" and r.json()["stage"] == "confirmed"

    d = room.get(headers=a["h"]).json()
    assert d["meeting"]["stage"] == "confirmed" and d["next_action"]["code"] == "view_confirmed"
    c = room.get("/confirmed", headers=a["h"]).json()
    assert c["candidate_id"] == room.cands[1]
    assert c["candidate"]["station"]["name"] and c["my_route"]["origin"] == "강남"
    assert sorted(p["nickname"] for p in c["participants"]) == ["민수", "지은", "호스트"]

    # 확정 이후에는 더 응답하거나 제안·확정할 수 없다
    assert respond(room, a, "reject").status_code == 409
    assert propose(room, 0).status_code == 409
    assert confirm(room).status_code == 409


def test_host_can_confirm_without_every_response(client, session_factory):
    """응답하지 않은 사람이 있어도 호스트가 확정할 수 있다. 확정한 호스트는 동의로 기록된다."""
    room, (a, b) = make_ready(client, session_factory)
    assert confirm(room).json()["error"]["code"] == "INVALID_STAGE"  # 제안 전
    propose(room)
    respond(room, a, "accept")
    assert room.get().json()["next_action"]["code"] == "respond_to_proposal"
    r = confirm(room)
    assert r.status_code == 200 and r.json()["stage"] == "confirmed"
    by = {p["nickname"]: p["response"] for p in room.get().json()["participants"]}
    assert by == {"호스트": "accept", "민수": "accept", "지은": "pending"}


def test_host_cannot_confirm_with_rejection(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    respond(room, b, "reject")
    r = confirm(room)
    assert r.status_code == 409 and r.json()["error"]["code"] == "HAS_REJECTION"
    assert room.get().json()["meeting"]["stage"] == "proposed"


def test_rejection_keeps_proposal_open_until_everyone_responded(client, session_factory):
    """시안: 거절해도 제안은 열려 있고, 전원이 응답했는데 거절이 있으면 '확정되지 않았어요'(재조율)."""
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    r = respond(room, b, "reject")
    assert r.json()["status"] == "pending" and r.json()["stage"] == "proposed"

    d = room.get().json()["proposal"]  # 호스트가 아직 응답하지 않음
    assert (d["responded_count"], d["rejected_count"], d["needs_replan"]) == (2, 1, False)
    assert room.get().json()["next_action"]["code"] == "respond_to_proposal"

    respond(room, room.host, "accept")  # 전원 응답 + 거절 1 -> 재조율
    d = room.get().json()["proposal"]
    assert (d["responded_count"], d["accepted_count"], d["rejected_count"], d["needs_replan"]) == (3, 2, 1, True)
    assert room.get().json()["next_action"]["code"] == "repropose"
    assert room.get(headers=a["h"]).json()["next_action"]["code"] == "wait_reproposal"
    assert room.get().json()["meeting"]["stage"] == "proposed"  # 확정되지 않음
    assert room.get("/confirmed").status_code == 409


def test_rejecter_can_change_mind_and_confirm(client, session_factory):
    """시안: '거절 완료 / 수정하기' -> 거절한 사람이 동의로 바꾸면 전원 동의로 확정된다."""
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    respond(room, room.host, "accept")
    respond(room, b, "reject")
    assert room.get().json()["proposal"]["needs_replan"] is True

    assert respond(room, b, "accept").json()["status"] == "pending"
    assert room.get().json()["proposal"]["needs_replan"] is False
    r = confirm(room)
    assert r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["stage"] == "confirmed"
    d = room.get().json()
    assert d["meeting"]["stage"] == "confirmed" and d["proposal"]["needs_replan"] is False
    assert room.get("/confirmed", headers=b["h"]).json()["candidate_id"] == room.cands[0]


def test_accepter_can_change_to_reject(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    respond(room, a, "reject")  # 동의 -> 거절 수정
    d = room.get().json()["proposal"]
    assert (d["accepted_count"], d["rejected_count"]) == (0, 1)
    assert respond(room, b, "accept").json()["status"] == "pending"


def test_reproposal_resets_responses(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room, 0)
    respond(room, a, "accept")
    respond(room, b, "reject")

    r = propose(room, 1)
    assert r.status_code == 201 and r.json()["version"] == 2
    d = room.get().json()
    assert d["proposal"]["candidate_id"] == room.cands[1] and d["proposal"]["accepted_count"] == 0
    assert {p["response"] for p in d["participants"]} == {"pending"}
    assert d["next_action"]["code"] == "respond_to_proposal"

    for who in (a, b, room.host):
        respond(room, who, "accept")
    confirm(room)
    assert room.get().json()["meeting"]["stage"] == "confirmed"
    assert room.get("/confirmed").json()["candidate_id"] == room.cands[1]


def test_host_can_replace_pending_proposal(client, session_factory, db):
    room, (a, _) = make_ready(client, session_factory)
    propose(room, 0)
    respond(room, a, "accept")
    assert propose(room, 1).json()["version"] == 2
    statuses = [p.status for p in db.scalars(select(models.Proposal).order_by(models.Proposal.version))]
    assert statuses == ["superseded", "pending"]
    # 이전 제안에 대한 동의는 새 제안에 이월되지 않는다
    assert room.get().json()["proposal"]["accepted_count"] == 0


def test_participant_response_is_idempotent_while_pending(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    respond(room, a, "accept")  # 같은 응답 반복은 문제 없음 (중복 행 없음)
    assert room.get().json()["proposal"]["accepted_count"] == 1

    respond(room, a, "reject")  # 진행 중에는 바꿀 수 있다 (거절해도 제안은 pending)
    assert room.get().json()["proposal"]["status"] == "pending"


def test_dashboard_shows_responses_but_no_reasons(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    d = room.get(headers=b["h"]).json()
    by = {p["nickname"]: p["response"] for p in d["participants"]}
    assert by == {"호스트": "pending", "민수": "accept", "지은": "pending"}
    assert d["next_action"]["code"] == "respond_to_proposal"
    assert room.get(headers=a["h"]).json()["next_action"]["code"] == "wait_responses"


def test_invalid_response_value_rejected(client, session_factory):
    room, (a, _) = make_ready(client, session_factory)
    propose(room)
    assert room.post("/proposal/response", {"response": "maybe"}, headers=a["h"]).status_code == 422
    assert room.post("/proposal/response", {"response": "accept", "participant_id": 1}, headers=a["h"]).status_code == 422


# ---------------------------------------------------------------- 제외 / 나가기가 확정에 미치는 영향
def test_excluding_last_pending_person_lets_host_confirm(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    respond(room, room.host, "accept")
    r = room.post(f"/participants/{b['id']}/exclude")
    assert r.status_code == 200 and r.json()["status"] == "excluded"
    assert room.get().json()["meeting"]["stage"] == "proposed"  # 자동 확정 안 함
    assert room.get().json()["next_action"]["code"] == "confirm_proposal"
    confirm(room)
    assert room.get().json()["meeting"]["stage"] == "confirmed"
    assert [p["nickname"] for p in room.get("/confirmed").json()["participants"]] == ["호스트", "민수"]


def test_excluded_participant_loses_access(client, session_factory):
    room, (a, _) = make_ready(client, session_factory)
    room.post(f"/participants/{a['id']}/exclude")
    assert room.get(headers=a["h"]).status_code == 401
    assert a["id"] not in [p["id"] for p in room.get().json()["participants"]]


def test_cannot_exclude_host_or_stranger(client, session_factory):
    room, (a, _) = make_ready(client, session_factory)
    other = new_room(client)
    assert room.post(f"/participants/{room.host_id}/exclude").json()["error"]["code"] == "CANNOT_EXCLUDE_HOST"
    assert room.post(f"/participants/{other.host_id}/exclude").status_code == 404
    assert room.post("/participants/99999/exclude").status_code == 404
    assert room.post(f"/participants/{a['id']}/exclude", headers=a["h"]).status_code == 403


def test_leaving_lets_host_confirm(client, session_factory):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "accept")
    respond(room, room.host, "accept")
    assert client.delete(f"/meetings/{room.id}/me", headers=b["h"]).status_code == 204
    assert room.get().json()["next_action"]["code"] == "confirm_proposal"
    confirm(room)
    assert room.get().json()["meeting"]["stage"] == "confirmed"


def test_leaving_removes_my_response_and_conditions(client, session_factory, db):
    room, (a, b) = make_ready(client, session_factory)
    propose(room)
    respond(room, a, "reject")
    client.delete(f"/meetings/{room.id}/me", headers=a["h"])
    assert db.scalar(select(models.ProposalResponse).where(models.ProposalResponse.participant_id == a["id"])) is None
    assert db.scalar(select(models.Condition).where(models.Condition.participant_id == a["id"])) is None
    assert db.scalar(select(models.Condition).where(models.Condition.participant_id == b["id"])) is not None


# ---------------------------------------------------------------- 마감 후 참여 승인
def _late_request(client):
    room = new_room(client)
    room.add("민수")
    room.post("/close")
    r = room.join("늦은사람").json()
    return room, r


def test_join_request_approve_and_claim_once(client):
    room, req = _late_request(client)
    assert [x["nickname"] for x in room.get("/join-requests").json()["requests"]] == ["늦은사람"]
    assert room.get().json()["host"]["pending_join_requests"] == 1

    claim = lambda secret: client.post(  # noqa: E731
        f"/meetings/{room.id}/join-requests/{req['request_id']}/claim", json={"request_secret": secret}
    )
    assert claim(req["request_secret"]).json() == {"status": "pending"}

    assert room.post(f"/join-requests/{req['request_id']}/approve").json()["status"] == "approved"
    got = claim(req["request_secret"])
    assert got.status_code == 200 and got.json()["status"] == "approved"
    token = got.json()["access_token"]
    assert room.get(headers=auth(token)).json()["me"]["nickname"] == "늦은사람"
    assert room.get(headers=auth(token)).json()["next_action"]["code"] == "submit_conditions"

    again = claim(req["request_secret"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_CLAIMED"
    assert room.post(f"/join-requests/{req['request_id']}/reject").status_code == 409  # 이미 처리됨


def test_late_joiner_must_submit_before_recommendation(client):
    room, req = _late_request(client)
    room.post(f"/join-requests/{req['request_id']}/approve")
    room.submit(room.host, "쌍문")
    r = room.post("/recommendations")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONDITIONS_INCOMPLETE"
    assert set(r.json()["error"]["pending_nicknames"]) == {"민수", "늦은사람"}


def test_join_request_wrong_secret_looks_like_missing(client):
    room, req = _late_request(client)
    r = client.post(
        f"/meetings/{room.id}/join-requests/{req['request_id']}/claim", json={"request_secret": "x" * 20}
    )
    assert r.status_code == 404
    other = new_room(client)
    r = client.post(
        f"/meetings/{other.id}/join-requests/{req['request_id']}/claim", json={"request_secret": req["request_secret"]}
    )
    assert r.status_code == 404  # 다른 약속방에서는 같은 번호의 신청이 없다


def test_join_request_rejected_never_gets_token(client):
    room, req = _late_request(client)
    assert room.post(f"/join-requests/{req['request_id']}/reject").json()["status"] == "rejected"
    r = client.post(
        f"/meetings/{room.id}/join-requests/{req['request_id']}/claim", json={"request_secret": req["request_secret"]}
    )
    assert r.json() == {"status": "rejected"}


def test_join_request_approval_blocked_after_recommendation_and_when_full(client, session_factory):
    room, req = _late_request(client)
    advance_to_recommended(session_factory, room)
    r = room.post(f"/join-requests/{req['request_id']}/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STAGE"

    full = new_room(client, max_participants=3)
    full.add("a")
    full.post("/close")
    r1 = full.join("b").json()  # 정원(3) 중 2명 -> 신청 가능
    r2 = full.join("c").json()
    assert full.post(f"/join-requests/{r1['request_id']}/approve").status_code == 200
    r = full.post(f"/join-requests/{r2['request_id']}/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "MEETING_FULL"


def test_join_request_duplicate_nickname_gets_suffix(client):
    room = new_room(client)
    room.add("민수")
    room.post("/close")
    a = room.join("민수").json()
    b = room.join("민수").json()
    assert a["nickname"] == "민수(2)" and b["nickname"] == "민수(3)"


def test_participants_cannot_manage_join_requests(client):
    room, req = _late_request(client)
    room.post(f"/join-requests/{req['request_id']}/approve")
    got = client.post(
        f"/meetings/{room.id}/join-requests/{req['request_id']}/claim", json={"request_secret": req["request_secret"]}
    ).json()
    member = auth(got["access_token"])
    assert client.get(f"/meetings/{room.id}/join-requests", headers=member).status_code == 403
    assert client.get(f"/meetings/{room.id}/join-requests").status_code == 401
