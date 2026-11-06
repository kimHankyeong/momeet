import { useEffect, useState } from 'react';
import MeetingLayout from '../components/MeetingLayout/MeetingLayout';
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

// 이 브라우저에 저장된 약속방을 서버에서 불러와 목록으로 만든다
const loadMeetings = () =>
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
            ended: res.meeting.stage === 'confirmed',
            reconnectLink: reconnectLinkOf(id),
          };
        })
        .catch(() => null),
    ),
  ).then((list) => list.filter((m) => m && !m.ended)); // 종료(확정)된 약속방은 설정 대상에서 뺀다

export default function SettingsPage() {
  const [meetings, setMeetings] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    loadMeetings().then(setMeetings);
  }, []);

  // 방장 권한을 받으면 목록(방장 여부·개인 링크)을 새로 불러오고, 열려 있는 팝업도 새 정보로 바꾼다
  const handleClaimed = (id) =>
    loadMeetings().then((list) => {
      setMeetings(list);
      setSelected(list.find((x) => x.id === id) || null);
    });

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
    <MeetingLayout active="settings">
      <section className="space-y-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">약속방 설정</h2>
          <p className="text-sm text-gray-700 mt-1">종료되지 않은 약속방만 설정할 수 있어요</p>
        </div>
        {meetings.length === 0 ? (
          <p className="text-sm text-gray-400 py-6">참여 중인 약속방이 없어요.</p>
        ) : (
          meetings.map((m) => (
            <div
              key={m.id}
              className="relative bg-white p-6 rounded-3xl border border-gray-100 shadow-sm"
            >
              <h4 className="text-base font-bold text-gray-900">{m.name}</h4>
              <p className="text-sm text-gray-600 mt-1">{m.dateLabel}</p>
              <p className="text-xs text-[#6C5CE7] mt-1">
                {m.participants}/{m.maxParticipants} 참여 중
              </p>
              <button
                type="button"
                onClick={() => setSelected(m)}
                className="absolute right-6 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600 underline"
              >
                선택
              </button>
            </div>
          ))
        )}
      </section>

      <section className="border-t border-gray-200 pt-6 space-y-3">
        <h2 className="text-2xl font-bold text-gray-900">서비스 정보</h2>
      </section>

      <MeetingSettingsModal
        isOpen={!!selected}
        meeting={selected}
        onClose={() => setSelected(null)}
        onLeave={handleLeave}
        onClaimed={handleClaimed}
      />
    </MeetingLayout>
  );
}