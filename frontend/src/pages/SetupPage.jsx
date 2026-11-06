import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ConditionSetupModal from '../components/ConditionSetupModal';
import { getMeeting } from '../api/meetApi';

const DOW = ['일', '월', '화', '수', '목', '금', '토'];
// "2026-11-10" → "11월 10일 (화)"
const dateLabel = (s) => {
  const [y, m, d] = s.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  return `${m}월 ${d}일 (${DOW[dt.getDay()]})`;
};

export default function SetupPage() {
  const { id } = useParams();
  const savedMeeting = (() => {
  try { return JSON.parse(localStorage.getItem(`momeet_meeting_${id}`)) || {}; }
  catch { return {}; }
  })();
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);

  // 백엔드 대시보드(GET /meetings/{id})에서 받아오는 약속 및 참여자 상태
  const [meetInfo, setMeetInfo] = useState({ title: '', dateRange: '', joinCode: '', startDate: '', dateStart: '', dateEnd: '', totalDays: 7 });
  const [participants, setParticipants] = useState([]);
  const [loadError, setLoadError] = useState('');

  const fetchMeetData = async () => {
    try {
      const res = await getMeeting(id);
      setMeetInfo({
        title: res.meeting.title,
        dateRange: `${dateLabel(res.meeting.date_start)} - ${dateLabel(res.meeting.date_end)}`,
        joinCode: res.meeting.join_code,
        startDate: res.meeting.date_start, // 조건 입력 시간표의 첫날
        dateStart: res.meeting.date_start, 
        dateEnd: res.meeting.date_end,
        totalDays:
          Math.round((new Date(res.meeting.date_end) - new Date(res.meeting.date_start)) / 86400000) + 1,
      });
      setParticipants(
        res.participants.map((p) => ({
          id: p.id,
          name: p.is_me ? `${p.nickname} (나)` : p.nickname,
          isHost: p.is_host,
          isMe: p.is_me,
          status: p.input_status === 'submitted' ? 'COMPLETED' : 'IN_PROGRESS',
        })),
      );
      setLoadError('');
    } catch (err) {
      setLoadError(err.response?.data?.error?.message || '약속 정보를 불러오지 못했어요.');
    }
  };

  // 처음 열 때 + 5초마다 다시 불러오기 (다른 참여자의 입력 상태 반영)
  useEffect(() => {
    // 개인 재접속 링크(?token=...)로 들어오면 토큰을 저장하고 주소에서 지운다
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    if (urlToken) {
      localStorage.setItem(`momeet_token_${id}`, urlToken);
      window.history.replaceState(null, '', window.location.pathname);
    }
    const first = setTimeout(fetchMeetData, 0);
    const t = setInterval(fetchMeetData, 5000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // 현재 사용자('나')의 조건 입력 완료 여부
  const myData = participants.find((p) => p.isMe);
  const isMyConditionSubmitted = myData?.status === 'COMPLETED';

  // 완료한 참여자 수
  const completedCount = participants.filter((p) => p.status === 'COMPLETED').length;

  // 모달에서 '개인 조건 최종 제출' 클릭 시: 서버 상태를 다시 불러온다
  // TODO: 모든 참여자 입력 완료 + 방장 '모집 마감' 후 추천 화면으로 이동
  const handleModalSubmit = () => {
    fetchMeetData();
  };

  // 링크 복사: 서버가 발급한 입장 코드 복사 (참여자도 가능)
  const handleCopy = async () => {
    if (!meetInfo.joinCode) return;
    try {
      await navigator.clipboard.writeText(meetInfo.joinCode);
      alert(`입장 코드가 복사되었습니다: ${meetInfo.joinCode}`);
    } catch {
      window.prompt('아래 입장 코드를 복사해 주세요.', meetInfo.joinCode);
    }
  };

  if (loadError && !meetInfo.title) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
        {loadError}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* 대시보드 본문 */}
      <div className="flex-1 flex max-w-6xl w-full mx-auto px-6 py-8 gap-8">
        {/* 좌측 사이드바 */}
        <aside className="w-44 shrink-0 space-y-1.5 pt-2">
          <div className="px-4 py-2.5 bg-[#6C5CE7] text-white font-bold rounded-xl text-sm inline-block w-full">
            내 약속방
          </div>
          {/* [변경] 클릭 시 해당 화면으로 이동 */}
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

        {/* 메인 영역 */}
        <main className="flex-1 space-y-6">
          {/* 상단 약속 정보 카드 */}
          <section className="bg-white p-6 rounded-3xl border border-gray-100 shadow-sm space-y-6">
            <div>
              <h1 className="text-xl font-bold text-gray-900">{meetInfo.title}</h1>
              <p className="text-xs text-gray-400 mt-1">{meetInfo.dateRange}</p>
            </div>

            {/* Stepper */}
            <div className="flex justify-between items-center text-xs font-semibold pt-4 border-t border-gray-100">
              <div className="flex items-center gap-2 text-[#6C5CE7]">
                <span className="w-6 h-6 rounded-full bg-[#6C5CE7] text-white flex items-center justify-center">1</span>
                <span>모집</span>
              </div>
              <div className="h-[2px] flex-1 bg-[#6C5CE7] mx-3" />
              <div className="flex items-center gap-2 text-[#6C5CE7]">
                <span className="w-6 h-6 rounded-full border-2 border-[#6C5CE7] text-[#6C5CE7] flex items-center justify-center">2</span>
                <span>입력</span>
              </div>
              <div className="h-[2px] flex-1 bg-gray-200 mx-3" />
              <div className="flex items-center gap-2 text-gray-300">
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center">3</span>
                <span>추천</span>
              </div>
              <div className="h-[2px] flex-1 bg-gray-200 mx-3" />
              <div className="flex items-center gap-2 text-gray-300">
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center">4</span>
                <span>제안</span>
              </div>
              <div className="h-[2px] flex-1 bg-gray-200 mx-3" />
              <div className="flex items-center gap-2 text-gray-300">
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center">5</span>
                <span>확정</span>
              </div>
            </div>
          </section>

          {/* 2열 하단 카드 */}
          <div className="grid grid-cols-2 gap-6">
            {/* 좌측: 내 조건 입력 카드 */}
            <section className="bg-white p-8 rounded-3xl border border-gray-100 shadow-sm flex flex-col items-center justify-center text-center min-h-[320px]">
              {!isMyConditionSubmitted ? (
                <div className="space-y-4">
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(true)}
                    className="w-12 h-12 rounded-full border-2 border-dashed border-gray-300 text-gray-400 flex items-center justify-center text-2xl mx-auto hover:border-[#6C5CE7] hover:text-[#6C5CE7] transition-colors"
                  >
                    +
                  </button>
                  <div>
                    <h3 className="text-base font-bold text-gray-900">내 조건을 입력해 주세요</h3>
                    <p className="text-xs text-gray-400 mt-1 max-w-[200px] mx-auto">
                      가능한 시간, 출발역, 이동 조건을 입력해야 추천 장소를 확인할 수 있어요.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center text-xl mx-auto font-bold">
                    ✓
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-gray-900">내 조건 입력 완료</h3>
                    <p className="text-xs text-gray-400 mt-1 max-w-[220px] mx-auto">
                      {participants.length}명 중 {completedCount}명이 입력을 완료했어요.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(true)}
                    className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-semibold rounded-xl transition-colors"
                  >
                    내 조건 확인
                  </button>
                </div>
              )}
            </section>

            {/* 우측: 참여자 목록 카드 */}
            <section className="bg-white p-6 rounded-3xl border border-gray-100 shadow-sm space-y-4">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-gray-900">참여자</h3>
                  <span className="text-xs text-gray-400 font-medium">
                    {completedCount}/{participants.length} 완료
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="px-3 py-1.5 bg-[#6C5CE7] text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 transition-colors"
                >
                  🔗 링크 복사하기
                </button>
              </div>

              <div className="space-y-3 pt-2">
                {participants.map((person) => (
                  <div key={person.id} className="flex justify-between items-center text-sm">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full bg-indigo-50 text-[#6C5CE7] font-bold flex items-center justify-center text-xs">
                        👤
                      </div>
                      <span className="font-semibold text-gray-800">{person.name}</span>
                      {person.isHost && (
                        <span className="bg-indigo-50 text-[#6C5CE7] text-[10px] px-1.5 py-0.5 rounded font-bold">
                          방장
                        </span>
                      )}
                    </div>
                    <span
                      className={`text-xs font-semibold ${
                        person.status === 'COMPLETED' ? 'text-emerald-600' : 'text-gray-400'
                      }`}
                    >
                      {person.status === 'COMPLETED' ? '입력완료 ✓' : '입력 중'}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </main>
      </div>

      {/* 모달 */}
      <ConditionSetupModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmitSuccess={handleModalSubmit}
        meetingId={id}
        startDate={meetInfo.startDate}
        totalDays={meetInfo.totalDays}
      />
    </div>
  );
}