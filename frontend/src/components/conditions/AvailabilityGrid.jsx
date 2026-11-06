import { useState, useEffect } from 'react';
import './AvailabilityGrid.css';

const DAYS_PER_PAGE = 7;

// selected: Set("날짜인덱스-시간"), onChange: 새 Set을 받는 함수
// startDate: 약속방 첫날(Date). 있으면 칸 이름을 "11/6"처럼 실제 날짜로 보여 준다
function AvailabilityGrid({ selected, onChange, totalDays = 8, startDate }) {
  const dayLabel = (day) => {
    if (!startDate) return `${day + 1}일`;
    const d = new Date(startDate);
    d.setDate(d.getDate() + day);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const [expanded, setExpanded] = useState(false);
  const [startDay, setStartDay] = useState(0); // 화면 첫 번째 날짜 인덱스
  const [dragMode, setDragMode] = useState(null); // 'add' | 'remove' | null

  const startHour = expanded ? 0 : 7;
  const hours = Array.from({ length: 24 - startHour }, (_, i) => startHour + i);

  const visibleCount = Math.min(DAYS_PER_PAGE, totalDays);
  const maxStart = totalDays - visibleCount; // 마지막 화면의 시작 인덱스
  const days = Array.from({ length: visibleCount }, (_, i) => startDay + i);

  const goPrev = () => setStartDay((s) => Math.max(0, s - DAYS_PER_PAGE));
  const goNext = () => setStartDay((s) => Math.min(maxStart, s + DAYS_PER_PAGE));

  const keyOf = (day, hour) => `${day}-${hour}`;

  const applyCells = (keys, mode) => {
    const next = new Set(selected);
    keys.forEach((k) => (mode === 'add' ? next.add(k) : next.delete(k)));
    onChange(next);
  };

  const handleCellDown = (day, hour) => {
    const mode = selected.has(keyOf(day, hour)) ? 'remove' : 'add';
    setDragMode(mode);
    applyCells([keyOf(day, hour)], mode);
  };

  const handleCellEnter = (day, hour) => {
    if (dragMode) applyCells([keyOf(day, hour)], dragMode);
  };

  const toggleDay = (day) => {
    const keys = hours.map((h) => keyOf(day, h));
    const allOn = keys.every((k) => selected.has(k));
    applyCells(keys, allOn ? 'remove' : 'add');
  };

  const toggleHour = (hour) => {
    const keys = days.map((d) => keyOf(d, hour));
    const allOn = keys.every((k) => selected.has(k));
    applyCells(keys, allOn ? 'remove' : 'add');
  };

  useEffect(() => {
    const stop = () => setDragMode(null);
    window.addEventListener('mouseup', stop);
    return () => window.removeEventListener('mouseup', stop);
  }, []);

  return (
    <div>
      <div className="grid__wrap">
        <button
            type="button"
            className="grid__arrow"
            disabled={startDay === 0}
            onClick={goPrev}
            aria-label="이전 날짜"
     >
        ‹
    </button>

        <div className="grid__table" style={{ '--cols': days.length }}>
          <div className="grid__corner" />
          {days.map((d, i) => (
            <button
              type="button"
              key={d}
              className={`grid__day ${i % 2 === 0 ? 'grid__day--odd' : ''}`}
              onClick={() => toggleDay(d)}
            >
              {dayLabel(d)}
            </button>
          ))}

          {hours.map((h) => (
            <div className="grid__row" key={h}>
              <button type="button" className="grid__hour" onClick={() => toggleHour(h)}>
                {String(h).padStart(2, '0')}:00
              </button>
              {days.map((d, i) => (
                <div
                  key={d}
                  className={
                    'grid__cell' +
                    (i % 2 === 0 ? ' grid__cell--odd' : '') +
                    (selected.has(keyOf(d, h)) ? ' grid__cell--on' : '')
                  }
                  onMouseDown={() => handleCellDown(d, h)}
                  onMouseEnter={() => handleCellEnter(d, h)}
                />
              ))}
            </div>
          ))}
        </div>

        <button
            type="button"
            className="grid__arrow"
            disabled={startDay >= maxStart}
            onClick={goNext}
            aria-label="다음 날짜"
        >
            ›
        </button>
      </div>

      <button type="button" className="grid__expand" onClick={() => setExpanded((v) => !v)}>
        {expanded ? '축소' : '확장'}
      </button>
      <p className="grid__notice">
        선택된 시간은 약속 장소 도착 시간이 아닌 출발 가능 시간이에요.
      </p>
    </div>
  );
}

export default AvailabilityGrid;