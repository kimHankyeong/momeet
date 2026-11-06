import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ConditionSetupModal from '../components/ConditionSetupModal';
// import { getMeetDetail } from '../api/meetApi'; // 실제 API 연동 시 사용

export default function SetupPage() {
  const { id } = useParams();
  const savedMeeting = (() => {
  try { return JSON.parse(localStorage.getItem(`momeet_meeting_${id}`)) || {}; }
  catch { return {}; }
  })();
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);

  // 실제 백엔드 API에서 받아올 약속 및 참여자 상태
  const [meetInfo] = useState({
    title: '친구들과 저녁 약속',
    dateRange: '11월 1일 (일) - 11월 8일 (일)',
  });

  // 동적 참여자 목록 (실제로는 백엔드에서 받아옴)
  const [participants, setParticipants] = useState([
    { id: 1, name: '디소공 (나)', isHost: true, isMe: true, status: 'IN_PROGRESS' },
  ]);

  /* 백엔드 연동 예시 코드 (주석 해제 후 사용)
  useEffect(() => {
    async function fetchMeetData() {
      try {
        const res = await getMeetDetail(id);
        setParticipants(res.data.participants);
        setMeetInfo(res.data.meetInfo);
      } catch (err) {
        console.error('약속 정보 불러오기 실패:', err);
      }
    }
    fetchMeetData();
  }, [id]);
  */

  // 현재 사용자('나')의 조건 입력 완료 여부
  const myData = participants.find((p) => p.isMe);
  const isMyConditionSubmitted = myData?.status === 'COMPLETED';

  // 완료한 참여자 수
  const completedCount = participants.filter((p) => p.status === 'COMPLETED').length;

  // 모달에서 '개인 조건 최종 제출' 클릭 시
  const handleModalSubmit = (submittedData) => {
    setParticipants((prev) =>
      prev.map((p) => (p.isMe ? { ...p, status: 'COMPLETED' } : p))
    );
    // 임시: 시연용으로 바로 추천 화면으로 이동
    // TODO: 모든 참여자 입력 완료 + 방장 '모집 마감' 후 이동하도록 변경
    navigate(`/meet/${id}/recommend`);
  };

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
                  onClick={() => alert('초대 링크가 복사되었습니다!')}
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
        dateStart={savedMeeting.date_start}
        dateEnd={savedMeeting.date_end}
      />
    </div>
  );
}
