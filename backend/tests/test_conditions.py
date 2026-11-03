"""조건 입력(초안/제출/재제출) · 추천 실행/조회 · 역 검색. 계산은 B의 app.core 를 그대로 사용한다."""
from sqlalchemy import select

from app import models
from tests.conftest import conditions, new_room, run_pipeline


def put_draft(room, headers, body):
    return room.client.put(f"/meetings/{room.id}/conditions/me/draft", json=body, headers=headers)


def submit(room, headers, body=None):
    kw = {"json": body} if body is not None else {}
    return room.client.post(f"/meetings/{room.id}/conditions/me/submit", headers=headers, **kw)


def input_room(client, names=("민수", "지은")):
    room = new_room(client)
    people = [room.add(n) for n in names]
    assert room.post("/close").status_code == 200
    return room, people


# ---------------------------------------------------------------- 역 검색
def test_station_search(client):
    r = client.get("/stations", params={"q": "쌍문"})
    assert r.status_code == 200
    assert r.json()["stations"][0]["name"] == "쌍문"
    assert {"name", "lines", "lat", "lng"} <= set(r.json()["stations"][0])
    assert client.get("/stations", params={"q": "신설동역"}).json()["stations"][0]["name"] == "신설동"  # '역' 접미사 허용
    assert client.get("/stations", params={"q": "없는역xyz"}).json() == {"stations": []}


def test_station_search_input_limits(client):
    assert client.get("/stations").status_code == 422
    assert client.get("/stations", params={"q": ""}).status_code == 422
    assert client.get("/stations", params={"q": "가" * 21}).status_code == 422
    assert client.get("/stations", params={"q": "신", "limit": 500}).status_code == 422
    assert len(client.get("/stations", params={"q": "신", "limit": 3}).json()["stations"]) <= 3


# ---------------------------------------------------------------- 초안 / 제출
def test_draft_save_and_read_back(client):
    room, (a, _) = input_room(client)
    r = put_draft(room, a["h"], {"default_station": "신촌"})  # 임시저장은 있는 것만 검사
    assert r.status_code == 200 and r.json()["status"] == "draft"
    got = client.get(f"/meetings/{room.id}/conditions/me", headers=a["h"]).json()
    assert got["status"] == "draft" and got["conditions"]["default_station"] == "신촌"
    assert room.get(headers=a["h"]).json()["participants"][1]["input_status"] == "draft"


def test_no_conditions_yet(client):
    room, (a, _) = input_room(client)
    assert client.get(f"/meetings/{room.id}/conditions/me", headers=a["h"]).json() == {"status": "none", "conditions": None}


def test_submit_requires_complete_conditions_and_reports_field_errors(client):
    room, (a, _) = input_room(client)
    r = submit(room, a["h"], {"default_station": "신촌"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONDITIONS_INVALID"
    codes = {e["code"] for e in r.json()["error"]["errors"]}
    assert "NO_AVAILABILITY" in codes
    assert all("field" in e for e in r.json()["error"]["errors"])
    # 실패한 제출은 상태를 바꾸지 않는다
    assert client.get(f"/meetings/{room.id}/conditions/me", headers=a["h"]).json()["status"] == "none"


def test_validation_errors_from_fairness(client):
    room, (a, _) = input_room(client)
    d0 = room.date0
    cases = {
        "STATION_NOT_FOUND": conditions("없는역", d0),
        "DATE_OUT_OF_RANGE": {"availability": {"2000-01-01": [13]}, "default_station": "쌍문"},
        "INVALID_CONSTRAINT": conditions("쌍문", d0, constraints={"max_transfers": {"value": -1, "level": "required"}}),
    }
    for code, body in cases.items():
        r = submit(room, a["h"], body)
        assert r.status_code == 422, code
        assert code in {e["code"] for e in r.json()["error"]["errors"]}, (code, r.json())


def test_unknown_and_oversized_fields_rejected(client):
    room, (a, _) = input_room(client)
    assert put_draft(room, a["h"], {**conditions("쌍문", room.date0), "is_host": True}).status_code == 422
    assert put_draft(room, a["h"], {"availability": {"2026-01-01": ["13"]}}).status_code == 422  # 시간은 정수
    big = {f"2026-01-{i:02d}": [13] for i in range(1, 29)} | {f"2026-02-{i:02d}": [13] for i in range(1, 29)}
    big |= {f"2026-03-{i:02d}": [13] for i in range(1, 10)}
    assert len(big) > 62 and put_draft(room, a["h"], {"availability": big}).status_code == 422


def test_submit_uses_saved_draft_when_body_omitted(client):
    room, (a, _) = input_room(client)
    r = submit(room, a["h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_DRAFT"

    put_draft(room, a["h"], conditions("신촌", room.date0))
    r = submit(room, a["h"])
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    assert room.get(headers=a["h"]).json()["participants"][1]["input_status"] == "submitted"


def test_resubmission_replaces_conditions(client):
    room, (a, _) = input_room(client)
    submit(room, a["h"], conditions("신촌", room.date0))
    r = submit(room, a["h"], conditions("강남", room.date0, hours=(10, 11)))
    got = client.get(f"/meetings/{room.id}/conditions/me", headers=a["h"]).json()
    assert r.status_code == 200 and got["conditions"]["default_station"] == "강남"
    assert got["conditions"]["availability"][room.date0] == [10, 11]


def test_station_names_are_normalized(client):
    room, (a, _) = input_room(client)
    submit(room, a["h"], conditions("신설동역", room.date0))
    assert client.get(f"/meetings/{room.id}/conditions/me", headers=a["h"]).json()["conditions"]["default_station"] == "신설동"


def test_editing_after_submit_requires_resubmit(client):
    room, (a, b) = input_room(client)
    room.submit(room.host, "쌍문")
    room.submit(a["h"], "강남")
    room.submit(b["h"], "신촌")
    put_draft(room, a["h"], conditions("잠실", room.date0))  # 제출 후 수정 -> 초안으로 되돌아감
    r = room.post("/recommendations")
    assert r.status_code == 409 and r.json()["error"]["pending_nicknames"] == ["민수"]
    submit(room, a["h"])
    assert room.post("/recommendations").status_code == 200


def test_conditions_locked_outside_input_stage(client, session_factory):
    room = new_room(client)
    p = room.add("민수")
    assert put_draft(room, p["h"], conditions("신촌", room.date0)).status_code == 409  # 모집 중
    room.post("/close")
    run_pipeline(room, [p])
    r = submit(room, p["h"], conditions("강남", room.date0))
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STAGE"  # 추천 후에는 잠김


def test_conditions_require_auth_and_are_private(client):
    room, (a, b) = input_room(client)
    submit(room, a["h"], conditions("신촌", room.date0))
    assert client.get(f"/meetings/{room.id}/conditions/me").status_code == 401
    assert client.put(f"/meetings/{room.id}/conditions/me/draft", json={}).status_code == 401
    # 다른 참여자의 토큰으로는 자기 조건만 보인다
    assert client.get(f"/meetings/{room.id}/conditions/me", headers=b["h"]).json()["status"] == "none"
    other = new_room(client)
    assert client.get(f"/meetings/{room.id}/conditions/me", headers=other.host).status_code == 401
    # 다른 사람 조건을 읽는 경로가 없다
    assert client.get(f"/meetings/{room.id}/conditions/{a['id']}", headers=b["h"]).status_code == 404


def test_other_participants_conditions_never_appear_in_dashboard(client):
    room, (a, b) = input_room(client)
    submit(room, a["h"], conditions("신촌", room.date0))
    text = room.get(headers=b["h"]).text
    assert "신촌" not in text and "availability" not in text and "default_station" not in text


# ---------------------------------------------------------------- 추천 실행
def test_recommendation_is_host_only(client):
    room, (a, _) = input_room(client)
    r = client.post(f"/meetings/{room.id}/recommendations", headers=a["h"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "HOST_ONLY"
    assert client.post(f"/meetings/{room.id}/recommendations").status_code == 401


def test_recommendation_needs_everyone_submitted(client):
    room, (a, b) = input_room(client)
    room.submit(room.host, "쌍문")
    submit(room, a["h"], conditions("강남", room.date0))
    put_draft(room, b["h"], conditions("신촌", room.date0))  # 초안만 저장
    r = room.post("/recommendations")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONDITIONS_INCOMPLETE"
    assert r.json()["error"]["pending_nicknames"] == ["지은"]
    assert room.get().json()["meeting"]["stage"] == "input"  # 단계 불변


def test_recommendation_success_moves_stage_and_everyone_can_read(client):
    room, people = input_room(client)
    run_pipeline(room, people)
    assert room.get().json()["meeting"]["stage"] == "recommended"
    for who in [room.host] + [p["h"] for p in people]:
        v = room.get("/recommendations", headers=who).json()
        assert v["status"] == "ok" and v["stage"] == "recommended" and v["best"] == room.cands[0]
        c = v["candidates"][0]
        assert {"rank", "candidate_id", "date", "start", "end", "station", "max_travel_min", "accessibility", "my_route"} <= set(c)
        assert c["rank"] == 1 and c["my_route"]["minutes"] >= 0


def test_recommendation_shows_each_person_only_their_own_route(client):
    room, (a, b) = input_room(client)
    run_pipeline(room, [a, b])
    origins = {}
    for name, who in (("host", room.host), ("a", a["h"]), ("b", b["h"])):
        v = room.get("/recommendations", headers=who).json()
        assert "legs" not in str(v)  # 원본 결과(모든 참여자의 경로)는 응답에 없다
        origins[name] = {c["my_route"]["origin"] for c in v["candidates"]}
    assert origins == {"host": {"쌍문"}, "a": {"강남"}, "b": {"신촌"}}


def test_recommendation_rerun_in_recommended_stage(client):
    room, people = input_room(client)
    run_pipeline(room, people)
    first = list(room.cands)
    again = room.post("/recommendations")
    assert again.status_code == 200 and [c["candidate_id"] for c in again.json()["candidates"]] == first


def test_recommendation_not_ready_before_run(client):
    room, (a, _) = input_room(client)
    v = room.get("/recommendations", headers=a["h"]).json()
    assert v["status"] == "not_ready" and v["candidates"] == [] and v["stage"] == "input"


def test_no_candidate_keeps_stage_and_explains(client):
    """모두가 가능한 시간이 겹치지 않으면 후보가 없다 -> 단계는 그대로, 사유를 보여 주고 조건을 고쳐 재실행."""
    room2, (a2, b2) = input_room(client)
    room2.submit(room2.host, "쌍문", hours=(13, 14))
    submit(room2, a2["h"], conditions("강남", room2.date0, hours=(3, 4)))
    submit(room2, b2["h"], conditions("신촌", room2.date0, hours=(22, 23)))
    r = room2.post("/recommendations")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "no_candidate" and body["candidates"] == []
    assert body["reasons"], "후보가 없는 사유가 있어야 한다"
    assert room2.get().json()["meeting"]["stage"] == "input"
    assert room2.post("/proposal", {"candidate_id": "c_20990101_1500_창동"}).status_code == 409

    # 조건을 고치면 다시 실행되어 추천 단계로 넘어간다
    submit(room2, a2["h"], conditions("강남", room2.date0, hours=(13, 14)))
    submit(room2, b2["h"], conditions("신촌", room2.date0, hours=(13, 14)))
    ok = room2.post("/recommendations").json()
    assert ok["status"] == "ok" and room2.get().json()["meeting"]["stage"] == "recommended"


def test_excluded_or_left_people_are_not_required_for_recommendation(client):
    room, (a, b) = input_room(client)
    room.submit(room.host, "쌍문")
    submit(room, a["h"], conditions("강남", room.date0))
    assert room.post("/recommendations").status_code == 409  # 지은 미제출
    room.post(f"/participants/{b['id']}/exclude")
    assert room.post("/recommendations").status_code == 200


def test_result_deleted_with_meeting_and_conditions_cascade(client, db):
    room, people = input_room(client)
    run_pipeline(room, people)
    assert db.scalar(select(models.RecommendationResult)) is not None
    assert len(list(db.scalars(select(models.Condition)))) == 3
    assert client.delete(f"/meetings/{room.id}", headers=room.host).status_code == 204
    db.expire_all()
    assert db.scalar(select(models.RecommendationResult)) is None
    assert list(db.scalars(select(models.Condition))) == []


def test_stored_result_is_not_exposed_by_any_endpoint(client):
    room, (a, b) = input_room(client)
    run_pipeline(room, [a, b])
    for who in (room.host, a["h"], b["h"]):
        for path in ("", "/recommendations", "/conditions/me"):
            assert "legs" not in room.get(path, headers=who).text
