"""
서울교통공사 1~8호선 원본 데이터 → momeet 정제 JSON 변환 스크립트

실행 (backend 폴더에서):
    python scripts/build_subway_data.py

입력 (backend/data/raw/):
    edges_raw.csv          서울교통공사_역간거리 및 소요시간 (cp949)
    transfers_raw.csv      서울교통공사_환승역거리 소요시간 정보 (cp949)
    stations_raw.csv       서울시 역사마스터 정보 (cp949, 좌표)
    accessibility_raw.xlsx 서울교통공사 역별 승강설비현황 (엘리베이터·휠체어리프트)

출력 (backend/data/):
    stations.json   물리 역 목록 (역명, 노선, 좌표, 노선별 접근성)
    edges.json      같은 노선 인접역 간 운행시간
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

LINES = [str(i) for i in range(1, 9)]  # 서비스 범위: 서울교통공사 1~8호선

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

# 6호선 응암순환 구간은 응암→역촌→불광→독바위→연신내→구산→응암 한 방향만 운행
ONEWAY_LOOP = ("6", "응암")


def norm(name: str) -> str:
    """역명 정규화: 공백 제거, 괄호(부역명·호선표기) 제거, 별칭 통일"""
    name = name.strip().replace(" ", "")
    name = re.sub(r"\(.*?\)", "", name)
    return ALIASES.get(name, name)


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


# ---------------------------------------------------------------- 역간 운행시간
def build_edges():
    rows = read_csv(require(RAW / "edges_raw.csv"))
    edges, nodes = [], {}
    prev = {}          # 호선별 직전 역
    loop_open = False  # 6호선 응암순환 진행 중 여부

    for r in rows:
        line = r["호선"].strip()
        if line not in LINES:
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
        })
        if oneway and name == ONEWAY_LOOP[1]:
            loop_open = False  # 응암으로 돌아오면 순환 종료
        prev[line] = name

    return edges, nodes


# ---------------------------------------------------------------- 환승
def build_transfers(nodes):
    rows = read_csv(require(RAW / "transfers_raw.csv"))
    transfers, skipped = [], []

    for r in rows:
        line = r["호선"].strip()
        to_line = r["환승노선"].strip().replace("호선", "")
        name = norm(r["환승역명"])
        if line == to_line:
            continue  # 같은 호선 지선 연결(성수, 강동)은 역간 데이터로 이미 연결됨
        frm, to = node_id(name, line), node_id(name, to_line)
        if to_line not in LINES or frm not in nodes or to not in nodes:
            skipped.append(f"{name} {line}→{r['환승노선'].strip()}")
            continue
        transfers.append({
            "station": name,
            "from": frm,
            "to": to,
            "meters": int(r["환승거리"]),
            "seconds": to_seconds(r["환승소요시간"]),
        })
    return transfers, skipped


# ---------------------------------------------------------------- 좌표
def load_coords():
    rows = read_csv(require(RAW / "stations_raw.csv"))
    coords = {}
    for r in rows:
        m = re.fullmatch(r"0?(\d)호선", r["호선"].strip())
        if not m or m.group(1) not in LINES:
            continue
        coords[node_id(norm(r["역사명"]), m.group(1))] = (
            float(r["위도"]), float(r["경도"]))
    return coords


# ---------------------------------------------------------------- 접근성
def load_accessibility():
    wb = openpyxl.load_workbook(require(RAW / "accessibility_raw.xlsx"), data_only=True)
    ws = wb["역별승강설비현황"]
    acc = {}
    for r in ws.iter_rows(min_row=4, values_only=True):
        m = re.match(r"(\d)", str(r[0] or ""))  # '5(연)' 같은 연장구간 표기 처리
        name = r[1]
        if not name or not m or m.group(1) not in LINES:
            continue
        line = m.group(1)
        el, es, mw, wl, vl = (int(v or 0) for v in r[2:7])
        acc[node_id(norm(str(name)), line)] = {
            "elevator": el,
            "escalator": es,
            "wheelchair_lift": wl + vl,  # 휠체어리프트 + 수직형리프트
        }
    return acc


# ---------------------------------------------------------------- 물리 역 묶기
def build_stations(nodes, coords, acc):
    stations = {}
    for nid, (name, line) in sorted(nodes.items(), key=lambda x: (x[1][0], int(x[1][1]))):
        st = stations.setdefault(name, {
            "name": name,
            "aliases": [old for old, new in ALIASES.items() if new == name],  # 역 검색용 (예: 이수)
            "lines": [], "lat": None, "lng": None, "nodes": [],
        })
        a = acc.get(nid)
        st["lines"].append(line)
        st["nodes"].append({
            "id": nid,
            "line": line,
            "accessibility": a if a else None,  # None = 정보 없음(unknown)
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
    edges, nodes = build_edges()
    transfers, skipped = build_transfers(nodes)
    coords = load_coords()
    acc = load_accessibility()
    stations = build_stations(nodes, coords, acc)

    for fname, data in [("stations.json", stations), ("edges.json", edges), ("transfers.json", transfers)]:
        with open(OUT / fname, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    no_coord = [s["name"] for s in stations if s["lat"] is None]
    no_acc = [n["id"] for s in stations for n in s["nodes"] if n["accessibility"] is None]

    print(f"노드(역×노선) {len(nodes)}개 / 물리 역 {len(stations)}개")
    print(f"역간 연결 {len(edges)}개 / 환승 연결 {len(transfers)}개")
    print(f"범위 밖 환승 제외 {len(skipped)}개 (공항철도·경의중앙선·9호선 등)")
    print(f"좌표 없는 역 {len(no_coord)}개: {no_coord}")
    print(f"접근성 정보 없는 노드 {len(no_acc)}개: {no_acc}")


if __name__ == "__main__":
    main()
