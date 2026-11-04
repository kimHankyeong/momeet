import axios from 'axios';

// 환경 변수 또는 백엔드 기본 서버 주소
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * 개인 조건 입력 정보 전송 API
 * @param {string} meetId - 모임 ID
 * @param {object} data - { location: string, options: string[] }
 */
export const submitUserConditions = async (meetId, data) => {
  const response = await api.post(`/api/v1/meets/${meetId}/conditions`, data);
  return response.data;
};