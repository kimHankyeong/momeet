import { useState } from 'react';
import MeetingSidebar from '../components/MeetingSidebar/MeetingSidebar';
import MeetingCard from '../components/MeetingCard/MeetingCard';

// TODO: 임시 데이터입니다. api/meetApi.js에 목록 조회 함수가 생기면 교체하세요.
const MOCK_MEETINGS = [
  { id: 'abc', name: '친구들과 저녁 약속', dateLabel: '11월 7일 (일) 17:00', place: '종로3가역',
    participants: 3, maxParticipants: 4, stage: '제안', ended: false },
  { id: 'def', name: '고등학교 동창 모임', dateLabel: '10월 16일 (금) 20:00', place: '삼각지역',
    participants: 8, ended: true, daysUntilDelete: 10 },
  { id: 'ghi', name: '맛집 탐방 약속', dateLabel: '10월 10일 (토) 13:00', place: '홍대입구역',
    participants: 3, ended: true, daysUntilDelete: 4 },
];

export default function JoinedMeetingsPage() {
  const [tab, setTab] = useState('ongoing'); // 'ongoing' | 'ended'
  const meetings = MOCK_MEETINGS; // TODO: API 데이터로 교체

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
