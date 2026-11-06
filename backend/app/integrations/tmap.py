"""티맵(SK Open API) 호출: 장소·주소 검색, 두 지점 사이 보행 거리·시간.

실패 원인은 TmapError 메시지에 담아 로그에 남긴다 (키 값은 넣지 않는다).
"""
import math
import re

import httpx

from app.config import get_settings

BASE = "https://apis.openapi.sk.com/tmap"

# 도로명("노해로 342", "세종대로 110", "테헤란로 4길 5") 또는 지번("쌍문동 123-4") 주소처럼 보이는 입력
_ADDRESS_LIKE = re.compile(r"[로길]\s*\d|[동리가]\s*\d+(-\d+)?\s*$")


class TmapError(Exception):
    """호출 실패 (키 없음·인증·한도·네트워크·결과 없음). 메시지는 원인 보고용."""

    def __init__(self, message: str, status: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status = status
        self.detail = detail


def configured() -> bool:
    return bool(get_settings().tmap_app_key.strip())


def _call(method: str, path: str, **kw) -> dict:
    s = get_settings()
    if not configured():
        raise TmapError("TMAP_APP_KEY가 설정되지 않았습니다.")
    try:
        r = httpx.request(
            method, f"{BASE}/{path}", headers={"appKey": s.tmap_app_key.strip()}, timeout=s.tmap_timeout_sec, **kw
        )
    except httpx.HTTPError as e:
        raise TmapError(f"티맵 연결 실패({type(e).__name__})") from e
    if r.status_code == 204:  # 검색 결과가 없으면 오류가 아니라 204(내용 없음)로 온다
        return {}
    if r.status_code != 200:
        hint = {401: "키 오류·미활성", 403: "상품 미신청·권한", 429: "호출 한도 초과"}.get(r.status_code, "")
        raise TmapError(f"티맵 응답 {r.status_code} {hint}".strip(), r.status_code, r.text[:300])
    if not r.content.strip():  # 검색 결과가 없을 때 빈 응답이 올 수 있다
        return {}
    try:
        return r.json()
    except ValueError as e:
        raise TmapError("티맵 응답을 해석하지 못했습니다.") from e


def looks_like_address(text: str) -> bool:
    return bool(_ADDRESS_LIKE.search(text))


def _poi_address(p: dict) -> str:
    new = ((p.get("newAddressList") or {}).get("newAddress") or [{}])[0].get("fullAddressRoad")
    if new:
        return new
    parts = [p.get("upperAddrName"), p.get("middleAddrName"), p.get("lowerAddrName"), p.get("firstNo")]
    return " ".join(x for x in parts if x)


def _poi(query: str, count: int) -> list[dict]:
    """장소 검색 → [{name, address, lat, lng}]. 결과가 없으면 빈 목록."""
    data = _call(
        "GET", "pois",
        params={"version": 1, "searchKeyword": query, "count": count, "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO"},
    )
    pois = ((data.get("searchPoiInfo") or {}).get("pois") or {}).get("poi") or []
    places = []
    for p in pois:
        try:
            lat, lng = float(p["noorLat"]), float(p["noorLon"])
        except (KeyError, TypeError, ValueError):
            continue
        places.append({"name": p.get("name", ""), "address": _poi_address(p), "lat": round(lat, 6), "lng": round(lng, 6)})
    return places[:count]


def _address_hit(text: str) -> dict | None:
    """주소 변환 → {name, address, lat, lng}. 해당 주소가 없으면 None.
    name은 그 주소의 건물 이름(있으면), address는 티맵이 실제로 찾은 주소(입력과 번지가 다를 수 있다)."""
    try:
        data = _call(
            "GET", "geo/fullAddrGeo",
            params={"version": 1, "addressFlag": "F00", "coordType": "WGS84GEO", "fullAddr": text},
        )
    except TmapError as e:
        if e.status == 400 and "존재하지" in e.detail:  # "해당 주소 정보가 존재하지 않습니다"
            return None
        raise
    for c in (data.get("coordinateInfo") or {}).get("coordinate") or []:
        # 지번 주소는 lat/lon, 도로명 주소는 newLat/newLon에 값이 온다
        lat, lng = c.get("lat") or c.get("newLat"), c.get("lon") or c.get("newLon")
        if not (lat and lng):
            continue
        road = [c.get("city_do"), c.get("gu_gun"), c.get("newRoadName"), c.get("newBuildingIndex")]
        lot = [c.get("city_do"), c.get("gu_gun"), c.get("legalDong") or c.get("eup_myun"), c.get("bunji")]
        address = " ".join(x for x in (road if c.get("newRoadName") else lot) if x) or text
        return {
            "name": c.get("newBuildingName") or c.get("buildingName") or address,
            "address": address,
            "lat": round(float(lat), 6),
            "lng": round(float(lng), 6),
        }
    return None


def search_places(query: str, count: int = 5) -> list[dict]:
    """장소·주소 검색 → [{name, address, lat, lng}] (최대 count건).
    도로명·지번 주소처럼 보이면 정확한 번지(주소 변환)를 맨 앞에 두고 주변 장소를 이어 붙인다."""
    places: list[dict] = []
    if looks_like_address(query):
        hit = _address_hit(query)
        if hit:
            places.append(hit)
    for p in _poi(query, count):
        if all((round(p["lat"], 4), round(p["lng"], 4)) != (round(q["lat"], 4), round(q["lng"], 4)) for q in places):
            places.append(p)
    return places[:count]


def geocode(text: str) -> tuple[float, float]:
    """장소 이름 또는 주소 → (위도, 경도). 못 찾으면 LookupError.
    주소처럼 보이면 주소 변환(정확한 번지)을 먼저, 아니면 장소 검색의 첫 결과를 먼저 쓰고 서로 보완한다."""
    first_address = looks_like_address(text)
    for use_address in (first_address, not first_address):
        found = _address_hit(text) if use_address else (_poi(text, 1) or [None])[0]
        if found:
            return found["lat"], found["lng"]
    raise LookupError(text)


def walk(lat: float, lng: float, to_lat: float, to_lng: float) -> tuple[int, int]:
    """보행 (거리 m, 시간 분, 올림)."""
    data = _call(
        "POST", "routes/pedestrian", params={"version": 1},
        json={
            "startX": lng, "startY": lat, "endX": to_lng, "endY": to_lat,
            "reqCoordType": "WGS84GEO", "resCoordType": "WGS84GEO",
            "startName": "출발", "endName": "도착",
        },
    )
    try:
        p = data["features"][0]["properties"]
        return int(p["totalDistance"]), math.ceil(int(p["totalTime"]) / 60)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise TmapError("티맵 보행 경로 결과가 없습니다.") from e
