import { useState } from 'react';
import MeetingSidebar from '../components/MeetingSidebar/MeetingSidebar';
import MeetingSettingsModal from '../components/MeetingSettingsModal/MeetingSettingsModal';

// TODO: 임시 데이터입니다. 실제로는 내 약속방 목록 API + 개인 재접속 링크를 받아오세요.
const MOCK_MEETINGS = [
  { id: 'abc', name: '친구들과 저녁 약속', dateLabel: '11월 7일 (일) 17:00',
    participants: 3, maxParticipants: 4, reconnectLink: 'https://momeet.kr/invite/abc' },
];

export default function SettingsPage() {
  const [meetings, setMeetings] = useState(MOCK_MEETINGS);
  const [selected, setSelected] = useState(null);

  // TODO: 서버에 접근 권한 해제(F-011) 요청 후 목록에서 제거
  const handleLeave = (id) => setMeetings((prev) => prev.filter((m) => m.id !== id));

  return (
    <div className="max-w-[860px] mx-auto px-6 pt-12 flex gap-6">
      <MeetingSidebar />

      <main className="flex-1 min-w-0 space-y-12">
        <section className="space-y-3">
          <h2 className="text-sm font-bold text-gray-900">약속방 설정</h2>
          {meetings.length === 0 ? (
            <p className="text-xs text-gray-400 py-6">참여 중인 약속방이 없어요.</p>
          ) : (
            meetings.map((m) => (
              <div
                key={m.id}
                className="relative border-2 border-gray-300 rounded-[20px] px-6 py-4 bg-white"
              >
                <h4 className="text-sm font-bold text-gray-900">{m.name}</h4>
                <p className="text-[11px] text-gray-700 mt-1">{m.dateLabel}</p>
                <p className="text-[10px] text-[#6C5CE7] mt-1">
                  {m.participants}/{m.maxParticipants} 참여 중
                </p>
                <button
                  type="button"
                  onClick={() => setSelected(m)}
                  className="absolute right-5 top-1/2 -translate-y-1/2 text-[10px] text-gray-400 hover:text-gray-600 underline"
                >
                  선택
                </button>
              </div>
            ))
          )}
        </section>

        <section className="border-t border-gray-200 pt-4 space-y-3">
          <h2 className="text-sm font-bold text-gray-900">서비스 정보</h2>
          {/* TODO: 시안이 비어 있어요. 들어갈 내용(이용약관, 개인정보 처리방침 등)을 정해서 채우세요. */}
        </section>
      </main>

      <MeetingSettingsModal
        isOpen={!!selected}
        meeting={selected}
        onClose={() => setSelected(null)}
        onLeave={handleLeave}
      />
    </div>
  );
}