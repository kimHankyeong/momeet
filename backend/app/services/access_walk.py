"""출발 위치 → 출발역 도보(거리·시간)를 티맵 보행 경로로 구한다.

입력 이름과 검증은 B의 validate_conditions 를 따른다.
    default_origin  {lat, lng}                      기본 출발역에 쓰는 출발 위치 (좌표는 소수 3자리로 반올림되어 저장)
    exception_stations[].origin                      그 예외 출발역에 쓰는 출발 위치
주소만 보내도 된다: {address: "..."} 는 서버가 좌표로 바꾼 뒤 검증하며, 주소 자체는 저장하지 않는다.

저장 결과: 조건 데이터의 `default_access` / 예외 출발역의 `access`
    {station, walk_m, minutes, source: "tmap" | "estimate"}
추천 계산(timeslot)은 이 값을 쓰고, 없으면 B의 직선거리 추정(subway.access_walk)으로 계산한다.
티맵을 쓸 수 없으면(키 없음·인증·한도·네트워크) 같은 추정을 `source: "estimate"`로 저장한다.
"""
import logging

from app.core import subway
from app.errors import AppError
from app.integrations import tmap

log = logging.getLogger("momeet")

MAX_LOOKUPS_PER_SAVE = 10  # 한 번 저장할 때 티맵 보행 호출 상한 (넘으면 추정). 호출 한도 보호.


def _origin_error(message: str, field: str) -> AppError:
    return AppError(
        "CONDITIONS_INVALID", "조건을 확인해 주세요.", 422,
        {"errors": [{"code": "INVALID_ORIGIN", "message": message, "field": field}]},
    )


def _geocode(origin, field: str):
    """{address} 형태면 {lat, lng}로 바꾼다. 좌표가 있으면 그대로 둔다(주소는 버림). 그 외는 B의 검증에 맡긴다."""
    if not isinstance(origin, dict) or "address" not in origin:
        return origin
    rest = {k: v for k, v in origin.items() if k != "address"}
    if "lat" in rest or "lng" in rest:
        return rest
    address = origin["address"]
    if not isinstance(address, str) or not 1 <= len(address.strip()) <= 100:
        raise _origin_error("주소는 1~100자로 입력해 주세요.", field)
    try:
        lat, lng = tmap.geocode(address.strip())
    except LookupError:
        raise _origin_error("주소를 찾을 수 없습니다. 도로명 또는 지번 주소로 입력해 주세요.", field)
    except tmap.TmapError as e:
        log.warning("주소 변환 실패: %s", e)
        raise AppError("GEOCODE_UNAVAILABLE", "주소를 좌표로 바꾸지 못했습니다. 지도에서 위치를 직접 선택해 주세요.", 503)
    return {"lat": lat, "lng": lng}


def resolve_addresses(data: dict) -> dict:
    """검증 전에 주소 입력을 좌표로 바꾼 사본을 돌려준다. 주소가 없으면 data 그대로."""
    exceptions = data.get("exception_stations")
    has_address = isinstance(data.get("default_origin"), dict) and "address" in data["default_origin"]
    has_address |= isinstance(exceptions, list) and any(
        isinstance(e, dict) and isinstance(e.get("origin"), dict) and "address" in e["origin"] for e in exceptions
    )
    if not has_address:
        return data
    out = dict(data)
    if "default_origin" in out:
        out["default_origin"] = _geocode(out["default_origin"], "default_origin")
    if isinstance(exceptions, list):
        out["exception_stations"] = [
            {**e, "origin": _geocode(e["origin"], "exception_stations")} if isinstance(e, dict) and "origin" in e else e
            for e in exceptions
        ]
    return out


class _Resolver:
    def __init__(self, previous: dict | None):
        self.lookups = 0
        self.tmap_down = False  # 이번 저장에서 한 번 실패하면 나머지는 기다리지 않고 바로 추정한다
        self.memo: dict[tuple, dict] = {}
        # 이전에 저장된 티맵 결과는 그대로 쓴다: 초안을 자주 저장해도 호출이 늘지 않는다.
        # 추정값은 다시 시도하도록 재사용하지 않는다.
        prev = previous or {}
        pairs = [(prev.get("default_origin"), prev.get("default_access"))]
        pairs += [(e.get("origin"), e.get("access")) for e in prev.get("exception_stations") or [] if isinstance(e, dict)]
        for origin, acc in pairs:
            if isinstance(origin, dict) and isinstance(acc, dict) and acc.get("source") == "tmap":
                self.memo[(origin["lat"], origin["lng"], acc.get("station"))] = acc

    def access(self, origin: dict, station: str) -> dict:
        key = (origin["lat"], origin["lng"], station)
        if key in self.memo:
            return self.memo[key]
        st = subway.get_station(station)
        result = None
        if tmap.configured() and not self.tmap_down and self.lookups < MAX_LOOKUPS_PER_SAVE:
            self.lookups += 1
            try:
                meters, minutes = tmap.walk(origin["lat"], origin["lng"], st["lat"], st["lng"])
                result = {"station": station, "walk_m": meters, "minutes": minutes, "source": "tmap"}
            except tmap.TmapError as e:
                self.tmap_down = True
                log.warning("보행 경로 호출 실패, 이번 저장의 나머지도 직선거리로 추정: %s", e)
        if result is None:
            meters, minutes = subway.access_walk(origin["lat"], origin["lng"], station)
            result = {"station": station, "walk_m": meters, "minutes": minutes, "source": "estimate"}
        self.memo[key] = result
        return result


def apply(clean: dict, previous: dict | None) -> None:
    """검증을 통과한 조건(clean)의 출발 위치마다 출발역까지 도보 정보를 채운다."""
    r = _Resolver(previous)
    if clean.get("default_origin") and clean.get("default_station"):
        clean["default_access"] = r.access(clean["default_origin"], clean["default_station"])
    for ex in clean.get("exception_stations", []):
        if ex.get("origin"):
            ex["access"] = r.access(ex["origin"], ex["station"])
