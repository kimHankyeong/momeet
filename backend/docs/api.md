# 백A API 초안 (약속방 · 인증 · 진행 상태)

프론트는 이 문서로 화면·mock을 만들고, 실제 서버는 `/docs`(Swagger)에서 바로 호출해 볼 수 있다.
조건 입력·추천 계산은 백B의 `app/core`(지하철 경로·공평성 추천)를 호출한다 (`docs/integration-B.md`).

## 공통

- Base URL: 개발 `http://localhost:8000`
- 인증: `Authorization: Bearer <access_token>` (쿠키 미사용). 토큰은 **약속방마다 별개**이며 다른 약속방에서는 통하지 않는다.
- 시간: UTC ISO 8601, 끝에 `Z` (예: `2026-12-01T09:30:00Z`). 날짜(`date_start` 등)는 `YYYY-MM-DD`.
- 오류 형식 (모든 오류 동일):

```json
{ "error": { "code": "INVALID_CODE", "message": "입장 코드를 찾을 수 없습니다." } }
```

입력 검증 실패는 `422 VALIDATION_ERROR`이며 **입력값은 응답에 포함하지 않고** 필드 위치만 알려 준다.

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "입력값이 올바르지 않습니다.",
             "fields": [ { "field": "nickname", "reason": "string_too_long" } ] } }
```

### 단계 (`stage`)

```
recruiting → input → recommended → proposed → confirmed
 (모집 중)   (마감 후)  (추천 완료)   (제안됨)    (확정)
```

**화면(시안)의 5단계 스텝퍼와의 대응:** 시안은 *모집 → 입력 → 추천 → 제안 → 확정* 이고, 참여자가 링크로 들어오면서 동시에 각자 조건을 입력한다("입력 중/입력완료").
그래서 API는 `recruiting`과 `input` **두 단계 모두에서 조건 입력이 가능**하다. 두 값은 화면에서 "입력" 단계 하나로 묶어 보여 주면 된다.
(`recruiting` = 모집 마감 전, `input` = 호스트가 모집을 마감한 뒤 추천 실행 대기. 스텝퍼의 "모집" 칸이 따로 활성화되는 순간이 언제인지는 기획/디자인 확인 필요.)

| 전이 | 누가/무엇이 | 조건 |
| --- | --- | --- |
| recruiting → input | 호스트 `POST /close` ("참여자 모집 마감") | 참여자 2명 이상. 마감 전에는 새 참여자가 들어올 수 있고, 마감 후에는 호스트 승인이 필요하다 |
| input → recommended | 호스트 `POST /recommendations` | 활성 참여자 **전원 조건 제출** + 추천 후보가 1개 이상 (후보가 없으면 단계는 그대로) |
| recommended → proposed | 호스트 `POST /proposal` | 후보 검증 통과 |
| proposed → confirmed | 마지막 사람이 동의 → **자동** | 활성 참여자 **전원**(호스트 포함) 동의 |

거절이 나와도 제안은 `pending`으로 열려 있다. **전원이 응답했는데 거절이 있으면 `proposal.needs_replan = true`** (시안: "이번 제안은 확정되지 않았어요")이고, 거절한 사람이 동의로 바꾸면 전원 동의로 확정된다. 호스트가 다른 후보를 다시 제안하면 응답은 처음부터 시작한다.

### 주요 오류 코드

| HTTP | code | 의미 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음/만료/다른 약속방/제외됨 |
| 401 | `INVALID_CREDENTIALS` | 호스트 비밀번호 불일치 |
| 403 | `HOST_ONLY` | 호스트 전용 기능 |
| 404 | `INVALID_CODE` | 입장 코드가 없거나 형식이 틀리거나 **만료된 방** (구분하지 않는다) |
| 404 | `MEETING_NOT_FOUND`, `PARTICIPANT_NOT_FOUND`, `JOIN_REQUEST_NOT_FOUND` | 대상 없음 |
| 409 | `INVALID_STAGE` | 지금 단계에서 불가 (`stage`, `allowed_stages` 포함) |
| 409 | `MEETING_FULL`, `JOIN_CLOSED`, `NOT_ENOUGH_PARTICIPANTS`, `NO_ACTIVE_PROPOSAL`, `NOT_CONFIRMED`, `NO_DRAFT` | 상태 충돌 |
| 409 | `CONDITIONS_INCOMPLETE` | 아직 제출하지 않은 참여자가 있어 추천 불가 (`pending_nicknames` 포함) |
| 410 | `MEETING_EXPIRED` | 만료된 약속방 (모든 접근 차단) |
| 422 | `VALIDATION_ERROR`, `INVALID_CANDIDATE` | 입력/후보 오류 |
| 422 | `CONDITIONS_INVALID` | 조건 값 오류. `errors: [{code, message, field}]` 에 B의 검증 결과가 그대로 들어간다 |
| 429 | `TOO_MANY_ATTEMPTS` | 입장 코드 추측 / 호스트 비밀번호 실패 초과. `Retry-After` 헤더(초) 와 `retry_after` 필드 |

---

## 약속방 생성

`POST /meetings` → `201`

```json
// 요청
{
  "title": "금요일 저녁 모임",          // 1~12자 (시안)
  "description": "다 같이 보자",        // 선택, 최대 200자
  "date_start": "2026-12-01",
  "date_end": "2026-12-07",            // date_start 이후, 1~7일 범위 (팀 결정)
  "max_participants": 10,              // 선택(기본 10), 2~10 (팀 결정: 최대 10명)
  "host_nickname": "한경",              // 1~8자 (시안)
  "host_password": "my-host-password"  // 8~72바이트: 호스트 재접속용
}
```

**PIN은 받지 않는다.** 참여자가 입력할 **입장 코드는 서버가 겹치지 않게 발급**한다 (`pin`, `join_code`를 보내면 `422`).

```json
// 응답: 호스트 토큰이 바로 발급된다 (생성자 = 호스트)
{
  "meeting_id": "Qx3k9aB1",
  "join_code": "k7m2x9qa",           // 참여자에게 공유할 입장 코드 (서버 발급, 8자: 소문자+숫자)
  "access_token": "…",
  "token_type": "bearer",
  "expires_at": "2027-01-01T00:00:00Z",
  "participant": { "id": 1, "nickname": "한경", "is_host": true },
  "meeting": { "id": "Qx3k9aB1", "title": "…", "description": "…", "date_start": "2026-12-01",
               "date_end": "2026-12-07", "stage": "recruiting", "max_participants": 10,
               "closed_at": null, "expires_at": "2027-01-01T00:00:00Z" }
}
```

## 입장 코드

- **8자, 소문자 + 숫자**, 헷갈리는 문자(`i l o 0 1`)는 쓰지 않는다. 방마다 겹치지 않는다. 호스트는 정하지 않는다.
- 입력은 너그럽게 받는다: 대소문자 무시, 공백·하이픈 무시, **`MOMEET-` 접두사 허용** (예: `MOMEET-k7m2x9qa`, `k7m2-x9qa`). 화면에 `MOMEET-코드`로 보여 줘도 되고, 사용자가 **초대 링크를 붙여넣으면 프론트가 링크에서 코드만 뽑아 보낸다.**
- 코드는 방 만들기 응답(`join_code`)과, 인증된 대시보드(`meeting.join_code`)에서 확인할 수 있다 (시안: 참여자도 링크 복사).
- **방 ID만으로는 입장할 수 없다.** 입장은 코드로만 한다.
- 추측 방어: 코드가 틀린(없음·형식 오류·만료) 요청이 **같은 클라이언트에서 10분 안에 10번**이면 5분간 `429`. **올바른 코드를 섞어도 횟수는 초기화되지 않는다.**
  - ⚠️ 배포 환경(렌더 등)의 프록시 뒤에서는 클라이언트 구분이 모두 같은 주소로 보일 수 있다. 서버 실행 시 프록시 헤더를 신뢰하도록 설정해야 한다 (`uvicorn ... --proxy-headers --forwarded-allow-ips="*"`). **미설정 시 한 사람의 오타가 모두를 잠글 수 있다.** 설정 방법과 주의(`*` 신뢰의 위험)는 [deploy-render.md](deploy-render.md) 5절.

### 입장 코드로 방 미리보기 (참여 화면의 제목·날짜·모집 중 카드)

`GET /join/{code}` → `200` (인증 불필요). 코드가 없거나 만료면 `404 INVALID_CODE`.

```json
{ "meeting_id": "Qx3k9aB1", "id": "Qx3k9aB1", "title": "금요일 저녁 모임", "description": "다 같이 보자",
  "date_start": "2026-12-01", "date_end": "2026-12-07", "stage": "recruiting",
  "participant_count": 3, "max_participants": 10, "can_join": true, "can_request_join": false }
```

## 공개 정보 (방 ID로 조회, 로그인 전)

`GET /meetings/{id}/public` → `200` (인증 불필요)

```json
{ "id": "Qx3k9aB1", "title": "금요일 저녁 모임", "description": "다 같이 보자",
  "date_start": "2026-12-01", "date_end": "2026-12-07", "stage": "recruiting",
  "participant_count": 3, "max_participants": 10,
  "can_join": true,            // 즉시 참여 가능 (모집 중 + 정원 여유)
  "can_request_join": false }  // 마감 후 참여 신청 가능 (조건 입력 단계 + 정원 여유)
```

입장 코드, 호스트 정보, 참여자 목록은 포함하지 않는다.

## 참여

`POST /join/{code}` (인증 불필요, **코드만으로 입장**)

```json
{ "nickname": "민수" }          // 1~8자 (시안)
```

- 모집 중 → `201`, 토큰 발급. 닉네임이 겹치면 접미사가 붙는다 (`민수` → `민수(2)`). 실제 닉네임은 응답의 `participant.nickname`을 사용한다.

```json
{ "meeting_id": "Qx3k9aB1", "access_token": "…", "token_type": "bearer",
  "expires_at": "…", "participant": { "id": 2, "nickname": "민수", "is_host": false } }
```

- 조건 입력 단계(마감 후) → `202`, 호스트 승인 대기. `request_secret`은 **이때 한 번만** 보인다.

```json
{ "status": "pending", "meeting_id": "Qx3k9aB1", "request_id": 4, "nickname": "민수", "request_secret": "…" }
```

- 추천 이후 → `409 JOIN_CLOSED`, 정원 초과 → `409 MEETING_FULL`
- 코드 오류 → `404 INVALID_CODE` (위 "추측 방어" 참고)

## 호스트 재접속

`POST /meetings/{id}/host-login` → `200` (응답은 생성 응답의 토큰 부분과 동일)

```json
{ "host_password": "my-host-password" }
```

새 토큰을 발급하고 **이전 호스트 토큰은 즉시 무효**가 된다. 일반 참여자의 재접속은 저장해 둔 토큰으로 한다.

## 대시보드

`GET /meetings/{id}` (인증) → `200`

```json
{
  "meeting": { "id": "…", "title": "…", "stage": "proposed", "max_participants": 10,
               "date_start": "…", "date_end": "…", "closed_at": "…", "expires_at": "…", "description": null },
  "me": { "participant_id": 2, "nickname": "민수", "is_host": false },
  "participants": [
    { "id": 1, "nickname": "한경", "is_host": true,  "is_me": false, "input_status": "submitted", "response": "accept" },
    { "id": 2, "nickname": "민수", "is_host": false, "is_me": true,  "input_status": "submitted", "response": "pending" }
  ],
  "proposal": { "id": 3, "version": 1, "status": "pending", "candidate_id": "c_20261107_1500_창동",
                "candidate": { … },          // 후보 공개 정보 (장소·시간)
                "my_route": { … },           // 내 경로만. 추천 이후 참여한 사람은 null
                "accepted_count": 1, "rejected_count": 0, "responded_count": 1, "total": 2,   // 시안 "참여자 2/4 동의"
                "needs_replan": false },     // 전원 응답 + 거절 있음 -> "이번 제안은 확정되지 않았어요"
  "next_action": { "code": "respond_to_proposal", "message": "제안에 동의 또는 거절하세요." },
  "progress": { "submitted": 2, "total": 4 },  // 시안 "참여자 2/4 완료" (입력 단계)
  "host": { "pending_join_requests": 0 }       // 호스트에게만 포함
}
```

- `input_status`: `none` | `draft` | `submitted` (조건 **내용**은 절대 포함되지 않는다)
- `response`: `proposed`/`confirmed` 단계에서만 포함. `pending` | `accept` | `reject`
- `proposal`: 제안이 없으면 `null`. `status`: `pending` | `accepted` | `superseded` (거절은 상태가 아니라 `rejected_count`/`needs_replan`으로 표현)
- 동의 여부만 공유되고 거절 이유·개인 이동 조건은 공유되지 않는다 (시안 하단 문구와 동일)
- `candidate`는 B의 `get_candidate`, `my_route`는 B의 `get_my_route` 결과 (다른 참여자의 경로·출발역은 포함되지 않는다)

### `next_action.code`

| code | 대상 | 단계 |
| --- | --- | --- |
| `submit_conditions` | 미제출자 (호스트 포함) | recruiting, input |
| `wait_conditions` | 제출한 호스트 (다른 참여자 미제출) | recruiting, input |
| `close_recruiting` | 호스트 (전원 제출 + 2명 이상) | recruiting |
| `wait_recruiting` | 제출한 참여자 | recruiting |
| `run_recommendation` | 호스트 (전원 제출) | input |
| `wait_recommendation` | 제출 완료한 참여자 | input |
| `propose_candidate` / `wait_proposal` | 호스트 / 참여자 | recommended |
| `respond_to_proposal` / `wait_responses` | 미응답 / 응답 완료 | proposed (진행 중 제안) |
| `repropose` / `wait_reproposal` | 호스트 / 참여자 | proposed + `needs_replan` |
| `view_confirmed` | 모두 | confirmed |

## 역 검색 · 조건 입력 · 추천

### 역 자동완성

`GET /stations?q=쌍문&limit=10` (인증 불필요, `q` 1~20자, `limit` 1~20)

```json
{ "stations": [ { "name": "쌍문", "lines": ["4"], "lat": 37.648627, "lng": 127.034709 } ] }
```

`GET /places?q=노해로 342` — 출발지 **장소·주소 검색** (인증 불필요, `q` 2~50자, **최대 5건**). 도로명·지번 주소와 장소 이름 모두 검색된다.

```json
{ "places": [
  { "name": "신원리베르텔", "address": "서울 도봉구 노해로 341", "lat": 37.651445, "lng": 127.045912 },
  { "name": "서울 도봉구 노해로 343-1", "address": "서울 도봉구 노해로 343-1", "lat": 37.651418, "lng": 127.046457 } ] }
```

- 도로명·지번 주소처럼 보이면 **정확한 번지(건물 이름)가 맨 앞**에 오고 주변 장소가 이어진다. `address`는 티맵이 실제로 찾은 주소라서 입력한 번지와 다를 수 있다(없는 번지는 가까운 번지로 잡힌다).
- 사용자가 고른 항목의 `lat`/`lng`를 조건의 `default_origin`(또는 예외의 `origin`)에 그대로 보내면 된다. 결과가 없으면 `places: []`.
- 티맵 호출 한도 보호: 같은 검색어는 10분간 캐시하고, **클라이언트당 분당 30건**(캐시에 없는 검색)까지만 허용한다 → `429 RATE_LIMITED`(`Retry-After`). 입력할 때마다 부르지 말고 **입력이 멈춘 뒤(0.4초) 또는 검색 버튼/엔터**에 호출한다.
- 티맵을 쓸 수 없으면 `503 PLACES_UNAVAILABLE`(주소를 직접 입력하게 안내).
- 시·도를 뺀 `도봉구 노해로 437`처럼 티맵이 못 찾는 형식은 결과가 없을 수 있다. `서울 도봉구 …` 또는 `노해로 437`처럼 입력한다.

`신설동역`처럼 `역`을 붙이거나 별칭(예: `이수`)으로 검색해도 된다. 서울 지하철 1~8호선 범위.

### 내 조건 조회 / 임시저장 / 제출

| 요청 | 설명 |
| --- | --- |
| `GET /meetings/{id}/conditions/me` | `{ "status": "none"\|"draft"\|"submitted", "conditions": {…}\|null, "updated_at": "…" }` — **본인 것만** 조회 가능 |
| `PUT /meetings/{id}/conditions/me/draft` | 임시저장 (있는 항목만 검사). `recruiting`/`input` 단계에서 가능 |
| `POST /meetings/{id}/conditions/me/submit` | 제출/재제출 (필수 항목 모두 필요). **본문을 생략하면 저장해 둔 초안을 제출**. 없으면 `409 NO_DRAFT` |

```json
// 요청 본문 (draft / submit 공통)
{
  "availability": { "2026-11-07": [13, 14, 15], "2026-11-08": [10] },   // 날짜 -> 출발 가능한 시(0~23). 약속방 날짜 범위 안
  "default_station": "쌍문",                                              // 필수(제출 시)
  "default_origin": { "lat": 37.6514, "lng": 127.0459 },                  // 선택. 출발 위치. {"address": "..."}도 가능
  "exception_stations": [ { "date": "2026-11-08", "hours": [10], "station": "수유",
                            "origin": { "lat": 37.66, "lng": 127.02 } } ],   // 선택. origin도 선택
  "constraints": {                                                         // 선택. level: "required"(필수) | "preferred"(선호)
    "max_travel_min":  { "value": 60,   "level": "required" },
    "max_transfers":   { "value": 1,    "level": "preferred" },
    "max_walk_m":      { "value": 500,  "level": "preferred" },
    "needs_elevator":  { "value": true, "level": "required" },
    "avoid_stairs":    { "value": true, "level": "preferred" }
  }
}
```

```json
// 응답 200: 정리된 조건 (역명은 표준 이름, 시간은 정렬·중복 제거)
{ "status": "submitted", "conditions": { "availability": {…}, "default_station": "쌍문", "exception_stations": [], "constraints": {…} },
  "updated_at": "2026-11-02T09:30:00Z" }
```

```json
// 422 CONDITIONS_INVALID
{ "error": { "code": "CONDITIONS_INVALID", "message": "조건을 확인해 주세요.",
             "errors": [ { "code": "STATION_NOT_FOUND", "message": "…", "field": "default_station" } ] } }
```

`errors[].code`: `NO_AVAILABILITY`, `STATION_REQUIRED`, `STATION_NOT_FOUND`, `DATE_OUT_OF_RANGE`, `INVALID_FORMAT`, `INVALID_CONSTRAINT`, `INVALID_ORIGIN`, `ORIGIN_TOO_FAR` (`field`는 문제가 된 항목 이름).

**출발 위치 → 출발역 도보 (선택 입력)**
- `default_origin`(기본 출발역용), 예외 출발역의 `origin`을 보내면 그 위치에서 **그 출발역까지 걸어가는 거리·시간**이 이동시간에 더해진다. 출발 시각도 출발 위치에서 나서는 시각이다. 위치를 안 보내면 도보는 0이다.
- 좌표는 수도권 범위만 받고 **소수 3자리(약 100m)로 반올림해 저장**한다. 출발역까지 직선거리가 3km를 넘으면 `422 ORIGIN_TOO_FAR`.
- **주소·장소 이름만 보내도 된다** (`{"address": "서울 도봉구 노해로 342"}`): 서버가 좌표로 바꾼 뒤 검증하며 **주소는 저장하지 않는다**(응답에는 좌표만). 못 찾으면 `422 INVALID_ORIGIN`, 변환 서비스 장애면 `503 GEOCODE_UNAVAILABLE`(좌표로 다시 보내면 됨).
- 서버가 도보를 구해 조건에 저장한다: `default_access` / `exception_stations[].access` = `{ "station", "walk_m", "minutes", "source" }`. `source`는 `"tmap"`(티맵 보행 경로) 또는 `"estimate"`(직선거리×1.3 추정, 티맵 키 없음·한도·장애 시). `estimate`는 다음 저장 때 티맵을 다시 시도한다. 같은 위치·역으로 다시 저장해도 티맵을 다시 부르지 않는다.

- 제출 후 다시 `draft`로 저장하면 상태가 `draft`로 돌아가며, 다시 **제출해야** 추천에 포함된다.
- `recruiting`/`input`에서만 입력·수정할 수 있고, 추천이 실행된 뒤(`recommended` 이후)에는 잠긴다 (`409 INVALID_STAGE`).
- 대시보드의 `input_status`가 `none`/`draft`/`submitted`로 바뀐다.

### 추천 실행 (호스트) / 조회 (참여자)

`POST /meetings/{id}/recommendations` → `200` — 호스트만. 전원이 제출한 뒤에만 가능하며(아니면 `409 CONDITIONS_INCOMPLETE`),
`input`/`recommended` 단계에서 다시 실행할 수 있다. 응답은 아래 조회 응답과 같다.

`GET /meetings/{id}/recommendations` → `200` — 모든 참여자. **내 경로(`my_route`)만** 포함한다.

```json
{
  "status": "ok",                      // "ok" | "no_candidate" | "not_ready"(추천 실행 전)
  "stage": "recommended",
  "best": "c_20261107_1500_창동",       // 1순위 candidate_id
  "candidates": [
    { "rank": 1, "candidate_id": "c_20261107_1500_창동", "date": "2026-11-07", "start": "15:00", "end": "17:00",
      "station": { "name": "창동", "lines": ["1","4"], "lat": 37.65, "lng": 127.05 },
      "max_travel_min": 32, "accessibility": "met",
      "my_route": { "origin": "쌍문", "depart_at": "14:28", "minutes": 32, "transfers": 1, "walk_m": 210, "walk_min": 3,
                    "access": { "walk_m": 140, "minutes": 2, "source": "tmap" },
                    "segments": [ { "line": "4", "board": "쌍문", "alight": "충무로", "stops": 10, "minutes": 22 } ] } }
  ]
}
```

- `no_candidate`이면 `candidates: []` 와 `reasons: [...]`(통합 사유)가 오고 **단계는 `input`에 머문다.** 조건을 고쳐 다시 제출한 뒤 호스트가 재실행한다.
- 추천이 실행된 뒤에 참여한 사람은 `my_route`가 `null`이다.
- 같은 날 같은 역은 가장 좋은 시간 1개만, 날짜별 최대 3개, 전체 순위(`rank`) 순서.
- `accessibility`: 만남 장소 역의 엘리베이터 상태 `met` | `unmet` | `unknown` (필수 조건 판단에서 `unknown`은 충족으로 보지 않는다).
- `my_route.minutes`는 출발 위치에서 나서는 순간부터의 총 시간, `walk_m`은 도보 합계(출발 위치→출발역 + 환승 도보), `max_walk_m` 조건도 이 합계와 비교한다. `access`는 출발 위치를 입력했을 때만 있고(없으면 `null`) 출발 위치→출발역 구간만 나타낸다. 출발 위치 좌표는 어떤 응답에도 나오지 않는다(본인 조건 조회 제외).
- `segments[]`: 구간별 `{line, board, alight, stops, minutes}` (환승이 있으면 구간이 여러 개).

---

## 모집 마감 (호스트)

`POST /meetings/{id}/close` → `200` `{ "meeting": { … "stage": "input", "closed_at": "…" } }`

참여자가 2명 미만이면 `409 NOT_ENOUGH_PARTICIPANTS`, 이미 마감했으면 `409 INVALID_STAGE`.

## 제안 (호스트) / 응답 (전원)

`POST /meetings/{id}/proposal` → `201`

```json
{ "candidate_id": "c_20261107_1500_창동" }   // 추천 결과의 candidate_id 그대로. 이번 추천 결과에 없는 후보면 422 INVALID_CANDIDATE
```

```json
{ "id": 3, "version": 1, "status": "pending",
  "candidate_id": "c_20261107_1500_창동",
  "candidate": { "candidate_id": "…", "date": "2026-11-07", "start": "15:00", "end": "17:00",
                 "station": { "name": "창동", "lines": ["1","4"], "lat": 37.65, "lng": 127.05 },
                 "max_travel_min": 32, "accessibility": "met" },
  "my_route": { "origin": "쌍문", "depart_at": "14:28", "minutes": 32, "transfers": 1, "walk_m": 210, "walk_min": 3,
                    "access": { "walk_m": 140, "minutes": 2, "source": "tmap" },
                "segments": [ { "line": "4", "board": "쌍문", "alight": "충무로", "stops": 10, "minutes": 22 } ] },
  "stage": "proposed" }
```

- `recommended` 또는 `proposed` 단계에서 가능. 진행 중인 제안이 있으면 `superseded`로 바뀌고 새 제안은 응답 없이 시작한다.

`POST /meetings/{id}/proposal/response`

```json
{ "response": "accept" }       // "accept" | "reject"
```

응답은 위 제안 객체와 같다 (`status`가 `accepted`이면 `stage`가 `confirmed`).
- 제안이 열려 있는 동안(확정 전) **언제든 응답을 바꿀 수 있다** (시안: "동의 완료/거절 완료 → 수정하기"). 같은 응답을 반복해도 된다.
- 전원 동의 → `status: "accepted"`, `stage: "confirmed"`. 거절이 있어도 `status`는 `pending`이고, 전원 응답 후에는 `needs_replan`이 `true`가 된다.
- 확정된 뒤에는 `409 INVALID_STAGE`, 열린 제안이 없으면 `409 NO_ACTIVE_PROPOSAL`.

## 확정 화면

`GET /meetings/{id}/confirmed` (인증) → `200`, 확정 전이면 `409 NOT_CONFIRMED`

```json
{ "meeting": { … }, "candidate_id": "c_20261107_1500_창동", "candidate": { … }, "my_route": { … },
  "participants": [ { "id": 1, "nickname": "한경", "is_host": true } ] }
```

## 마감 후 참여 승인 / 참여자 제외 (호스트)

| 요청 | 설명 |
| --- | --- |
| `GET /meetings/{id}/join-requests` | 대기 중 신청 `{ "requests": [{ "id", "nickname", "created_at" }] }` |
| `POST /meetings/{id}/join-requests/{rid}/approve` | 승인 (입력 단계에서만, 정원 확인). `{ "id", "status": "approved" }` |
| `POST /meetings/{id}/join-requests/{rid}/reject` | 거절 |
| `POST /meetings/{id}/join-requests/{rid}/claim` | **신청자**가 결과 확인 (인증 대신 `{ "request_secret": "…" }`). 대기/거절이면 `{ "status": "pending"\|"rejected" }`, 승인이면 토큰 발급(한 번만, 이후 `409 ALREADY_CLAIMED`) |
| `POST /meetings/{id}/participants/{pid}/exclude` | 참여자 제외. 토큰 즉시 무효. 제외 결과로 남은 전원이 동의한 상태면 자동 확정 |

신청자는 승인될 때까지 `claim`을 주기적으로 호출한다.

## 삭제

| 요청 | 설명 |
| --- | --- |
| `DELETE /meetings/{id}/me` → `204` | 내 데이터 삭제 + 토큰 무효화 (내 응답·조건 등 하위 데이터 함께 삭제). 호스트는 `409 HOST_CANNOT_LEAVE` |
| `DELETE /meetings/{id}` → `204` | 호스트가 약속방과 모든 하위 데이터를 삭제 |

## 프론트가 알아 두면 좋은 점

- 토큰은 로그인/참여 응답에서 **한 번만** 내려간다. `localStorage` 등에 저장해 재접속에 쓴다.
- 서버가 쿠키를 쓰지 않으므로 CORS는 `Authorization`/`Content-Type` 헤더만 허용한다. 프론트 Origin은 서버 `CORS_ORIGINS`에 등록해야 한다.
- 화면 분기는 `stage`와 `next_action.code`를 기준으로 한다.
