"""
추천 알고리즘 테스트

실행 (backend 폴더에서):
    pip install pytest
    python -m pytest tests -q
"""

import json

from app.core import fairness
from app.core.fairness import (
    get_candidate, get_my_route, recommend, sort_key, validate_conditions, view_for,
)

DATES = ["2026-11-07", "2026-11-08"]


def person(pid, station, hours, date="2026-11-07", **constraints):
    return {
        "id": pid,
        "availability": {date: hours},
        "default_station": station,
        "exception_stations": [],
        "constraints": {k: {"value": v[0], "level": v[1]} for k, v in constraints.items()},
    }


def fake(minutes, preferred_met=0, station="A"):
    return {"max_minutes": max(minutes), "total_minutes": sum(minutes), "preferred_met": preferred_met,
            "date": "2026-11-07", "start": "15:00", "station": station}


# ------------------------------------------------------------------ 정렬 기준
def test_공평성_최대_이동시간이_짧은_곳이_먼저():
    a = fake([10, 20, 60], station="A")  # 총합 90, 최대 60
    b = fake([25, 30, 35], station="B")  # 총합 90, 최대 35
    assert sorted([a, b], key=sort_key)[0]["station"] == "B"


def test_최대가_같으면_선호_조건_많이_맞는_곳():
    a = fake([30, 30], preferred_met=0, station="A")
    b = fake([30, 30], preferred_met=2, station="B")
    assert sorted([a, b], key=sort_key)[0]["station"] == "B"


def test_최대_선호가_같으면_총_이동시간_짧은_곳():
    a = fake([30, 30, 30], station="A")
    b = fake([10, 20, 30], station="B")
    assert sorted([a, b], key=sort_key)[0]["station"] == "B"


# ------------------------------------------------------------------ 실제 데이터로 추천
def sample():
    return [
        person("p1", "쌍문", [13, 14, 15]),
        person("p2", "방화", [14, 15]),
        person("p3", "잠실", [13, 14, 15]),
    ]


def test_추천_결과_기본():
    r = recommend(sample(), DATES)
    assert r["status"] == "ok"
    assert r["best"] == r["candidates"][0]["candidate_id"]
    assert [c["rank"] for c in r["candidates"]] == list(range(1, len(r["candidates"]) + 1))
    # 정렬 순서 유지
    keys = [sort_key(c) for c in r["candidates"]]
    assert keys == sorted(keys)
    # 날짜별 최대 3개, 같은 날 같은 역 중복 없음
    for d in DATES:
        same_day = [c for c in r["candidates"] if c["date"] == d]
        assert len(same_day) <= 3
        assert len({c["station"] for c in same_day}) == len(same_day)
    # DB 저장용으로 JSON 변환 가능해야 함
    json.dumps(r, ensure_ascii=False)


def test_출발시각은_본인이_고른_시간_안():
    people = {p["id"]: p for p in sample()}
    r = recommend(sample(), DATES)
    for c in r["candidates"]:
        for pid, leg in c["legs"].items():
            assert int(leg["depart_at"][:2]) in people[pid]["availability"][c["date"]]


def test_필수_최대_이동시간_지킴():
    ps = sample()
    ps[1]["constraints"] = {"max_travel_min": {"value": 40, "level": "required"}}
    r = recommend(ps, DATES)
    assert all(c["legs"]["p2"]["minutes"] <= 40 for c in r["candidates"])


def test_엘리베이터_필수면_unknown_역_제외():
    ps = sample()
    ps[0]["constraints"] = {"needs_elevator": {"value": True, "level": "required"}}
    r = recommend(ps, DATES)
    assert r["candidates"]
    assert all(c["accessibility"] == "met" for c in r["candidates"])


def test_시간이_안_겹치면_후보_없음_사유():
    ps = [person("p1", "쌍문", [8]), person("p2", "방화", [20])]
    r = recommend(ps, ["2026-11-07"])
    assert r["status"] == "no_candidate"
    assert r["best"] is None
    assert r["reasons"][0]["code"] == "NO_COMMON_TIME"


def test_한_명이_날짜를_안_고르면_사유():
    ps = [person("p1", "쌍문", [14]), person("p2", "방화", [14], date="2026-11-08")]
    r = recommend(ps, DATES)
    assert r["status"] == "no_candidate"
    assert {x["code"] for x in r["reasons"]} == {"SOME_UNAVAILABLE"}
    assert "1명" in r["reasons"][0]["message"]


def test_한_명만_필수를_걸면_다른_사람이_와서_만남():
    ps = sample()
    ps[1]["constraints"] = {"max_travel_min": {"value": 5, "level": "required"}}
    r = recommend(ps, ["2026-11-07"])
    assert r["status"] == "ok"
    assert all(c["legs"]["p2"]["minutes"] <= 5 for c in r["candidates"])


def test_각자_필수는_되지만_동시에_안_되면_사유():
    ps = sample()[:2]  # 쌍문, 방화
    for p in ps:
        p["constraints"] = {"max_travel_min": {"value": 5, "level": "required"}}
    r = recommend(ps, ["2026-11-07"])
    assert r["status"] == "no_candidate"
    assert r["reasons"][0]["code"] == "REQUIRED_COMBINED"


def test_특정_필수_조건이_항상_막히면_인원수만_표시():
    # 모든 시간 가능 후보에서 p2의 최대 이동시간만 계속 실패한 상황
    fails = {"2026-11-07": [[("p2", "max_travel_min")], [("p2", "max_travel_min"), ("p1", "max_walk_m")]]}
    reasons = fairness._reasons(["2026-11-07"], [], fails, {})
    assert reasons[0]["code"] == "REQUIRED_UNMET"
    assert "최대 이동시간" in reasons[0]["message"] and "1명" in reasons[0]["message"]
    assert "p2" not in reasons[0]["message"]


# ------------------------------------------------------------------ 조회 · 제안 · 개인정보
def test_조회는_본인_경로만():
    r = recommend(sample(), DATES)
    v = view_for(r, "p1")
    for c in v["candidates"]:
        assert set(c) == {"rank", "candidate_id", "date", "start", "end", "station",
                          "max_travel_min", "accessibility", "my_route"}
        assert c["my_route"]["origin"] == "쌍문"
    text = json.dumps(v, ensure_ascii=False)
    assert "legs" not in text and "p2" not in text and "p3" not in text


def test_정수_id로_넘기고_JSON_저장_후에도_조회됨():
    ps = sample()
    for i, p in enumerate(ps, 1):
        p["id"] = i
    saved = json.loads(json.dumps(recommend(ps, DATES), ensure_ascii=False))  # DB 저장 → 다시 읽기
    assert view_for(saved, 1)["candidates"][0]["my_route"]["origin"] == "쌍문"
    assert get_my_route(saved, saved["best"], 2)["origin"] == "방화"


def test_추천_전이면_not_ready():
    assert view_for(None, "p1")["status"] == "not_ready"


def test_제안_검증_과_내_경로():
    r = recommend(sample(), DATES)
    cid = r["best"]
    assert get_candidate(r, cid)["candidate_id"] == cid
    assert get_candidate(r, "c_20261107_1500_없는역") is None
    route = get_my_route(r, cid, "p2")
    assert route["origin"] == "방화" and route["segments"]
    assert get_my_route(r, cid, "없는사람") is None


# ------------------------------------------------------------------ 조건 검증
def test_검증_정상_및_정리():
    data = {
        "availability": {"2026-11-07": [15, 14, 14]},
        "default_station": "신설동역",
        "exception_stations": [{"date": "2026-11-07", "hours": [14], "station": "이수"}],
        "constraints": {"max_travel_min": {"value": 60, "level": "required"},
                        "needs_elevator": {"value": False, "level": "preferred"}},
    }
    errors, clean = validate_conditions(data, DATES, final=True)
    assert errors == []
    assert clean["availability"]["2026-11-07"] == [14, 15]
    assert clean["default_station"] == "신설동"
    assert clean["exception_stations"][0]["station"] == "총신대입구"
    assert "needs_elevator" not in clean["constraints"]


def test_검증_역_이름_표기():
    # 서울역은 '역'을 떼고 와도 찾고, 같은 이름 다른 역은 노선을 붙인 이름으로 구분
    data = {
        "availability": {"2026-11-07": [14]},
        "default_station": "서울",
        "exception_stations": [{"date": "2026-11-07", "hours": [14], "station": "양평(경의중앙)"}],
    }
    errors, clean = validate_conditions(data, DATES, final=True)
    assert errors == []
    assert clean["default_station"] == "서울역"
    assert clean["exception_stations"][0]["station"] == "양평(경의중앙)"


def test_검증_에러_코드():
    data = {
        "availability": {"2026-12-25": [10]},
        "default_station": "서면",
        "constraints": {"max_walk_m": {"value": -1, "level": "required"}, "unknown": {"value": 1, "level": "required"}},
    }
    errors, _ = validate_conditions(data, DATES, final=True)
    codes = {e["code"] for e in errors}
    assert {"DATE_OUT_OF_RANGE", "NO_AVAILABILITY", "STATION_NOT_FOUND", "INVALID_CONSTRAINT"} <= codes


def test_임시저장은_빈_값_허용():
    errors, _ = validate_conditions({}, DATES, final=False)
    assert errors == []
    errors, _ = validate_conditions({}, DATES, final=True)
    assert {e["code"] for e in errors} == {"NO_AVAILABILITY", "STATION_REQUIRED"}


def test_최대_도보는_미터_단위_표시는_분도_같이():
    from app.core.subway import walk_minutes
    assert walk_minutes(0) == 0 and walk_minutes(72) == 1 and walk_minutes(73) == 2
    ps = sample()
    ps[0]["constraints"] = {"max_walk_m": {"value": 72, "level": "required"}}  # 화면 '1분' → 72m
    r = recommend(ps, DATES)
    assert all(c["legs"]["p1"]["walk_m"] <= 72 for c in r["candidates"])
    v = view_for(r, "p1")
    assert all("walk_min" in c["my_route"] for c in v["candidates"])


# ------------------------------------------------------------------ 출발 위치 (출발역까지 도보 포함)
HOME = {"lat": 37.6553, "lng": 127.0420}  # 쌍문역에서 약 1km 떨어진 위치 (예시)


def test_출발_위치가_있으면_역까지_도보가_이동시간에_더해짐():
    from app.core.subway import access_walk
    base = recommend(sample(), DATES)
    ps = sample()
    ps[0]["default_origin"] = HOME
    r = recommend(ps, DATES)
    walk_m, walk_min = access_walk(HOME["lat"], HOME["lng"], "쌍문")
    assert walk_min > 0
    # 같은 후보가 남아 있으면 p1 이동시간이 정확히 도보만큼 늘어남
    same = {c["candidate_id"]: c for c in base["candidates"]}
    for c in r["candidates"]:
        if c["candidate_id"] in same:
            assert c["legs"]["p1"]["minutes"] == same[c["candidate_id"]]["legs"]["p1"]["minutes"] + walk_min
        leg = c["legs"]["p1"]
        assert leg["access_walk_m"] == walk_m and leg["access_min"] == walk_min
        assert int(leg["depart_at"][:2]) in ps[0]["availability"][c["date"]]  # 집에서 출발하는 시각 기준


def test_내_경로에_출발_위치_도보가_보이고_좌표는_안_보임():
    ps = sample()
    ps[0]["default_origin"] = HOME
    r = recommend(ps, DATES)
    me = view_for(r, "p1")["candidates"][0]["my_route"]
    assert me["access"]["minutes"] > 0 and me["access"]["walk_m"] > 0
    assert me["walk_m"] >= me["access"]["walk_m"]
    other = view_for(r, "p2")["candidates"][0]["my_route"]
    assert other["access"] is None
    text = json.dumps(r, ensure_ascii=False) + json.dumps(view_for(r, "p1"), ensure_ascii=False)
    assert "37.655" not in text and "127.042" not in text


def test_출발_위치_검증_반올림_및_에러():
    data = {"availability": {"2026-11-07": [14]}, "default_station": "쌍문",
            "default_origin": {"lat": 37.655312, "lng": 127.041987}}
    errors, clean = validate_conditions(data, DATES, final=True)
    assert errors == [] and clean["default_origin"] == {"lat": 37.655, "lng": 127.042}

    far = dict(data, default_origin={"lat": 37.50, "lng": 127.03})  # 쌍문역에서 십몇 km
    assert {e["code"] for e in validate_conditions(far, DATES)[0]} == {"ORIGIN_TOO_FAR"}

    bad = dict(data, default_origin={"lat": "37.6", "lng": 127.0})
    assert {e["code"] for e in validate_conditions(bad, DATES)[0]} == {"INVALID_ORIGIN"}

    ex = dict(data, exception_stations=[{"date": "2026-11-07", "hours": [14], "station": "수유",
                                         "origin": {"lat": 37.6380, "lng": 127.0257}}])
    errors, clean = validate_conditions(ex, DATES)
    assert errors == [] and clean["exception_stations"][0]["origin"] == {"lat": 37.638, "lng": 127.026}


def test_출발_위치_없으면_예전과_똑같음():
    errors, clean = validate_conditions({"availability": {"2026-11-07": [14]}, "default_station": "쌍문"}, DATES)
    assert errors == [] and "default_origin" not in clean
    r = recommend(sample(), DATES)
    assert all(c["my_route"]["access"] is None for c in view_for(r, "p1")["candidates"])

def test_지도용_경로는_지나가는_역_전체와_역_좌표():
    from app.core import subway
    r = subway.find_route("쌍문", "충무로")
    stops = subway.path_stops(r.path)
    assert stops[0]["name"] == "쌍문" and stops[-1]["name"] == "충무로"
    assert len(stops) == r.segments[0].stops + 1  # 환승 없음: 정차 역 수 + 출발역
    assert all({"name", "line", "lat", "lng"} <= set(s) for s in stops)

    # 환승이 있으면 환승역이 노선을 바꿔 두 번 나온다
    r2 = subway.find_route("방화", "강남")
    names = [s["name"] for s in subway.path_stops(r2.path)]
    assert r2.transfers >= 1 and len(names) == len(set(names)) + r2.transfers
