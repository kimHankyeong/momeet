# 렌더(Render) 배포 가이드 — 백엔드

- 대상: 이 저장소의 `backend/` (FastAPI). 프론트는 별도로 배포하고, 이 문서는 **백엔드 서버**만 다룹니다.
- 상태: **아직 실제로 배포해 보지 않았습니다.** 로컬 실행·테스트는 검증했고, 아래 렌더 설정은 공식 문서(링크)와 일반 절차를 근거로 정리한 것입니다. 배포 중 화면·옵션 이름이 다르면 공식 문서를 우선하세요. 확인하지 못한 부분은 ⚠️로 표시했습니다.
- 저장소: https://github.com/kimHankyeong/momeet

## 링크 모음

| 용도 | 링크 |
| --- | --- |
| 렌더 대시보드 | https://dashboard.render.com |
| FastAPI 배포 공식 가이드 | https://docs.render.com/deploy-fastapi |
| FastAPI 예제 저장소 (렌더 제공) | https://github.com/render-examples/fastapi |
| 무료 인스턴스 제한 | https://docs.render.com/free |
| Blueprint(`render.yaml`) 명세 | https://docs.render.com/blueprint-spec |
| 이 프로젝트 저장소 | https://github.com/kimHankyeong/momeet |
| 이 프로젝트 API 문서 | [api.md](api.md) |

---

## 1. 먼저 알아 둘 것 (무료 플랜)

공식 안내([Deploy for Free](https://docs.render.com/free)) 기준입니다.

| 제한 | 내용 | 우리에게 미치는 영향 |
| --- | --- | --- |
| **15분 동안 요청이 없으면 잠듦** | 다시 깨우는 데 약 1분(공식), 블로그에는 30~60초 | 발표 직전 첫 요청이 느림. 프론트에 로딩 표시 필요 |
| **파일 시스템이 사라짐** | 재배포·재시작·잠듦 때마다 **로컬 SQLite 파일이 초기화**됨 | 🔴 **약속방·참여자 데이터가 사라질 수 있음** (아래 2절) |
| 월 750시간 | 한 달 내내 켜 두는 서비스 1개 분량. 한도를 넘으면 월말까지 정지 | 서비스는 1개만 |
| 렌더가 언제든 재시작할 수 있음 | 무료 인스턴스 | 데이터 보존에 의존하면 안 됨 |

⚠️ 무료 인스턴스의 **CPU 성능과 요청 제한 시간은 확인하지 못했습니다.** 추천 계산은 로컬에서 최악 조건(10명·7일·11시간) 약 33초였고, 렌더 무료는 이보다 느릴 수 있습니다. 배포 후 실제 시간을 재 보고, 길면 [coordination.md](coordination.md) 1절의 대안(최적화/비동기화/입력 제한)을 적용하세요.

---

## 2. 데이터 저장 방식 선택 (중요)

현재 서버는 `DATABASE_URL`로 DB를 정하고, 기본값은 SQLite 파일(`sqlite:///./momeet.db`)입니다.

| 선택 | 방법 | 장단점 |
| --- | --- | --- |
| **A. SQLite 그대로 (데모용)** | 아무 설정 없이 배포 | 가장 간단. **잠들거나 재시작하면 데이터가 사라짐.** 시연 직전에 시드로 방을 다시 만들면 됨 (`python -m scripts.seed --yes`) |
| B. 렌더 외부/별도 DB (Postgres 등) | `DATABASE_URL`에 Postgres 주소, `requirements.txt`에 드라이버 추가 | 데이터 유지. ⚠️ **이 프로젝트는 Postgres에서 실행해 보지 않았습니다**(JSON 컬럼을 씀). 무료 DB의 기간·용량 제한도 확인하지 못했습니다 |
| C. 유료 인스턴스 + 영구 디스크 | 렌더 유료 플랜 | 공식 문서상 유료 서비스는 영구 디스크를 쓸 수 있음. 비용 발생 |

**권장(해커톤):** A로 시작하고, 시연 당일에 ① 서버를 미리 깨워 두고 ② 시드 데이터를 다시 만들거나 시연용 방을 새로 만든 뒤 진행합니다. 데이터 유지가 꼭 필요하면 B를 **먼저 로컬에서** 시험한 다음 적용하세요.

---

## 3. 배포 절차 (대시보드)

1. https://dashboard.render.com 에서 가입하고 **GitHub 계정을 연동**해 `kimHankyeong/momeet` 접근을 허용합니다.
2. **New + → Web Service** 선택 후 저장소 `momeet`을 고릅니다.
3. 설정:

   | 항목 | 값 |
   | --- | --- |
   | Name | `momeet-backend` (주소가 `https://momeet-backend.onrender.com` 형태가 됨) |
   | Branch | **`backA`** (현재 A 코드가 있는 브랜치. `main`에 합친 뒤에는 `main`) |
   | Root Directory | **`backend`** (B 코드가 `from app.core import ...`라서 `backend/`가 실행 기준) |
   | Runtime / Language | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | Instance Type | Free |
   | Health Check Path | `/health` (선택 사항. 서버에 `GET /health`가 있음) |

4. **Environment Variables**에 아래를 추가합니다 (4절 참고).
5. **Create Web Service**를 누르면 빌드가 시작됩니다. 로그에서 `Application startup complete` 계열 문구와 `Your service is live`를 확인합니다.
6. 배포 주소 + `/docs` 를 열어 Swagger가 뜨는지 확인합니다.

> 비밀값(키)은 Git에 올리지 않고 **렌더의 Environment Variables에만** 넣습니다. `.env` 파일은 저장소에 없습니다.

### 처음 배포 때 흔히 막히는 점
- `uvicorn: command not found`: 렌더 포럼 사례([링크](https://community.render.com/t/python-fastapi-service-fails-with-uvicorn-command-not-found/39292))가 있습니다. 우리 `requirements.txt`에는 `uvicorn[standard]`가 들어 있으니 **Root Directory가 `backend`인지**, Build Command가 `requirements.txt`를 읽는지 먼저 확인하세요.
- Python 버전: ⚠️ 우리는 **Python 3.14**에서 테스트했습니다. 렌더가 다른 버전으로 빌드하면 의존성 오류가 날 수 있습니다. 렌더에서 `PYTHON_VERSION` 환경 변수로 버전을 지정할 수 있다고 알고 있지만 **공식 문서로 확인하지 못했습니다.** 지정 후 로컬에서 같은 버전으로 `python -m pytest`를 먼저 돌려 보는 것을 권합니다.

---

## 4. 환경 변수

| 이름 | 값 | 필수 | 설명 |
| --- | --- | --- | --- |
| `CORS_ORIGINS` | 프론트 주소 (여러 개는 쉼표로) | **필수** | 예: `https://momeet-front.onrender.com,http://localhost:5173`. 정확한 주소여야 하고 끝에 `/`를 붙이지 않음. 틀리면 브라우저에서 CORS 오류 |
| `FORWARDED_ALLOW_IPS` | `*` | **권장** | 프록시 뒤 클라이언트 구분용 (5절). Start Command에 `--proxy-headers --forwarded-allow-ips="*"`를 붙여도 같음 |
| `DATABASE_URL` | (비워 두면 SQLite) | 선택 | 2절 참고 |
| `BCRYPT_ROUNDS` | `12` (기본) | 선택 | 값이 크면 로그인·방 생성이 느려짐. 무료 CPU에서 느리면 10으로 낮출 수 있으나 보안이 약해짐 |
| `MEETING_TTL_DAYS`, `TOKEN_TTL_DAYS` | `30` (기본) | 선택 | |
| `SEOUL_OPEN_API_KEY` | 서울시 인증키 | 선택 | **지금은 서버가 이 키를 쓰지 않습니다.** 가동 상태 연동 구현 후 필요 |
| `TMAP_APP_KEY` | 티맵 앱키 | 선택 | 출발 위치→출발역 도보 계산에 사용. 비우면 직선거리 추정으로 동작 |

전체 이름은 [`.env.example`](../.env.example)에 있습니다. 렌더에서는 `.env` 대신 이 변수들을 **Environment** 탭에 입력합니다.

---

## 5. 클라이언트 IP와 시도 제한 (배포 때 꼭 확인)

서버는 **같은 클라이언트가 입장 코드를 10번 틀리면 5분간 잠그고**, 호스트 비밀번호도 클라이언트별로 제한합니다. 렌더는 서버 앞에 프록시가 있어서 설정 없이는 **모든 사용자가 프록시 주소 하나로 보입니다.** 그러면 한 사람의 오타가 모두를 잠글 수 있습니다.

- uvicorn은 `X-Forwarded-For`로 클라이언트 주소를 바꾸되, **신뢰하는 주소 목록(`--forwarded-allow-ips` 또는 `FORWARDED_ALLOW_IPS`)에 있는 연결일 때만** 바꿉니다. 기본값은 `127.0.0.1`입니다.
- `*`은 모든 연결을 신뢰하라는 뜻이라, **서버 포트가 인터넷에 직접 열려 있으면 누구나 IP를 속일 수 있어** 위험합니다. 렌더에서는 외부 요청이 렌더 프록시를 거치므로 보통 `*`로 둡니다. ⚠️ 다만 **렌더 프록시가 `X-Forwarded-For`에 실제 클라이언트 IP를 넣는지, 클라이언트가 보낸 값을 그대로 이어붙이는지는 확인하지 못했습니다.**
- 배포 후 직접 확인하세요:
  1. 내 PC에서 `GET /join/zzzzzzzz`를 11번 호출해 `429`가 되는지 확인합니다.
  2. 그 직후 **다른 네트워크(휴대폰 데이터 등)** 에서 올바른 코드로 `GET /join/{코드}`가 `200`인지 확인합니다. 이것이 `429`면 모든 사용자가 한 주소로 보이는 것이므로 설정을 다시 보세요.
  3. 요청 헤더에 가짜 `X-Forwarded-For`를 넣어 호출해도 제한을 피하지 못하는지 확인합니다(보안 확인).

---

## 6. 배포 후 점검 체크리스트

1. `GET https://<서비스 주소>/health` → `{"status":"ok"}`
2. `https://<서비스 주소>/docs` → Swagger 화면
3. 방 생성 → 응답의 `join_code` 확인 → `GET /join/{join_code}` → `POST /join/{join_code}` 참여
4. 조건 제출 → 호스트 `POST /recommendations` → **응답 시간 기록** (렌더 CPU에서 몇 초인지)
5. 프론트에서 호출해 CORS 오류가 없는지 (브라우저 개발자 도구 Console/Network)
6. 5절의 클라이언트 구분 확인
7. 15분 이상 쉰 뒤 첫 요청 시간 측정 (잠든 상태에서 깨어나는 시간)

## 7. 문제 해결

| 증상 | 원인 후보 | 확인 |
| --- | --- | --- |
| 빌드 실패 | Python 버전, Root Directory, 의존성 | 렌더 **Logs**의 빌드 로그, `PYTHON_VERSION` |
| 배포됐는데 접속 안 됨/502 | Start Command의 호스트·포트 | `--host 0.0.0.0 --port $PORT` 확인 |
| 브라우저에서 CORS 오류 | `CORS_ORIGINS`에 프론트 주소 없음/형식 오류 | 정확한 주소(스킴 포함, 끝 `/` 없음), 저장 후 재배포 |
| 모든 사용자가 `429` | 프록시 뒤에서 클라이언트 구분 실패 | 5절 |
| 방이 갑자기 사라짐 | 무료 인스턴스 재시작/잠듦 → SQLite 초기화 | 2절 |
| 첫 요청이 매우 느림 | 잠든 서비스 깨우는 중 | 발표 전 미리 호출, 프론트 로딩 표시 |
| 추천 요청이 오래 걸림/실패 | 추천 계산 시간 | [coordination.md](coordination.md) 1절 성능 |
| `500 INTERNAL_ERROR` | 서버 내부 오류 | 렌더 **Logs**에서 `처리되지 않은 오류: <메서드> <경로>`와 스택 확인 (응답에는 상세가 없음) |
| DB 컬럼 오류 (`join_code` 등) | 예전 DB 파일과 코드 구조 불일치 | 무료 SQLite는 재배포 시 초기화되므로 보통 해결됨. 로컬은 `momeet.db` 삭제 |

원인 보고 형식은 [coordination.md](coordination.md) 5절을 따릅니다.

---

## 8. 선택: Blueprint(`render.yaml`)로 설정을 코드화

설정을 파일로 관리하려면 **저장소 루트**에 `render.yaml`을 둡니다(공식 명세: 파일 이름은 `render.yaml`, 저장소 루트 위치 — [Blueprint YAML Reference](https://docs.render.com/blueprint-spec)). 아래는 위 3~4절 값을 옮긴 **예시이며 실제로 배포해 보지 않았습니다.** 필드 이름은 명세에서 확인하세요.

```yaml
services:
  - type: web
    name: momeet-backend
    runtime: python
    plan: free
    branch: backA            # main에 합친 뒤에는 main
    rootDir: backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: FORWARDED_ALLOW_IPS
        value: "*"
      - key: CORS_ORIGINS
        sync: false          # 대시보드에서 값을 직접 입력 (명세: sync:false 는 값을 물어봄)
      - key: SEOUL_OPEN_API_KEY
        sync: false
      - key: TMAP_APP_KEY
        sync: false
```

- 비밀값은 `value`로 적지 말고 `sync: false`로 두어 **대시보드에서 직접 입력**하세요(파일에 적으면 Git에 올라갑니다).
- 이 파일은 현재 저장소에 **추가하지 않았습니다.** 필요하면 알려 주세요.

---

## 9. 팀에 전달할 값 (배포 후)

| 받는 사람 | 전달할 것 |
| --- | --- |
| 프론트 | 백엔드 주소 `https://<서비스 주소>`, API 문서 [api.md](api.md), 방 만들기/참여 흐름 변경(입장 코드) |
| 프론트 → 백엔드 | **프론트 배포 주소** (서버의 `CORS_ORIGINS`에 등록해야 함) |
| 모두 | 무료 인스턴스는 잠들고 데이터가 초기화될 수 있다는 점, 시연 전 점검 절차(6절) |

키 값은 채팅·문서·저장소에 올리지 말고 렌더의 환경 변수에만 넣으세요.
