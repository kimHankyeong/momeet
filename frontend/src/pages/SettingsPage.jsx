import { useEffect, useState } from 'react';
import MeetingSidebar from '../components/MeetingSidebar/MeetingSidebar';
import MeetingSettingsModal from '../components/MeetingSettingsModal/MeetingSettingsModal';
import { deleteMeeting, getMeeting, leaveMeeting } from '../api/meetApi';

const DOW = ['일', '월', '화', '수', '목', '금', '토'];
const dateLabel = (s) => {
  const [y, m, d] = s.split('-').map(Number);
  return `${m}월 ${d}일 (${DOW[new Date(y, m - 1, d).getDay()]})`;
};

// 이 브라우저에 저장된 약속방 ID 목록 (방 만들기·참여할 때 momeet_token_방ID로 저장됨)
const savedMeetingIds = () => {
  const ids = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key.startsWith('momeet_token_')) ids.push(key.slice('momeet_token_'.length));
  }
  return ids;
};

// 개인 재접속 링크: 이 링크를 열면 다른 기기에서도 내 자리로 들어온다 (토큰이 들어 있으니 남에게 공유 금지)
const reconnectLinkOf = (id) =>
  `${window.location.origin}/meet/${id}/setup?token=${localStorage.getItem(`momeet_token_${id}`)}`;

export default function SettingsPage() {
  const [meetings, setMeetings] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    Promise.all(
      savedMeetingIds().map((id) =>
        getMeeting(id)
          .then((res) => {
            const c = res.proposal?.candidate;
            return {
              id,
              name: res.meeting.title,
              dateLabel: c
                ? `${dateLabel(c.date)} ${c.start}`
                : `${dateLabel(res.meeting.date_start)} - ${dateLabel(res.meeting.date_end)}`,
              participants: res.participants.length,
              maxParticipants: res.meeting.max_participants,
              isHost: res.me.is_host,
              reconnectLink: reconnectLinkOf(id),
            };
          })
          .catch(() => null),
      ),
    ).then((list) => setMeetings(list.filter(Boolean)));
  }, []);

    // 참여자: 나가기(F-011) / 방장: 약속방 삭제
  const handleLeave = async (id) => {
    const m = meetings.find((x) => x.id === id);
    try {
      if (m?.isHost) await deleteMeeting(id);
      else await leaveMeeting(id);
      setMeetings((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      alert(e.response?.data?.error?.message || '처리하지 못했어요.');
    }
  };

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