import React, { useState } from 'react';
import { useParams } from 'react-router-dom';

// ✅ 테스트용: 1이면 방장(디소공), 4면 참여자(두루미) 화면으로 확인 가능
const ME_ID = 1;

const STEPS = ['모집', '입력', '추천', '제안', '확정'];

// 진행 단계 표시 (SetupPage의 Stepper와 같은 모양, current는 0~4)
function Stepper({ current }) {
  return (
    <div className="flex justify-between items-center text-xs font-semibold pt-4 border-t border-gray-100">
      {STEPS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <React.Fragment key={label}>
            <div
              className={`flex items-center gap-2 ${
                done || active ? 'text-[#6C5CE7]' : 'text-gray-300'
              }`}
            >
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
              <div
                className={`h-[2px] flex-1 mx-3 ${
                  i < current ? 'bg-[#6C5CE7]' : 'bg-gray-200'
                }`}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// 참여자 상태 표시 (동의 / 거절 / 대기)
function StatusBadge({ response }) {
  if (response === 'AGREED')
    return <span className="text-xs font-semibold text-emerald-600">동의 ✓</span>;
  if (response === 'REJECTED')
    return <span className="text-xs font-semibold text-red-500">거절 ✕</span>;
  return <span className="text-xs font-semibold text-gray-400">대기</span>;
}

export default function ProposalPage() {
  const { id } = useParams();

  // 백엔드에서 받아올 값들 (지금은 임시 데이터)
  const meetInfo = {
    title: '친구들과 저녁 약속',
    dateRange: '11월 1일 (일) - 11월 8일 (일)',
  };

  const proposal = {
    dateText: '11월 7일 (토) 17:00',
    headline: '11월 7일,',
    placeName: '종로3가역',
    myMinutes: 21,
    transfers: 1,
    walkMeters: 320,
    departAt: '14:35',
    route: ['정릉', '환승', '종로3가'],
  };

  const [participants, setParticipants] = useState([
    { id: 1, name: '디소공', isHost: true, response: 'PENDING' },
    { id: 2, name: '홍길동', isHost: false, response: 'AGREED' },
    { id: 3, name: '아무개', isHost: false, response: 'AGREED' },
    { id: 4, name: '두루미', isHost: false, response: 'REJECTED' },
  ]);

  const me = participants.find((p) => p.id === ME_ID);
  const agreedCount = participants.filter((p) => p.response === 'AGREED').length;
  const allResponded = participants.every((p) => p.response !== 'PENDING');
  const anyRejected = participants.some((p) => p.response === 'REJECTED');

  // 화면 단계: 제안 중 / 확정 안 됨 / 확정
  const stage = !allResponded ? 'PROPOSAL' : anyRejected ? 'FAILED' : 'CONFIRMED';
  const currentStep = stage === 'CONFIRMED' ? 4 : 3;

  // 내 응답 변경 (TODO: 백엔드 API 연결)
  const respond = (response) => {
    setParticipants((prev) =>
      prev.map((p) => (p.id === ME_ID ? { ...p, response } : p))
    );
  };

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <div className="flex-1 flex max-w-6xl w-full mx-auto px-6 py-8 gap-8">
        {/* 좌측 사이드바 */}
        <aside className="w-44 shrink-0 space-y-1.5 pt-2">
          <div className="px-4 py-2.5 bg-[#6C5CE7] text-white font-bold rounded-xl text-sm w-full">
            내 약속방
          </div>
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
            <Stepper current={currentStep} />
          </section>

          <div className="grid grid-cols-2 gap-6 items-start">
            {/* 좌측: 제안 내용 + 응답 영역 */}
            <section className="px-4 py-2 space-y-8">
              {/* 큰 제목 */}
              {stage === 'FAILED' ? (
                <h2 className="text-3xl font-extrabold leading-snug text-[#6C5CE7]">
                  이번 제안은
                  <br />
                  확정되지 않았어요.
                </h2>
              ) : (
                <h2 className="text-3xl font-extrabold leading-snug text-[#6C5CE7]">
                  {proposal.headline}
                  <br />
                  {proposal.placeName}에서 만나요.
                </h2>
              )}

              {/* 단계별 응답 영역 */}
              {stage === 'PROPOSAL' && me.response === 'PENDING' && (
                <div className="text-center space-y-3">
                  <p className="text-base text-gray-900">약속에 참여할까요?</p>
                  <p className="text-xs text-gray-300">약속 시간 전까지 수정할 수 있어요.</p>
                  <div className="flex gap-3 justify-center">
                    <button
                      type="button"
                      onClick={() => respond('AGREED')}
                      className="px-8 py-2 rounded-full bg-[#6C5CE7] text-white text-sm font-semibold hover:opacity-90"
                    >
                      동의하기
                    </button>
                    <button
                      type="button"
                      onClick={() => respond('REJECTED')}
                      className="px-8 py-2 rounded-full bg-gray-300 text-white text-sm font-semibold hover:opacity-90"
                    >
                      거절하기
                    </button>
                  </div>
                </div>
              )}

              {stage === 'PROPOSAL' && me.response !== 'PENDING' && (
                <div className="text-center space-y-3">
                  <p
                    className={`text-base ${
                      me.response === 'AGREED' ? 'text-emerald-600' : 'text-red-500'
                    }`}
                  >
                    {me.response === 'AGREED' ? '동의 완료' : '거절 완료'}
                  </p>
                  <p className="text-xs text-gray-300">다른 참여자의 응답을 기다리고 있어요.</p>
                  <button
                    type="button"
                    onClick={() => respond('PENDING')}
                    className="px-8 py-2 rounded-full bg-[#6C5CE7] text-white text-sm font-semibold hover:opacity-90"
                  >
                    수정하기
                  </button>
                </div>
              )}

              {stage === 'FAILED' && (
                <div className="space-y-4">
                  <p className="text-xs text-gray-400 leading-relaxed">
                    참여자 중 동의 하지 않은 사람이 있어요.
                    <br />
                    재조율이 필요합니다.
                  </p>
                  {me.isHost ? (
                    <button
                      type="button"
                      onClick={() => alert('추천 단계로 돌아갑니다 (TODO)')}
                      className="w-full py-2.5 rounded-full bg-[#6C5CE7] text-white text-sm font-semibold hover:opacity-90"
                    >
                      기존 추천 후보 다시 보기
                    </button>
                  ) : (
                    <div className="w-full py-2.5 rounded-full border border-[#6C5CE7] text-[#6C5CE7] text-sm text-center">
                      주최자의 새 제안을 기다리고 있어요.
                    </div>
                  )}
                </div>
              )}

              {stage === 'CONFIRMED' && (
                <p className="text-xs text-gray-700 leading-relaxed">
                  모든 참여자가 동의했어요.
                  <br />
                  각자의 이동 경로를 확인해 주세요.
                </p>
              )}

              {/* 날짜/장소/내 이동 정보 */}
              <div className="space-y-3 text-base">
                <div className="flex justify-between">
                  <span>날짜 및 시각</span>
                  <span>{proposal.dateText}</span>
                </div>
                <div className="flex justify-between">
                  <span>장소</span>
                  <span>{proposal.placeName}</span>
                </div>

                {stage === 'CONFIRMED' ? (
                  <RouteSummary proposal={proposal} />
                ) : (
                  <div className="flex justify-between items-start">
                    <div>
                      <p>내 예상 이동</p>
                      <p className="text-[11px] text-gray-500 mt-1">
                        환승 {proposal.transfers}회 · 도보 {proposal.walkMeters}m
                      </p>
                    </div>
                    <div className="text-right">
                      <p>{proposal.myMinutes}분</p>
                      <button
                        type="button"
                        onClick={() => alert('경로 보기 (TODO)')}
                        className="text-[11px] font-bold text-[#6C5CE7] underline mt-1"
                      >
                        내 경로 보기
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* 우측: 참여자 동의 현황 */}
            <section className="bg-white p-6 rounded-3xl border border-gray-300 space-y-4 min-h-[380px]">
              <div className="flex items-center gap-2">
                <h3 className="text-xl font-bold text-gray-900">참여자</h3>
                <span className="text-xs text-gray-500">
                  {agreedCount}/{participants.length} 동의
                </span>
              </div>

              <div className="space-y-3 pt-2">
                {participants.map((p) => (
                  <div key={p.id} className="flex justify-between items-center text-sm">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-[#6C5CE7] text-white flex items-center justify-center">
                        👤
                      </div>
                      <span className="font-medium text-gray-900">
                        {p.name}
                        {p.id === ME_ID && ' (나)'}
                      </span>
                      {p.isHost && (
                        <span className="bg-[#6C5CE7] text-white text-[10px] px-2 py-0.5 rounded-full font-bold">
                          방장
                        </span>
                      )}
                    </div>
                    <StatusBadge response={p.response} />
                  </div>
                ))}
              </div>

              {stage !== 'CONFIRMED' && (
                <p className="text-[11px] text-gray-300 text-center pt-6">
                  동의 여부만 공유돼요. 개인 이동 조건과 거절 이유는 공개되지 않아요.
                </p>
              )}
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}

// 확정 화면의 내 이동 경로 요약
function RouteSummary({ proposal }) {
  return (
    <div className="space-y-4">
      <p className="font-bold">내 예상 이동</p>

      <div className="flex items-center">
        {proposal.route.map((name, i) => (
          <React.Fragment key={name}>
            <div className="flex flex-col items-center w-12">
              <span
                className={`w-9 h-9 rounded-full ${
                  i === 1 ? 'bg-white border-4 border-blue-800' : 'bg-lime-600'
                } ${i === 2 ? '!bg-blue-800' : ''}`}
              />
              <span className="text-[11px] mt-1">{name}</span>
            </div>
            {i < proposal.route.length - 1 && (
              <div className={`h-1.5 flex-1 rounded ${i === 0 ? 'bg-lime-600' : 'bg-blue-800'}`} />
            )}
          </React.Fragment>
        ))}
      </div>

      <div className="flex justify-between border border-gray-300 rounded-full px-5 py-1.5 text-[11px]">
        <span>환승 {proposal.transfers}회</span>
        <span>도보 약 {proposal.walkMeters}m</span>
        <span>출발 권장 {proposal.departAt}</span>
      </div>
    </div>
  );
}