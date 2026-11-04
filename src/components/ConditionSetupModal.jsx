import React, { useState } from 'react';
import AvailabilityGrid from './conditions/AvailabilityGrid';

export default function ConditionSetupModal({ isOpen, onClose, onSubmitSuccess }) {
  const [step, setStep] = useState(1);

  // STEP 1: 시간 선택
const [selectedCells, setSelectedCells] = useState(new Set());

const START_DATE = new Date(2026, 10, 1); // 약속 시작일 (TODO: 약속 데이터에서 받기)
const DOW = ['일', '월', '화', '수', '목', '금', '토'];

const selectedTimes = (() => {
  const byDay = {};
  selectedCells.forEach((key) => {
    const [d, h] = key.split('-').map(Number);
    (byDay[d] ||= []).push(h);
  });
  const result = [];
  const pad = (n) => String(n).padStart(2, '0');
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
          result.push(`${label} ${pad(start)}:00-${pad(prev + 1)}:00`);
          start = hours[i];
        }
        prev = hours[i];
      }
    });
  return result;
})();

  // STEP 2: 출발역 (Frame 9, 16)
  const [location, setLocation] = useState('');
  const [tempInput, setTempInput] = useState('');
  const [isEditingLocation, setIsEditingLocation] = useState(false);

  // STEP 3: 이동 조건 상태 (Frame 11, 12, 13)
  const [isSelectingCondition, setIsSelectingCondition] = useState(false); // Frame 12(선택 리스트) 열림 여부
  const [addedConditions, setAddedConditions] = useState([]); // 선택된 조건 목록

  // STEP 4: 최종 동의 체크박스 (Frame 14, 22)
  const [isConfirmed, setIsConfirmed] = useState(false);

  if (!isOpen) return null;

  const handleNext = () => setStep((prev) => Math.min(prev + 1, 4));

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

  const handleSubmit = () => {
    onSubmitSuccess({ location, selectedTimes, addedConditions });
    onClose();
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
            <AvailabilityGrid selected={selectedCells} onChange={setSelectedCells} totalDays={8} />

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
        {/* STEP 2: 어디서 출발하나요? (Frame 9, 16) */}
        {step === 2 && (
          <div className="space-y-6 pt-1">
            <div className="min-h-[120px] flex flex-col justify-center">
              {(!location || isEditingLocation) ? (
                <div className="space-y-2 text-center">
                  <input
                    type="text"
                    placeholder="지하철 역 검색"
                    value={tempInput}
                    onChange={(e) => setTempInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && tempInput.trim()) {
                        setLocation(tempInput.trim());
                        setIsEditingLocation(false);
                      }
                    }}
                    className="w-full py-3.5 px-4 bg-[#F5F5F7] border-none rounded-2xl text-sm text-center placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#6C5CE7]"
                    autoFocus
                  />
                  <span className="text-xs text-gray-300 block pt-1">다른 출발 설정</span>
                </div>
              ) : (
                <div className="space-y-2 text-center">
                  <div className="w-full py-3.5 bg-[#6C5CE7] text-white font-bold rounded-2xl text-sm shadow-sm">
                    {location}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setTempInput(location);
                      setIsEditingLocation(true);
                    }}
                    className="text-xs text-gray-400 hover:text-gray-600 underline"
                  >
                    다른 출발 설정
                  </button>
                </div>
              )}
            </div>

            <button
              type="button"
              disabled={!location}
              onClick={handleNext}
              className={`w-full py-3.5 font-bold rounded-2xl text-sm transition-all ${
                location
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

            {/* 2) 출발역 */}
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
                  <span className="text-gray-400 text-[11px]">기본 출발역</span>
                  <span className="font-bold text-gray-800">{location || '신설동역'}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-400 text-[11px]">예외 출발역</span>
                  <span className="font-bold text-gray-800">1개</span>
                  <span className="bg-[#F5F5F7] text-gray-700 text-[10px] px-2 py-0.5 rounded">
                    11월 7일 (토) 11:00-23:00 정릉역
                  </span>
                </div>
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
            <button
              type="button"
              disabled={!isConfirmed}
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