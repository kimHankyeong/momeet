"""
지하철 원본 데이터 → momeet 정제 JSON 변환 스크립트

범위: 서울교통공사 1~8호선 + 9호선 + 우이신설선
     (1호선은 서울역~청량리 구간만, 코레일 구간 제외)

실행 (backend 폴더에서):
    python scripts/build_subway_data.py

입력 (backend/data/raw/):
    edges_raw.csv          서울교통공사_역간거리 및 소요시간 (1~8호선, 운행시간 있음)
    transfers_raw.csv      서울교통공사_환승역거리 소요시간 정보
    stations_raw.csv       서울시 역사마스터 정보 (좌표)
    accessibility_raw.xlsx 서울교통공사 역별 승강설비현황 (엘리베이터·휠체어리프트)
    line9_dist_raw.csv     국가철도공단_수도권9호선_역간거리 (거리만 있음)
    ui_dist_raw.csv        국가철도공단_우이신설선_역간거리 (거리만 있음)
    elevator_points_raw.csv 서울시 지하철역 엘리베이터 위치정보 (9호선·우이신설 엘리베이터 유무 판단용)

출력 (backend/data/):
    stations.json   물리 역 목록 (역명, 노선, 좌표, 노선별 접근성)
    edges.json      같은 노선 인접역 간 운행시간 (estimated=True면 거리로 추정한 값)
    transfers.json  같은 역 노선 간 환승 거리·시간
"""

import csv
import json
import re
import sys
from pathlib import Path

import openpyxl

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
OUT = BASE / "data"

METRO_LINES = [str(i) for i in range(1, 9)]  # 서울교통공사 1~8호선: 공식 운행시간
# 운행시간이 없어 거리로 추정하는 노선: 노선 ID → 원본 파일
DISTANCE_LINES = {
    "9": "line9_dist_raw.csv",
    "우이신설": "ui_dist_raw.csv",
}
LINES = METRO_LINES + list(DISTANCE_LINES)

# 데이터마다 표기가 다른 역명 → 대표 역명
ALIASES = {
    "신내역": "신내",
    "이수": "총신대입구",      # 4호선 총신대입구 = 7호선 이수 (같은 역)
    "당고개": "불암산",        # 역명 변경 (역간 데이터는 옛 이름)
    "뚝섬유원지": "자양",      # 역명 변경 (역간·좌표 데이터는 옛 이름)
}

# 0:00으로 시작하지 않는 지선 구간: (호선, 지선 첫 역) → 분기역
BRANCH_START = {
    ("2", "용답"): "성수",      # 성수지선 성수-용답-신답-용두-신설동
    ("2", "도림천"): "신도림",  # 신정지선 신도림-도림천-양천구청-신정네거리-까치산
    ("5", "둔촌동"): "강동",    # 마천지선 강동-둔촌동-...-마천
}

# 공공데이터에 없어서 팀이 직접 확인한 접근성 정보 (노드 ID → 정보)
# elevator 1 = 대수는 모르고 '있음'만 확인
MANUAL_ACCESSIBILITY = {
    "삼전_9": {"elevator": 1, "source": "manual"},  # 엘리베이터 위치정보에 없음, 팀 확인 (2026-11-04)
}

# 6호선 응암순환 구간은 응암→역촌→불광→독바위→연신내→구산→응암 한 방향만 운행
ONEWAY_LOOP = ("6", "응암")


def norm(name: str) -> str:
    """역명 정규화: 공백 제거, 괄호(부역명·호선표기) 제거, 별칭 통일"""
    name = name.strip().replace(" ", "")
    name = re.sub(r"\(.*?\)", "", name)
    return ALIASES.get(name, name)


def norm_line(text: str) -> str | None:
    """'4호선', '04호선', '9호선(연장)', '우이신설선', '5(연)' → 노선 ID. 범위 밖이면 None"""
    text = text.strip()
    if text.startswith("우이신설"):
        return "우이신설"
    m = re.match(r"0?(\d)(호선)?(\(.*\))?$", text)
    if m and m.group(1) in LINES:
        return m.group(1)
    return None


def node_id(name: str, line: str) -> str:
    return f"{name}_{line}"


def to_seconds(text: str) -> int:
    """'1:30' 또는 '02:13' → 초"""
    m, s = text.strip().split(":")
    return int(m) * 60 + int(s)


def read_csv(path: Path):
    for enc in ("cp949", "utf-8-sig"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    sys.exit(f"[오류] 인코딩을 읽을 수 없음: {path}")


def require(path: Path) -> Path:
    if not path.exists():
        sys.exit(f"[오류] 파일 없음: {path}\n  data/raw/ 에 파일명을 맞춰 넣어주세요.")
    return path


# ---------------------------------------------------------------- 1~8호선 역간 운행시간
def build_metro_edges():
    rows = read_csv(require(RAW / "edges_raw.csv"))
    edges, nodes = [], {}
    prev = {}          # 호선별 직전 역
    loop_open = False  # 6호선 응암순환 진행 중 여부

    for r in rows:
        line = r["호선"].strip()
        if line not in METRO_LINES:
            continue
        name = norm(r["역명"])
        sec = to_seconds(r["운행시간"])
        km = float(r["역간거리(km)"] or 0)
        nodes.setdefault(node_id(name, line), (name, line))

        if sec == 0:  # 노선(구간) 시작
            prev[line] = name
            loop_open = (line, name) == ONEWAY_LOOP
            continue

        frm = BRANCH_START.get((line, name), prev[line])
        oneway = loop_open and line == ONEWAY_LOOP[0]
        edges.append({
            "from": node_id(frm, line),
            "to": node_id(name, line),
            "line": line,
            "seconds": sec,
            "km": km,
            "oneway": oneway,
            "estimated": False,
        })
        if oneway and name == ONEWAY_LOOP[1]:
            loop_open = False  # 응암으로 돌아오면 순환 종료
        prev[line] = name

    return edges, nodes


def fit_time_model(edges):
    """
    1~8호선 실제 운행시간으로 '거리 → 시간' 환산식 추정 (최소제곱 직선)
    운행시간(초) = a + b × 거리(km)
    """
    pts = [(e["km"], e["seconds"]) for e in edges if e["km"] > 0]
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    b = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
    a = my - b * mx
    return a, b


# ---------------------------------------------------------------- 9호선·우이신설 (거리 → 시간 추정)
def build_distance_edges(nodes, a, b):
    """
    원본은 노선 순서대로 역이 나열되고, 각 행의 역간거리 = 다음 역까지 거리
    (마지막 역은 빈칸). 9호선은 일반열차 기준이며 급행은 반영하지 않음.
    """
    edges = []
    for line, fname in DISTANCE_LINES.items():
        rows = read_csv(require(RAW / fname))
        names = [norm(r["역명"]) for r in rows]
        for i, r in enumerate(rows):
            nodes.setdefault(node_id(names[i], line), (names[i], line))
            dist = (r.get("역간거리") or "").strip()
            if i + 1 >= len(rows) or not dist:
                continue
            km = float(dist)
            edges.append({
                "from": node_id(names[i], line),
                "to": node_id(names[i + 1], line),
                "line": line,
                "seconds": round(a + b * km),
                "km": km,
                "oneway": False,
                "estimated": True,
            })
    return edges


# ---------------------------------------------------------------- 환승
def build_transfers(nodes):
    rows = read_csv(require(RAW / "transfers_raw.csv"))
    transfers, skipped = {}, []

    for r in rows:
        line = r["호선"].strip()
        to_line = norm_line(r["환승노선"])
        name = norm(r["환승역명"])
        if line == to_line:
            continue  # 같은 호선 지선 연결(성수, 강동)은 역간 데이터로 이미 연결됨
        frm, to = node_id(name, line), node_id(name, to_line or "")
        if to_line is None or frm not in nodes or to not in nodes:
            skipped.append(f"{name} {line}→{r['환승노선'].strip()}")
            continue
        transfers[(frm, to)] = {
            "station": name,
            "from": frm,
            "to": to,
            "meters": int(r["환승거리"]),
            "seconds": to_seconds(r["환승소요시간"]),
        }

    # 9호선·우이신설선 쪽에서 1~8호선으로 가는 방향은 원본에 없음 → 반대 방향 값을 그대로 사용
    for (frm, to), t in list(transfers.items()):
        if (to, frm) not in transfers:
            transfers[(to, frm)] = {**t, "from": to, "to": frm}

    return list(transfers.values()), skipped


# ---------------------------------------------------------------- 좌표
def load_coords():
    rows = read_csv(require(RAW / "stations_raw.csv"))
    coords = {}
    for r in rows:
        line = norm_line(r["호선"])
        if line is None:
            continue
        coords[node_id(norm(r["역사명"]), line)] = (float(r["위도"]), float(r["경도"]))
    return coords


# ---------------------------------------------------------------- 접근성 (서울교통공사 1~8호선만 있음)
def load_accessibility():
    wb = openpyxl.load_workbook(require(RAW / "accessibility_raw.xlsx"), data_only=True)
    ws = wb["역별승강설비현황"]
    acc = {}
    for r in ws.iter_rows(min_row=4, values_only=True):
        m = re.match(r"(\d)", str(r[0] or ""))  # '5(연)' 같은 연장구간 표기 처리
        name = r[1]
        if not name or not m or m.group(1) not in METRO_LINES:
            continue
        line = m.group(1)
        el, es, mw, wl, vl = (int(v or 0) for v in r[2:7])
        acc[node_id(norm(str(name)), line)] = {
            "elevator": el,
            "escalator": es,
            "wheelchair_lift": wl + vl,  # 휠체어리프트 + 수직형리프트
        }
    return acc


def add_elevator_points(acc, nodes):
    """
    9호선·우이신설선은 승강설비 대수 자료가 없음.
    서울시 엘리베이터 위치정보에 그 역 이름으로 등록된 엘리베이터가 있으면 '있음'으로 보고
    위치 점 개수를 대수로 사용 (source=elevator_location). 없으면 그대로 unknown.
    """
    counts = {}
    for r in read_csv(require(RAW / "elevator_points_raw.csv")):
        name = (r.get("지하철역명") or "").strip()
        if name:
            counts[norm(name)] = counts.get(norm(name), 0) + 1

    for nid, (name, line) in nodes.items():
        if line in DISTANCE_LINES and nid not in acc and counts.get(name):
            acc[nid] = {"elevator": counts[name], "source": "elevator_location"}

    # 그래도 정보가 없는 역은 팀이 직접 확인한 값으로 채움
    for nid, info in MANUAL_ACCESSIBILITY.items():
        if nid in nodes and nid not in acc:
            acc[nid] = dict(info)
    return acc


# ---------------------------------------------------------------- 물리 역 묶기
def line_order(line: str):
    return (0, int(line)) if line.isdigit() else (1, line)


def build_stations(nodes, coords, acc):
    stations = {}
    for nid, (name, line) in sorted(nodes.items(), key=lambda x: (x[1][0], line_order(x[1][1]))):
        st = stations.setdefault(name, {
            "name": name,
            "aliases": [old for old, new in ALIASES.items() if new == name],  # 역 검색용 (예: 이수)
            "lines": [], "lat": None, "lng": None, "nodes": [],
        })
        st["lines"].append(line)
        st["nodes"].append({
            "id": nid,
            "line": line,
            "accessibility": acc.get(nid),  # None = 정보 없음(unknown)
        })
        if st["lat"] is None and nid in coords:
            st["lat"], st["lng"] = coords[nid]

    for st in stations.values():
        # 환승역은 승강설비가 한 노선 이름으로만 집계된 경우가 있음 (예: 까치산은 5호선 행에만 존재)
        # → 같은 물리 역의 다른 노선 정보를 공유하고 shared=True로 표시
        own = [n["accessibility"] for n in st["nodes"] if n["accessibility"]]
        for n in st["nodes"]:
            if n["accessibility"] is None and own:
                n["accessibility"] = {**own[0], "shared": True}

        known = [n["accessibility"] for n in st["nodes"] if n["accessibility"]]
        if len(known) < len(st["nodes"]):
            st["elevator"] = "unknown"
        else:
            st["elevator"] = "met" if all(k["elevator"] > 0 for k in known) else "unmet"
    return sorted(stations.values(), key=lambda s: s["name"])


def main():
    edges, nodes = build_metro_edges()
    a, b = fit_time_model(edges)
    edges += build_distance_edges(nodes, a, b)
    transfers, skipped = build_transfers(nodes)
    coords = load_coords()
    acc = add_elevator_points(load_accessibility(), nodes)
    stations = build_stations(nodes, coords, acc)

    for fname, data in [("stations.json", stations), ("edges.json", edges), ("transfers.json", transfers)]:
        with open(OUT / fname, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    no_coord = [s["name"] for s in stations if s["lat"] is None]
    unknown = [s["name"] for s in stations if s["elevator"] == "unknown"]

    print(f"노선: {', '.join(LINES)}")
    print(f"노드(역×노선) {len(nodes)}개 / 물리 역 {len(stations)}개")
    print(f"역간 연결 {len(edges)}개 (거리로 추정 {sum(e['estimated'] for e in edges)}개) / 환승 연결 {len(transfers)}개")
    print(f"거리→시간 환산식: 운행시간(초) = {a:.1f} + {b:.1f} × 거리(km)")
    print(f"범위 밖 환승 제외 {len(skipped)}개 (공항철도·경의중앙선·신분당선 등)")
    print(f"좌표 없는 역 {len(no_coord)}개: {no_coord}")
    print(f"엘리베이터 정보 없는 역(unknown) {len(unknown)}개")


if __name__ == "__main__":
    main()