// 역 이름·노선 표시 도우미 (추천·제안·참여한 약속·역 검색에서 같이 씀)

// '선'만 붙이면 어색한 노선 이름 (나머지는 "경의중앙" → "경의중앙선")
const LINE_NAME = {
  공항철도: '공항철도',
  에버라인: '에버라인',
  김포골드: '김포골드라인',
  의정부: '의정부경전철',
  인천1: '인천1호선',
  인천2: '인천2호선',
  'GTX-A': 'GTX-A',
};

// ["2", "5"] → "2·5호선", ["1", "우이신설"] → "1호선·우이신설선"
export const linesLabel = (lines = []) => {
  const nums = lines.filter((l) => /^\d+$/.test(l));
  const others = lines.filter((l) => !/^\d+$/.test(l)).map((l) => LINE_NAME[l] || `${l}선`);
  return [...(nums.length ? [`${nums.join('·')}호선`] : []), ...others].join('·');
};

// 서버 역 이름 → 화면 이름: "강남" → "강남역", "서울역" → "서울역", "양평(경의중앙)" → "양평역(경의중앙)"
export const stationLabel = (name = '') => {
  const m = name.match(/^(.*?)(\(.*\))$/);
  const [base, suffix] = m ? [m[1], m[2]] : [name, ''];
  return `${base.endsWith('역') ? base : `${base}역`}${suffix}`;
};
