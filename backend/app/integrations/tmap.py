"""티맵(SK Open API) 호출: 주소 → 좌표, 두 지점 사이 보행 거리·시간.

실패 원인은 TmapError 메시지에 담아 로그에 남긴다 (키 값은 넣지 않는다).
"""
import math

import httpx

from app.config import get_settings

BASE = "https://apis.openapi.sk.com/tmap"


class TmapError(Exception):
    """호출 실패 (키 없음·인증·한도·네트워크·결과 없음). 메시지는 원인 보고용."""


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
    if r.status_code != 200:
        hint = {401: "키 오류·미활성", 403: "상품 미신청·권한", 429: "호출 한도 초과"}.get(r.status_code, "")
        raise TmapError(f"티맵 응답 {r.status_code} {hint}".strip())
    try:
        return r.json()
    except ValueError as e:
        raise TmapError("티맵 응답을 해석하지 못했습니다.") from e


def geocode(address: str) -> tuple[float, float]:
    """주소 → (위도, 경도). 찾지 못하면 LookupError."""
    data = _call(
        "GET", "geo/fullAddrGeo",
        params={"version": 1, "addressFlag": "F00", "coordType": "WGS84GEO", "fullAddr": address},
    )
    for c in (data.get("coordinateInfo") or {}).get("coordinate") or []:
        # 지번 주소는 lat/lon, 도로명 주소는 newLat/newLon에 값이 온다
        lat, lng = c.get("lat") or c.get("newLat"), c.get("lon") or c.get("newLon")
        if lat and lng:
            return float(lat), float(lng)
    raise LookupError(address)


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
