"""
지하철 경로 계산 (수도권 전철: 1~9호선, 광역철도, 경전철, GTX-A)
서울교통공사 구간 밖(9호선·우이신설·광역철도 등) 운행시간은 거리로 추정한 값 (edges.json의 estimated=True)

데이터: backend/data/stations.json, edges.json, transfers.json
        (scripts/build_subway_data.py 로 생성)

그래프
    노드  = 역 × 노선 (예: 강남_2). 같은 역도 노선이 다르면 다른 노드 → 환승 횟수 계산 가능
    간선1 = 같은 노선 인접역, 비용 = 운행시간 + 정차시간
    간선2 = 같은 역 다른 노선(환승), 비용 = 환승 보행시간 + 환승 대기시간

주요 함수
    find_route(출발역, 도착역, ...)         두 역 사이 최단 경로 1개
    routes_from(출발역, ...)                 출발역 → 모든 역 최단 경로 (추천용, 1번 계산)
    travel_matrix(참여자별 출발역, 후보역)   참여자 × 후보역 이동정보 표
    search_stations(검색어)                  역 자동완성
"""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# ------------------------------------------------------------------ 가정값
# 표준 운행시간 데이터에는 정차시간과 환승 대기시간이 없어서 아래 값을 더한다.
DWELL_SEC = 30            # 역마다 정차시간
TRANSFER_WAIT_SEC = 180   # 환승 후 열차 대기시간 (평균)
MAX_TRANSFERS_LIMIT = 4   # 탐색할 최대 환승 횟수

# 도보 거리 → 도보 시간 환산 (분). 환승 데이터와 같은 보행속도 1.2m/s = 분당 72m
WALK_M_PER_MIN = 72


def walk_minutes(meters: int) -> int:
    """도보 거리(m) → 도보 시간(분, 올림). 프론트의 '최대 도보 거리 10분' 같은 조건 비교용"""
    return math.ceil(meters / WALK_M_PER_MIN) if meters > 0 else 0


# 출발 위치 → 출발역 도보 추정. 실제 길은 직선보다 돌아가므로 직선거리에 1.3배
WALK_DETOUR = 1.3
MAX_ACCESS_M = 3000  # 출발 위치는 출발역에서 걸어갈 만한 거리 안이어야 함 (도보 약 40분)


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이 직선거리(m)"""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def access_walk(lat: float, lng: float, station: str) -> tuple[int, int]:
    """출발 위치 → 출발역 예상 도보 (거리 m, 시간 분)"""
    st = get_station(station)
    meters = round(distance_m(lat, lng, st["lat"], st["lng"]) * WALK_DETOUR)
    return meters, walk_minutes(meters)


# 엘리베이터가 필요한 사용자의 환승 보행시간 배율.
# 근거: '모두의 지하철 프로젝트'(무의·서울시·서울교통공사, 2025) 실증조사에서
#       휠체어 이용자 환승 평균 19분 vs 비장애인 평균 3.3분 → 약 5.7배
ACCESSIBLE_TRANSFER_FACTOR = 5.7


# ------------------------------------------------------------------ 결과 형식
@dataclass
class Segment:
    """같은 노선을 타고 가는 한 구간"""
    line: str
    board: str        # 탑승역
    alight: str       # 하차역
    stops: int        # 정차 역 수
    minutes: int


@dataclass
class Route:
    origin: str
    destination: str
    minutes: int                  # 총 예상 이동시간 (올림)
    transfers: int                # 환승 횟수
    walk_m: int                   # 환승 보행거리 합
    segments: list[Segment] = field(default_factory=list)
    path: list[str] = field(default_factory=list)  # 지나가는 노드 ID 순서

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ 데이터 로드
@lru_cache(maxsize=1)
def _load():
    with open(DATA_DIR / "stations.json", encoding="utf-8") as f:
        stations = json.load(f)
    with open(DATA_DIR / "edges.json", encoding="utf-8") as f:
        edges = json.load(f)
    with open(DATA_DIR / "transfers.json", encoding="utf-8") as f:
        transfers = json.load(f)

    by_name = {}       # 역명/별칭 → 역 정보
    node_info = {}     # 노드 ID → (역명, 노선, 접근성)
    for st in stations:
        by_name[st["name"]] = st
        for alias in st.get("aliases", []):
            by_name[alias] = st
        for n in st["nodes"]:
            node_info[n["id"]] = (st["name"], n["line"], n["accessibility"])

    # 인접 리스트: node → [(다음 node, 초, 종류, 보행m)]
    graph: dict[str, list[tuple[str, int, str, int]]] = {}
    for e in edges:
        cost = e["seconds"] + DWELL_SEC
        graph.setdefault(e["from"], []).append((e["to"], cost, "ride", 0))
        if not e["oneway"]:
            graph.setdefault(e["to"], []).append((e["from"], cost, "ride", 0))
    for t in transfers:
        graph.setdefault(t["from"], []).append((t["to"], t["seconds"], "transfer", t["meters"]))

    return stations, by_name, node_info, graph


def _has_elevator(node_id: str) -> bool:
    _, _, node_info, _ = _load()
    acc = node_info[node_id][2]
    return bool(acc) and acc.get("elevator", 0) > 0


# ------------------------------------------------------------------ 역 조회
def get_station(name: str) -> dict:
    """역명 또는 별칭(예: 이수)으로 역 정보 조회. 없으면 KeyError"""
    _, by_name, _, _ = _load()
    key = name.strip().replace(" ", "").removesuffix("역") if name.strip() != "서울역" else "서울역"
    if key in by_name:
        return by_name[key]
    if name.strip() in by_name:
        return by_name[name.strip()]
    if f"{key}역" in by_name:  # "서울" → 서울역 (이름 자체가 '역'으로 끝나는 역)
        return by_name[f"{key}역"]
    raise KeyError(f"범위 밖이거나 없는 역: {name}")


def search_stations(query: str, limit: int = 10) -> list[dict]:
    """역 자동완성: 앞부분 일치 우선, 그다음 포함. 별칭으로도 검색됨"""
    stations, _, _, _ = _load()
    q = query.strip().replace(" ", "")
    if q.endswith("역") and q != "서울역":
        q = q[:-1]  # "신설동역" → "신설동" (화면에 역 붙여서 보여주므로 그대로 검색해도 되게)
    if not q:
        return []
    prefix, contains = [], []
    for st in stations:
        names = [st["name"], *st.get("aliases", [])]
        item = {"name": st["name"], "lines": st["lines"], "lat": st["lat"], "lng": st["lng"]}
        if any(n.startswith(q) for n in names):
            prefix.append(item)
        elif any(q in n for n in names):
            contains.append(item)
    return (prefix + contains)[:limit]


def nearby_stations(lat: float, lng: float, limit: int = 3) -> list[dict]:
    """
    출발 위치 근처 역 (가까운 순). 걸어갈 만한 거리(MAX_ACCESS_M) 안의 역만.
    walk_m / walk_min 은 access_walk 와 같은 추정 (직선거리 × WALK_DETOUR)
    """
    stations, _, _, _ = _load()
    found = []
    for st in stations:
        if st["lat"] is None:
            continue
        meters = round(distance_m(lat, lng, st["lat"], st["lng"]) * WALK_DETOUR)
        if meters <= MAX_ACCESS_M:
            found.append({"name": st["name"], "lines": st["lines"], "lat": st["lat"], "lng": st["lng"],
                          "walk_m": meters, "walk_min": walk_minutes(meters)})
    found.sort(key=lambda s: s["walk_m"])
    return found[:limit]


def path_stops(path: list[str]) -> list[dict]:
    """
    지나가는 노드 ID 목록 → 지도에 그릴 역 목록 [{name, line, lat, lng}].
    환승역은 노선이 바뀌므로 같은 역이 두 번 나온다 (예: 동대문역사문화공원 4호선 → 5호선)
    """
    _, by_name, node_info, _ = _load()
    stops = []
    for nid in path:
        name, line, _ = node_info[nid]
        st = by_name[name]
        stops.append({"name": name, "line": line, "lat": st["lat"], "lng": st["lng"]})
    return stops


# ------------------------------------------------------------------ 최단경로
def _dijkstra(origin: str, needs_elevator: bool, max_transfers: int | None):
    """
    출발역의 모든 노선 노드에서 동시에 시작하는 다익스트라.
    상태 = (노드, 환승 횟수) → 환승 횟수 제한을 정확히 지킬 수 있음.
    비교 순서: 이동시간 → 환승 횟수
    """
    _, _, _, graph = _load()
    limit = MAX_TRANSFERS_LIMIT if max_transfers is None else min(max_transfers, MAX_TRANSFERS_LIMIT)
    start = get_station(origin)

    best: dict[tuple[str, int], tuple[float, int]] = {}  # 상태 → (초, 보행m)
    prev: dict[tuple[str, int], tuple[str, int] | None] = {}
    pq = []
    for n in start["nodes"]:
        state = (n["id"], 0)
        best[state] = (0, 0)
        prev[state] = None
        heapq.heappush(pq, (0, 0, 0, n["id"]))

    done = set()
    while pq:
        sec, tr, walk, node = heapq.heappop(pq)
        state = (node, tr)
        if state in done:
            continue
        done.add(state)

        for nxt, cost, kind, meters in graph.get(node, []):
            ntr = tr
            if kind == "transfer":
                ntr += 1
                if ntr > limit:
                    continue
                if needs_elevator and not (_has_elevator(node) and _has_elevator(nxt)):
                    continue
                walk_sec = cost * (ACCESSIBLE_TRANSFER_FACTOR if needs_elevator else 1)
                cost = walk_sec + TRANSFER_WAIT_SEC
            nstate = (nxt, ntr)
            nsec = sec + cost
            if nstate not in best or nsec < best[nstate][0]:
                best[nstate] = (nsec, walk + meters)
                prev[nstate] = state
                heapq.heappush(pq, (nsec, ntr, walk + meters, nxt))
    return best, prev


def _build_route(origin: str, dest_name: str, end_state, best, prev) -> Route:
    _, _, node_info, _ = _load()
    states = []
    s = end_state
    while s is not None:
        states.append(s)
        s = prev[s]
    states.reverse()
    nodes = [n for n, _ in states]

    # 노드 순서 → 노선별 구간으로 묶기
    segments: list[Segment] = []
    seg_start, seg_sec = 0, 0.0
    for i in range(1, len(nodes) + 1):
        end_of_seg = i == len(nodes) or node_info[nodes[i]][1] != node_info[nodes[i - 1]][1]
        if i < len(nodes) and not end_of_seg:
            continue
        if i - 1 > seg_start:  # 실제로 이동한 구간만
            sec = best[states[i - 1]][0] - best[states[seg_start]][0]
            segments.append(Segment(
                line=node_info[nodes[seg_start]][1],
                board=node_info[nodes[seg_start]][0],
                alight=node_info[nodes[i - 1]][0],
                stops=i - 1 - seg_start,
                minutes=math.ceil(sec / 60),
            ))
        seg_start = i

    total_sec, walk = best[end_state]
    return Route(
        origin=get_station(origin)["name"],
        destination=dest_name,
        minutes=math.ceil(total_sec / 60),
        transfers=end_state[1],
        walk_m=walk,
        segments=segments,
        path=nodes,
    )


def _pick_best_state(dest: dict, best) -> tuple[str, int] | None:
    """도착역의 어떤 노선 노드든 도착하면 됨 → (시간, 환승) 가장 작은 상태"""
    ids = {n["id"] for n in dest["nodes"]}
    cands = [(v[0], s[1], s) for s, v in best.items() if s[0] in ids]
    return min(cands)[2] if cands else None


def find_route(origin: str, destination: str,
               needs_elevator: bool = False,
               max_transfers: int | None = None) -> Route | None:
    """두 역 사이 최단 경로. 조건을 만족하는 경로가 없으면 None"""
    dest = get_station(destination)
    if get_station(origin)["name"] == dest["name"]:
        return Route(origin=dest["name"], destination=dest["name"], minutes=0, transfers=0, walk_m=0)
    best, prev = _dijkstra(origin, needs_elevator, max_transfers)
    end = _pick_best_state(dest, best)
    return _build_route(origin, dest["name"], end, best, prev) if end else None


def routes_from(origin: str,
                needs_elevator: bool = False,
                max_transfers: int | None = None,
                candidates: list[str] | None = None) -> dict[str, Route]:
    """
    출발역 → 모든 역(또는 candidates) 최단 경로.
    다익스트라 1번으로 전체를 구하므로 추천 계산에서 참여자당 1번만 호출하면 됨.
    도달 불가한 역은 결과에서 빠짐.
    """
    stations, _, _, _ = _load()
    origin_name = get_station(origin)["name"]
    targets = [get_station(c) for c in candidates] if candidates else stations
    best, prev = _dijkstra(origin, needs_elevator, max_transfers)

    result = {}
    for dest in targets:
        if dest["name"] == origin_name:
            result[dest["name"]] = Route(origin=origin_name, destination=origin_name,
                                         minutes=0, transfers=0, walk_m=0)
            continue
        end = _pick_best_state(dest, best)
        if end:
            result[dest["name"]] = _build_route(origin, dest["name"], end, best, prev)
    return result


def travel_matrix(origins: dict[str, dict], candidates: list[str] | None = None) -> dict[str, dict[str, Route]]:
    """
    참여자 × 후보역 이동정보 표.

    origins 예시:
        {
          "p1": {"station": "쌍문", "needs_elevator": False, "max_transfers": None},
          "p2": {"station": "수유", "needs_elevator": True,  "max_transfers": 1},
        }
    반환: {"p1": {"창동": Route, ...}, "p2": {...}}
    """
    return {
        pid: routes_from(
            o["station"],
            needs_elevator=o.get("needs_elevator", False),
            max_transfers=o.get("max_transfers"),
            candidates=candidates,
        )
        for pid, o in origins.items()
    }


def station_accessibility(name: str) -> str:
    """역 단위 엘리베이터 상태: met / unmet / unknown (fairness.py 필수 조건 판단용)"""
    return get_station(name).get("elevator", "unknown")


if __name__ == "__main__":
    # 간단 확인: python -m app.core.subway  (backend 폴더에서)
    for a, b in [("쌍문", "강남"), ("방화", "잠실"), ("이수", "노원")]:
        r = find_route(a, b)
        print(f"{a} → {b}: {r.minutes}분, 환승 {r.transfers}회, 보행 {r.walk_m}m")
        for s in r.segments:
            print(f"   {s.line}호선 {s.board} → {s.alight} ({s.stops}개 역, {s.minutes}분)")
