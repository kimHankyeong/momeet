"""
지하철 원본 데이터 → momeet 정제 JSON 변환 스크립트

범위: 수도권 전철 전체
     - 서울교통공사 1~8호선: 공식 운행시간
     - 9호선·우이신설선·코레일 구간(1·3·4호선 연장, 수인분당, 경의중앙, 경춘, 경강, 서해)
       공항철도·신분당·에버라인·김포골드·의정부·신림·인천1·2호선·GTX-A: 거리로 시간 추정
     (자기부상철도는 운행 중단으로 제외)
     추가 입력: 국가철도공단 역간거리 파일들, 국토교통부_도시철도 전체노선, 전체_도시철도역사정보

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
    "신길온천": "능길",        # 4호선·수인분당선 역명 변경 (2025)
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


# ---------------------------------------------------------------- 수도권 광역·경전철 (거리 → 시간 추정)
# 서울교통공사 구간은 위의 공식 운행시간을 그대로 쓰고, 그 밖의 구간만 덧붙인다.
# 순서: 국가철도공단 역간거리 파일(구간별로 순서대로 나열) → 없으면 국토교통부 전체노선의 순번
KORAIL_DIST = "국가철도공단_코레일 역간거리_20251231.CSV"
LINE1_DIST = "국가철도공단_수도권1호선_역간거리_20260630.CSV"
LINE4_DIST = "국가철도공단_수도권4호선_역간거리_20251231.CSV"
INCHEON_DIST = "국가철도공단_인천교통공사 역간거리_20251231.CSV"
AIRPORT_DIST = "국가철도공단_공항철도_역간거리_20260630.CSV"
EVERLINE_DIST = "국가철도공단_에버라인 역간거리_20251231.CSV"
ALL_LINES = "국토교통부_도시철도 전체노선_20251211.csv"
STATION_INFO = "전체_도시철도역사정보_20260630.xlsx"

# 노선 ID → (출처, 구간 목록)
#   ("dist", 파일, 선명)          역간거리 파일의 그 선명 행을 순서대로 (역간거리 = 다음 역까지, 빈칸이면 구간 끝)
#   ("order", 운영기관, 노선명)    전체노선 파일의 순번 순서
#   ("names", [역, 역, ...])       직접 적은 순서 (연결 구간·지선)
REGIONAL_LINES = {
    "1": [  # 코레일 1호선 (경인·경부·광명·서동탄). 서울역~청량리 구간은 기존 데이터와 겹쳐 건너뜀
        ("dist", LINE1_DIST, "1호선(경인선)"),
        ("dist", LINE1_DIST, "1호선(경부선)"),
        ("dist", LINE1_DIST, "1호선(광명선)"),
        ("dist", LINE1_DIST, "1호선(서동탄선)"),
    ],
    "3": [("dist", KORAIL_DIST, "3호선"), ("names", ["삼송", "지축"])],  # 일산선
    "4": [("dist", LINE4_DIST, "4호선")],  # 진접선 ~ 안산과천선 ~ 오이도
    "7": [("dist", INCHEON_DIST, "7호선"), ("names", ["온수", "까치울"])],  # 부천·인천 연장
    "8": [("names", ["암사", "암사역사공원", "장자호수공원", "구리", "동구릉", "다산", "별내"])],  # 별내선
    "수인분당": [("dist", KORAIL_DIST, "수인분당")],
    "경의중앙": [("dist", KORAIL_DIST, "경의중앙"), ("names", ["가좌", "신촌", "서울역"])],
    "경춘": [("dist", KORAIL_DIST, "경춘")],
    "경강": [("dist", KORAIL_DIST, "경강")],
    "서해": [
        ("dist", KORAIL_DIST, "서해선"),
        ("names", ["부천종합운동장", "소사"]),
        ("order", "서해철도주식회사", "서해선"),
    ],
    "공항철도": [("dist", AIRPORT_DIST, "공항")],
    "신분당": [("order", "네오트랜스주식회사", "신분당")],
    "에버라인": [("dist", EVERLINE_DIST, "에버라인")],
    "김포골드": [("order", "김포골드라인운영주식회사", "김포골드라인")],
    "의정부": [("order", "의정부경량전철주식회사", "의정부")],
    "신림": [("order", "남서울경전철주식회사", "신림선")],
    "인천1": [("dist", INCHEON_DIST, "인천1호선")],
    "인천2": [("dist", INCHEON_DIST, "인천2호선")],
    # 수서~동탄, 운정중앙~서울역 두 구간 (삼성역 미개통)
    "GTX-A": [("names", ["수서", "성남", "구성", "동탄"]), ("names", ["운정중앙", "킨텍스", "대곡", "연신내", "서울역"])],
}

# 역간거리 파일에서 구간이 끊기는 곳 (빈칸 없이 다른 지선이 이어 적힌 경우): (노선, 역)
SEQUENCE_BREAK = {("경의중앙", "신촌")}  # 경의중앙 끝(지평) 뒤에 서울역 지선(신촌-서울역)이 이어 적혀 있음

# 같은 이름이지만 다른 역 → 노선 이름을 붙여 구분
SEPARATE_STATIONS = {
    ("양평", "경의중앙"): "양평(경의중앙)",  # 5호선 양평(영등포구)과 다른 역
    ("신촌", "경의중앙"): "신촌(경의중앙)",  # 2호선 신촌과 다른 역 (환승역 아님)
}

# 역사정보 파일의 노선명 → 노선 ID (좌표 찾기용)
INFO_LINE = {
    "1호선": "1", "경부선": "1", "경원선": "1", "경인선": "1", "장항선": "1",
    "2호선": "2", "3호선": "3", "일산선": "3", "4호선": "4", "안산과천선": "4", "진접선": "4",
    "5호선": "5", "6호선": "6", "7호선": "7", "도시철도 7호선": "7", "8호선": "8", "수도권 광역철도 8호선": "8",
    "서울 도시철도 9호선": "9", "수도권  도시철도 9호선": "9",
    "분당선": "수인분당", "수인선": "수인분당", "경의중앙선": "경의중앙", "경춘선": "경춘", "경강선": "경강",
    "서해선": "서해", "인천국제공항선": "공항철도", "신분당선": "신분당", "에버라인": "에버라인",
    "김포도시철도": "김포골드", "의정부": "의정부", "수도권 경량도시철도 신림선": "신림", "우이신설선": "우이신설",
    "인천지하철 1호선": "인천1", "인천지하철 2호선": "인천2",
}

# 서울교통공사 환승 원본의 환승노선 표기 → 노선 ID (1~9호선·우이신설 밖의 노선)
TRANSFER_LINE = {
    "경의중앙선": "경의중앙", "수인분당선": "수인분당", "공항철도": "공항철도", "신분당선": "신분당",
    "경춘선": "경춘", "신림선": "신림", "김포골드라인": "김포골드", "서해선": "서해",
}

# 역사정보 파일에 없는 역 좌표 (지도 서비스에서 확인한 대략값)
MANUAL_COORDS = {
    "도라산": (37.8995, 126.7090),
    "동탄": (37.2003, 127.0957),
    "킨텍스": (37.6687, 126.7448),
    "운정중앙": (37.7177, 126.7468),
}

# 노선별 평균 속도로 시간을 계산하는 급행 노선 (km/h). 나머지는 1~8호선으로 맞춘 환산식 사용
LINE_KMH = {"GTX-A": 100}

# 역간거리 파일 값이 직선거리와 너무 다르면(파일의 행 어긋남 등) 직선거리 × 이 배율을 쓴다
TRACK_DETOUR = 1.2


def norm_regional(name: str) -> str:
    """역명 정규화 + 끝의 '역' 제거 ('김포공항역' → '김포공항', 서울역은 그대로), '·' → '.'"""
    name = norm(name).replace("·", ".")
    if name.endswith("역") and name != "서울역":
        name = name[:-1]
    return ALIASES.get(name, name)


def straight_km(p, q) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(p[0]), math.radians(q[0])
    dp, dl = p2 - p1, math.radians(q[1] - p[1])
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_station_info():
    """전체 도시철도 역사정보 → {(역명, 노선): 좌표}, {역명: 좌표}"""
    wb = openpyxl.load_workbook(require(RAW / STATION_INFO), read_only=True)
    by_line, by_name = {}, {}
    for r in wb.active.iter_rows(min_row=2, values_only=True):
        line = INFO_LINE.get(str(r[3] or "").strip())
        if line is None or r[9] is None:
            continue
        name = norm_regional(str(r[1]))
        p = (float(r[9]), float(r[10]))
        by_line.setdefault((name, line), p)
        by_name.setdefault(name, p)
    for name, p in MANUAL_COORDS.items():
        by_name.setdefault(name, p)
    return by_line, by_name


def regional_sequences(line: str):
    """노선 하나의 구간 목록 → [[(역명, 다음 역까지 km 또는 None), ...], ...]"""
    seqs = []
    for src in REGIONAL_LINES[line]:
        kind = src[0]
        if kind == "names":
            seqs.append([(n, None) for n in src[1]])
        elif kind == "order":
            _, op, line_name = src
            rows = [r for r in read_csv(require(RAW / ALL_LINES))
                    if r["철도운영기관명"] == op and r["노선명"] == line_name]
            rows.sort(key=lambda r: int(r["순번"]))
            seqs.append([(norm_regional(r["역명"]), None) for r in rows])
        else:  # dist
            _, fname, line_name = src
            cur = []
            for r in read_csv(require(RAW / fname)):
                if r["선명"].strip() != line_name:
                    continue
                name = norm_regional(r["역명"])
                if (line, name) in SEQUENCE_BREAK and cur:
                    seqs.append(cur)
                    cur = []
                km_text = (list(r.values())[3] or "").strip()
                cur.append((name, float(km_text) if km_text else None))
                if not km_text:  # 빈칸 = 구간 끝
                    seqs.append(cur)
                    cur = []
            if cur:
                seqs.append(cur)
    return seqs


def build_regional_edges(nodes, coords, edges, a, b):
    """
    수도권 광역·경전철 구간을 덧붙인다. 이미 있는 역간 연결(서울교통공사 구간)은 건너뛴다.
    coords: 기존 좌표 {노드 ID: 좌표} (새 노드 좌표를 여기에 채워 넣음)
    """
    by_line, by_name = load_station_info()
    have = {frozenset((e["from"], e["to"])) for e in edges}
    name_pos = {}  # 역명 → 대표 좌표 (같은 이름 다른 역 검사용)
    for nid, (name, _) in nodes.items():
        if nid in coords:
            name_pos.setdefault(name, coords[nid])

    new_edges, far, no_coord = [], [], set()

    def place(raw_name, line):
        name = SEPARATE_STATIONS.get((raw_name, line), raw_name)
        nid = node_id(name, line)
        if nid not in nodes:
            nodes[nid] = (name, line)
        if nid not in coords:
            p = by_line.get((raw_name, line)) or by_name.get(raw_name) or name_pos.get(name)
            if p:
                coords[nid] = p
        p = coords.get(nid)
        if p is None:
            no_coord.add(name)
        elif name in name_pos and straight_km(name_pos[name], p) > 1.0:
            far.append(f"{name}({line}) {straight_km(name_pos[name], p):.1f}km")
        elif p:
            name_pos.setdefault(name, p)
        return nid

    for line in REGIONAL_LINES:
        for seq in regional_sequences(line):
            for (n1, km), (n2, _) in zip(seq, seq[1:]):
                frm, to = place(n1, line), place(n2, line)
                if frm == to or frozenset((frm, to)) in have:
                    continue
                straight = straight_km(coords[frm], coords[to]) if frm in coords and to in coords else None
                if straight is not None and not (km and 0.6 * straight <= km <= 2.5 * straight):
                    km = round(straight * TRACK_DETOUR, 1)
                if not km:
                    sys.exit(f"[오류] 거리를 알 수 없음: {frm} - {to}")
                if line in LINE_KMH:
                    sec = round(km / LINE_KMH[line] * 3600)
                else:
                    sec = round(a + b * km)
                have.add(frozenset((frm, to)))
                new_edges.append({
                    "from": frm, "to": to, "line": line, "seconds": sec, "km": km,
                    "oneway": False, "estimated": True,
                })
    return new_edges, far, sorted(no_coord)


def add_default_transfers(transfers, nodes):
    """
    환승 원본(서울교통공사)에 없는 환승은 기존 환승의 중앙값으로 채운다.
    같은 물리 역(같은 역명)에 있는 노선끼리 모두 연결.
    """
    import statistics
    sec = round(statistics.median(t["seconds"] for t in transfers))
    meters = round(statistics.median(t["meters"] for t in transfers))
    have = {(t["from"], t["to"]) for t in transfers}
    by_name = {}
    for nid, (name, _) in nodes.items():
        by_name.setdefault(name, []).append(nid)
    added = 0
    for name, nids in by_name.items():
        for frm in nids:
            for to in nids:
                if frm != to and (frm, to) not in have:
                    transfers.append({"station": name, "from": frm, "to": to,
                                      "meters": meters, "seconds": sec, "estimated": True})
                    added += 1
    return added, sec, meters


# ---------------------------------------------------------------- 환승
def build_transfers(nodes):
    rows = read_csv(require(RAW / "transfers_raw.csv"))
    transfers, skipped = {}, []

    for r in rows:
        line = r["호선"].strip()
        to_line = norm_line(r["환승노선"]) or TRANSFER_LINE.get(r["환승노선"].strip())
        name = norm(r["환승역명"])
        name = SEPARATE_STATIONS.get((name, to_line), name)
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

    # 9호선·우이신설선·광역철도 쪽에서 1~8호선으로 가는 방향은 원본에 없음 → 반대 방향 값을 그대로 사용
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
    wb = openpyxl.load_workbook(require(RAW / "accessibility_raw.xlsx"), data_only=True, read_only=True)
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


KORAIL_ACC = "한국철도공사_역별 승강설비 현황_20230101.csv"
INCHEON_ACC = "인천교통공사_엘리베이터 설치현황_20260630.csv"

# 코레일 승강설비 자료의 노선명 → 노선 ID (수도권 전철이 지나는 노선만)
KORAIL_ACC_LINE = {
    "경부선": "1", "경원선": "1", "경인선": "1", "장항선": "1",
    "일산선": "3", "과천선": "4", "안산선": "4",
    "분당선": "수인분당", "수인선": "수인분당", "수인분당선": "수인분당",
    "중앙선": "경의중앙", "경의선": "경의중앙", "용산선": "경의중앙",
    "경춘선": "경춘", "경강선": "경강", "서해선": "서해",
}
# 인천교통공사 엘리베이터 자료의 호선 → 노선 ID
INCHEON_ACC_LINE = {"1": "인천1", "2": "인천2", "7": "7"}


def add_regional_accessibility(acc, nodes):
    """
    서울교통공사 자료에 없는 광역철도 역의 엘리베이터 정보를 채운다.
      - 코레일 운영 역: 한국철도공사 역별 승강설비 현황 (2023.01, 역사별 대수)
      - 인천1·2호선, 7호선 부천·인천 구간: 인천교통공사 엘리베이터 설치현황 (한 대 = 한 행 → 역별로 셈)
    같은 이름의 다른 지역 역(전국 자료)과 섞이지 않도록 수도권 노선 이름으로 맞춘다.
    """
    korail = {}  # (역명, 노선 ID) → 정보
    for r in read_csv(require(RAW / KORAIL_ACC)):
        line = KORAIL_ACC_LINE.get(r["노선명"].strip())
        counts = [int(r[k] or 0) for k in ("엘리베이터", "에스컬레이터", "휠체어리프트")]
        if line is None or not any(counts):
            continue  # 설비가 전부 0 = 코레일 관리가 아닌 역(서해선 소사~원시 등)이거나 미집계 → 정보 없음으로 둠
        name = norm_regional(r["역명"].strip().removesuffix("역사"))
        name = SEPARATE_STATIONS.get((name, line), name)
        info = korail.setdefault((name, line), {"elevator": 0, "escalator": 0, "wheelchair_lift": 0, "source": "korail_2023"})
        info["elevator"] += int(r["엘리베이터"] or 0)
        info["escalator"] += int(r["에스컬레이터"] or 0)
        info["wheelchair_lift"] += int(r["휠체어리프트"] or 0)
    korail_by_name = {}  # 노선이 달라도 같은 역 (예: 4호선·수인분당선 한대앞은 안산선으로만 집계)
    for (name, _), info in korail.items():
        korail_by_name.setdefault(name, info)

    incheon = {}
    for r in read_csv(require(RAW / INCHEON_ACC)):
        line = INCHEON_ACC_LINE.get(r["호선"].strip())
        name = norm_regional(r["역명"])
        if line is None or r["장비종류"].strip() != "EL" or "환기구" in name or name.startswith("대피"):
            continue
        incheon[(name, line)] = incheon.get((name, line), 0) + 1

    filled = 0
    for nid, (name, line) in nodes.items():
        if nid in acc:
            continue
        if (name, line) in incheon:
            acc[nid] = {"elevator": incheon[(name, line)], "source": "incheon_2026"}
        elif (name, line) in korail:
            acc[nid] = dict(korail[(name, line)])
        elif line in set(KORAIL_ACC_LINE.values()) and name in korail_by_name:
            acc[nid] = dict(korail_by_name[name])
        else:
            continue
        filled += 1
    return filled


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

    add_regional_accessibility(acc, nodes)

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
    coords = load_coords()
    regional, far, no_coord_regional = build_regional_edges(nodes, coords, edges, a, b)
    edges += regional
    transfers, skipped = build_transfers(nodes)  # 광역철도 노드가 생긴 뒤에 읽어야 그쪽 환승도 들어감
    added_tr, tr_sec, tr_m = add_default_transfers(transfers, nodes)
    acc = add_elevator_points(load_accessibility(), nodes)
    stations = build_stations(nodes, coords, acc)

    for fname, data in [("stations.json", stations), ("edges.json", edges), ("transfers.json", transfers)]:
        with open(OUT / fname, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    no_coord = [s["name"] for s in stations if s["lat"] is None]
    unknown = [s["name"] for s in stations if s["elevator"] == "unknown"]

    print(f"노선: {', '.join(LINES + [l for l in REGIONAL_LINES if l not in LINES])}")
    print(f"광역·경전철 역간 연결 {len(regional)}개 추가 / 기본값 환승 {added_tr}개 추가 ({tr_sec}초, {tr_m}m)")
    print(f"같은 이름인데 1km 넘게 떨어진 역 (확인 필요): {far}")
    print(f"광역·경전철 중 좌표 없는 역: {no_coord_regional}")
    print(f"노드(역×노선) {len(nodes)}개 / 물리 역 {len(stations)}개")
    print(f"역간 연결 {len(edges)}개 (거리로 추정 {sum(e['estimated'] for e in edges)}개) / 환승 연결 {len(transfers)}개")
    print(f"거리→시간 환산식: 운행시간(초) = {a:.1f} + {b:.1f} × 거리(km)")
    print(f"범위 밖 환승 제외 {len(skipped)}개 (공항철도·경의중앙선·신분당선 등)")
    print(f"좌표 없는 역 {len(no_coord)}개: {no_coord}")
    print(f"엘리베이터 정보 없는 역(unknown) {len(unknown)}개")


if __name__ == "__main__":
    main()