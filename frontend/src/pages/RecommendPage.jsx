import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import routeMap from '../assets/route-map.png';
import { createProposal, getMeeting, getRecommendations } from '../api/meetApi';

const STEPS = ['모집', '입력', '추천', '제안', '확정'];

// 서울 지하철 노선 색
const LINE_COLOR = {
  1: '#0052A4', 2: '#00A84D', 3: '#EF7C1C', 4: '#00A5DE', 5: '#996CAC',
  6: '#CD7C2F', 7: '#747F00', 8: '#E6186C', 9: '#BDB092', 우이신설: '#B0CE18',
};

// 내 경로를 티맵 지도에 노선 색 선으로 그린다.
// stops: [{name, line, lat, lng}] (지나가는 역 전체, 서버 my_route.stops)
// 지도를 못 불러오면(키 없음 등) 아래 깔린 기존 이미지가 그대로 보인다
function RouteMap({ stops, fallback }) {
  const boxRef = useRef(null);

  useEffect(() => {
    const T = window.Tmapv2;
    const box = boxRef.current;
    if (!T || !box || !stops?.length) return undefined;
    let map;
    try {
      box.innerHTML = '';
      box.id = 'route-map';
      const pts = stops.map((s) => new T.LatLng(s.lat, s.lng));
      map = new T.Map('route-map', { center: pts[pts.length - 1], width: '100%', height: '100%', zoom: 13 });

      // 노선이 바뀌는 곳(환승역)에서 선을 나눠 노선 색으로 그린다
      let start = 0;
      for (let i = 1; i <= stops.length; i++) {
        if (i === stops.length || stops[i].line !== stops[start].line) {
          if (i - start > 1) {
            new T.Polyline({
              path: pts.slice(start, i),
              strokeColor: LINE_COLOR[stops[start].line] || '#6C5CE7',
              strokeWeight: 6,
              map,
            });
          }
          start = i;
        }
      }
      new T.Marker({ position: pts[0], map, title: `출발 ${stops[0].name}` });
      new T.Marker({ position: pts[pts.length - 1], map, title: `만남 ${stops[stops.length - 1].name}` });

      if (pts.length > 1) {
        const bounds = new T.LatLngBounds();
        pts.forEach((p) => bounds.extend(p));
        map.fitBounds(bounds);
      }
    } catch (e) {
      console.error('지도를 그리지 못했어요', e);
    }
    return () => {
      try {
        map?.destroy();
      } catch {
        /* 이미 지워짐 */
      }
    };
  }, [stops]);

  return (
    <div className="relative w-full h-[260px] rounded-2xl overflow-hidden">
      <img src={fallback} alt="추천 장소 노선" className="absolute inset-0 w-full h-full object-contain" />
      <div ref={boxRef} className="absolute inset-0" />
    </div>
  );
}

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
// "2026-11-10" → "11월 10일 (화)"
const dateLabel = (s) => {
  const [y, m, d] = s.split('-').map(Number);
  return `${m}월 ${d}일 (${DOW[new Date(y, m - 1, d).getDay()]})`;
};
// ["2", "5"] → "2·5호선", ["1", "우이신설"] → "1호선·우이신설선"
const linesLabel = (lines) => {
  const nums = lines.filter((l) => /^\d+$/.test(l));
  const others = lines.filter((l) => !/^\d+$/.test(l)).map((l) => `${l}선`);
  return [...(nums.length ? [`${nums.join('·')}호선`] : []), ...others].join('·');
};

// 서버 추천 후보 → 화면 형식 (내 이동은 본인 경로만 내려옴. 추천 이후 참여자는 my_route가 없음)
const toCandidate = (c) => ({
  id: c.candidate_id,
  name: c.station.name.endsWith('역') ? c.station.name : `${c.station.name}역`,
  lines: linesLabel(c.station.lines),
  when: `${dateLabel(c.date)} ${c.start}`,
  maxMin: c.max_travel_min,
  myMin: c.my_route ? c.my_route.minutes : '-',
  transfers: c.my_route ? c.my_route.transfers : '-',
  stops: c.my_route?.stops || [], // 지도용 (지나가는 역 전체)
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

  // 약속 정보(제목·날짜·방장 여부) + 추천 결과 불러오기
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
        // 이미 제안이 나갔으면 참여자는 제안 화면으로 (방장은 다른 후보로 다시 제안할 수 있게 남김)
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

  // 방장: 선택한 후보로 공식 제안 → 제안 화면으로 이동
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
    <div className="min-h-screen bg-white flex flex-col">
      <div className="flex-1 flex max-w-6xl w-full mx-auto px-6 py-8 gap-8">
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

          {errorMsg && <p className="text-sm text-red-500 text-center">{errorMsg}</p>}

          {!loading && selected && (
            <div className="grid grid-cols-2 gap-6 items-stretch">
              {/* 좌측: 선택 후보 미리보기 */}
              <section className="bg-white p-6 rounded-3xl border border-gray-300 flex flex-col justify-between min-h-[380px]">
                <div className="flex-1 flex items-center justify-center">
                  <RouteMap stops={selected.stops} fallback={routeMap} />
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