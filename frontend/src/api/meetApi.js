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

// 기존 이름 유지 (ConditionSetupModal 호환용)
export const submitUserConditions = submitConditions;

export const hostLogin = async (id, hostPassword) =>
  (await api.post(`/meetings/${id}/host-login`, { host_password: hostPassword })).data;

export const joinMeeting = async (code, nickname) =>
  (await api.post(`/join/${encodeURIComponent(code)}`, { nickname })).data;

export const leaveMeeting = async (id) => {
  await api.delete(`/meetings/${id}/me`);
  localStorage.removeItem(`momeet_token_${id}`);
};

// 약속방 삭제 (방장만): 방과 모든 데이터 삭제
export const deleteMeeting = async (id) => {
  await api.delete(`/meetings/${id}`);
  localStorage.removeItem(`momeet_token_${id}`);
};