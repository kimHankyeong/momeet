"""출발지 장소·주소 검색 GET /places (최대 5건, 캐시, 호출 제한) 와 티맵 응답 해석. 실제 티맵은 호출하지 않는다."""
import pytest

from app.integrations import tmap
from app.services import places as places_svc


@pytest.fixture(autouse=True)
def _clean():
    places_svc.reset()
    yield
    places_svc.reset()


def fake_places(n=8):
    return [{"name": f"장소{i}", "address": f"서울 중구 {i}", "lat": 37.5 + i / 1000, "lng": 127.0} for i in range(n)]


@pytest.fixture()
def fake(monkeypatch):
    calls = []

    def search(q, count=5):
        calls.append(q)
        return fake_places()  # 일부러 5건보다 많이 돌려준다

    monkeypatch.setattr(tmap, "search_places", search)
    return calls


# ---------------------------------------------------------------- 엔드포인트
def test_returns_at_most_five(client, fake):
    r = client.get("/places", params={"q": "서울시청"})
    assert r.status_code == 200
    places = r.json()["places"]
    assert len(places) == 5 and set(places[0]) == {"name", "address", "lat", "lng"}


def test_query_limits(client, fake):
    assert client.get("/places").status_code == 422
    assert client.get("/places", params={"q": "가"}).status_code == 422
    assert client.get("/places", params={"q": "가" * 51}).status_code == 422
    assert client.get("/places", params={"q": "  가  "}).json() == {"places": []}  # 공백 정리 후 1글자는 검색하지 않는다
    assert fake == []


def test_same_query_is_cached(client, fake):
    for q in ["서울시청", "서울시청", " 서울시청 "]:
        assert client.get("/places", params={"q": q}).status_code == 200
    assert len(fake) == 1


def test_rate_limit_per_client(client, fake):
    for i in range(places_svc.RATE_LIMIT):
        assert client.get("/places", params={"q": f"검색어{i}"}).status_code == 200
    r = client.get("/places", params={"q": "또다른검색"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) >= 1
    assert client.get("/places", params={"q": "검색어0"}).status_code == 200  # 캐시에 있으면 제한과 무관


def test_outage_reported_without_details(client, monkeypatch):
    def down(q, count=5):
        raise tmap.TmapError("티맵 응답 429 호출 한도 초과")

    monkeypatch.setattr(tmap, "search_places", down)
    r = client.get("/places", params={"q": "서울시청"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "PLACES_UNAVAILABLE"
    assert "429" not in r.text  # 원인 상세는 서버 로그에만


def test_without_tmap_key_is_unavailable(client):
    r = client.get("/places", params={"q": "서울시청"})  # 테스트 환경은 키가 비어 있다
    assert r.status_code == 503


# ---------------------------------------------------------------- 티맵 응답 해석
def poi(name, lat, lng, road=None):
    p = {"name": name, "noorLat": str(lat), "noorLon": str(lng), "upperAddrName": "서울", "middleAddrName": "중구",
         "lowerAddrName": "태평로1가", "firstNo": "31"}
    if road:
        p["newAddressList"] = {"newAddress": [{"fullAddressRoad": road}]}
    return p


ADDR_HIT = {"coordinateInfo": {"coordinate": [{
    "city_do": "서울", "gu_gun": "도봉구", "newRoadName": "노해로", "newBuildingIndex": "341",
    "newBuildingName": "신원리베르텔", "lat": "", "lon": "", "newLat": "37.651445", "newLon": "127.045912"}]}}


def fake_call(address=ADDR_HIT, pois=None):
    paths = []

    def call(method, path, **kw):
        paths.append(path)
        if path == "pois":
            return {"searchPoiInfo": {"pois": {"poi": pois if pois is not None else []}}}
        if isinstance(address, Exception):
            raise address
        return address

    return call, paths


def test_search_places_parses_pois(monkeypatch):
    pois = [poi("서울특별시청", 37.566704, 126.978382, road="서울 중구 세종대로 110"), poi("시청 별관", 37.564, 126.975),
            {"name": "좌표없음"}] + [poi(f"더{i}", 37.5 + i / 100, 127.0) for i in range(6)]
    call, paths = fake_call(pois=pois)
    monkeypatch.setattr(tmap, "_call", call)
    got = tmap.search_places("서울시청", 5)
    assert paths == ["pois"]  # 주소처럼 보이지 않으면 장소 검색만 부른다
    assert len(got) == 5 and got[0] == {"name": "서울특별시청", "address": "서울 중구 세종대로 110", "lat": 37.566704, "lng": 126.978382}
    assert got[1]["address"] == "서울 중구 태평로1가 31"  # 도로명 주소가 없으면 지번
    assert all(g["name"] != "좌표없음" for g in got)  # 좌표가 없는 항목은 건너뛴다


def test_road_address_returns_exact_hit_first_then_places(monkeypatch):
    pois = [poi("서울 도봉구 노해로 341", 37.6514, 127.0459),  # 정확한 번지와 같은 위치: 중복으로 빠진다
            poi("서울 도봉구 노해로 343-1", 37.6520, 127.0461), poi("신원리베르텔 상가", 37.6530, 127.0470)]
    call, paths = fake_call(pois=pois)
    monkeypatch.setattr(tmap, "_call", call)
    got = tmap.search_places("서울 도봉구 노해로 342", 5)
    assert paths == ["geo/fullAddrGeo", "pois"]
    assert got[0] == {"name": "신원리베르텔", "address": "서울 도봉구 노해로 341", "lat": 37.651445, "lng": 127.045912}
    assert [g["name"] for g in got[1:]] == ["서울 도봉구 노해로 343-1", "신원리베르텔 상가"]


def test_address_not_found_is_not_an_outage(monkeypatch):
    err = tmap.TmapError("티맵 응답 400", 400, '{"error":{"message":"해당 주소 정보가 존재하지 않습니다."}}')
    call, _ = fake_call(address=err, pois=[poi("서울 도봉구 노해로 343", 37.652, 127.046)])
    monkeypatch.setattr(tmap, "_call", call)
    assert [g["name"] for g in tmap.search_places("도봉구 노해로 437", 5)] == ["서울 도봉구 노해로 343"]  # 주소는 못 찾아도 장소 결과는 나온다

    other = tmap.TmapError("티맵 응답 429 호출 한도 초과", 429, "")
    call, _ = fake_call(address=other)
    monkeypatch.setattr(tmap, "_call", call)
    with pytest.raises(tmap.TmapError):  # 진짜 오류는 그대로 올린다
        tmap.search_places("서울 도봉구 노해로 342", 5)


def test_search_places_empty(monkeypatch):
    monkeypatch.setattr(tmap, "_call", lambda *a, **k: {})
    assert tmap.search_places("없는곳") == []


def test_geocode_order(monkeypatch):
    # 주소처럼 보이면 주소 변환(정확한 번지)을 먼저 쓴다
    call, paths = fake_call(pois=[poi("엉뚱한 옆 번지", 37.0, 127.0)])
    monkeypatch.setattr(tmap, "_call", call)
    assert tmap.geocode("서울 도봉구 노해로 342") == (37.651445, 127.045912) and paths == ["geo/fullAddrGeo"]
    # 장소 이름이면 장소 검색 첫 결과를 먼저 쓴다
    call, paths = fake_call(pois=[poi("서울특별시청", 37.5667, 126.9784)])
    monkeypatch.setattr(tmap, "_call", call)
    assert tmap.geocode("서울시청") == (37.5667, 126.9784) and paths == ["pois"]
    # 먼저 쓴 쪽에 없으면 다른 쪽으로 보완하고, 둘 다 없으면 LookupError
    call, paths = fake_call(address={}, pois=[])
    monkeypatch.setattr(tmap, "_call", call)
    with pytest.raises(LookupError):
        tmap.geocode("없는주소")
    assert paths == ["pois", "geo/fullAddrGeo"]


def test_no_content_response_is_empty_result_not_error(monkeypatch):
    """티맵은 장소 검색 결과가 없으면 204로 응답한다. 장애로 취급하면 안 된다."""

    class Resp:
        status_code, content, text = 204, b"", ""

    monkeypatch.setattr(tmap, "configured", lambda: True)
    monkeypatch.setattr(tmap.httpx, "request", lambda *a, **k: Resp())
    assert tmap.search_places("없는곳없는곳") == []
    with pytest.raises(LookupError):
        tmap.geocode("없는곳없는곳")
