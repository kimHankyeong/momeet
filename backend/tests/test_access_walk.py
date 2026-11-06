"""출발 위치(default_origin) → 출발역 도보: API 수용, 주소 변환, 티맵/추정, 재사용, 추천 반영.
테스트는 실제 티맵을 호출하지 않는다 (conftest가 키를 비우고, 호출은 monkeypatch로 대체)."""
import pytest

from app.core import subway
from app.core.timeslot import generate_candidates
from app.integrations import tmap
from tests.conftest import conditions, new_room


def put_draft(room, headers, body):
    return room.client.put(f"/meetings/{room.id}/conditions/me/draft", json=body, headers=headers)


def my_data(room, headers) -> dict:
    return room.client.get(f"/meetings/{room.id}/conditions/me", headers=headers).json()["conditions"]


def near(station: str, d_lat: float = 0.009) -> dict:
    """역에서 위도로 약 1km 떨어진 위치"""
    st = subway.get_station(station)
    return {"lat": round(st["lat"] + d_lat, 6), "lng": st["lng"]}


@pytest.fixture()
def one(client):
    room = new_room(client)
    me = room.add("민수")
    assert room.post("/close").status_code == 200
    return room, me


@pytest.fixture()
def fake_tmap(monkeypatch):
    calls = {"walk": 0, "geocode": 0}

    def walk(*a):
        calls["walk"] += 1
        return 800, 12

    def geocode(addr):
        calls["geocode"] += 1
        return 37.6514, 127.0459

    monkeypatch.setattr(tmap, "configured", lambda: True)
    monkeypatch.setattr(tmap, "walk", walk)
    monkeypatch.setattr(tmap, "geocode", geocode)
    return calls


# ---------------------------------------------------------------- API가 default_origin을 받는다
def test_default_origin_accepted_and_rounded(one):
    room, me = one
    r = put_draft(room, me["h"], {**conditions("쌍문", room.date0), "default_origin": {"lat": 37.65149, "lng": 127.04591}})
    assert r.status_code == 200, r.text
    assert my_data(room, me["h"])["default_origin"] == {"lat": 37.651, "lng": 127.046}  # B의 정밀도(소수 3자리)


def test_bad_origin_rejected(one):
    room, me = one
    for origin in [{"lat": 10, "lng": 10}, {"lat": 37.6}, {"lat": "37.6", "lng": 127.0}, near("쌍문", 0.05)]:
        r = put_draft(room, me["h"], {**conditions("쌍문", room.date0), "default_origin": origin})
        assert r.status_code == 422, origin
        assert {e["code"] for e in r.json()["error"]["errors"]} & {"INVALID_ORIGIN", "ORIGIN_TOO_FAR"}, origin


# ---------------------------------------------------------------- 저장 · 추정
def test_origin_without_tmap_key_uses_estimate(one):
    room, me = one
    put_draft(room, me["h"], {**conditions("쌍문", room.date0), "default_origin": near("쌍문")})
    acc = my_data(room, me["h"])["default_access"]
    assert acc["station"] == "쌍문" and acc["source"] == "estimate"
    walk_m, minutes = subway.access_walk(*[my_data(room, me["h"])["default_origin"][k] for k in ("lat", "lng")], "쌍문")
    assert (acc["walk_m"], acc["minutes"]) == (walk_m, minutes)  # B의 추정과 같다


def test_no_origin_means_no_access(one):
    room, me = one
    put_draft(room, me["h"], conditions("쌍문", room.date0))
    data = my_data(room, me["h"])
    assert "default_access" not in data and "default_origin" not in data


# ---------------------------------------------------------------- 티맵 사용 · 재사용 · 대체
def test_tmap_result_used_and_reused(one, fake_tmap):
    room, me = one
    body = {**conditions("쌍문", room.date0), "default_origin": near("쌍문")}
    put_draft(room, me["h"], body)
    assert my_data(room, me["h"])["default_access"] == {"station": "쌍문", "walk_m": 800, "minutes": 12, "source": "tmap"}
    assert fake_tmap["walk"] == 1
    put_draft(room, me["h"], body)  # 같은 위치·역은 다시 부르지 않는다
    assert room.client.post(f"/meetings/{room.id}/conditions/me/submit", headers=me["h"]).status_code == 200
    assert fake_tmap["walk"] == 1
    r = put_draft(room, me["h"], {**body, "default_station": "창동"})  # 역을 바꾸면 다시 구한다
    assert r.status_code == 200, r.text
    assert fake_tmap["walk"] == 2 and my_data(room, me["h"])["default_access"]["station"] == "창동"


def test_address_is_geocoded_and_not_stored(one, fake_tmap):
    room, me = one
    put_draft(room, me["h"], {**conditions("쌍문", room.date0), "default_origin": {"address": "서울 도봉구 노해로 342"}})
    data = my_data(room, me["h"])
    assert data["default_origin"] == {"lat": 37.651, "lng": 127.046}
    assert "address" not in str(data)  # 주소는 저장하지 않는다
    put_draft(room, me["h"], {**conditions("쌍문", room.date0), "default_origin": data["default_origin"]})
    assert fake_tmap["geocode"] == 1  # 좌표를 주면 변환하지 않는다


def test_address_not_found_and_geocode_outage(one, monkeypatch):
    room, me = one
    body = {**conditions("쌍문", room.date0), "default_origin": {"address": "없는주소"}}
    monkeypatch.setattr(tmap, "configured", lambda: True)

    def not_found(a):
        raise LookupError(a)

    monkeypatch.setattr(tmap, "geocode", not_found)
    r = put_draft(room, me["h"], body)
    assert r.status_code == 422 and r.json()["error"]["errors"][0]["code"] == "INVALID_ORIGIN"

    def down(a):
        raise tmap.TmapError("티맵 응답 429 호출 한도 초과")

    monkeypatch.setattr(tmap, "geocode", down)
    r = put_draft(room, me["h"], body)
    assert r.status_code == 503 and r.json()["error"]["code"] == "GEOCODE_UNAVAILABLE"
    assert "429" not in r.text  # 원인 상세는 로그에만
    long_addr = {**conditions("쌍문", room.date0), "default_origin": {"address": "가" * 101}}
    assert put_draft(room, me["h"], long_addr).status_code == 422


def test_walk_failure_falls_back_and_stops_calling(one, monkeypatch):
    room, me = one
    calls = []

    def down(*a):
        calls.append(1)
        raise tmap.TmapError("티맵 연결 실패")

    monkeypatch.setattr(tmap, "configured", lambda: True)
    monkeypatch.setattr(tmap, "walk", down)
    d0 = room.date0
    ex = [{"date": d0, "hours": [h], "station": s, "origin": near(s)} for h, s in zip([9, 10, 11], ["강남", "신촌", "잠실"])]
    body = {**conditions("쌍문", d0, hours=[9, 10, 11, 13]), "default_origin": near("쌍문"), "exception_stations": ex}
    assert put_draft(room, me["h"], body).status_code == 200
    assert len(calls) == 1  # 첫 실패 후에는 부르지 않고 기다리지도 않는다
    data = my_data(room, me["h"])
    assert data["default_access"]["source"] == "estimate"
    assert all(e["access"]["source"] == "estimate" for e in data["exception_stations"])


def test_lookup_cap_per_save(one, fake_tmap):
    room, me = one
    d0 = room.date0
    hours = list(range(24))
    stations = ["강남", "신촌", "잠실", "수유", "건대입구", "홍대입구", "노원", "왕십리", "사당", "종로3가", "서울역", "합정"]
    ex = [{"date": d0, "hours": [h], "station": s, "origin": near(s)} for h, s in zip(hours, stations)]
    assert put_draft(room, me["h"], {**conditions("쌍문", d0, hours=hours), "exception_stations": ex}).status_code == 200
    assert fake_tmap["walk"] == 10  # 상한. 나머지 2건은 추정
    sources = [e["access"]["source"] for e in my_data(room, me["h"])["exception_stations"]]
    assert sources.count("tmap") == 10 and sources.count("estimate") == 2


# ---------------------------------------------------------------- 추천에 반영
HOME = {"lat": 37.651, "lng": 127.046}


def _all(default_access=None):
    d = "2026-11-07"
    p1 = {"id": "1", "availability": {d: [13, 14, 15]}, "default_station": "쌍문", "default_origin": HOME,
          "exception_stations": [], "constraints": {}}
    if default_access:
        p1["default_access"] = default_access
    p2 = {"id": "2", "availability": {d: [13, 14, 15]}, "default_station": "강남",
          "exception_stations": [], "constraints": {}}
    cands, _ = generate_candidates([p1, p2], [d], stations=["쌍문", "수유", "강남", "신촌", "잠실"])
    return {c.candidate_id: c.to_dict() for c in cands}


def test_stored_access_replaces_estimate():
    est = _all()
    tm = _all({"station": "쌍문", "walk_m": 900, "minutes": 15, "source": "tmap"})
    common = set(est) & set(tm)
    assert common
    for cid in common:
        e1, t1 = est[cid]["legs"]["1"], tm[cid]["legs"]["1"]
        assert (e1["access_source"], t1["access_source"]) == ("estimate", "tmap")
        assert (t1["access_walk_m"], t1["access_min"]) == (900, 15)
        # 총 이동시간·총 도보는 B와 같은 규칙: 도보 시간/거리가 그대로 더해진다
        assert t1["minutes"] - e1["minutes"] == 15 - e1["access_min"]
        assert t1["walk_m"] - e1["walk_m"] == 900 - e1["access_walk_m"]
        assert tm[cid]["legs"]["2"]["minutes"] == est[cid]["legs"]["2"]["minutes"]  # 위치 없는 사람은 그대로
        h, m = map(int, t1["depart_at"].split(":"))
        sh, sm = map(int, tm[cid]["start"].split(":"))
        assert sh * 60 + sm - (h * 60 + m) == t1["minutes"]  # 출발 위치에서 나서는 시각


def test_stale_stored_access_for_other_station_is_ignored():
    est = _all()
    stale = _all({"station": "수유", "walk_m": 900, "minutes": 15, "source": "tmap"})
    assert all(c["legs"]["1"] == est[cid]["legs"]["1"] for cid, c in stale.items())  # 추정으로 대체


def test_route_view_matches_front_contract(client):
    room = new_room(client)
    me = room.add("민수")
    assert room.post("/close").status_code == 200
    room.submit(room.host, "쌍문", default_origin=near("쌍문"))
    room.submit(me["h"], "강남")
    body = room.recommend()
    mine = body["candidates"][0]["my_route"]
    assert set(mine["access"]) == {"walk_m", "minutes", "source"} and mine["access"]["source"] == "estimate"
    assert mine["walk_m"] >= mine["access"]["walk_m"] > 0 and mine["walk_min"] > 0  # walk_m은 도보 합계
    theirs = room.client.get(f"/meetings/{room.id}/recommendations", headers=me["h"]).json()["candidates"][0]["my_route"]
    assert theirs["access"] is None  # 본인 값만 보인다
    assert "lat" not in str(mine) and "default_origin" not in str(body)  # 위치 좌표는 응답에 없다
