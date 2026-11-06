"""
시연 시나리오 실행: data/demo/scenario.json 의 4명 조건으로 실제 추천을 돌려서 화면에 나올 내용을 출력

실행 (backend 폴더에서):
    python -m scripts.demo_scenario

시나리오 파일의 participants[].conditions 는 조건 입력 API에 보내는 형식과 같아서
시드 데이터나 프론트 mock으로 그대로 쓸 수 있음
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from app.core import subway
from app.core.fairness import get_my_route, recommend, validate_conditions, view_for

SCENARIO = Path(__file__).resolve().parent.parent / "data" / "demo" / "scenario.json"
WEEKDAY = "월화수목금토일"


def _dates(start: str, end: str) -> list[str]:
    d, e = date.fromisoformat(start), date.fromisoformat(end)
    return [(d + timedelta(days=i)).isoformat() for i in range((e - d).days + 1)]


def _label(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.month}월 {x.day}일({WEEKDAY[x.weekday()]})"


def _lines(station: str) -> str:
    """['2', '5'] → '2·5호선', ['1', '2', '우이신설'] → '1·2호선·우이신설선'"""
    lines = subway.get_station(station)["lines"]
    nums = [l for l in lines if l.isdigit()]
    others = [l + "선" for l in lines if not l.isdigit()]
    return "·".join(([("·".join(nums) + "호선")] if nums else []) + others)


def main() -> None:
    sc = json.loads(SCENARIO.read_text(encoding="utf-8"))
    dates = _dates(sc["date_start"], sc["date_end"])
    print(f"[{sc['title']}] {_label(dates[0])} ~ {_label(dates[-1])}\n")

    participants = []
    for p in sc["participants"]:
        errors, clean = validate_conditions(p["conditions"], dates, final=True)
        if errors:
            raise SystemExit(f"{p['name']} 조건 오류: {errors}")
        participants.append({"id": p["name"], **clean})
        print(f"- {p['name']}: {p['persona']}")
    print()

    result = recommend(participants, dates)
    if result["status"] != "ok":
        print("추천 후보 없음")
        for r in result["reasons"]:
            print(f"  {r['date']} {r['message']}")
        return

    print("추천 후보 (전체 최적 순)")
    for c in result["candidates"]:
        mark = "★" if c["candidate_id"] == result["best"] else " "
        legs = ", ".join(f"{pid} {leg['minutes']}분" for pid, leg in c["legs"].items())
        print(f"{mark}{c['rank']}. {_label(c['date'])} {c['start']}  {c['station']}역 ({_lines(c['station'])})"
              f"  최대 {c['max_minutes']}분 | {legs}")

    best = result["best"]
    print(f"\n1등 후보 각자 화면 (본인 경로만 보임)")
    for p in participants:
        v = view_for(result, p["id"])
        me = get_my_route(result, best, p["id"])
        path = " → ".join([me["segments"][0]["board"]] + [s["alight"] for s in me["segments"]]) if me["segments"] else me["origin"]
        if me.get("access"):
            path = f"출발 위치 (도보 {me['access']['minutes']}분) → " + path
        print(f"- {p['id']}: {me['origin']}에서 {me['depart_at']} 출발 예상, {me['minutes']}분, "
              f"환승 {me['transfers']}회, 도보 {me['walk_m']}m(약 {me['walk_min']}분)  [{path}]  (후보 {len(v['candidates'])}개 조회)")


if __name__ == "__main__":
    main()
