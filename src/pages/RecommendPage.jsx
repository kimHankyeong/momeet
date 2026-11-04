import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

// ✅ 테스트용: true면 방장 화면, false면 참여자 화면
const IS_HOST = true;

const STEPS = ['모집', '입력', '추천', '제안', '확정'];

function Stepper({ current }) {
  return (
    <div className="flex justify-between items-center text-xs font-semibold pt-4 border-t border-gray-100">
      {STEPS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <React.Fragment key={label}>
            <div className={`flex items-center gap-2 ${done || active ? 'text-[#6C5CE7]' : 'text-gray-300'}`}>
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center ${
                  done
                    ? 'bg-[#6C5CE7] text-white'
                    : active
                    ? 'border-2 border-[#6C5CE7] text-[#6C5CE7]'
                    : 'bg-gray-100'
                }`}
              >
                {i + 1}
              </span>
              <span>{label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-[2px] flex-1 mx-3 ${i < current ? 'bg-[#6C5CE7]' : 'bg-gray-200'}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// 임시 데이터 (TODO: 백엔드 추천 결과로 교체)
const CANDIDATES = [
  { id: 1, name: '종로3가역', lines: '1·3·5호선', when: '11월 7일 17:00', maxMin: 27, myMin: 21, transfers: 1 },
  { id: 2, name: '을지로3가역', lines: '2·3호선', when: '11월 3일 18:00', maxMin: 43, myMin: 18, transfers: 1 },
  { id: 3, name: '충무로역', lines: '3·4호선', when: '11월 7일 14:00', maxMin: 49, myMin: 28, transfers: 0 },
];

export default function RecommendPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const meetInfo = {
    title: '친구들과 저녁 약속',
    dateRange: '11월 1일 (일) - 11월 8일 (일)',
  };

  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(1);
  const [proposed, setProposed] = useState(false); // 방장이 제안했는지

  // 추천 계산 중인 척 (TODO: 실제 API 응답 대기로 교체)
  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 1500);
    return () => clearTimeout(t);
  }, []);

  const selected = CANDIDATES.find((c) => c.id === selectedId);

  const handlePropose = () => {
    setProposed(true);
    // TODO: 백엔드에 제안 저장 후 이동
    navigate(`/meet/${id}/proposal`);
  };

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <div className="flex-1 flex max-w-6xl w-full mx-auto px-6 py-8 gap-8">
        {/* 좌측 사이드바 */}
        <aside className="w-44 shrink-0 space-y-1.5 pt-2">
          <div className="px-4 py-2.5 bg-[#6C5CE7] text-white font-bold rounded-xl text-sm w-full">내 약속방</div>
          <div className="px-4 py-2.5 text-gray-400 font-medium rounded-xl text-sm cursor-pointer hover:bg-gray-100">
            참여한 약속
          </div>
          <div className="px-4 py-2.5 text-gray-400 font-medium rounded-xl text-sm cursor-pointer hover:bg-gray-100">
            설정
          </div>
        </aside>

        <main className="flex-1 space-y-6">
          {/* 약속 정보 + 진행 단계 */}
          <section className="bg-white p-6 rounded-3xl border-2 border-[#6C5CE7] space-y-6">
            <div>
              <h1 className="text-xl font-bold text-gray-900">{meetInfo.title}</h1>
              <p className="text-xs text-gray-500 mt-1">{meetInfo.dateRange}</p>
            </div>
            <Stepper current={2} />
          </section>

          {/* 상태 배너 */}
          <div className="bg-[#7B61FF] text-white text-xl font-bold text-center py-5 rounded-3xl">
            {loading ? '조건에 맞는 약속 시간과 장소를 찾고 있어요' : '조건에 맞는 약속 시간과 장소를 찾았어요'}
          </div>

          {!loading && (
            <div className="grid grid-cols-2 gap-6 items-stretch">
              {/* 좌측: 선택 후보 미리보기 */}
              <section className="bg-white p-6 rounded-3xl border border-gray-300 flex flex-col justify-between min-h-[380px]">
                {/* TODO: 피그마에서 노선 그림을 내보내 <img>로 교체 */}
                <div className="flex-1 bg-gray-100 rounded-2xl flex items-center justify-center text-sm text-gray-400">
                  노선 이미지 자리
                </div>
                <div className="mt-4 border border-gray-300 rounded-2xl px-4 py-3">
                  <p className="text-base font-medium text-gray-900">📍 {selected.name}</p>
                  <p className="text-xs text-gray-600 mt-1">
                    선택 후보 | 내 예상 이동 {selected.myMin}분
                  </p>
                </div>
              </section>

              {/* 우측: 추천 후보 목록 */}
              <section className="bg-white p-6 rounded-3xl border border-gray-300 space-y-3">
                <div className="flex justify-between items-center">
                  <h3 className="text-xl font-bold text-gray-900">추천 후보</h3>
                  <span className="text-xs text-gray-700">전체 최적 기준 정렬</span>
                </div>

                {CANDIDATES.map((c) => {
                  const isOn = c.id === selectedId;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setSelectedId(c.id)}
                      className={`w-full text-left rounded-2xl px-4 py-3 flex items-center justify-between border ${
                        isOn ? 'border-[#6C5CE7]' : 'border-gray-300'
                      }`}
                    >
                      <div>
                        <p className="text-base font-medium text-gray-900">
                          <span className={isOn ? 'text-[#6C5CE7]' : 'text-gray-400'}>📍</span> {c.name}
                        </p>
                        <p className="text-xs text-gray-700 mt-1">
                          {c.lines} | {c.when}
                        </p>
                      </div>
                      <div className="flex items-center gap-4 text-center">
                        <Stat label="최대 이동" value={`${c.maxMin}분`} />
                        <Stat label="내 이동" value={`${c.myMin}분`} />
                        <Stat label="내 환승" value={`${c.transfers}회`} />
                        <span
                          className={`w-4 h-4 rounded-full ${
                            isOn ? 'bg-[#6C5CE7]' : 'bg-gray-200 border border-gray-300'
                          }`}
                        />
                      </div>
                    </button>
                  );
                })}

                {IS_HOST ? (
                  <button
                    type="button"
                    onClick={handlePropose}
                    className="w-full py-2.5 rounded-full bg-[#6C5CE7] text-white text-sm font-semibold hover:opacity-90"
                  >
                    선택한 장소로 공식 제안하기
                  </button>
                ) : (
                  <div className="w-full py-2.5 rounded-full border border-[#6C5CE7] text-[#6C5CE7] text-sm text-center">
                    제안 대기 중
                  </div>
                )}
              </section>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-[10px] text-gray-600">{label}</p>
      <p className="text-xs text-gray-900 mt-0.5">{value}</p>
    </div>
  );
}