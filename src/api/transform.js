const CONSTRAINT_KEY = {
  maxTime: 'max_travel_min',
  maxTransfer: 'max_transfers',
  maxWalk: 'max_walk_m',
  elevator: 'needs_elevator',
  avoidStairs: 'avoid_stairs',
};

const pad = (n) => String(n).padStart(2, '0');

// Date → "YYYY-MM-DD" (로컬 기준. toISOString 금지)
export const toDateString = (d) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

// 선택 칸 Set("0-16") → { "2026-11-01": [16,17,...] }
export function cellsToAvailability(selectedCells, startDate) {
  const result = {};
  selectedCells.forEach((key) => {
    const [dayIdx, hour] = key.split('-').map(Number);
    const date = new Date(startDate);
    date.setDate(date.getDate() + dayIdx);
    (result[toDateString(date)] ||= []).push(hour);
  });
  Object.values(result).forEach((arr) => arr.sort((a, b) => a - b));
  return result;
}

// 화면 조건 목록 → constraints
export function conditionsToConstraints(addedConditions) {
  const out = {};
  addedConditions.forEach((c) => {
    const key = CONSTRAINT_KEY[c.id];
    if (!key) return;
    let value;
    if (c.type === 'badge') value = true;
    else {
      const num = parseInt(c.value, 10); // "60분"→60, "1회"→1
      value = c.id === 'maxWalk' ? num * 72 : num; // 도보 분→미터
    }
    out[key] = { value, level: c.priority === '필수' ? 'required' : 'preferred' };
  });
  return out;
}

// "신설동역" → "신설동" (백엔드는 역 이름만)
export const stripStationSuffix = (name) => name.replace(/역$/, '');
