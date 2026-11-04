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

## 기존 개발 DB가 있다면

테이블 구조가 바뀌었다 (방 PIN → 입장 코드). 마이그레이션 도구가 없어서 **예전 `momeet.db`를 삭제하고 다시 실행**해야 한다. (해커톤 개발용 SQLite 기준)

## API 키 (선택)

서울시 엘리베이터 API와 티맵 보행자 경로를 쓸 때만 필요하다. **키가 없어도 서버와 테스트는 그대로 실행된다.**

- 내 컴퓨터: `.env`에 `SEOUL_OPEN_API_KEY=`, `TMAP_APP_KEY=` 뒤에 값만 한 줄로 넣는다 (따옴표·공백 없이).
- 배포(렌더 등): 서비스 설정의 환경 변수에 같은 이름으로 넣는다. `.env` 파일은 올라가지 않는다.
- `.env`는 `.gitignore`에 들어 있다. 키를 채팅·이슈·코드·문서에 붙여넣지 않는다.
- 키는 각자 무료로 발급받을 수 있다 (서울 열린데이터광장 > 인증키 관리, SK Open API > 앱 > appKey).

## 테스트

```bash
python -m pytest                # 백A + 백B(test_fairness) 전체
```

## 시드 데이터 (개발용)

```bash
python -m scripts.seed --yes    # 단계별 약속방 5개 + 입장 코드·토큰 출력 (호스트 비밀번호 demo-password)
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
