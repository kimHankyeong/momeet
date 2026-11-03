# 모밋 백엔드 (FastAPI)

- 백A: 약속방 · 인증 · 진행 상태 · 조건 입력/추천 API — 구현 현황은 [CHECKLIST.md](CHECKLIST.md)
- 백B: 지하철 경로 · 후보 생성 · 공평성 추천 (`app/core/`, `data/`)
- API 초안: [docs/api.md](docs/api.md) · 연동 현황: [docs/integration-B.md](docs/integration-B.md)

> `backend/` 폴더에서 실행한다 (B 코드가 `from app.core import ...` 로 import한다).

## 실행

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # 필요하면 값 수정 (macOS/Linux: cp)
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

## 테스트

```bash
python -m pytest                # 백A + 백B(test_fairness) 전체
```

## 시드 데이터 (개발용)

```bash
python -m scripts.seed --yes    # 단계별 약속방 5개 + 토큰 출력 (PIN 1234 / 호스트 비밀번호 demo-password)
```

## 구조

```
app/
  main.py, config.py, database.py, models.py, schemas.py, security.py, errors.py, deps.py
  routers/       meetings.py, proposals.py, conditions.py     # HTTP 계층 (백A)
  services/      meetings, proposals, joins, conditions, views, state, hooks   # 업무 로직 (백A)
  integrations/  candidates.py                                # 저장된 추천 결과 <-> B의 get_candidate
  core/          subway.py, timeslot.py, fairness.py          # 백B: 경로·후보·추천 (순수 로직)
data/            지하철 데이터 (백B)
scripts/         seed.py (백A), build_subway_data.py (백B)
tests/           test_meetings, test_flow, test_conditions (백A), test_fairness (백B)
docs/
```
