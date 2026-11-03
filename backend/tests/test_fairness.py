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
    text = json.dumps(v, ensure_ascii=False)
    assert "방화" not in text and "잠실" not in text.replace("잠실새내", "").replace(r["candidates"][0]["station"], "")
    assert all(c["my_route"]["origin"] == "쌍문" for c in v["candidates"])
    assert "legs" not in text


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


def test_검증_에러_코드():
    data = {
        "availability": {"2026-12-25": [10]},
        "default_station": "구로",
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
