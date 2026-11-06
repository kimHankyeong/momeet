import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const m = config.url?.match(/^\/meetings\/([^/?]+)/);
  const token = (m && localStorage.getItem(`momeet_token_${m[1]}`)) || localStorage.getItem('momeet_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const saveToken = (meetingId, token) => {
  localStorage.setItem('momeet_token', token);
  localStorage.setItem(`momeet_token_${meetingId}`, token);
};

// 약속 생성 (경로·필드는 api.md 확인 후 확정)
export const createMeeting = async (body) =>
  (await api.post('/meetings', body)).data;

// 약속 조회
export const getMeeting = async (id) =>
  (await api.get(`/meetings/${id}`)).data;

// 조건 임시저장 / 최종 제출
export const saveDraft = async (id, body) =>
  (await api.put(`/meetings/${id}/conditions/me/draft`, body)).data;

export const submitConditions = async (id, body) =>
  (await api.post(`/meetings/${id}/conditions/me/submit`, body)).data;

// 역 검색 (자동완성)
export const searchStations = async (q) =>
  (await api.get('/stations', { params: { q } })).data;

// 출발 위치 근처 역 (가까운 순, 도보 추정 포함)
export const nearbyStations = async (lat, lng) =>
  (await api.get('/stations/nearby', { params: { lat, lng } })).data;

// 출발지 장소·주소 검색 (티맵, 최대 5건)
export const searchPlaces = async (q) =>
  (await api.get('/places', { params: { q } })).data;

// 기존 이름 유지 (ConditionSetupModal 호환용)
export const submitUserConditions = submitConditions;

export const hostLogin = async (id, hostPassword) =>
  (await api.post(`/meetings/${id}/host-login`, { host_password: hostPassword })).data;

export const joinMeeting = async (code, nickname) =>
  (await api.post(`/join/${encodeURIComponent(code)}`, { nickname })).data;

// 입장 코드로 방 미리보기 (인증 불필요) → { meeting_id, title, stage, can_join, ... }
export const previewJoin = async (code) =>
  (await api.get(`/join/${encodeURIComponent(code)}`)).data;

// 초대 링크: 처음 온 사람은 참여, 이미 참여한 사람은 지금 단계 화면으로 간다 (토큰이 없어 공유해도 안전)
export const inviteLinkOf = (joinCode) => `${window.location.origin}/join/${joinCode}`;

// 진행 단계별 화면 (recruiting·input은 같은 "입력" 화면)
export const stagePath = (id, stage) => {
  if (stage === 'recommended') return `/meet/${id}/recommend`;
  if (stage === 'proposed' || stage === 'confirmed') return `/meet/${id}/proposal`;
  return `/meet/${id}/setup`;
};

export const leaveMeeting = async (id) => {
  await api.delete(`/meetings/${id}/me`);
  localStorage.removeItem(`momeet_token_${id}`);
};

// 약속방 삭제 (방장만): 방과 모든 데이터 삭제
export const deleteMeeting = async (id) => {
  await api.delete(`/meetings/${id}`);
  localStorage.removeItem(`momeet_token_${id}`);
};

// 모집 마감 (방장만, 참여자 2명 이상)
export const closeRecruiting = async (id) =>
  (await api.post(`/meetings/${id}/close`)).data;

// 추천 실행 (방장만, 전원 조건 제출 후) → { status: 'ok' | 'no_candidate', candidates, reasons? }
export const runRecommendations = async (id) =>
  (await api.post(`/meetings/${id}/recommendations`)).data;

// 추천 결과 조회 (모든 참여자, 내 경로만 포함) → { status, best, candidates[] }
export const getRecommendations = async (id) =>
  (await api.get(`/meetings/${id}/recommendations`)).data;

// 공식 제안 (방장만): 추천 후보의 candidate_id를 그대로 보낸다
export const createProposal = async (id, candidateId) =>
  (await api.post(`/meetings/${id}/proposal`, { candidate_id: candidateId })).data;

// 제안 응답 (전원): 'accept' | 'reject'. 확정 전까지 여러 번 바꿀 수 있다
export const respondProposal = async (id, response) =>
  (await api.post(`/meetings/${id}/proposal/response`, { response })).data;

// 방장: 진행 중인 제안 확정 (거절이 있으면 409 HAS_REJECTION)
export const confirmProposal = async (id) =>
  (await api.post(`/meetings/${id}/proposal/confirm`)).data;