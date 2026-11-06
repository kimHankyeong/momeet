import { useState } from 'react';
import AvailabilityGrid from './conditions/AvailabilityGrid';
import { submitConditions } from '../api/meetApi';
import { cellsToAvailability } from '../api/transform';


// startDate: 약속방 시작일 "YYYY-MM-DD", totalDays: 약속방 날짜 수 (SetupPage가 서버에서 받아 넘김)
export default function ConditionSetupModal({ isOpen, onClose, onSubmitSuccess, meetingId, startDate, totalDays = 7 }) {

  const [step, setStep] = useState(1);

  // STEP 1: 시간 선택
const [selectedCells, setSelectedCells] = useState(new Set());

// "2026-11-10" → 로컬 Date (new Date("2026-11-10")은 UTC로 해석돼서 쓰지 않음)
const START_DATE = startDate
  ? new Date(Number(startDate.slice(0, 4)), Number(startDate.slice(5, 7)) - 1, Number(startDate.slice(8, 10)))
  : new Date();
const DOW = ['일', '월', '화', '수', '목', '금', '토'];
const pad = (n) => String(n).padStart(2, '0');

// [변경] 문자열 대신 객체 배열로 만들고, selectedTimes는 여기서 파생
const timeRanges = (() => {
  const byDay = {};
  selectedCells.forEach((key) => {
    const [d, h] = key.split('-').map(Number);
    (byDay[d] ||= []).push(h);
  });
  const result = [];
  Object.keys(byDay)
    .map(Number)
    .sort((a, b) => a - b)
    .forEach((d) => {
      const hours = byDay[d].sort((a, b) => a - b);
      const date = new Date(START_DATE);
      date.setDate(date.getDate() + d);
      const label = `${date.getMonth() + 1}월 ${date.getDate()}일(${DOW[date.getDay()]})`;
      let start = hours[0];
      let prev = hours[0];
      for (let i = 1; i <= hours.length; i++) {
        if (hours[i] !== prev + 1) {
          result.push({
            id: `${d}-${start}`,
            label,
            start: `${pad(start)}:00`,
            end: `${pad(prev + 1)}:00`,
          });
          start = hours[i];
        }
        prev = hours[i];
      }
    });
  return result;
})();

const selectedTimes = timeRanges.map((r) => `${r.label} ${r.start}-${r.end}`);

  // STEP 2: 출발지 + 출발역 [변경]
  const [origin, setOrigin] = useState(null); // { place, station } 확정된 기본 출발
  const [originDraft, setOriginDraft] = useState({ place: '', station: '' });
  const [exceptions, setExceptions] = useState([]);
  const [showExceptionForm, setShowExceptionForm] = useState(false);
  const [exceptionDraft, setExceptionDraft] = useState({ rangeId: '', place: '', station: '' });

  // STEP 3: 이동 조건 상태 (Frame 11, 12, 13)
  const [isSelectingCondition, setIsSelectingCondition] = useState(false); // Frame 12(선택 리스트) 열림 여부
  const [addedConditions, setAddedConditions] = useState([]); // 선택된 조건 목록

  // STEP 4: 최종 동의 체크박스 (Frame 14, 22)
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  if (!isOpen) return null;

  const handleNext = () => setStep((prev) => Math.min(prev + 1, 4));

  // [추가] 기본 출발 확정
  const commitOrigin = () => {
    const place = originDraft.place.trim();
    const station = originDraft.station.trim();
    if (place && station) setOrigin({ place, station });
  };

  // [추가] 예외 출발 추가/삭제
  const handleAddException = () => {
    const { rangeId, place, station } = exceptionDraft;
    const range = timeRanges.find((r) => r.id === rangeId);
    if (!range || !place.trim() || !station.trim()) return;
    setExceptions((prev) => [
      ...prev,
      {
        id: Date.now(),
        label: range.label,
        startTime: range.start,
        endTime: range.end,
        place: place.trim(),
        station: station.trim(),
      },
    ]);
    setExceptionDraft({ rangeId: '', place: '', station: '' });
  };

  const handleRemoveException = (id) =>
    setExceptions((prev) => prev.filter((e) => e.id !== id));

  // 조건 선택 및 추가 핸들러
  const handleSelectOption = (item) => {
    if (!addedConditions.some((c) => c.id === item.id)) {
      setAddedConditions((prev) => [...prev, item]);
    }
    setIsSelectingCondition(false);
  };

  const handleRemoveCondition = (id) => {
    setAddedConditions((prev) => prev.filter((c) => c.id !== id));
  };

  const handleTogglePriority = (id, priority) => {
    setAddedConditions((prev) =>
      prev.map((c) => (c.id === id ? { ...c, priority } : c))
    );
  };

  const handleValueChange = (id, value) => {
    setAddedConditions((prev) =>
      prev.map((c) => (c.id === id ? { ...c, value } : c))
    );
  };

 const handleSubmit = async () => {
  setSubmitting(true);
  setErrorMsg('');
  const constraints = {};
  addedConditions.forEach((c) => {
    const level = c.priority === '필수' ? 'required' : 'preferred';
    const val = parseInt(c.value, 10) || 0;
    if (c.id === 'maxTime') constraints.max_travel_min = { value: val, level };
    if (c.id === 'maxTransfer') constraints.max_transfers = { value: val, level };
    if (c.id === 'maxWalk') constraints.max_walk_m = { value: val * 72, level };
    if (c.id === 'elevator') constraints.needs_elevator = { value: true, level };
    if (c.id === 'avoidStairs') constraints.avoid_stairs = { value: true, level };
  });

  const stationName = (origin?.station || '').replace(/역$/, '').trim();
  try {
    await submitConditions(meetingId, {
      availability: cellsToAvailability(selectedCells, START_DATE),
      default_station: stationName,
      constraints,
    });
    onSubmitSuccess({ location: stationName, selectedTimes, addedConditions });
    onClose();
  } catch (e) {
    const err = e.response?.data?.error;
    setErrorMsg(err?.errors?.[0]?.message || err?.message || '제출하지 못했어요. 다시 시도해 주세요.');
  } finally {
    setSubmitting(false);
  }
};

  // 3단계 선택 가능한 전체 항목 (Frame 12)
  const availableOptions = [
  { id: 'maxTime', name: '최대 이동 시간', value: '60분', priority: '필수', type: 'select',
    options: ['30분', '60분', '90분', '120분'] },
  { id: 'maxTransfer', name: '최대 환승 횟수', value: '1회', priority: '필수', type: 'select',
    options: ['0회', '1회', '2회', '3회'] },
  { id: 'maxWalk', name: '최대 도보 거리', value: '10분', priority: '선호', type: 'select',
    options: ['5분', '10분', '15분', '20분'] },
  { id: 'elevator', name: '엘리베이터 필요', value: '엘리베이터 이용', priority: '필수', type: 'badge' },
  { id: 'avoidStairs', name: '계단 회피', value: '계단 없는 경로', priority: '선호', type: 'badge' },
  ];
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white w-full max-w-[440px] rounded-[32px] p-6 shadow-2xl relative space-y-5 max-h-[85vh] overflow-y-auto">
        {/* 모달 상단 헤더 */}
        <div className="flex justify-between items-start">
          <div>
            <h3 className="text-lg font-bold text-gray-900">
              {step === 1 && '언제 가능한가요?'}
              {step === 2 && '어디서 출발하나요?'}
              {step === 3 && '이동 시 고려할 조건이 있나요?'}
              {step === 4 && '잊으신 조건은 없나요?'}
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              {step === 1 && '시간이나 요일을 클릭해주세요'}
              {step === 2 && '출발하는 지하철 역을 알려주세요'}
              {step === 3 && '아무 조건도 설정하지 않아도 괜찮아요'}
              {step === 4 && '제출하기 전 한 번 더 확인해 주세요'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-gray-400 hover:text-gray-600 font-normal pt-1"
          >
            나가기
          </button>
        </div>

        {step === 1 && (
          <div className="space-y-6 pt-1">
            <AvailabilityGrid selected={selectedCells} onChange={setSelectedCells} totalDays={totalDays} startDate={START_DATE} />

            <button
              type="button"
              disabled={selectedCells.size === 0}
              onClick={handleNext}
              className={`w-full py-3.5 font-bold rounded-2xl text-sm transition-all ${
                selectedCells.size > 0
                  ? 'bg-[#6C5CE7] hover:bg-[#5b4cdb] text-white shadow-sm'
                  : 'bg-[#F5F5F7] text-gray-300 cursor-not-allowed'
              }`}
            >
              다음
            </button>
          </div>
        )}

        {/* STEP 2: 어디서 출발하나요? [변경] 출발지 + 역, 예외 출발 */}
        {step === 2 && (
          <div className="space-y-6 pt-1">
            <div className="space-y-2 text-center">
              {/* 기본 출발: 미확정이면 입력, 확정이면 보라색 칩 */}
              {!origin ? (
                <>
                  <input
                    type="text"
                    placeholder="출발지"
                    value={originDraft.place}
                    onChange={(e) => setOriginDraft((d) => ({ ...d, place: e.target.value }))}
                    className="w-full py-3.5 px-4 bg-[#F5F5F7] border-none rounded-full text-sm text-center placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#6C5CE7]"
                    autoFocus
                  />
                  <input
                    type="text"
                    placeholder="지하철 역 검색"
                    value={originDraft.station}
                    onChange={(e) => setOriginDraft((d) => ({ ...d, station: e.target.value }))}
                    onKeyDown={(e) => e.key === 'Enter' && commitOrigin()}
                    className="w-full py-3.5 px-4 bg-[#F5F5F7] border-none rounded-full text-sm text-center placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#6C5CE7]"
                  />
                  <span className="text-xs text-gray-300 block pt-1">다른 출발 설정</span>
                </>
              ) : (
                <>
                  {[origin.place, origin.station].map((text, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => {
                        setOriginDraft(origin); // 칩을 누르면 다시 수정
                        setOrigin(null);
                      }}
                      className="w-full py-3.5 bg-[#6C5CE7] text-white font-bold rounded-full text-sm shadow-sm"
                    >
                      {text}
                    </button>
                  ))}

                  {/* 확정된 예외 출발들 */}
                  {exceptions.map((ex) => (
                    <div key={ex.id} className="space-y-2 pt-3">
                      <div className="flex justify-between items-center px-4 text-xs">
                        <span className="text-gray-700">
                          {ex.label} {ex.startTime} ~ {ex.endTime}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleRemoveException(ex.id)}
                          className="text-gray-400 hover:text-gray-600 underline"
                        >
                          삭제
                        </button>
                      </div>
                      {[ex.place, ex.station].map((text, i) => (
                        <div
                          key={i}
                          className="w-full py-3 border border-[#6C5CE7] text-[#6C5CE7] font-bold rounded-full text-sm"
                        >
                          {text}
                        </div>
                      ))}
                    </div>
                  ))}

                  {/* 예외 출발 입력 폼 */}
                  {showExceptionForm ? (
                    <div className="space-y-2 pt-3">
                      <select
                        value={exceptionDraft.rangeId}
                        onChange={(e) => setExceptionDraft((d) => ({ ...d, rangeId: e.target.value }))}
                        className="w-full py-3.5 px-4 bg-[#F5F5F7] rounded-full text-sm text-center text-gray-500 focus:outline-none focus:ring-2 focus:ring-[#6C5CE7]"
                      >
                        <option value="">날짜 선택</option>
                        {timeRanges.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.label} {r.start} ~ {r.end}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        placeholder="출발지"
                        value={exceptionDraft.place}
                        onChange={(e) => setExceptionDraft((d) => ({ ...d, place: e.target.value }))}
                        className="w-full py-3.5 px-4 bg-[#F5F5F7] border-none rounded-full text-sm text-center placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#6C5CE7]"
                      />
                      <input
                        type="text"
                        placeholder="지하철 역 검색"
                        value={exceptionDraft.station}
                        onChange={(e) => setExceptionDraft((d) => ({ ...d, station: e.target.value }))}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddException()}
                        className="w-full py-3.5 px-4 bg-[#F5F5F7] border-none rounded-full text-sm text-center placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#6C5CE7]"
                      />
                      <button
                        type="button"
                        onClick={handleAddException}
                        disabled={
                          !exceptionDraft.rangeId ||
                          !exceptionDraft.place.trim() ||
                          !exceptionDraft.station.trim()
                        }
                        className="text-xs underline text-gray-500 hover:text-[#6C5CE7] disabled:text-gray-300 disabled:no-underline disabled:cursor-not-allowed"
                      >
                        추가
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setShowExceptionForm(true)}
                      className="text-xs text-gray-400 hover:text-gray-600 underline pt-1"
                    >
                      다른 출발 설정
                    </button>
                  )}
                </>
              )}
            </div>

            <button
              type="button"
              disabled={!origin}
              onClick={handleNext}
              className={`w-full py-3.5 font-bold rounded-full text-sm transition-all ${
                origin
                  ? 'bg-[#6C5CE7] hover:bg-[#5b4cdb] text-white shadow-sm'
                  : 'bg-[#F5F5F7] text-gray-300 cursor-not-allowed'
              }`}
            >
              다음
            </button>
          </div>
        )}

        {/* STEP 3: 이동 시 고려할 조건이 있나요? (Frame 11, 12, 13) */}
        {step === 3 && (
          <div className="space-y-5 pt-1">
            {/* 1) Frame 11: 설정된 조건이 없을 때 */}
            {addedConditions.length === 0 && !isSelectingCondition && (
              <div className="space-y-3 py-4 text-center">
                <button
                  type="button"
                  onClick={() => setIsSelectingCondition(true)}
                  className="w-full py-3.5 bg-[#F5F5F7] hover:bg-gray-200 text-[#A0A0A0] text-sm font-medium rounded-2xl transition-colors"
                >
                  이동 조건 추가하기
                </button>
                <p className="text-xs text-[#B0B0B0] font-normal">
                  설정한 조건이 없어요. 제한 없이 진행할 수 있어요.
                </p>
              </div>
            )}

            {/* 2) Frame 12: 항목 선택 리스트 (이동 조건 추가하기 클릭 시) */}
            {isSelectingCondition && (
              <div className="space-y-2 py-1">
                {availableOptions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleSelectOption(item)}
                    className="w-full flex justify-between items-center py-3.5 px-5 bg-[#F5F5F7] hover:bg-[#EAEAF0] text-[#808080] hover:text-[#6C5CE7] rounded-2xl text-xs font-medium transition-colors"
                  >
                    <span>{item.name}</span>
                    <span className="text-[#A0A0A0] text-base font-normal">+</span>
                  </button>
                ))}
              </div>
            )}

            {/* 3) Frame 13: 이미 추가된 조건 카드가 있을 때 */}
            {addedConditions.length > 0 && !isSelectingCondition && (
              <div className="space-y-4">
                {addedConditions.map((cond) => (
                  <div key={cond.id} className="border-b border-gray-100 pb-3 space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-xs font-bold text-gray-900">{cond.name}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveCondition(cond.id)}
                        className="text-xs text-gray-400 hover:text-gray-600 underline"
                      >
                        제거
                      </button>
                    </div>

                    <div className="flex justify-between items-center gap-2">
                      {/* 좌측 값 선택/표시 */}
                      {cond.type === 'select' ? (
                        <select
                          value={cond.value}
                          onChange={(e) => handleValueChange(cond.id, e.target.value)}
                          className="bg-[#F5F5F7] text-xs px-3 py-2 rounded-xl border-none text-gray-700 font-medium focus:outline-none cursor-pointer pr-6"
                        >
                         {cond.options.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                        ))}
                        </select>
                      ) : (
                        <span className="px-4 py-2 bg-[#6C5CE7] text-white text-xs font-bold rounded-2xl">
                          {cond.value}
                        </span>
                      )}

                      {/* 우측 [ 필수 ] [ 선호 ] 토글 */}
                      <div className="flex bg-[#F5F5F7] p-0.5 rounded-2xl text-xs">
                        <button
                          type="button"
                          onClick={() => handleTogglePriority(cond.id, '필수')}
                          className={`px-3.5 py-1.5 rounded-xl font-bold transition-all ${
                            cond.priority === '필수'
                              ? 'bg-[#6C5CE7] text-white shadow-sm'
                              : 'text-gray-400 hover:text-gray-600'
                          }`}
                        >
                          필수
                        </button>
                        <button
                          type="button"
                          onClick={() => handleTogglePriority(cond.id, '선호')}
                          className={`px-3.5 py-1.5 rounded-xl font-bold transition-all ${
                            cond.priority === '선호'
                              ? 'bg-[#6C5CE7] text-white shadow-sm'
                              : 'text-gray-400 hover:text-gray-600'
                          }`}
                        >
                          선호
                        </button>
                      </div>
                    </div>
                  </div>
                ))}

                {/* 추가 조건 더 입력하기 버튼 */}
                <button
                  type="button"
                  onClick={() => setIsSelectingCondition(true)}
                  className="w-full py-3.5 bg-[#F5F5F7] hover:bg-gray-200 text-[#A0A0A0] text-xs font-medium rounded-2xl transition-colors mt-2"
                >
                  이동 조건 추가하기
                </button>
              </div>
            )}

            {/* 하단 보라색 다음 버튼 */}
            <button
              type="button"
              onClick={handleNext}
              className="w-full py-3.5 bg-[#6C5CE7] hover:bg-[#5b4cdb] text-white font-bold rounded-2xl text-sm transition-colors shadow-sm"
            >
              다음
            </button>
          </div>
        )}

        {/* STEP 4: 잊으신 조건은 없나요? (Frame 14, 22) */}
        {step === 4 && (
          <div className="space-y-5 pt-1">
            {/* 1) 출발 가능 시간 */}
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-[#6C5CE7]">출발 가능 시간</span>
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="text-xs text-gray-300 hover:text-gray-500"
                >
                  수정
                </button>
              </div>
              <div className="space-y-1.5">
                {selectedTimes.map((time, idx) => (
                  <div
                    key={idx}
                    className="bg-[#F5F5F7] py-2 px-4 rounded-2xl text-xs text-gray-700 font-medium text-center"
                  >
                    {time}
                  </div>
                ))}
              </div>
            </div>

            {/* 2) 출발역 [변경] 실제 값 표시 */}
            <div className="space-y-1 pt-1">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-[#6C5CE7]">출발역</span>
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="text-xs text-gray-300 hover:text-gray-500"
                >
                  수정
                </button>
              </div>
              <div className="text-xs space-y-1 text-gray-700 pt-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400 text-[11px]">기본 출발</span>
                  <span className="font-bold text-gray-800">
                    {origin ? `${origin.place} · ${origin.station}` : '-'}
                  </span>
                </div>
                {exceptions.length > 0 && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-gray-400 text-[11px]">예외 출발</span>
                      <span className="font-bold text-gray-800">{exceptions.length}개</span>
                    </div>
                    {exceptions.map((ex) => (
                      <div key={ex.id} className="bg-[#F5F5F7] text-gray-700 text-[10px] px-2 py-1 rounded">
                        {ex.label} {ex.startTime}-{ex.endTime} · {ex.place} · {ex.station}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 3) 이동/접근성 조건 */}
            <div className="space-y-1.5 border-t border-gray-100 pt-3">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-[#6C5CE7]">이동/접근성 조건</span>
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="text-xs text-gray-300 hover:text-gray-500"
                >
                  수정
                </button>
              </div>
              <div className="space-y-1.5">
                {addedConditions.length > 0 ? (
                  addedConditions.map((cond) => (
                    <div key={cond.id} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-700">{cond.name}</span>
                        <span className="text-gray-700 font-medium">{cond.value}</span>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          cond.priority === '필수'
                            ? 'bg-[#6C5CE7] text-white'
                            : 'bg-gray-200 text-gray-600'
                        }`}
                      >
                        {cond.priority}
                      </span>
                    </div>
                  ))
                ) : (
                  <span className="text-xs text-gray-400">설정된 조건이 없습니다.</span>
                )}
              </div>
            </div>

            {/* 동의 체크박스 및 안내 문구 (Frame 14 vs 22) */}
            <div className="pt-2 border-t border-gray-100 space-y-2 text-center">
              <p className="text-[11px] text-gray-400 leading-tight">
                제출하면 내 조건이 약속 추천에 반영돼요.<br />
                제출 전에는 다시 수정할 수 있어요.
              </p>

              <button
                type="button"
                onClick={() => setIsConfirmed(!isConfirmed)}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-600 pt-1"
              >
                {isConfirmed ? (
                  <span className="w-4 h-4 rounded-full bg-[#6C5CE7] text-white text-[10px] font-bold flex items-center justify-center">
                    ✓
                  </span>
                ) : (
                  <span className="w-4 h-4 rounded-full border border-gray-300 inline-block" />
                )}
                <span>입력한 조건을 확인했어요.</span>
              </button>
            </div>

            {/* 제출 버튼 */}
            {errorMsg && <p className="text-xs text-red-500 text-center">{errorMsg}</p>}
            <button
              type="button"
              disabled={!isConfirmed || submitting}
              onClick={handleSubmit}
              className={`w-full py-3.5 font-bold rounded-2xl text-sm transition-all ${
                isConfirmed
                  ? 'bg-[#6C5CE7] hover:bg-[#5b4cdb] text-white shadow-sm'
                  : 'bg-[#F5F5F7] text-gray-300 cursor-not-allowed'
              }`}
            >
              개인 조건 최종 제출
            </button>
          </div>
        )}

      </div>
    </div>
  );
}