import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import StationMap from '../components/StationMap/StationMap';
import { createProposal, getMeeting, getRecommendations } from '../api/meetApi';

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

const DOW = ['일', '월', '화', '수', '목', '금', '토'];
const dateLabel = (s) => {
  const [y, m, d] = s.split('-').map(Number);
  return `${m}월 ${d}일 (${DOW[new Date(y, m - 1, d).getDay()]})`;
};
const linesLabel = (lines) => {
  const nums = lines.filter((l) => /^\d+$/.test(l));
  const others = lines.filter((l) => !/^\d+$/.test(l)).map((l) => `${l}선`);
  return [...(nums.length ? [`${nums.join('·')}호선`] : []), ...others].join('·');
};

const toCandidate = (c) => ({
  id: c.candidate_id,
  name: c.station.name.endsWith('역') ? c.station.name : `${c.station.name}역`,
  lines: linesLabel(c.station.lines),
  lat: c.station.lat,
  lng: c.station.lng,
  when: `${dateLabel(c.date)} ${c.start}`,
  maxMin: c.max_travel_min,
  myMin: c.my_route ? c.my_route.minutes : '-',
  transfers: c.my_route ? c.my_route.transfers : '-',
  stops: c.my_route?.stops || [],
});

export default function RecommendPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [meetInfo, setMeetInfo] = useState({ title: '', dateRange: '' });
  const [isHost, setIsHost] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [proposing, setProposing] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.all([getMeeting(id), getRecommendations(id)])
      .then(([dash, rec]) => {
        if (!alive) return;
        setMeetInfo({
          title: dash.meeting.title,
          dateRange: `${dateLabel(dash.meeting.date_start)} - ${dateLabel(dash.meeting.date_end)}`,
        });
        setIsHost(dash.me.is_host);
        if (!dash.me.is_host && ['proposed', 'confirmed'].includes(dash.meeting.stage)) {
          navigate(`/meet/${id}/proposal`, { replace: true });
          return;
        }
        const list = (rec.candidates || []).map(toCandidate);
        setCandidates(list);
        setSelectedId(rec.best || list[0]?.id || null);
        if (rec.status !== 'ok') setErrorMsg('아직 추천 결과가 없어요. 방장이 추천을 받으면 보여요.');
      })
      .catch((e) => alive && setErrorMsg(e.response?.data?.error?.message || '추천 결과를 불러오지 못했어요.'))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [id, navigate]);

  const selected = candidates.find((c) => c.id === selectedId);

  const handlePropose = async () => {
    setProposing(true);
    setErrorMsg('');
    try {
      await createProposal(id, selectedId);
      navigate(`/meet/${id}/proposal`);
    } catch (e) {
      setErrorMsg(e.response?.data?.error?.message || '제안하지 못했어요.');
    } finally {
      setProposing(false);
    }
  };

  return (
    <div className="h-[calc(100vh-64px)] overflow-hidden bg-white flex flex-col">
      <div className="flex-1 min-h-0 flex max-w-6xl w-full mx-auto px-6 py-6 gap-8">
        {/* 좌측 사이드바 */}
        <aside className="w-44 shrink-0 space-y-1.5 pt-2">
          <div className="px-4 py-2.5 bg-[#6C5CE7] text-white font-bold rounded-xl text-sm w-full">내 약속방</div>
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

        <main className="flex-1 min-w-0 min-h-0 flex flex-col gap-4">
          {/* 약속 정보 + 진행 단계 */}
          <section className="shrink-0 bg-white p-5 rounded-3xl border-2 border-[#6C5CE7] space-y-4">
            <div>
              <h1 className="text-xl font-bold text-gray-900">{meetInfo.title}</h1>
              <p className="text-xs text-gray-500 mt-1">{meetInfo.dateRange}</p>
            </div>
            <Stepper current={2} />
          </section>

          {/* 상태 배너 */}
          <div className="shrink-0 bg-[#7B61FF] text-white text-xl font-bold text-center py-4 rounded-3xl">
            {loading ? '조건에 맞는 약속 시간과 장소를 찾고 있어요' : '조건에 맞는 약속 시간과 장소를 찾았어요'}
          </div>

          {errorMsg && <p className="shrink-0 text-sm text-red-500 text-center">{errorMsg}</p>}

          {!loading && selected && (
            <div className="flex-1 min-h-[300px] max-h-[480px] grid grid-cols-2 gap-6">
              {/* 좌측: 지도 */}
              <section className="min-h-0 bg-white p-5 rounded-3xl border border-gray-300 flex flex-col gap-3">
                <div className="flex-1 min-h-0 rounded-2xl overflow-hidden [&>*]:!h-full [&>*]:!w-full">
                  <StationMap lat={selected.lat} lng={selected.lng} name={selected.name} />
                </div>
                <div className="shrink-0 border border-gray-300 rounded-2xl px-4 py-3">
                  <p className="text-base font-medium text-gray-900">📍 {selected.name}</p>
                  <p className="text-xs text-gray-600 mt-1">
                    선택 후보 | 내 예상 이동 {selected.myMin}분
                  </p>
                </div>
              </section>

              {/* 우측: 후보 목록 (목록만 스크롤) */}
              <section className="min-h-0 bg-white p-5 rounded-3xl border border-gray-300 flex flex-col gap-3">
                <div className="shrink-0 flex justify-between items-center">
                  <h3 className="text-xl font-bold text-gray-900">추천 후보</h3>
                  <span className="text-xs text-gray-700">전체 최적 기준 정렬</span>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
                  {candidates.map((c) => {
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
                </div>

                <div className="shrink-0">
                  {isHost ? (
                    <button
                      type="button"
                      disabled={proposing}
                      onClick={handlePropose}
                      className="w-full py-2.5 rounded-full bg-[#6C5CE7] text-white text-sm font-semibold hover:opacity-90 disabled:opacity-40"
                    >
                      선택한 장소로 공식 제안하기
                    </button>
                  ) : (
                    <div className="w-full py-2.5 rounded-full border border-[#6C5CE7] text-[#6C5CE7] text-sm text-center">
                      제안 대기 중
                    </div>
                  )}
                </div>
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