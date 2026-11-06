import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import JoinModal from '../components/JoinModal/JoinModal';
import { getMeeting, previewJoin, stagePath } from '../api/meetApi';

// 초대 링크(/join/:code)로 들어온 화면.
// 이 브라우저에 그 방의 토큰이 있으면(이미 참여한 사람) 지금 단계 화면으로 바로 보내고,
// 없으면 입장 코드가 채워진 참여 모달을 연다.
export default function InvitePage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [mode, setMode] = useState('loading'); // loading | join | error
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { meeting_id: id } = await previewJoin(code);
        if (localStorage.getItem(`momeet_token_${id}`)) {
          try {
            const res = await getMeeting(id);
            if (alive) navigate(stagePath(id, res.meeting.stage), { replace: true });
            return;
          } catch (e) {
            // 만료·제외된 토큰이면 지우고 새로 참여하게 한다
            if (e.response?.status !== 401) throw e;
            localStorage.removeItem(`momeet_token_${id}`);
          }
        }
        if (alive) setMode('join');
      } catch (e) {
        if (!alive) return;
        setError(e.response?.data?.error?.message || '초대 링크를 확인하지 못했어요.');
        setMode('error');
      }
    })();
    return () => {
      alive = false;
    };
  }, [code, navigate]);

  if (mode === 'join') {
    return <JoinModal isOpen initialCode={code} onClose={() => navigate('/')} />;
  }

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-base text-gray-700">
        {mode === 'error' ? error : '약속방으로 이동하고 있어요…'}
      </p>
      {mode === 'error' && (
        <button
          type="button"
          onClick={() => navigate('/')}
          className="px-5 py-2.5 bg-[#6C5CE7] text-white rounded-xl text-sm font-semibold hover:opacity-90"
        >
          홈으로
        </button>
      )}
    </div>
  );
}
