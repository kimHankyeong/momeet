import { useEffect, useState } from 'react';
import MeetingSidebar from '../components/MeetingSidebar/MeetingSidebar';
import MeetingCard from '../components/MeetingCard/MeetingCard';
import { getMeeting } from '../api/meetApi';

const DOW = ['일', '월', '화', '수', '목', '금', '토'];
const dateLabel = (s) => {
  const [y, m, d] = s.split('-').map(Number);
  return `${m}월 ${d}일 (${DOW[new Date(y, m - 1, d).getDay()]})`;
};

// 서버 단계 → 카드에 표시할 단계 (모집 중과 마감 후 입력은 화면에서 "입력"으로 묶음)
const STAGE_LABEL = { recruiting: '입력', input: '입력', recommended: '추천', proposed: '제안', confirmed: '확정' };

// 이 브라우저에 저장된 약속방 ID 목록 (방 만들기·참여할 때 momeet_token_방ID로 저장됨)
const savedMeetingIds = () => {
  const ids = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key.startsWith('momeet_token_')) ids.push(key.slice('momeet_token_'.length));
  }
  return ids;
};

// 대시보드 응답 → MeetingCard 형식
const toCard = (id, res) => {
  const c = res.proposal?.candidate;
  return {
    id,
    name: res.meeting.title,
    dateLabel: c
      ? `${dateLabel(c.date)} ${c.start}`
      : `${dateLabel(res.meeting.date_start)} - ${dateLabel(res.meeting.date_end)}`,
    place: c ? `${c.station.name}역` : '장소 미정',
    participants: res.participants.length,
    maxParticipants: res.meeting.max_participants,
    stage: STAGE_LABEL[res.meeting.stage],
    ended: false,
  };
};

export default function JoinedMeetingsPage() {
  const [tab, setTab] = useState('ongoing'); // 'ongoing' | 'ended'
  const [meetings, setMeetings] = useState([]);

  useEffect(() => {
    // 방마다 대시보드를 불러온다. 만료·삭제된 방이나 토큰이 무효인 방은 목록에서 뺀다
    Promise.all(
      savedMeetingIds().map((id) =>
        getMeeting(id)
          .then((res) => toCard(id, res))
          .catch(() => null),
      ),
    ).then((list) => setMeetings(list.filter(Boolean)));
  }, []);

  const ongoing = meetings.filter((m) => !m.ended);
  const ended = meetings.filter((m) => m.ended);
  const list = tab === 'ongoing' ? ongoing : ended;

  return (
    <div className="max-w-[860px] mx-auto px-6 pt-12 flex gap-6">
      <MeetingSidebar />

      <main className="flex-1 min-w-0 space-y-4">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setTab('ongoing')}
            className={`px-4 py-1 rounded-full text-[11px] font-bold border border-[#6C5CE7] ${
              tab === 'ongoing' ? 'bg-[#6C5CE7] text-white' : 'bg-white text-[#6C5CE7]'
            }`}
          >
            진행 중 {ongoing.length}
          </button>
          <button
            type="button"
            onClick={() => setTab('ended')}
            className={`px-4 py-1 rounded-full text-[11px] font-bold border border-[#6C5CE7] ${
              tab === 'ended' ? 'bg-[#6C5CE7] text-white' : 'bg-white text-[#6C5CE7]'
            }`}
          >
            종료된 약속 {ended.length}
          </button>
        </div>

        <div className="space-y-6">
          {list.length === 0 ? (
            <p className="text-xs text-gray-400 py-10 text-center">약속이 없어요.</p>
          ) : (
            list.map((m) => <MeetingCard key={m.id} meeting={m} />)
          )}
        </div>
      </main>
    </div>
  );
}