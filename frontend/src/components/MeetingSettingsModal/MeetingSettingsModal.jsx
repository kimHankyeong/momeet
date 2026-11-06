import { useState } from 'react';
import { hostLogin, leaveMeeting, saveToken } from '../../api/meetApi';
import './MeetingSettingsModal.css';

// meeting: { id, name, reconnectLink, isHost }
// onClaimed(id): 방장 권한을 받은 뒤 목록을 새로 불러오게 한다
export default function MeetingSettingsModal({ isOpen, meeting, onClose, onLeave, onClaimed }) {
  const [copied, setCopied] = useState(false);
  const [view, setView] = useState('main'); // main | claim | done
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen || !meeting) return null;

  const close = () => {
    setView('main');
    setPassword('');
    setError('');
    onClose();
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(meeting.reconnectLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 클립보드 접근이 막힌 환경에서는 입력창을 직접 선택해서 복사
    }
  };

  // 참여자: 약속방 나가기 / 방장: 약속방 삭제 (방장은 나갈 수 없어서 삭제만 가능)
  const handleLeave = () => {
    const msg = meeting.isHost
      ? '약속방을 삭제하시겠어요? 모든 참여자의 정보가 함께 삭제되고 되돌릴 수 없어요.'
      : '약속방을 나가시겠어요? 개인 링크로 다시 들어올 수 없어요.';
    if (window.confirm(msg)) {
      onLeave?.(meeting.id);
      close();
    }
  };

  // 방장 권한 요청: 방을 만들 때 정한 비밀번호가 맞으면 지금의 참여 기록을 지우고 방장으로 바꾼다
  const handleClaim = async () => {
    setBusy(true);
    setError('');
    try {
      // 비밀번호부터 확인한다. 틀리면 참여 기록은 그대로 남는다
      const res = await hostLogin(meeting.id, password);
      try {
        // 남겨 두면 조건을 내지 않은 참여자로 남아 추천이 막힌다. (아직 저장된 참여자 토큰으로 지운다)
        await leaveMeeting(meeting.id);
      } catch {
        // 이미 지워진 기록 등은 무시하고 방장으로 바꾼다
      }
      saveToken(meeting.id, res.access_token);
      setPassword('');
      setView('done');
      onClaimed?.(meeting.id);
    } catch (e) {
      const err = e.response?.data?.error;
      setError(err?.code === 'INVALID_CREDENTIALS' ? '비밀번호가 틀렸습니다' : err?.message || '권한을 받지 못했어요. 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  if (view === 'claim' || view === 'done') {
    const done = view === 'done';
    return (
      <div className="msm__overlay">
        <div className="msm">
          <div className="msm__body">
            <div className="msm__head">
              <div>
                <h3 className="msm__title">{done ? '방장 권한을 받았어요' : '방장이신가요?'}</h3>
                <p className="msm__sub">
                  {done ? '이제 방장으로 제안과 추천을 진행할 수 있어요' : '설정해두신 비밀번호로 권한을 받을 수 있어요'}
                </p>
              </div>
              <button type="button" className="msm__close" onClick={close}>
                나가기
              </button>
            </div>

            {done ? (
              <button type="button" className="msm__claim-btn" onClick={close}>
                확인
              </button>
            ) : (
              <>
                <p className="msm__note">방장으로 바꾸면 지금의 참여 기록(입력한 조건 포함)은 삭제돼요.</p>
                <input
                  type="password"
                  className="msm__claim-input"
                  placeholder="비밀번호 입력"
                  value={password}
                  maxLength={72}
                  autoFocus
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && password && !busy && handleClaim()}
                />
                {error && <p className="msm__error">{error}</p>}
                <button
                  type="button"
                  className="msm__claim-btn"
                  disabled={!password || busy}
                  onClick={handleClaim}
                >
                  요청
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="msm__overlay">
      <div className="msm">
        <div className="msm__body">
          <div className="msm__head">
            <div>
              <h3 className="msm__title">{meeting.name}</h3>
              {/* TODO: 디자인의 부제 문구는 이동 조건 단계 문구 같아요. 확인 후 수정하세요. */}
              <p className="msm__sub">아무 조건도 설정하지 않아도 괜찮아요</p>
            </div>
            <button type="button" className="msm__close" onClick={close}>
              나가기
            </button>
          </div>

          <p className="msm__label">🔗 개인 재접속 링크</p>
          <div className="msm__row">
            <input
              type="text"
              readOnly
              value={meeting.reconnectLink}
              onFocus={(e) => e.target.select()}
              className="msm__input"
            />
            <button type="button" className="msm__copy" onClick={handleCopy}>
              {copied ? '복사됨' : '링크 복사'}
            </button>
          </div>

          {!meeting.isHost && (
            <button type="button" className="msm__claim-link" onClick={() => setView('claim')}>
              방장이신가요?
            </button>
          )}
        </div>

        <div className="msm__foot">
          <button type="button" className="msm__leave" onClick={handleLeave}>
            {meeting.isHost ? '🗑 약속방 삭제' : '↪ 약속방 나가기'}
          </button>
        </div>
      </div>
    </div>
  );
}
