# 백A ↔ 백B 연동 현황

백B가 올린 `backend/app/core/` (지하철 경로 · 시간/장소 후보 · 공평성 추천)를 백A의 API/DB 계층이 호출한다. **B 코드는 수정하지 않았다.**

## 호출 관계

| 백A 위치 | 호출하는 B 함수 | 용도 |
| --- | --- | --- |
| `routers/conditions.py` `GET /stations` | `subway.search_stations(q, limit)` | 역 자동완성 |
| `services/conditions.py` 임시저장/제출 | `fairness.validate_conditions(data, dates, final)` | 조건 검증·정리 (오류 목록은 그대로 `errors`로 반환) |
| `services/conditions.py` 추천 실행 | `fairness.recommend(participants, dates)` | 추천 계산 → 결과 JSON을 `recommendation_results`에 저장 |
| `services/conditions.py` 추천 조회 | `fairness.view_for(result, participant_id)` | 본인 경로만 남긴 응답 |
| `integrations/candidates.py` | `fairness.get_candidate(result, candidate_id)` | 제안 시 후보 검증 / 대시보드·확정 화면의 후보 정보 |
| `integrations/candidates.py` | `fairness.get_my_route(result, candidate_id, participant_id)` | 제안·확정 화면의 "내 경로" |

- `dates` = 약속방의 `date_start ~ date_end` 전체 날짜 (`YYYY-MM-DD` 목록)
- `participants` = 활성 참여자 전원 `{"id": "<참여자 id 문자열>", **저장된 정리된 조건}`
- 후보 ID는 B의 `c_<날짜>_<HHMM>_<역명>` 형식 그대로 사용한다. 형식 검사는 `schemas.ProposalCreate`, **실제 유효성은 저장된 추천 결과에 있는지**로 판단한다.

## 저장 (백A가 만든 테이블)

| 테이블 | 내용 | 삭제 |
| --- | --- | --- |
| `conditions` | 참여자당 1행 (`participant_id` UNIQUE). `data` = `validate_conditions`가 정리한 JSON, `status` = draft/submitted | 참여자 삭제(내 데이터 삭제) 또는 약속방 삭제 시 `ON DELETE CASCADE`. 호스트가 제외한 참여자의 조건 행은 남지만 활성 참여자가 아니므로 추천에서 빠진다 |
| `recommendation_results` | 약속방당 1행. `result` = `recommend` 반환 JSON 전체(모든 참여자의 경로 포함) | 약속방 삭제 시 CASCADE |

- `recommendation_results.result`에는 **모든 참여자의 출발역·경로**가 들어 있으므로 원본을 응답으로 내보내지 않는다. 항상 `view_for` / `get_candidate` / `get_my_route`를 거친다 (테스트로 `legs`가 어떤 응답에도 없음을 확인).
- 조건은 본인만 조회할 수 있다 (`GET /conditions/me`). 다른 사람 조건을 읽는 경로는 없다.

## 단계와의 관계

- 조건 입력/제출은 `input` 단계에서만 가능 (`recommended` 이후 잠김).
- `POST /recommendations`는 활성 참여자 **전원 제출** 후에만 실행된다. 후보가 있으면(`status=ok`) `input → recommended`, **후보가 없으면(`no_candidate`) 단계는 그대로**이고 사유(`reasons`)를 돌려준다.
- 단계/입력 상태를 바꾸는 함수는 `services/hooks.py` (`set_input_status`, `mark_recommended` 등)에 모아 두었다.

## B와 확인할 점

1. **`accessibility` 값**: 응답에 B가 정한 `met`/`unmet`/`unknown`을 그대로 내보낸다. 프론트 표시 문구는 B/프론트와 합의.
2. **참여자 id**: `recommend`에 `str(participants.id)`를 넘긴다. 추천 이후 참여자가 늘 수 없으므로(입력 단계 이후 승인 불가) `my_route`가 `null`인 경우는 거의 없다.
3. **제외된 참여자**: 추천 후에 제외돼도 저장된 추천 결과는 다시 계산하지 않는다 (제외된 사람이 포함된 기준의 결과). 필요하면 호스트가 `recommended` 단계에서 재실행한다.
4. **성능**: 3명·1일 기준 추천 계산 약 0.15초(로컬 측정). 동시에 2건까지만 계산하도록 제한했다 (`services/conditions.py`). 참여자·날짜가 많을 때의 시간은 측정하지 않았다.
5. **패키지 경로**: B 코드는 `from app.core import ...` 형태라서 `backend/` 폴더에서 실행해야 한다 (`uvicorn app.main:app`, `pytest` 모두 `backend/` 기준).
