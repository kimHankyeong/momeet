"""
발표용 비교: 지도상 중간지점 vs 총 이동시간 최소 vs momeet(가장 오래 걸리는 사람 기준)

실행 (backend 폴더에서):
    python -m scripts.compare_midpoint                  # 시연 시나리오 1개 비교
    python -m scripts.compare_midpoint --random 300     # 무작위 그룹 300개 통계

비교 방식 (장소만 비교, 시간 조건은 빼고 각자 기본 출발역 기준)
    지도 중간지점 : 출발역 좌표 평균에서 가장 가까운 역
    총합 최소     : 전원 이동시간 합이 가장 작은 역
    momeet        : 가장 오래 걸리는 사람의 이동시간이 가장 작은 역 (같으면 총합)
각 방식 모두 이동시간 계산은 같은 경로 계산(subway.py)을 쓰고,
엘리베이터 필요한 사람은 엘리베이터 경로·환승 가중치를 똑같이 적용한다.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from app.core import subway

SCENARIO = Path(__file__).resolve().parent.parent / "data" / "demo" / "scenario.json"


def _needs_elevator(p: dict) -> bool:
    c = p.get("constraints", {})
    return any(c.get(k, {}).get("value") for k in ("needs_elevator", "avoid_stairs"))


def _travel_table(people: list[dict]) -> dict[str, dict[str, int]]:
    """참여자별 {역: 이동시간(분)}"""
    return {
        p["id"]: {name: r.minutes for name, r in
                  subway.routes_from(p["default_station"], needs_elevator=_needs_elevator(p)).items()}
        for p in people
    }


def _nearest_station(lat: float, lng: float) -> str:
    stations = subway._load()[0]
    return min(stations, key=lambda s: (s["lat"] - lat) ** 2 + ((s["lng"] - lng) * math.cos(math.radians(lat))) ** 2)["name"]


def _required_ok(p: dict, station: str, minutes: int) -> bool:
    """장소 기준으로 확인 가능한 필수 조건 (최대 이동시간, 엘리베이터·계단 회피)"""
    req = {k: c["value"] for k, c in p.get("constraints", {}).items() if c.get("level") == "required"}
    if "max_travel_min" in req and minutes > req["max_travel_min"]:
        return False
    if (req.get("needs_elevator") or req.get("avoid_stairs")) and subway.station_accessibility(station) != "met":
        return False
    return True


def compare(people: list[dict]) -> dict:
    table = _travel_table(people)
    reachable = set.intersection(*(set(t) for t in table.values()))

    def summary(station: str) -> dict:
        mins = {pid: table[pid][station] for pid in table}
        return {
            "station": station,
            "minutes": mins,
            "max": max(mins.values()),
            "total": sum(mins.values()),
            "gap": max(mins.values()) - min(mins.values()),
            "violations": sum(not _required_ok(p, station, mins[p["id"]]) for p in people),
        }

    coords = [subway.get_station(p["default_station"]) for p in people]
    mid = _nearest_station(sum(c["lat"] for c in coords) / len(coords), sum(c["lng"] for c in coords) / len(coords))

    # momeet은 필수 조건을 맞추는 역 중에서 고름 (실제 추천과 같은 규칙)
    allowed = [s for s in reachable if all(_required_ok(p, s, table[p["id"]][s]) for p in people)] or list(reachable)
    momeet = min(allowed, key=lambda s: (max(table[p][s] for p in table), sum(table[p][s] for p in table), s))
    total_min = min(reachable, key=lambda s: (sum(table[p][s] for p in table), s))

    return {"지도 중간지점": summary(mid), "총합 최소": summary(total_min), "momeet": summary(momeet)}


def print_compare(result: dict, names: list[str]) -> None:
    print(f"{'방식':<10}{'역':<12}" + "".join(f"{n:>8}" for n in names) + f"{'최대':>6}{'총합':>6}{'격차':>6}{'필수위반':>8}")
    for label, r in result.items():
        row = "".join(f"{r['minutes'][n]:>7}분" for n in names)
        print(f"{label:<10}{r['station']:<12}{row}{r['max']:>5}분{r['total']:>5}분{r['gap']:>5}분{r['violations']:>6}명")


def random_groups(n: int, seed: int = 42) -> None:
    rnd = random.Random(seed)
    names = [s["name"] for s in subway._load()[0]]
    stats = {k: {"max": 0, "total": 0, "gap": 0} for k in ("지도 중간지점", "총합 최소", "momeet")}
    over60 = {k: 0 for k in stats}
    worse = 0
    for _ in range(n):
        people = [{"id": f"p{i}", "default_station": s, "constraints": {}}
                  for i, s in enumerate(rnd.sample(names, rnd.randint(3, 5)))]
        res = compare(people)
        for k, r in res.items():
            for m in ("max", "total", "gap"):
                stats[k][m] += r[m]
            over60[k] += r["max"] > 60
        worse += res["지도 중간지점"]["max"] > res["momeet"]["max"]

    print(f"무작위 그룹 {n}개 (3~5명, 1~9호선·우이신설선 역에서 무작위 출발)\n")
    print(f"{'방식':<10}{'평균 최대':>10}{'평균 총합':>10}{'평균 격차':>10}{'최대 60분 초과':>14}")
    for k, s in stats.items():
        print(f"{k:<10}{s['max'] / n:>9.1f}분{s['total'] / n:>9.1f}분{s['gap'] / n:>9.1f}분{over60[k] / n * 100:>12.0f}%")
    print(f"\n지도 중간지점이 momeet보다 '가장 오래 걸리는 사람'을 더 오래 걸리게 한 경우: {worse / n * 100:.0f}%")


def main() -> None:
    if "--random" in sys.argv:
        idx = sys.argv.index("--random")
        n = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 300
        random_groups(n)
        return
    sc = json.loads(SCENARIO.read_text(encoding="utf-8"))
    people = [{"id": p["name"], **p["conditions"]} for p in sc["participants"]]
    print(f"[{sc['title']}] 출발역: " + ", ".join(f"{p['id']}({p['default_station']})" for p in people) + "\n")
    print_compare(compare(people), [p["id"] for p in people])


if __name__ == "__main__":
    main()
