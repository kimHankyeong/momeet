"""
공평성 추천 (F-006 4~8단계) + 백A가 API에서 부르는 함수 모음

백A가 쓰는 함수
    validate_conditions(data, dates, final)       조건 임시저장/제출 검증 → (에러 목록, 정리된 조건)
    recommend(participants, dates)                추천 실행 → 결과(dict, JSON 그대로 DB 저장)
    view_for(result, participant_id)              추천 결과 조회 응답 (본인 경로만 남김)
    get_candidate(result, candidate_id)           공식 제안 검증 (추천 결과에 있는 후보인지)
    get_my_route(result, candidate_id, pid)       제안/확정 화면용 내 경로

추천 순서
    1. timeslot.generate_candidates: 시간적으로 가능한 날짜 × 시간 × 역
    2. 필수 조건 미충족 후보 제외 (접근성 unknown은 통과 못 함, 조건 임의 완화 X)
    3. 같은 날 같은 역은 가장 좋은 시간 1개만 (시안처럼 서로 다른 장소를 비교하도록)
    4. 정렬: 최대 이동시간 → 선호 조건 충족 수(많을수록) → 총 이동시간
    5. 날짜별 최대 3개 → 전체 순서로 합쳐서 순위 부여, 1등 = best
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from app.core import subway
from app.core.timeslot import generate_candidates

TOP_PER_DATE = 3
KST = timezone(timedelta(hours=9))

CONSTRAINT_KEYS = {
    "max_travel_min": int,
    "max_transfers": int,
    "max_walk_min": int,   # 분 단위 (프론트 '최대 도보 거리 10분'). 출발 위치→역 + 환승 도보를 1.2m/s로 환산해 비교
    "needs_elevator": bool,
    "avoid_stairs": bool,
}
CONSTRAINT_LABELS = {
    "max_travel_min": "최대 이동시간",
    "max_transfers": "최대 환승 횟수",
    "max_walk_min": "최대 도보 거리",
    "needs_elevator": "엘리베이터 필요",
    "avoid_stairs": "계단 회피",
}


# ================================================================== 조건 검증
def _err(code: str, message: str, field: str | None = None) -> dict:
    return {"code": code, "message": message, "field": field}


def _station_name(name) -> str | None:
    """입력 역명 → 표준 역명 ('신설동역', '이수' 등 허용). 없으면 None"""
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        return subway.get_station(name)["name"]
    except KeyError:
        return None


def _valid_hours(hours) -> bool:
    return isinstance(hours, list) and all(isinstance(h, int) and 0 <= h <= 23 for h in hours)


# 출발 위치 좌표 허용 범위 (수도권) / 저장 정밀도
LAT_RANGE, LNG_RANGE = (36.8, 38.3), (126.3, 127.9)
ORIGIN_DECIMALS = 3   # 소수점 3자리 ≈ 100m. 집 위치를 정확히 저장하지 않으려고 반올림


def _check_origin(origin, station: str | None, field: str, errors: list) -> dict | None:
    """
    출발 위치 {"lat", "lng"} 검사 + 반올림. 없으면 None.
    출발역이 있으면 그 역까지 걸어갈 만한 거리(MAX_ACCESS_M)인지도 확인
    """
    if origin in (None, {}):
        return None
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not (isinstance(origin, dict) and num(origin.get("lat")) and num(origin.get("lng"))
            and LAT_RANGE[0] <= origin["lat"] <= LAT_RANGE[1] and LNG_RANGE[0] <= origin["lng"] <= LNG_RANGE[1]):
        errors.append(_err("INVALID_ORIGIN", "출발 위치가 올바르지 않습니다.", field))
        return None
    point = {"lat": round(origin["lat"], ORIGIN_DECIMALS), "lng": round(origin["lng"], ORIGIN_DECIMALS)}
    if station:
        meters, _ = subway.access_walk(point["lat"], point["lng"], station)
        if meters > subway.MAX_ACCESS_M:
            errors.append(_err("ORIGIN_TOO_FAR",
                               f"출발 위치에서 {station}역까지 너무 멀어요. 더 가까운 역을 골라주세요.", field))
            return None
    return point


def validate_conditions(data: dict, dates: list[str], final: bool = True) -> tuple[list[dict], dict]:
    """
    조건 데이터 검증 + 정리.
    data: 프론트가 보낸 조건 JSON / dates: 약속방 후보 날짜 목록 ("YYYY-MM-DD")
    final: True = 최종 제출(필수 항목 다 있어야 함), False = 임시저장(있는 것만 검사)

    반환: (에러 목록, 정리된 조건)
        에러 목록이 비어 있으면 통과. 정리된 조건을 DB에 저장하면 됨
        (역명은 표준 이름으로, 시간은 정렬·중복 제거)
    """
    errors: list[dict] = []
    allowed = set(dates)
    clean: dict = {"availability": {}, "default_station": None, "exception_stations": [], "constraints": {}}
    if not isinstance(data, dict):
        return [_err("INVALID_FORMAT", "조건 형식이 올바르지 않습니다.")], clean

    # 출발 가능 시간
    availability = data.get("availability") or {}
    if not isinstance(availability, dict):
        errors.append(_err("INVALID_FORMAT", "출발 가능 시간 형식이 올바르지 않습니다.", "availability"))
        availability = {}
    for date, hours in availability.items():
        if date not in allowed:
            errors.append(_err("DATE_OUT_OF_RANGE", f"{date}은 약속 날짜 범위 밖입니다.", "availability"))
        elif not _valid_hours(hours):
            errors.append(_err("INVALID_FORMAT", "시간은 0~23 숫자 목록이어야 합니다.", "availability"))
        elif hours:
            clean["availability"][date] = sorted(set(hours))
    if final and not clean["availability"]:
        errors.append(_err("NO_AVAILABILITY", "출발 가능한 시간을 하나 이상 선택해 주세요.", "availability"))

    # 기본 출발역
    raw_station = data.get("default_station")
    if raw_station:
        name = _station_name(raw_station)
        if name is None:
            errors.append(_err("STATION_NOT_FOUND", f"{raw_station}: 범위 밖이거나 없는 역입니다.", "default_station"))
        clean["default_station"] = name
    elif final:
        errors.append(_err("STATION_REQUIRED", "기본 출발역을 선택해 주세요.", "default_station"))

    # 출발 위치 (선택). 있으면 위치 → 출발역 도보가 이동시간에 더해짐
    origin = _check_origin(data.get("default_origin"), clean["default_station"], "default_origin", errors)
    if origin:
        clean["default_origin"] = origin

    # 예외 출발역
    exceptions = data.get("exception_stations") or []
    if not isinstance(exceptions, list):
        errors.append(_err("INVALID_FORMAT", "예외 출발역 형식이 올바르지 않습니다.", "exception_stations"))
        exceptions = []
    for ex in exceptions:
        if not isinstance(ex, dict):
            errors.append(_err("INVALID_FORMAT", "예외 출발역 형식이 올바르지 않습니다.", "exception_stations"))
            continue
        name = _station_name(ex.get("station"))
        if name is None:
            errors.append(_err("STATION_NOT_FOUND", f"{ex.get('station')}: 범위 밖이거나 없는 역입니다.", "exception_stations"))
        elif ex.get("date") not in allowed:
            errors.append(_err("DATE_OUT_OF_RANGE", f"{ex.get('date')}은 약속 날짜 범위 밖입니다.", "exception_stations"))
        elif not _valid_hours(ex.get("hours")) or not ex.get("hours"):
            errors.append(_err("INVALID_FORMAT", "예외 출발역 시간은 0~23 숫자 목록이어야 합니다.", "exception_stations"))
        else:
            item = {"date": ex["date"], "hours": sorted(set(ex["hours"])), "station": name}
            ex_origin = _check_origin(ex.get("origin"), name, "exception_stations", errors)
            if ex_origin:
                item["origin"] = ex_origin
            clean["exception_stations"].append(item)

    # 이동·접근성 조건
    constraints = data.get("constraints") or {}
    if not isinstance(constraints, dict):
        errors.append(_err("INVALID_FORMAT", "이동 조건 형식이 올바르지 않습니다.", "constraints"))
        constraints = {}
    for key, c in constraints.items():
        typ = CONSTRAINT_KEYS.get(key)
        ok = (
            typ is not None and isinstance(c, dict)
            and c.get("level") in ("required", "preferred")
            and isinstance(c.get("value"), typ)
            and not (typ is int and (isinstance(c.get("value"), bool) or c["value"] < 0))
        )
        if not ok:
            errors.append(_err("INVALID_CONSTRAINT", f"{key}: 조건 값이 올바르지 않습니다.", "constraints"))
        elif typ is bool and c["value"] is False:
            continue  # 꺼진 조건은 저장 안 함
        else:
            clean["constraints"][key] = {"value": c["value"], "level": c["level"]}

    return errors, clean


# ================================================================== 조건 판단
def _required(p: dict) -> dict:
    return {k: c["value"] for k, c in p.get("constraints", {}).items() if c.get("level") == "required"}


def _preferred(p: dict) -> dict:
    return {k: c["value"] for k, c in p.get("constraints", {}).items() if c.get("level") == "preferred"}


def _meets(key: str, value, leg: dict, accessibility: str) -> bool:
    """조건 1개를 이 참여자 이동(leg)이 만족하는지"""
    if key == "max_travel_min":
        return leg["minutes"] <= value
    if key == "max_transfers":
        return leg["transfers"] <= value
    if key == "max_walk_min":
        return subway.walk_minutes(leg["walk_m"]) <= value
    if key in ("needs_elevator", "avoid_stairs"):
        # 경로상 환승은 subway에서 이미 엘리베이터 있는 곳만 지나게 계산됨 → 만나는 역만 확인
        return (not value) or accessibility == "met"
    return True


def _failed_required(c: dict, people: dict) -> list[tuple[str, str]]:
    """후보 c에서 필수 조건을 못 맞춘 (참여자, 조건) 목록. 비어 있으면 통과"""
    fails = []
    for pid, leg in c["legs"].items():
        for key, value in _required(people[pid]).items():
            if not _meets(key, value, leg, c["accessibility"]):
                fails.append((pid, key))
    return fails


def _preferred_score(c: dict, people: dict) -> tuple[int, int]:
    """(전원 합산 선호 조건 충족 수, 전체 선호 조건 수)"""
    met = total = 0
    for pid, leg in c["legs"].items():
        for key, value in _preferred(people[pid]).items():
            total += 1
            met += _meets(key, value, leg, c["accessibility"])
    return met, total


def sort_key(c: dict):
    """정렬: 최대 이동시간 짧은 순 → 선호 조건 많이 맞는 순 → 총 이동시간 짧은 순 (그다음 시간·역명으로 고정)"""
    return (c["max_minutes"], -c["preferred_met"], c["total_minutes"], c["date"], c["start"], c["station"])


# ================================================================== 추천
def recommend(participants: list[dict], dates: list[str]) -> dict:
    """
    participants: DB에 저장된 조건(validate_conditions가 정리한 것) + "id"
        [{"id": "p1", "availability": {...}, "default_station": "쌍문", "exception_stations": [], "constraints": {...}}, ...]
    dates: 약속방 후보 날짜 목록

    반환: 추천 결과 dict (JSON으로 그대로 저장했다가 view_for / get_candidate / get_my_route에 다시 넘기기)
    """
    # 결과를 JSON으로 저장하면 dict 키가 문자열이 됨 → id는 처음부터 문자열로 통일 (정수 id를 넘겨도 됨)
    participants = [{**p, "id": str(p["id"])} for p in participants]
    people = {p["id"]: p for p in participants}
    raw, diagnoses = generate_candidates(participants, dates)

    passed, failed_by_date = [], {}
    for cand in raw:
        c = cand.to_dict()
        c["accessibility"] = subway.station_accessibility(c["station"])
        fails = _failed_required(c, people)
        if fails:
            failed_by_date.setdefault(c["date"], []).append(fails)
            continue
        c["preferred_met"], c["preferred_total"] = _preferred_score(c, people)
        passed.append(c)

    # 같은 날 같은 역은 가장 좋은 시간 1개만
    best_per_station: dict[tuple[str, str], dict] = {}
    for c in passed:
        k = (c["date"], c["station"])
        if k not in best_per_station or sort_key(c) < sort_key(best_per_station[k]):
            best_per_station[k] = c

    # 날짜별 상위 3개 → 전체 순서로 합치기
    by_date: dict[str, list[dict]] = {}
    for c in best_per_station.values():
        by_date.setdefault(c["date"], []).append(c)
    picked = []
    for date in dates:
        picked += sorted(by_date.get(date, []), key=sort_key)[:TOP_PER_DATE]
    picked.sort(key=sort_key)
    for i, c in enumerate(picked, 1):
        c["rank"] = i

    result = {
        "status": "ok" if picked else "no_candidate",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "best": picked[0]["candidate_id"] if picked else None,
        "candidates": picked,
        "reasons": [] if picked else _reasons(dates, diagnoses, failed_by_date, people),
    }
    return result


def _reasons(dates, diagnoses, failed_by_date, people) -> list[dict]:
    """
    후보가 없을 때 날짜별 통합 사유. 참여자 이름 대신 인원수만 (F-011)
        SOME_UNAVAILABLE : 그 날 출발 가능 시간을 안 고른 사람이 있음
        NO_COMMON_TIME   : 이동시간까지 고려하면 2시간 같이 있을 시간이 없음
        REQUIRED_UNMET   : 어떤 후보에서도 특정 필수 조건을 못 맞추는 사람이 있음
        REQUIRED_COMBINED: 각자는 맞출 수 있지만 모두 동시에 맞추는 후보가 없음
    """
    diag = {d.date: d for d in diagnoses}
    reasons = []
    for date in dates:
        d = diag.get(date)
        if d and d.unavailable:
            reasons.append({"date": date, "code": "SOME_UNAVAILABLE",
                            "message": f"참여자 {len(d.unavailable)}명이 이 날 가능한 시간이 없습니다."})
            continue
        fails = failed_by_date.get(date)
        if not fails:
            reasons.append({"date": date, "code": "NO_COMMON_TIME",
                            "message": "이동시간까지 고려하면 2시간 이상 같이 있을 수 있는 시간이 없습니다."})
            continue

        # 모든 시간 가능 후보에서 매번 실패한 (참여자, 조건) = 그 조건 때문에 막힌 사람
        always = set(fails[0])
        for f in fails[1:]:
            always &= set(f)
        if always:
            by_key: dict[str, set] = {}
            for pid, key in always:
                by_key.setdefault(key, set()).add(pid)
            for key, pids in sorted(by_key.items()):
                reasons.append({"date": date, "code": "REQUIRED_UNMET",
                                "message": f"{CONSTRAINT_LABELS[key]}(필수)을 맞출 수 있는 역이 없습니다. ({len(pids)}명)"})
        else:
            reasons.append({"date": date, "code": "REQUIRED_COMBINED",
                            "message": "각자의 필수 조건을 모두 동시에 맞추는 시간·장소가 없습니다."})
    return reasons


# ================================================================== 조회용
def _station_view(name: str) -> dict:
    st = subway.get_station(name)
    return {"name": st["name"], "lines": st["lines"], "lat": st["lat"], "lng": st["lng"]}


def _route_view(leg: dict) -> dict:
    return {
        "origin": leg["origin"],
        "depart_at": leg["depart_at"],
        "minutes": leg["minutes"],
        "transfers": leg["transfers"],
        "walk_m": leg["walk_m"],
        "walk_min": subway.walk_minutes(leg["walk_m"]),
        # 출발 위치를 입력했을 때만: 위치 → 출발역 도보 (좌표는 내보내지 않음)
        "access": ({"walk_m": leg["access_walk_m"], "minutes": leg["access_min"]}
                   if leg.get("access_walk_m") else None),
        "segments": leg["route"]["segments"],
    }


def view_for(result: dict | None, participant_id: str) -> dict:
    """
    GET /meetings/{id}/recommendations 응답 그대로.
    다른 참여자의 출발역·경로·조건은 빼고 요청자 본인 경로(my_route)만 남김.
    result가 None(추천 실행 전)이면 not_ready.
    """
    if not result:
        return {"status": "not_ready", "best": None, "candidates": []}

    view = {"status": result["status"], "best": result["best"], "candidates": []}
    for c in result["candidates"]:
        leg = c["legs"].get(str(participant_id))
        view["candidates"].append({
            "rank": c["rank"],
            "candidate_id": c["candidate_id"],
            "date": c["date"],
            "start": c["start"],
            "end": c["end"],
            "station": _station_view(c["station"]),
            "max_travel_min": c["max_minutes"],
            "accessibility": c["accessibility"],
            "my_route": _route_view(leg) if leg else None,  # 추천 후 참여한 사람은 경로 없음
        })
    if result["status"] == "no_candidate":
        view["reasons"] = result["reasons"]
    return view


def get_candidate(result: dict | None, candidate_id: str) -> dict | None:
    """공식 제안 검증: 이번 추천 결과에 있는 후보면 공개 가능한 정보만 반환, 아니면 None"""
    if not result:
        return None
    for c in result["candidates"]:
        if c["candidate_id"] == candidate_id:
            return {
                "candidate_id": c["candidate_id"],
                "date": c["date"],
                "start": c["start"],
                "end": c["end"],
                "station": _station_view(c["station"]),
                "max_travel_min": c["max_minutes"],
                "accessibility": c["accessibility"],
            }
    return None


def get_my_route(result: dict | None, candidate_id: str, participant_id: str) -> dict | None:
    """제안/확정 화면의 '내 예상 이동 · 환승 · 도보 · 내 경로'. 없으면 None"""
    if not result:
        return None
    for c in result["candidates"]:
        if c["candidate_id"] == candidate_id:
            leg = c["legs"].get(str(participant_id))
            return _route_view(leg) if leg else None
    return None
