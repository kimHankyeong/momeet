import { useEffect, useRef, useState } from 'react';
import { searchStations } from '../api/meetApi';
import { linesLabel, stationLabel } from '../utils/station';

// 지하철역 입력 + 자동완성 (서버 /stations 검색)
// value: 입력값, onChange(text), onPick(서버 역 이름): 목록에서 고르면 서버 역 이름으로 확정
// 같은 이름 다른 역(예: 양평 / 양평(경의중앙))은 목록에서 노선으로 구분해 고른다
export default function StationInput({ value, onChange, onPick, onEnter, className = '', autoFocus = false }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const typed = useRef(''); // 사용자가 직접 입력한 값일 때만 검색 (목록·추천 칩으로 바뀐 값은 검색 안 함)

  useEffect(() => {
    const q = value.trim().replace(/역$/, '');
    if (!q || value !== typed.current) {
      setResults([]);
      return undefined;
    }
    let alive = true;
    // 입력이 멈춘 뒤 검색 (글자마다 부르지 않게)
    const t = setTimeout(() => {
      searchStations(q)
        .then((res) => {
          if (!alive) return;
          setResults(res.stations || []);
          setActive(0);
          setOpen(true);
        })
        .catch(() => alive && setResults([]));
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [value]);

  const pick = (st) => {
    typed.current = '';
    onChange(st.name);
    onPick?.(st.name);
    setResults([]);
    setOpen(false);
  };

  const handleKeyDown = (e) => {
    const showing = open && results.length > 0;
    if (e.key === 'ArrowDown' && showing) {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp' && showing) {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      if (showing) {
        e.preventDefault();
        pick(results[active]);
      } else {
        onEnter?.();
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <input
        type="text"
        placeholder="지하철 역 검색"
        value={value}
        onChange={(e) => {
          typed.current = e.target.value;
          onChange(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)} // 목록 클릭이 먼저 처리되게
        className={className}
        autoFocus={autoFocus}
      />
      {open && results.length > 0 && (
        <ul className="absolute z-10 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-2xl shadow-lg max-h-56 overflow-y-auto text-left">
          {results.map((st, i) => (
            <li key={st.name}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(st)}
                className={`w-full px-4 py-2.5 flex justify-between items-center text-sm ${
                  i === active ? 'bg-[#F0EEFF]' : 'hover:bg-gray-50'
                }`}
              >
                <span className="font-medium text-gray-900">{stationLabel(st.name)}</span>
                <span className="text-xs text-gray-500">{linesLabel(st.lines)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
