import { useState, useRef, useEffect } from 'react';
import { DayPicker } from 'react-day-picker';
import { ko } from 'date-fns/locale';
import 'react-day-picker/style.css';
import './DateRangeInput.css';

const format = (date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}.${m}.${d}`;
};

function DateRangeInput({ value, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef(null);

  // 바깥 클릭하면 달력 닫기
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (range) => {
    onChange(range);
    // 시작일과 종료일이 둘 다 선택되면 닫기
    // 첫 클릭에는 from == to(같은 날)로 들어오므로 그때는 닫지 않는다 (하루짜리는 바깥을 누르면 닫힘)
    if (range?.from && range?.to && range.from.getTime() !== range.to.getTime()) setIsOpen(false);
  };

  const label =
    value?.from && value?.to
      ? `${format(value.from)}-${format(value.to)}`
      : value?.from
      ? `${format(value.from)} - 종료일 선택`
      : '선택하기';

  const hasValue = value?.from;

  return (
    <div className="date-range" ref={wrapperRef}>
      <button
        type="button"
        className={`date-range__button ${hasValue ? 'date-range__button--filled' : ''}`}
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M3 10h18M8 3v4M16 3v4" />
        </svg>
        {label}
      </button>

      {isOpen && (
        <div className="date-range__popup">
          <DayPicker
            mode="range"
            selected={value}
            onSelect={handleSelect}
            locale={ko}
            disabled={{ before: new Date() }}
          />
        </div>
      )}
    </div>
  );
}

export default DateRangeInput;