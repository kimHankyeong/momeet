"""장소·주소 검색 (출발지 입력용). 티맵 호출 한도를 지키기 위해 같은 검색어는 잠시 캐시하고, 클라이언트별 호출 수를 제한한다."""
import logging
import threading
import time
from collections import deque

from app.errors import AppError
from app.integrations import tmap

log = logging.getLogger("momeet")

MAX_RESULTS = 5
CACHE_TTL_SEC = 600
CACHE_MAX = 200
RATE_LIMIT = 30     # 클라이언트당 티맵 호출(캐시에 없는 검색) 횟수
RATE_WINDOW_SEC = 60

_lock = threading.Lock()
_cache: dict[str, tuple[float, list[dict]]] = {}
_hits: dict[str, deque] = {}


def reset() -> None:
    """캐시와 호출 기록을 비운다 (테스트용)."""
    with _lock:
        _cache.clear()
        _hits.clear()


def search(client: str, query: str) -> list[dict]:
    q = " ".join(query.split())
    if len(q) < 2:
        return []
    key, now = q.lower(), time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SEC:
            return hit[1]
        hits = _hits.setdefault(client, deque())
        while hits and now - hits[0] > RATE_WINDOW_SEC:
            hits.popleft()
        if len(hits) >= RATE_LIMIT:
            wait = max(1, int(RATE_WINDOW_SEC - (now - hits[0])) + 1)
            raise AppError("RATE_LIMITED", "검색을 너무 자주 했습니다. 잠시 후 다시 시도해 주세요.", 429, {"retry_after": wait})
        hits.append(now)
        if len(_hits) > 1000:  # 오래된 클라이언트 기록 정리
            for k in [k for k, d in _hits.items() if not d or now - d[-1] > RATE_WINDOW_SEC]:
                del _hits[k]
    try:
        places = tmap.search_places(q, MAX_RESULTS)[:MAX_RESULTS]
    except tmap.TmapError as e:
        log.warning("장소 검색 실패: %s", e)
        raise AppError("PLACES_UNAVAILABLE", "장소 검색을 지금 쓸 수 없습니다. 주소를 직접 입력해 주세요.", 503)
    with _lock:
        if len(_cache) >= CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[key] = (now, places)
    return places
