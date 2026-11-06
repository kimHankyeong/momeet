# momeet 프론트엔드

React + Vite로 만든 momeet 웹 화면입니다. 서버(FastAPI)와는 REST API로 통신합니다.

- 배포: https://momeet-frontend.onrender.com
- API 명세: [../backend/docs/api.md](../backend/docs/api.md)
- 프로젝트 전체 소개: [../README.md](../README.md)

## 실행

```bash
cd frontend
npm install
copy .env.example .env     # macOS/Linux: cp .env.example .env
npm run dev                # http://localhost:5173
```

| 명령 | 설명 |
| --- | --- |
| `npm run dev` | 개발 서버 |
| `npm run build` | 배포용 빌드 (`dist/`) |
| `npm run lint` | 코드 검사 |
| `npm run preview` | 빌드 결과 미리보기 |

서버가 `http://localhost:8000`에서 떠 있어야 화면이 동작합니다 (실행 방법은 [../backend/README.md](../backend/README.md)).

## 환경 변수

| 이름 | 설명 |
| --- | --- |
| `VITE_API_URL` | 서버 주소. 없으면 `http://localhost:8000`. **빌드할 때 코드에 들어가므로 값을 바꾸면 다시 빌드·배포해야 한다** |

## 기술

React, Vite, Tailwind CSS, React Router, axios, Leaflet(OpenStreetMap 지도)

## 화면

| 경로 | 화면 |
| --- | --- |
| `/` | 홈 (약속 만들기, 초대 링크로 참여하기) |
| `/join/:code` | 초대 링크. 처음 온 사람은 참여, 이미 참여한 사람은 지금 단계 화면으로 이동 |
| `/meet/:id/setup` | 약속방 (모집·입력). 참여자 현황, 조건 입력, 초대 링크 복사, 모집 마감, 추천 실행 |
| `/meet/:id/recommend` | 추천 결과. 후보 목록, 선택한 역의 지도, 방장은 공식 제안 |
| `/meet/:id/proposal` | 제안 확인(동의·거절), 방장의 확정, 확정 결과 |
| `/meetings/joined` | 참여한 약속 (진행 중 / 종료된 약속) |
| `/meetings/settings` | 약속방 설정. 개인 재접속 링크, 나가기·삭제, 방장 권한 받기 |

## 폴더 구조

```
src/
├─ api/
│  ├─ meetApi.js       서버 호출 전부 (토큰 저장 포함)
│  └─ transform.js     화면 입력 ↔ 서버 형식 변환 (시간표, 이동 조건 등)
├─ pages/              화면
├─ components/         공통 UI와 화면별 컴포넌트 (조건 입력 모달, 출발지 선택, 역 지도 등)
└─ utils/
```

## 서버 연동 메모

- **인증:** 약속방마다 서버가 발급한 토큰을 `Authorization: Bearer`로 보낸다. 토큰은 브라우저 `localStorage`의 `momeet_token_<방ID>`에 저장한다 (쿠키 미사용).
- **실시간 갱신 없음:** 서버 푸시(웹소켓)가 없어서 약속방·추천·제안 화면이 **5초마다** 상태를 다시 확인한다.
- **날짜:** 서버와는 `YYYY-MM-DD`로 주고받고, 브라우저 시간대 때문에 하루 밀리지 않도록 로컬 날짜 기준으로 변환한다 (`toDateString`).
