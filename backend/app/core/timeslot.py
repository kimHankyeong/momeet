"""
시간·장소 후보 생성 (F-006 계산 방식 1~3단계)

후보 = 날짜 × 만남 시작 시각 × 만남 역

판단 기준
    - 참여자가 입력한 시간은 '도착'이 아니라 '출발 가능한 시간' (F-004)
      → 14시를 선택했다 = 14:00~14:59 사이에 출발할 수 있다
    - 모두가 만남 시작 시각(start)에 도착하도록 각자 출발한다고 가정
      출발 시각 = start - 이동시간 → 이 시각이 본인이 고른 시간 안이면 가능
    - 만남 시작부터 최소 2시간(MEET_MINUTES) 함께 있을 수 있어야 함
      → 전원이 start에 도착하므로 start ~ start+2시간이 공동 체류 구간
    - 날짜·시간별 예외 출발역이 있으면 그 시간대 출발은 예외역 기준으로 계산

여기서는 '시간적으로 가능한 후보'만 만든다.
최대 이동시간·도보·접근성 같은 필수/선호 조건 판단과 정렬은 fairness.py 담당.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from app.core import subway

MEET_MINUTES = 120   # 최소 공동 체류 시간
STEP_MINUTES = 30    # 만남 시작 시각 간격 (00분, 30분)
DAY_END = 24 * 60    # 만남은 당일 24:00 전에 끝나야 함


# ------------------------------------------------------------------ 결과 형식
@dataclass
class Leg:
    """참여자 1명의 후보까지 이동 정보"""
    participant_id: str
    origin: str          # 실제 출발역 (기본 or 예외)
    depart_at: str       # 예상 출발 시각 HH:MM (출발 위치가 있으면 그 위치에서 출발하는 시각)
    minutes: int         # 총 이동시간 = 출발 위치→역 도보 + 지하철
    transfers: int
    walk_m: int          # 총 도보 = 출발 위치→역 도보 + 환승 도보
    route: dict          # subway.Route.to_dict() (지하철 구간만)
    access_walk_m: int = 0   # 출발 위치 → 출발역 도보 거리 (위치 안 줬으면 0)
    access_min: int = 0      # 출발 위치 → 출발역 도보 시간
    access_source: str = ""  # "tmap"(티맵 보행 경로) | "estimate"(직선거리 추정). 위치 안 줬으면 빈 문자열


@dataclass
class Candidate:
    candidate_id: str
    date: str
    start: str
    end: str
    station: str
    legs: dict[str, Leg] = field(default_factory=dict)

    @property
    def max_minutes(self) -> int:
        return max(l.minutes for l in self.legs.values())

    @property
    def total_minutes(self) -> int:
        return sum(l.minutes for l in self.legs.values())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["max_minutes"] = self.max_minutes
        d["total_minutes"] = self.total_minutes
        return d


@dataclass
class DateDiagnosis:
    """후보가 없을 때 통합 사유를 만들기 위한 날짜별 진단 (fairness.py가 사용)"""
    date: str
    unavailable: list[str] = field(default_factory=list)   # 이 날 출발 가능 시간을 안 고른 참여자
    candidate_count: int = 0


# ------------------------------------------------------------------ 유틸
def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def make_candidate_id(date: str, start_min: int, station: str) -> str:
    """예: c_20261107_1500_창동  (A의 공식 제안 검증에서 그대로 사용)"""
    return f"c_{date.replace('-', '')}_{start_min // 60:02d}{start_min % 60:02d}_{station}"


def parse_candidate_id(candidate_id: str) -> tuple[str, int, str]:
    """make_candidate_id의 역변환 → (날짜, 시작 분, 역명)"""
    _, d, t, station = candidate_id.split("_", 3)
    date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return date, int(t[:2]) * 60 + int(t[2:]), station


def _is_true(constraints: dict, key: str) -> bool:
    c = constraints.get(key)
    return bool(c and c.get("value"))


def _required_value(constraints: dict, key: str):
    c = constraints.get(key)
    return c["value"] if c and c.get("level") == "required" else None


def _point(origin: dict | None) -> tuple[float, float] | None:
    return (origin["lat"], origin["lng"]) if origin else None


def _stored_access(info, station: str) -> tuple[int, int, str] | None:
    """조건에 저장된 출발 위치→출발역 도보 (m, 분, 출처). 다른 역 기준으로 구한 값이면 None (직선거리 추정으로 대체)"""
    if isinstance(info, dict) and info.get("station") == station and "walk_m" in info and "minutes" in info:
        return int(info["walk_m"]), int(info["minutes"]), str(info.get("source", ""))
    return None


def _origin_options(p: dict, date: str) -> list[tuple[str, tuple | None, tuple | None, set[int]]]:
    """
    이 날짜에 쓸 수 있는 (출발역, 출발 위치 좌표 or None, 저장된 도보 or None, 출발 가능한 시간들) 목록.
    예외 출발역이 지정된 시간은 기본 출발역에서 빼고 예외역에 배정.
    """
    hours = set(p.get("availability", {}).get(date, []))
    options: dict[tuple, set[int]] = {}
    for ex in p.get("exception_stations", []):
        if ex["date"] == date:
            ex_hours = hours & set(ex["hours"])
            if ex_hours:
                key = (ex["station"], _point(ex.get("origin")), _stored_access(ex.get("access"), ex["station"]))
                options.setdefault(key, set()).update(ex_hours)
                hours -= ex_hours
    if hours:
        st = p["default_station"]
        key = (st, _point(p.get("default_origin")), _stored_access(p.get("default_access"), st))
        options.setdefault(key, set()).update(hours)
    return [(station, point, stored, hrs) for (station, point, stored), hrs in options.items()]


# ------------------------------------------------------------------ 메인
def generate_candidates(participants: list[dict],
                        dates: list[str],
                        stations: list[str] | None = None,
                        meet_minutes: int = MEET_MINUTES,
                        step_minutes: int = STEP_MINUTES) -> tuple[list[Candidate], list[DateDiagnosis]]:
    """
    participants 예시 (조건 입력 JSON과 같은 모양 + id):
        {
          "id": "p1",
          "availability": {"2026-11-07": [13, 14, 15]},
          "default_station": "쌍문",
          "exception_stations": [{"date": "2026-11-08", "hours": [10], "station": "수유"}],
          "constraints": {
            "max_transfers": {"value": 1, "level": "required"},
            "needs_elevator": {"value": true, "level": "required"},
            ...
          }
        }
    stations: 후보역 목록. None이면 데이터에 있는 전체 역 (수도권 전철).

    반환: (시간적으로 가능한 후보 목록, 날짜별 진단)
    """
    if stations is None:
        stations = [s["name"] for s in subway._load()[0]]

    # 1) 참여자 × 출발역 별로 전체 역까지 경로를 한 번씩만 계산 (캐시)
    route_cache: dict[tuple[str, str], dict[str, subway.Route]] = {}

    def routes(p: dict, origin: str) -> dict[str, subway.Route]:
        key = (p["id"], origin)
        if key not in route_cache:
            c = p.get("constraints", {})
            route_cache[key] = subway.routes_from(
                origin,
                # 엘리베이터 필요·계단 회피는 경로 계산 자체가 달라짐 (환승 가능 여부, 보행시간)
                needs_elevator=_is_true(c, "needs_elevator") or _is_true(c, "avoid_stairs"),
                # 최대 환승 '필수'는 경로 탐색에서 바로 제한, '선호'는 fairness에서 정렬에 반영
                max_transfers=_required_value(c, "max_transfers"),
                candidates=stations,
            )
        return route_cache[key]

    candidates: list[Candidate] = []
    diagnoses: list[DateDiagnosis] = []

    for date in dates:
        diag = DateDiagnosis(date=date)
        options = {p["id"]: _origin_options(p, date) for p in participants}
        diag.unavailable = [pid for pid, opts in options.items() if not opts]
        if diag.unavailable:
            diagnoses.append(diag)
            continue

        # 2) 만남 시작 시각 후보: 2시간 체류가 당일 안에 끝나는 범위
        for start in range(0, DAY_END - meet_minutes + 1, step_minutes):
            for station in stations:
                legs = {}
                for p in participants:
                    leg = _best_leg(p, options[p["id"]], station, start, routes)
                    if leg is None:
                        break
                    legs[p["id"]] = leg
                else:
                    candidates.append(Candidate(
                        candidate_id=make_candidate_id(date, start, station),
                        date=date,
                        start=hhmm(start),
                        end=hhmm(start + meet_minutes),
                        station=station,
                        legs=legs,
                    ))
                    diag.candidate_count += 1
        diagnoses.append(diag)

    return candidates, diagnoses


def _best_leg(p: dict, options, station: str, start: int, routes) -> Leg | None:
    """
    이 참여자가 start에 station에 도착할 수 있는 방법 중 이동시간이 가장 짧은 것.
    출발 시각(start - 이동시간)이 그 출발역에 배정된 출발 가능 시간 안이어야 함.
    """
    best = None
    for origin, point, stored, hours in options:
        r = routes(p, origin).get(station)
        if r is None:          # 필수 조건(환승 제한·엘리베이터) 때문에 도달 불가
            continue
        if point is None:
            access_m, access_min, source = 0, 0, ""
        elif stored:           # 저장 시 구한 값 (티맵 실측 또는 추정)
            access_m, access_min, source = stored
        else:                  # 저장된 값이 없으면 직선거리 추정
            (access_m, access_min), source = subway.access_walk(*point, origin), "estimate"
        total = r.minutes + access_min
        depart = start - total
        if depart < 0 or depart // 60 not in hours:
            continue
        if best is None or total < best.minutes:
            best = Leg(
                participant_id=p["id"],
                origin=origin,
                depart_at=hhmm(depart),
                minutes=total,
                transfers=r.transfers,
                walk_m=r.walk_m + access_m,
                route=r.to_dict(),
                access_walk_m=access_m,
                access_min=access_min,
                access_source=source,
            )
    return best
