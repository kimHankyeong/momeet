import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { confirmProposal, getMeeting, respondProposal } from '../api/meetApi';
import { stationLabel } from '../utils/station';

const DOW = ['일', '월', '화', '수', '목', '금', '토'];
// "2026-11-10" → "11월 10일 (화)"
const dateLabel = (s) => {
  const [y, m, d] = s.split('-').map(Number);
  return `${m}월 ${d}일 (${DOW[new Date(y, m - 1, d).getDay()]})`;
};

// 서버 응답 값 ↔ 화면 값
const FROM_SERVER = { accept: 'AGREED', reject: 'REJECTED', pending: 'PENDING' };
const TO_SERVER = { AGREED: 'accept', REJECTED: 'reject' };

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
  const navigate = useNavigate();

  // 백엔드 대시보드(GET /meetings/{id})에서 받아오는 값들
  const [meetInfo, setMeetInfo] = useState({ title: '', dateRange: '' });
  const [proposal, setProposal] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [serverStage, setServerStage] = useState('');
  const [needsReplan, setNeedsReplan] = useState(false);
  const [editing, setEditing] = useState(false); // "수정하기"를 눌러 응답을 다시 고르는 중
  const [showRoute, setShowRoute] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [nextAction, setNextAction] = useState(''); // 서버가 알려 주는 내 다음 할 일 (wait_confirm 등)
  const [confirming, setConfirming] = useState(false);

  const fetchData = async () => {
    try {
      const res = await getMeeting(id);
      setMeetInfo({
        title: res.meeting.title,
        dateRange: `${dateLabel(res.meeting.date_start)} - ${dateLabel(res.meeting.date_end)}`,
      });
      setServerStage(res.meeting.stage);
      setNextAction(res.next_action?.code || '');
      setParticipants(
        res.participants.map((p) => ({
          id: p.id,
          name: p.nickname,
          isHost: p.is_host,
          isMe: p.is_me,
          response: FROM_SERVER[p.response] || 'PENDING',
        })),
      );
      const pr = res.proposal;
      if (pr) {
        const c = pr.candidate;
        const r = pr.my_route;
        const [, m, d] = c.date.split('-').map(Number);
        const station = stationLabel(c.station.name);
        setNeedsReplan(pr.needs_replan);
        setProposal({
          dateText: `${dateLabel(c.date)} ${c.start}`,
          headline: `${m}월 ${d}일,`,
          placeName: station,
          myMinutes: r ? r.minutes : '-',
          transfers: r ? r.transfers : '-',
          walkMeters: r ? r.walk_m : '-',
          departAt: r ? r.depart_at : '-',
          // 경로: 출발역 → (환승역) → 도착역
          route: r && r.segments.length ? [r.segments[0].board, ...r.segments.map((s) => s.alight)] : [station],
        });
      }
      setErrorMsg('');
    } catch (e) {
      setErrorMsg(e.response?.data?.error?.message || '약속 정보를 불러오지 못했어요.');
    }
  };

  // 처음 열 때 + 5초마다 다시 불러오기 (다른 참여자의 응답 반영)
  useEffect(() => {
    const first = setTimeout(fetchData, 0);
    const t = setInterval(fetchData, 5000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const me = participants.find((p) => p.isMe) || { response: 'PENDING', isHost: false };
  const myResponse = editing ? 'PENDING' : me.response;
  const agreedCount = participants.filter((p) => p.response === 'AGREED').length;

  // 화면 단계: 서버 기준 (확정 / 전원 응답했는데 거절 있음 / 제안 중)
  const stage = serverStage === 'confirmed' ? 'CONFIRMED' : needsReplan ? 'FAILED' : 'PROPOSAL';
  const currentStep = stage === 'CONFIRMED' ? 5 : 3; // 확정이면 5단계 모두 완료로 표시

  // 내 응답: 동의/거절은 서버에 저장, "수정하기"(PENDING)는 버튼만 다시 보여 준다
  const respond = async (response) => {
    if (response === 'PENDING') {
      setEditing(true);
      return;
    }
    try {
      await respondProposal(id, TO_SERVER[response]);
      setEditing(false);
      await fetchData();
    } catch (e) {
      setErrorMsg(e.response?.data?.error?.message || '응답을 저장하지 못했어요.');
    }
  };

  // 방장: 약속 확정 (응답하지 않은 사람이 있으면 한 번 더 묻는다)
  const pendingCount = participants.filter((p) => p.response === 'PENDING' && !p.isMe).length;
  const rejectedCount = participants.filter((p) => p.response === 'REJECTED').length;
  const handleConfirm = async () => {
    if (pendingCount > 0 && !window.confirm(`아직 응답하지 않은 참여자가 ${pendingCount}명 있어요. 그래도 확정할까요?`)) return;
    setConfirming(true);
    try {
      await confirmProposal(id);
      await fetchData();
    } catch (e) {
      setErrorMsg(e.response?.data?.error?.message || '확정하지 못했어요.');
    } finally {
      setConfirming(false);
    }
  };

  if (!proposal) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-sm text-gray-500">
        <p>{errorMsg || (serverStage ? '아직 방장이 제안하지 않았어요.' : '제안 정보를 불러오고 있어요…')}</p>
        {serverStage && (
          <button type="button" onClick={() => navigate(`/meet/${id}/setup`)} className="text-xs underline">
            약속방으로 돌아가기
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <div className="flex-1 flex max-w-6xl w-full mx-auto px-6 py-8 gap-8">
        {/* 좌측 사이드바 */}
        <aside className="w-44 shrink-0 space-y-1.5 pt-2">
          <div className="px-4 py-2.5 bg-[#6C5CE7] text-white font-bold rounded-xl text-sm w-full">
            내 약속방
          </div>
          <div
            onClick={() => navigate('/meetings/joined')}
            className="px-4 py-2.5 text-gray-400 font-medium rounded-xl text-sm cursor-pointer hover:bg-gray-100"
          >
            참여한 약속
          </div>
          <div
            onClick={() => navigate('/meetings/settings')}
            className="px-4 py-2.5 text-gray-400 font-medium rounded-xl text-sm cursor-pointer hover:bg-gray-100"
          >
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
              {stage === 'PROPOSAL' && myResponse === 'PENDING' && (
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

              {stage === 'PROPOSAL' && myResponse !== 'PENDING' && (
                <div className="text-center space-y-3">
                  <p
                    className={`text-base ${
                      myResponse === 'AGREED' ? 'text-emerald-600' : 'text-red-500'
                    }`}
                  >
                    {myResponse === 'AGREED' ? '동의 완료' : '거절 완료'}
                  </p>
                  <p className="text-xs text-gray-300">
                    {nextAction === 'wait_confirm'
                      ? '모두 동의했어요. 주최자의 확정을 기다리고 있어요.'
                      : '다른 참여자의 응답을 기다리고 있어요.'}
                  </p>
                  <button
                    type="button"
                    onClick={() => respond('PENDING')}
                    className="px-8 py-2 rounded-full bg-[#6C5CE7] text-white text-sm font-semibold hover:opacity-90"
                  >
                    수정하기
                  </button>
                </div>
              )}

              {/* 방장: 확정 / 다른 후보로 다시 제안 */}
              {stage === 'PROPOSAL' && me.isHost && (
                <div className="space-y-2 border-t border-gray-100 pt-5">
                  <button
                    type="button"
                    disabled={confirming || rejectedCount > 0}
                    onClick={handleConfirm}
                    className="w-full py-2.5 rounded-full bg-[#6C5CE7] text-white text-sm font-semibold hover:opacity-90 disabled:opacity-40"
                  >
                    {confirming ? '확정하는 중…' : '약속 확정하기'}
                  </button>
                  <p className="text-[11px] text-gray-400 text-center">
                    {rejectedCount > 0
                      ? '거절한 참여자가 있어 확정할 수 없어요. 다른 후보를 제안해 보세요.'
                      : pendingCount > 0
                      ? `동의 ${agreedCount}/${participants.length} · 응답을 기다리지 않고 확정할 수도 있어요.`
                      : '모두 동의했어요. 확정하면 모두에게 확정 화면이 보여요.'}
                  </p>
                  <button
                    type="button"
                    onClick={() => navigate(`/meet/${id}/recommend`)}
                    className="w-full text-xs text-gray-400 underline hover:text-gray-600"
                  >
                    다른 후보로 다시 제안하기
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
                      onClick={() => navigate(`/meet/${id}/recommend`)}
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
                  약속이 확정됐어요.
                  <br />
                  각자의 이동 경로를 확인해 주세요.
                </p>
              )}

              {errorMsg && <p className="text-xs text-red-500 text-center">{errorMsg}</p>}

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
                        onClick={() => setShowRoute((v) => !v)}
                        className="text-[11px] font-bold text-[#6C5CE7] underline mt-1"
                      >
                        {showRoute ? '경로 접기' : '내 경로 보기'}
                      </button>
                    </div>
                  </div>
                )}
                {stage !== 'CONFIRMED' && showRoute && <RouteSummary proposal={proposal} />}
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
                        {p.isMe && ' (나)'}
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
          <React.Fragment key={`${name}-${i}`}>
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