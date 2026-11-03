# 백A 구현 체크리스트 — 약속방 · 인증 · 진행 상태 · 조건 입력/추천 API

- 근거: Notion `해커톤 › 백엔드 › 파트분배` 의 "백A" 5일 계획 (D1~D5), `기능 명세` (React+Vite / **FastAPI**)
- 백B 연동: `kimHankyeong/momeet` 의 `backend/app/core/` (subway · timeslot · fairness) — **B 코드는 수정하지 않고 호출만** 함 ([docs/integration-B.md](docs/integration-B.md))
- 조건 입력·추천 API는 B 코드가 "백A가 API에서 부르는 함수"로 설계되어 있어 **백A에서 구현**했다 (파트분배 문서상 B 몫이었으나 협의 결과 A로 정리)
- 스택: FastAPI · SQLAlchemy 2 · SQLite(개발) → MySQL(교체 예정) · bcrypt · pytest
- 범례: `[x]` 구현 + 자동 테스트 통과 · `[~]` 구현했으나 일부만 검증/가정 포함 · `[ ]` 미구현 (사유 표기)

## 검증 상태 (실제 실행 결과)

- `python -m pytest` → **100개 통과, 0 실패** (백A 81개 + 백B `test_fairness` 19개, SQLite 메모리 DB, bcrypt rounds=4)
- 조건 제출 → **B의 실제 추천 계산** → 제안 → 동의 → 확정까지 테스트가 실제 코드를 그대로 통과한다 (mock 없음)
- 실서버(`uvicorn`)로 `/health`, `/docs`, 생성→참여→마감→대시보드, CORS(허용/비허용 Origin) 확인
- `scripts/seed.py --yes` 로 단계별 시드 5종(모집 중 / 입력 중 / 추천 완료 / 제안 응답 중 / 확정) 생성 확인
- **MySQL은 연결해 보지 않았습니다.** 배포·프론트 실연동도 하지 않았습니다.

---

## D1. 기반 세팅 (프론트 무관)

- [x] FastAPI 앱, CORS (허용 Origin만, 쿠키 미사용 → `allow_credentials=False`)
- [x] SQLAlchemy 모델/테이블: `meetings`, `participants`, `proposals`, `proposal_responses`, `join_requests` (+ `auth_attempts`, `conditions`, `recommendation_results`)
- [x] SQLite 개발 설정, `DATABASE_URL` 로 교체 가능 (SQLite는 FK/CASCADE 강제 켬)
- [x] PIN · 호스트 비밀번호 bcrypt 해시 (평문 저장·응답 노출 없음 — 테스트로 확인)
- [x] 개인 토큰 발급: 무작위 256bit, DB에는 sha256만 저장, 만료는 약속방 만료를 넘지 않음
- [x] 인증 의존성 `get_current_participant`, `require_host` (다른 약속방 토큰/만료/제외된 사람 거부)
- [x] 완료 기준: 토큰으로 참여자·호스트가 구분됨 ✔ (테스트)
- [~] MySQL 교체 — `DATABASE_URL`만 바꾸면 되게 작성했으나 **MySQL에서 실행해 보지 않음** (`pymysql` 필요, JSON 컬럼 사용)
- [ ] 스키마 마이그레이션(Alembic) — 현재는 시작 시 `create_all` (개발용). 운영 전 도입 필요

## D2. 생성 · 참여 · 재접속 API

- [x] `POST /meetings` — 생성자 = 호스트, 호스트 토큰 즉시 발급
- [x] `GET /meetings/{id}/public` — 로그인 전 정보 (PIN·참여자 목록·호스트 정보 비노출)
- [x] `POST /meetings/{id}/join` — 모집 중 즉시 참여 / 마감 후 승인 대기(202)
- [x] `POST /meetings/{id}/host-login` — 새 토큰 발급, **이전 호스트 토큰 즉시 무효**
- [x] 입력 검증: 제목/닉네임 길이·제어문자, PIN 4~6자리 숫자, 비밀번호 8~72바이트(bcrypt 한계), 날짜 범위, 정원 2~30, 정의되지 않은 필드 거부
- [x] 검증 오류 응답에 **입력값(PIN/비밀번호)을 싣지 않음**
- [x] 중복 닉네임 접미사 (`민수` → `민수(2)`)
- [x] PIN/비밀번호 실패 제한: 5회 연속 실패 시 5분 잠금(429 + `Retry-After`), 클라이언트(IP)별·종류별 독립, 성공 시 초기화
- [x] `docs/api.md` 요청·응답 JSON 초안 → **프론트에 공유 가능** (실제 응답으로 예시 확인)
- [x] 완료 기준: `/docs`에서 생성 → 참여 → 재접속 동작 ✔
- [~] 프록시 뒤 배포 시 클라이언트 IP — 현재는 연결 IP 사용. 배포 환경의 프록시 헤더 처리는 미설정

## D3. 상태 머신 · 제안 · 동의 · 확정

- [x] 단계 전이 `recruiting → input → recommended → proposed → confirmed`, 허용되지 않은 전이/작업은 `409 INVALID_STAGE`
- [x] `POST /meetings/{id}/close` — 호스트 전용, 참여자 2명 이상일 때만
- [x] `POST /meetings/{id}/proposal` — 호스트 전용, **후보는 B의 `get_candidate`로 검증** (저장된 추천 결과에 있는 후보만)
- [x] 후보 ID는 B 형식 `c_<날짜>_<HHMM>_<역명>` (한글·`4.19민주묘지` 같은 점 포함 이름 지원)
- [x] `POST /meetings/{id}/proposal/response` — 동의/거절, 진행 중에는 변경 가능
- [x] 전원 동의(호스트 포함) → **자동 확정**, 거절 1명 → 즉시 `rejected`
- [x] 재제안 시 응답 초기화 (새 버전으로 시작, 진행 중이던 제안은 `superseded`)
- [x] 제외/나가기로 남은 전원이 동의 상태가 되면 자동 확정
- [x] 완료 기준: 단계 전이가 테스트로 확인됨 ✔

## D4. 대시보드 · 확정 화면 API

- [x] `GET /meetings/{id}` — 단계, 참여자 상태(입력 상태/응답), 진행 중 제안(+ **내 경로**), `next_action`
- [x] `GET /meetings/{id}/confirmed` — 확정 후보 + **내 경로**, 확정 전이면 `409 NOT_CONFIRMED`
- [x] 다른 참여자의 조건·경로·토큰·해시·PIN이 응답에 없음 (테스트로 확인)
- [x] (시간 남으면) 마감 후 참여 승인: 신청 → 호스트 승인/거절 → 신청자가 `claim`으로 토큰 수령(1회)
- [x] (시간 남으면) 참여자 제외: 토큰 즉시 무효, 호스트는 제외 불가
- [ ] **프론트 시안에 맞춘 응답 필드 조정** — 프론트 확정 내용을 아직 받지 못함. 현재 필드는 파트분배 문서와 B의 응답 형식 기준
- [ ] 완료 기준(프론트가 화면에 바로 붙일 수 있음) — 프론트 연동 전이라 **미확인**

## 조건 입력 · 추천 API (파트분배 "백B D4~D5" 항목 — A에서 구현)

- [x] `GET /stations?q=` — B의 `search_stations` (인증 불필요, `q` 1~20자, `limit` 1~20)
- [x] `GET /meetings/{id}/conditions/me` — **본인 조건만** 조회
- [x] `PUT /meetings/{id}/conditions/me/draft` — 임시저장 (B의 `validate_conditions(final=False)`)
- [x] `POST /meetings/{id}/conditions/me/submit` — 제출/재제출 (`final=True`), 본문 생략 시 저장된 초안 제출
- [x] 검증 오류는 B의 오류 목록(`code`, `message`, `field`)을 `422 CONDITIONS_INVALID`의 `errors`로 그대로 전달
- [x] 요청 크기 제한 (날짜 62개, 예외역 100개, 제약 10개), 정의되지 않은 필드·정수가 아닌 시간 거부
- [x] 입력 단계에서만 수정 가능 (모집 중/추천 이후 `409`), 제출 후 초안 저장 시 다시 제출해야 추천에 포함
- [x] `POST /meetings/{id}/recommendations` — **호스트 전용**, 전원 제출 후에만 (`409 CONDITIONS_INCOMPLETE` + `pending_nicknames`), 제외된 사람은 제외하고 계산
- [x] 후보가 있으면 `input → recommended`, **후보가 없으면(`no_candidate`) 단계 유지 + 사유(`reasons`) 반환** → 조건 수정 후 재실행
- [x] `recommended` 단계에서 재실행 가능, 제안 이후에는 불가
- [x] `GET /meetings/{id}/recommendations` — 모든 참여자, **본인 경로만** (B의 `view_for`), 실행 전이면 `not_ready`
- [x] 추천 결과 원본(모든 참여자 경로)은 DB에만 두고 어떤 응답에도 내보내지 않음 (테스트)
- [x] 참여자/약속방 삭제 시 조건·추천 결과 CASCADE 삭제 (테스트)
- [x] 추천 계산 동시 실행 2건으로 제한 (CPU 보호), 동기 엔드포인트라 이벤트 루프를 막지 않음
- [~] 성능 — 3명·1일 약 0.15초(로컬)만 측정. 참여자 30명·31일 같은 큰 경우는 **측정 안 함**
- [ ] 제외된 사람이 포함된 기존 추천 결과의 자동 재계산 — 필요하면 호스트가 `recommended` 단계에서 재실행

## D5. 보안 · 배포 · 연동

- [x] 다른 참여자 조건 비노출 점검 (대시보드/공개/확정/추천 응답 — 테스트)
- [x] 내 데이터 삭제 + 토큰 무효화 `DELETE /meetings/{id}/me` (응답·조건 등 하위 데이터 CASCADE 삭제)
- [x] 호스트의 약속방 전체 삭제 `DELETE /meetings/{id}` (하위 데이터 전부 삭제 확인)
- [x] 만료된 약속방 접근 차단 (`410`, 공개/대시보드/참여/호스트 로그인 모두)
- [x] 내부 오류 상세 비노출 (`INTERNAL_ERROR`만), 모든 오류 동일 형식
- [x] 시드 데이터 `scripts/seed.py` (실제 파이프라인으로 5단계 생성)
- [x] 백B 연동 문서 `docs/integration-B.md`
- [ ] 배포 — 배포 대상/환경이 문서에 없어 **하지 않음**
- [ ] 프론트 연동 오류 수정 — 프론트가 아직 없음
- [ ] 자동 삭제 스케줄러(만료 데이터 정리) — 후순위. 지금은 접근 차단만 하고 데이터는 남음
- [ ] 확정 후 변경 요청 / 예외 출발역 UI — 후순위 (예외 출발역 *데이터 입력*은 구현됨)

---

## 가정한 값 (Notion에 확정 값이 없어 제가 정함 — 확인 필요)

| 항목 | 현재 값 | 바꾸는 곳 |
| --- | --- | --- |
| 약속방 입력 항목 | 제목, 설명(선택), 후보 날짜 범위(시작~끝, 최대 31일), 최대 인원(2~30, 기본 10), 호스트 닉네임, PIN, 호스트 비밀번호 | `app/schemas.py` `MeetingCreate` |
| PIN 형식 / 닉네임 | 4~6자리 숫자 / 1~20자 | `schemas.py` |
| 마감 최소 인원 | 2명 | `MIN_PARTICIPANTS_TO_CLOSE` |
| 약속방/토큰 유효기간 | 30일 | `MEETING_TTL_DAYS`, `TOKEN_TTL_DAYS` |
| 실패 제한 | 5회 → 5분 | `MAX_AUTH_FAILURES`, `AUTH_LOCK_MINUTES` |
| 추천에 쓰는 날짜 | 약속방 `date_start ~ date_end` 전체 | `services/conditions.py` `meeting_dates` |
| "전원 동의"의 전원 | 활성 참여자 전원, 호스트 포함 | `services/proposals.py` |
| 거절 후 단계 | `proposed` 유지 + 제안만 `rejected` | `services/proposals.py` |
| 마감 후 참여 | 입력 단계에서만 승인 신청 가능, 추천 이후 불가 | `services/meetings.py`, `joins.py` |
| 제출 후 초안 저장 | 상태가 `draft`로 돌아가 재제출 필요 | `services/conditions.py` |
| 후보 없음(`no_candidate`) | 단계를 올리지 않고 사유 반환 | `services/conditions.py` |

## 알려진 한계

- 동시 요청(정원 마지막 자리 경쟁 등)은 DB 트랜잭션/UNIQUE 제약에 의존하며, 부하·경쟁 테스트는 하지 않았습니다.
- Figma(`momeet`) 디자인은 접근할 수 없어 반영하지 못했습니다.
- 백B의 `fairness.py` 로직 자체의 정확성은 B의 테스트(19개)에 의존하며, A에서는 입출력 연동만 검증했습니다.
